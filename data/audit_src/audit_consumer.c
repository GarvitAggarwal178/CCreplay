/* Capability audit B consumer: drains audit_skstorage's ringbuf so we can
 * see the per-socket counter increment across calls, proving SK_STORAGE
 * state actually persists across callback invocations rather than being
 * re-zeroed. Usage: audit_consumer <map_id> <duration_s>
 */
#include <stdio.h>
#include <stdlib.h>
#include <signal.h>
#include <unistd.h>
#include <bpf/libbpf.h>
#include <bpf/bpf.h>

struct audit_event {
	unsigned long long ts_ns;
	unsigned int counter;
};

static volatile int stop;
static void on_alarm(int sig) { stop = 1; }

static int handle_event(void *ctx, void *data, size_t len)
{
	struct audit_event *e = data;
	if (len < sizeof(*e))
		return 0;
	printf("ts_ns=%llu counter=%u\n", e->ts_ns, e->counter);
	return 0;
}

int main(int argc, char **argv)
{
	if (argc != 3) {
		fprintf(stderr, "usage: %s <map_id> <duration_s>\n", argv[0]);
		return 1;
	}
	int map_id = atoi(argv[1]);
	int duration = atoi(argv[2]);

	int map_fd = bpf_map_get_fd_by_id(map_id);
	if (map_fd < 0) {
		fprintf(stderr, "bpf_map_get_fd_by_id(%d) failed\n", map_id);
		return 1;
	}

	struct ring_buffer *rb = ring_buffer__new(map_fd, handle_event, NULL, NULL);
	if (!rb) {
		fprintf(stderr, "ring_buffer__new failed\n");
		return 1;
	}

	signal(SIGALRM, on_alarm);
	alarm(duration);

	while (!stop) {
		int err = ring_buffer__poll(rb, 200);
		if (err < 0 && err != -4)
			break;
	}

	ring_buffer__free(rb);
	return 0;
}
