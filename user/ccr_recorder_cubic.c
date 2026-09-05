/* CCReplay CUBIC recorder: userspace loader/consumer for bpf/cubic_wrapper.bpf.c.
 *
 * Same architecture as user/ccr_recorder.c (Reno, v0) -- loads and registers
 * the ccr_cubic struct_ops congestion controller, drains its ringbuf to a
 * versioned binary .ccr trace file (TraceHeader + raw ccr_event_v1 records,
 * exact on-disk layout shared with the BPF side via bpf/ccr_event_v1.h), and
 * at teardown reads the authoritative drop/invocation/clock counters and
 * per-program BPF runtime stats *before* unregistering (ADR-013), writing
 * them to a JSON sidecar (RecorderRunMetadata, docs/REPLAY_ABI.md v1
 * section). trace_version = 1 (ADR-021); v0's ccr_recorder.c is untouched.
 *
 * Usage: ccr_recorder_cubic <out.ccr> <out_meta.json> <duration_s>
 *
 * Runs until duration_s elapses or SIGINT/SIGTERM is received. The caller
 * is responsible for starting the actual TCP transfer with `-C ccr_cubic`
 * concurrently, after this process prints "ATTACHED" to stdout.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <signal.h>
#include <unistd.h>
#include <time.h>
#include <errno.h>
#include <sys/utsname.h>
#include <bpf/libbpf.h>
#include <bpf/bpf.h>

#include "../bpf/ccr_event_v1.h"
#include "cubic_wrapper.skel.h"

#define RECORDER_VERSION 1u

static volatile sig_atomic_t stop;
static FILE *trace_out;
static unsigned long long events_written;

static void on_signal(int sig)
{
	(void)sig;
	stop = 1;
}

static int libbpf_print_fn(enum libbpf_print_level level, const char *fmt, va_list args)
{
	if (level == LIBBPF_DEBUG)
		return 0;
	return vfprintf(stderr, fmt, args);
}

static int handle_event(void *ctx, void *data, size_t len)
{
	(void)ctx;
	if (len < sizeof(struct ccr_event_v1)) {
		fprintf(stderr, "WARN: short ringbuf record (%zu < %zu), skipping\n",
			len, sizeof(struct ccr_event_v1));
		return 0;
	}
	if (fwrite(data, sizeof(struct ccr_event_v1), 1, trace_out) != 1) {
		fprintf(stderr, "ERROR: fwrite failed: %s\n", strerror(errno));
		return -1;
	}
	events_written++;
	return 0;
}

static __u64 now_ns(void)
{
	struct timespec ts;
	clock_gettime(CLOCK_MONOTONIC, &ts);
	return (__u64)ts.tv_sec * 1000000000ull + (__u64)ts.tv_nsec;
}

static int get_prog_stats(struct bpf_program *prog, __u64 *run_time_ns, __u64 *run_cnt)
{
	int fd = bpf_program__fd(prog);
	struct bpf_prog_info info = {};
	__u32 info_len = sizeof(info);
	int err;

	if (fd < 0)
		return -1;
	err = bpf_obj_get_info_by_fd(fd, &info, &info_len);
	if (err)
		return err;
	*run_time_ns = info.run_time_ns;
	*run_cnt = info.run_cnt;
	return 0;
}

int main(int argc, char **argv)
{
	if (argc != 4) {
		fprintf(stderr, "usage: %s <out.ccr> <out_meta.json> <duration_s>\n", argv[0]);
		return 1;
	}
	const char *trace_path = argv[1];
	const char *meta_path = argv[2];
	int duration_s = atoi(argv[3]);

	libbpf_set_print(libbpf_print_fn);

	struct cubic_wrapper_bpf *skel = cubic_wrapper_bpf__open();
	if (!skel) {
		fprintf(stderr, "ERROR: failed to open skeleton\n");
		return 1;
	}

	if (cubic_wrapper_bpf__load(skel)) {
		fprintf(stderr, "ERROR: failed to load skeleton\n");
		cubic_wrapper_bpf__destroy(skel);
		return 1;
	}

	trace_out = fopen(trace_path, "wb");
	if (!trace_out) {
		fprintf(stderr, "ERROR: fopen(%s): %s\n", trace_path, strerror(errno));
		cubic_wrapper_bpf__destroy(skel);
		return 1;
	}

	struct ccr_trace_header hdr;
	memset(&hdr, 0, sizeof(hdr));
	memcpy(hdr.magic, CCR_TRACE_MAGIC, 8);
	hdr.trace_version = CCR_TRACE_VERSION_1;
	hdr.recorder_version = RECORDER_VERSION;
	struct utsname uts;
	uname(&uts);
	strncpy(hdr.kernel_release, uts.release, sizeof(hdr.kernel_release) - 1);
	strncpy(hdr.reference_impl_id, "linux_tcp_cubic_kfunc", sizeof(hdr.reference_impl_id) - 1);
	hdr.callback_manifest = CCR_CUBIC_MANIFEST;
	hdr.private_state_schema_id = CCR_PRIVATE_SCHEMA_CUBIC_V1;
	hdr.record_size = sizeof(struct ccr_event_v1);
	hdr.creation_ts_ns = now_ns();

	if (fwrite(&hdr, sizeof(hdr), 1, trace_out) != 1) {
		fprintf(stderr, "ERROR: failed to write trace header\n");
		fclose(trace_out);
		cubic_wrapper_bpf__destroy(skel);
		return 1;
	}
	fflush(trace_out);

	struct ring_buffer *rb = ring_buffer__new(
		bpf_map__fd(skel->maps.ccr_events), handle_event, NULL, NULL);
	if (!rb) {
		fprintf(stderr, "ERROR: ring_buffer__new failed\n");
		fclose(trace_out);
		cubic_wrapper_bpf__destroy(skel);
		return 1;
	}

	if (cubic_wrapper_bpf__attach(skel)) {
		fprintf(stderr, "ERROR: failed to attach (register struct_ops) -- errno=%d (%s)\n",
			errno, strerror(errno));
		ring_buffer__free(rb);
		fclose(trace_out);
		cubic_wrapper_bpf__destroy(skel);
		return 1;
	}

	signal(SIGINT, on_signal);
	signal(SIGTERM, on_signal);

	printf("ATTACHED\n");
	fflush(stdout);

	__u64 t_start = now_ns();
	__u64 t_deadline = t_start + (__u64)duration_s * 1000000000ull;

	while (!stop && now_ns() < t_deadline) {
		int err = ring_buffer__poll(rb, 200 /* ms */);
		if (err < 0 && err != -EINTR) {
			fprintf(stderr, "ERROR: ring_buffer__poll: %d\n", err);
			break;
		}
	}

	/* Drain trailing events (ADR-013), same discipline as v0. */
	for (int idle_polls = 0; idle_polls < 10; ) {
		int err = ring_buffer__poll(rb, 50);
		if (err > 0) {
			idle_polls = 0;
		} else {
			idle_polls++;
		}
		if (err < 0 && err != -EINTR)
			break;
	}

	fflush(trace_out);

	struct ccr_counters {
		__u64 invocations;
		__u64 emitted;
		__u64 drops;
		__u64 clock_stable;
		__u64 clock_ambiguous;
	} counters = {0};
	__u32 key = 0;
	int counters_err = bpf_map__lookup_elem(
		skel->maps.ccr_counters_map, &key, sizeof(key), &counters, sizeof(counters), 0);

	__u64 run_time_ns[7] = {0}, run_cnt[7] = {0};
	get_prog_stats(skel->progs.ccr_cubic_init, &run_time_ns[0], &run_cnt[0]);
	get_prog_stats(skel->progs.ccr_cubic_cong_avoid, &run_time_ns[1], &run_cnt[1]);
	get_prog_stats(skel->progs.ccr_cubic_ssthresh, &run_time_ns[2], &run_cnt[2]);
	get_prog_stats(skel->progs.ccr_cubic_set_state, &run_time_ns[3], &run_cnt[3]);
	get_prog_stats(skel->progs.ccr_cubic_cwnd_event, &run_time_ns[4], &run_cnt[4]);
	get_prog_stats(skel->progs.ccr_cubic_pkts_acked, &run_time_ns[5], &run_cnt[5]);
	get_prog_stats(skel->progs.ccr_cubic_undo_cwnd, &run_time_ns[6], &run_cnt[6]);

	long file_size = ftell(trace_out);

	fclose(trace_out);
	ring_buffer__free(rb);
	cubic_wrapper_bpf__destroy(skel); /* unregisters struct_ops */

	FILE *meta = fopen(meta_path, "w");
	if (!meta) {
		fprintf(stderr, "ERROR: fopen(%s): %s\n", meta_path, strerror(errno));
		return 1;
	}
	fprintf(meta,
		"{\n"
		"  \"trace_version\": %u,\n"
		"  \"recorder_version\": %u,\n"
		"  \"kernel_release\": \"%s\",\n"
		"  \"invocations\": %llu,\n"
		"  \"emitted\": %llu,\n"
		"  \"drops\": %llu,\n"
		"  \"clock_stable\": %llu,\n"
		"  \"clock_ambiguous\": %llu,\n"
		"  \"counters_read_ok\": %s,\n"
		"  \"events_written_userspace\": %llu,\n"
		"  \"trace_file_bytes\": %ld,\n"
		"  \"duration_s_requested\": %d,\n"
		"  \"bpf_stats\": {\n"
		"    \"init\": {\"run_time_ns\": %llu, \"run_cnt\": %llu},\n"
		"    \"cong_avoid\": {\"run_time_ns\": %llu, \"run_cnt\": %llu},\n"
		"    \"ssthresh\": {\"run_time_ns\": %llu, \"run_cnt\": %llu},\n"
		"    \"set_state\": {\"run_time_ns\": %llu, \"run_cnt\": %llu},\n"
		"    \"cwnd_event\": {\"run_time_ns\": %llu, \"run_cnt\": %llu},\n"
		"    \"pkts_acked\": {\"run_time_ns\": %llu, \"run_cnt\": %llu},\n"
		"    \"undo_cwnd\": {\"run_time_ns\": %llu, \"run_cnt\": %llu}\n"
		"  }\n"
		"}\n",
		hdr.trace_version, hdr.recorder_version, hdr.kernel_release,
		(unsigned long long)counters.invocations,
		(unsigned long long)counters.emitted,
		(unsigned long long)counters.drops,
		(unsigned long long)counters.clock_stable,
		(unsigned long long)counters.clock_ambiguous,
		counters_err == 0 ? "true" : "false",
		events_written, file_size, duration_s,
		(unsigned long long)run_time_ns[0], (unsigned long long)run_cnt[0],
		(unsigned long long)run_time_ns[1], (unsigned long long)run_cnt[1],
		(unsigned long long)run_time_ns[2], (unsigned long long)run_cnt[2],
		(unsigned long long)run_time_ns[3], (unsigned long long)run_cnt[3],
		(unsigned long long)run_time_ns[4], (unsigned long long)run_cnt[4],
		(unsigned long long)run_time_ns[5], (unsigned long long)run_cnt[5],
		(unsigned long long)run_time_ns[6], (unsigned long long)run_cnt[6]);
	fclose(meta);

	fprintf(stderr,
		"DONE invocations=%llu emitted=%llu drops=%llu clock_stable=%llu clock_ambiguous=%llu events_written=%llu\n",
		(unsigned long long)counters.invocations,
		(unsigned long long)counters.emitted,
		(unsigned long long)counters.drops,
		(unsigned long long)counters.clock_stable,
		(unsigned long long)counters.clock_ambiguous,
		events_written);

	return 0;
}
