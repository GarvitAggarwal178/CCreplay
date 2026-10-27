/* N0 diagnostic-only generic struct_ops loader. Not part of the production
 * recorder path (that stays user/ccr_recorder.c, untouched). Loads any
 * compiled CC-recorder-shaped .bpf.o generically (no skeleton codegen
 * needed), attaches its struct_ops, drains its ringbuf (content discarded
 * -- these traces are never used for replay gates, per
 * docs/session/OVERNIGHT_EVIDENCE_PIPELINE.md N0.3/N0.4), and at teardown
 * reads the ccr_counters_map + per-program BPF stats, before detaching.
 *
 * Two drain modes:
 *   poll     -- ring_buffer__poll(), relies on the producer's wakeup
 *               (use for the BPF_RB_NO_WAKEUP variant's baseline-of-
 *               comparison programs that still signal wakeups normally).
 *   consume  -- ring_buffer__consume() in a tight timed loop, does NOT
 *               depend on any wakeup notification (required for the
 *               N0.3 BPF_RB_NO_WAKEUP variant, whose producer never
 *               signals epoll readiness).
 *
 * Usage: generic_loader <obj.o> <struct_ops_var_name> <duration_s> <poll|consume>
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <signal.h>
#include <unistd.h>
#include <errno.h>
#include <time.h>
#include <bpf/libbpf.h>
#include <bpf/bpf.h>

static volatile sig_atomic_t stop;
static unsigned long long events_seen;

static void on_signal(int sig) { (void)sig; stop = 1; }

static int handle_event(void *ctx, void *data, size_t len)
{
	(void)ctx; (void)data; (void)len;
	events_seen++;
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

	if (fd < 0)
		return -1;
	if (bpf_obj_get_info_by_fd(fd, &info, &info_len))
		return -1;
	*run_time_ns = info.run_time_ns;
	*run_cnt = info.run_cnt;
	return 0;
}

int main(int argc, char **argv)
{
	if (argc != 5) {
		fprintf(stderr, "usage: %s <obj.o> <struct_ops_var_name> <duration_s> <poll|consume>\n", argv[0]);
		return 1;
	}
	const char *obj_path = argv[1];
	const char *so_name = argv[2];
	int duration_s = atoi(argv[3]);
	int consume_mode = strcmp(argv[4], "consume") == 0;

	struct bpf_object *obj = bpf_object__open_file(obj_path, NULL);
	if (!obj) {
		fprintf(stderr, "ERROR: bpf_object__open_file(%s) failed\n", obj_path);
		return 1;
	}

	if (bpf_object__load(obj)) {
		fprintf(stderr, "ERROR: bpf_object__load failed\n");
		return 1;
	}

	struct bpf_map *so_map = bpf_object__find_map_by_name(obj, so_name);
	if (!so_map) {
		fprintf(stderr, "ERROR: struct_ops map '%s' not found\n", so_name);
		return 1;
	}
	struct bpf_map *counters_map = bpf_object__find_map_by_name(obj, "ccr_counters_map");
	struct bpf_map *events_map = bpf_object__find_map_by_name(obj, "ccr_events");
	if (!counters_map || !events_map) {
		fprintf(stderr, "ERROR: expected maps not found\n");
		return 1;
	}

	struct ring_buffer *rb = ring_buffer__new(bpf_map__fd(events_map), handle_event, NULL, NULL);
	if (!rb) {
		fprintf(stderr, "ERROR: ring_buffer__new failed\n");
		return 1;
	}

	struct bpf_link *link = bpf_map__attach_struct_ops(so_map);
	if (!link) {
		fprintf(stderr, "ERROR: bpf_map__attach_struct_ops failed: %d\n", -errno);
		return 1;
	}

	printf("ATTACHED\n");
	fflush(stdout);

	signal(SIGINT, on_signal);
	signal(SIGTERM, on_signal);

	__u64 t_start = now_ns();
	__u64 t_deadline = t_start + (__u64)duration_s * 1000000000ull;

	while (!stop && now_ns() < t_deadline) {
		if (consume_mode) {
			ring_buffer__consume(rb);
			usleep(2000); /* 2ms busy-poll interval, no wakeup dependency */
		} else {
			int err = ring_buffer__poll(rb, 200);
			if (err < 0 && err != -EINTR)
				break;
		}
	}
	/* final drain */
	for (int i = 0; i < 20; i++) {
		int n = consume_mode ? ring_buffer__consume(rb) : ring_buffer__poll(rb, 20);
		if (n <= 0)
			break;
	}

	__u32 key = 0;
	struct { __u64 invocations, emitted, drops; } counters = {0};
	int counters_err = bpf_map__lookup_elem(counters_map, &key, sizeof(key), &counters, sizeof(counters), 0);

	printf("{\n");
	printf("  \"struct_ops\": \"%s\",\n", so_name);
	printf("  \"mode\": \"%s\",\n", consume_mode ? "consume" : "poll");
	printf("  \"duration_s\": %d,\n", duration_s);
	printf("  \"counters_read_ok\": %s,\n", counters_err == 0 ? "true" : "false");
	printf("  \"invocations\": %llu,\n", (unsigned long long)counters.invocations);
	printf("  \"emitted\": %llu,\n", (unsigned long long)counters.emitted);
	printf("  \"drops\": %llu,\n", (unsigned long long)counters.drops);
	printf("  \"events_seen_userspace\": %llu,\n", events_seen);
	printf("  \"bpf_stats\": {\n");

	struct bpf_program *prog;
	int first = 1;
	bpf_object__for_each_program(prog, obj) {
		__u64 rt = 0, rc = 0;
		get_prog_stats(prog, &rt, &rc);
		printf("    %s\"%s\": {\"run_time_ns\": %llu, \"run_cnt\": %llu}\n",
			first ? "" : ",", bpf_program__name(prog),
			(unsigned long long)rt, (unsigned long long)rc);
		first = 0;
	}
	printf("  }\n");
	printf("}\n");

	bpf_link__destroy(link);
	ring_buffer__free(rb);
	bpf_object__close(obj);
	return 0;
}
