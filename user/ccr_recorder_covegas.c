/* CCReplay CoVegas recorder: userspace loader/consumer for
 * bpf/covegas_wrapper.bpf.c. Same architecture as user/ccr_recorder_cubic.c
 * (v1), adapted for v2's two clock brackets and wider counters struct
 * (ADR-022..024). trace_version = 2.
 *
 * Usage: ccr_recorder_covegas <out.ccr> <out_meta.json> <duration_s>
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

#include "../bpf/ccr_event_v2.h"
#include "covegas_wrapper.skel.h"

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
	if (len < sizeof(struct ccr_event_v2)) {
		fprintf(stderr, "WARN: short ringbuf record (%zu < %zu), skipping\n",
			len, sizeof(struct ccr_event_v2));
		return 0;
	}
	if (fwrite(data, sizeof(struct ccr_event_v2), 1, trace_out) != 1) {
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

	struct covegas_wrapper_bpf *skel = covegas_wrapper_bpf__open();
	if (!skel) {
		fprintf(stderr, "ERROR: failed to open skeleton\n");
		return 1;
	}

	if (covegas_wrapper_bpf__load(skel)) {
		fprintf(stderr, "ERROR: failed to load skeleton\n");
		covegas_wrapper_bpf__destroy(skel);
		return 1;
	}

	trace_out = fopen(trace_path, "wb");
	if (!trace_out) {
		fprintf(stderr, "ERROR: fopen(%s): %s\n", trace_path, strerror(errno));
		covegas_wrapper_bpf__destroy(skel);
		return 1;
	}

	struct ccr_trace_header hdr;
	memset(&hdr, 0, sizeof(hdr));
	memcpy(hdr.magic, CCR_TRACE_MAGIC, 8);
	hdr.trace_version = CCR_TRACE_VERSION_2;
	hdr.recorder_version = RECORDER_VERSION;
	struct utsname uts;
	uname(&uts);
	strncpy(hdr.kernel_release, uts.release, sizeof(hdr.kernel_release) - 1);
	strncpy(hdr.reference_impl_id, "ccreplay_covegas_instrumented", sizeof(hdr.reference_impl_id) - 1);
	hdr.callback_manifest = CCR_COVEGAS_MANIFEST;
	hdr.private_state_schema_id = CCR_PRIVATE_SCHEMA_COVEGAS_V2;
	hdr.record_size = sizeof(struct ccr_event_v2);
	hdr.creation_ts_ns = now_ns();

	if (fwrite(&hdr, sizeof(hdr), 1, trace_out) != 1) {
		fprintf(stderr, "ERROR: failed to write trace header\n");
		fclose(trace_out);
		covegas_wrapper_bpf__destroy(skel);
		return 1;
	}
	fflush(trace_out);

	struct ring_buffer *rb = ring_buffer__new(
		bpf_map__fd(skel->maps.ccr_events), handle_event, NULL, NULL);
	if (!rb) {
		fprintf(stderr, "ERROR: ring_buffer__new failed\n");
		fclose(trace_out);
		covegas_wrapper_bpf__destroy(skel);
		return 1;
	}

	if (covegas_wrapper_bpf__attach(skel)) {
		fprintf(stderr, "ERROR: failed to attach (register struct_ops) -- errno=%d (%s)\n",
			errno, strerror(errno));
		ring_buffer__free(rb);
		fclose(trace_out);
		covegas_wrapper_bpf__destroy(skel);
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
		__u64 clock_jiffies_stable;
		__u64 clock_jiffies_ambiguous;
		__u64 clock_ktime_stable;
		__u64 clock_ktime_ambiguous;
	} counters = {0};
	__u32 key = 0;
	int counters_err = bpf_map__lookup_elem(
		skel->maps.ccr_counters_map, &key, sizeof(key), &counters, sizeof(counters), 0);

	__u64 run_time_ns[5] = {0}, run_cnt[5] = {0};
	get_prog_stats(skel->progs.ccr_covegas_init, &run_time_ns[0], &run_cnt[0]);
	get_prog_stats(skel->progs.ccr_covegas_cong_avoid, &run_time_ns[1], &run_cnt[1]);
	get_prog_stats(skel->progs.ccr_covegas_ssthresh, &run_time_ns[2], &run_cnt[2]);
	get_prog_stats(skel->progs.ccr_covegas_undo_cwnd, &run_time_ns[3], &run_cnt[3]);
	get_prog_stats(skel->progs.ccr_covegas_pkts_acked, &run_time_ns[4], &run_cnt[4]);

	long file_size = ftell(trace_out);

	fclose(trace_out);
	ring_buffer__free(rb);
	covegas_wrapper_bpf__destroy(skel);

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
		"  \"clock_jiffies_stable\": %llu,\n"
		"  \"clock_jiffies_ambiguous\": %llu,\n"
		"  \"clock_ktime_stable\": %llu,\n"
		"  \"clock_ktime_ambiguous\": %llu,\n"
		"  \"counters_read_ok\": %s,\n"
		"  \"events_written_userspace\": %llu,\n"
		"  \"trace_file_bytes\": %ld,\n"
		"  \"duration_s_requested\": %d,\n"
		"  \"bpf_stats\": {\n"
		"    \"init\": {\"run_time_ns\": %llu, \"run_cnt\": %llu},\n"
		"    \"cong_avoid\": {\"run_time_ns\": %llu, \"run_cnt\": %llu},\n"
		"    \"ssthresh\": {\"run_time_ns\": %llu, \"run_cnt\": %llu},\n"
		"    \"undo_cwnd\": {\"run_time_ns\": %llu, \"run_cnt\": %llu},\n"
		"    \"pkts_acked\": {\"run_time_ns\": %llu, \"run_cnt\": %llu}\n"
		"  }\n"
		"}\n",
		hdr.trace_version, hdr.recorder_version, hdr.kernel_release,
		(unsigned long long)counters.invocations,
		(unsigned long long)counters.emitted,
		(unsigned long long)counters.drops,
		(unsigned long long)counters.clock_jiffies_stable,
		(unsigned long long)counters.clock_jiffies_ambiguous,
		(unsigned long long)counters.clock_ktime_stable,
		(unsigned long long)counters.clock_ktime_ambiguous,
		counters_err == 0 ? "true" : "false",
		events_written, file_size, duration_s,
		(unsigned long long)run_time_ns[0], (unsigned long long)run_cnt[0],
		(unsigned long long)run_time_ns[1], (unsigned long long)run_cnt[1],
		(unsigned long long)run_time_ns[2], (unsigned long long)run_cnt[2],
		(unsigned long long)run_time_ns[3], (unsigned long long)run_cnt[3],
		(unsigned long long)run_time_ns[4], (unsigned long long)run_cnt[4]);
	fclose(meta);

	fprintf(stderr,
		"DONE invocations=%llu emitted=%llu drops=%llu events_written=%llu\n",
		(unsigned long long)counters.invocations,
		(unsigned long long)counters.emitted,
		(unsigned long long)counters.drops,
		events_written);

	return 0;
}
