/* Consumer for audit_fields ringbuf: writes CSV for post-hoc PRE/POST diff
 * analysis in Python. Usage: audit_fields_consumer <map_id> <duration_s> <out_csv>
 */
#include <stdio.h>
#include <stdlib.h>
#include <signal.h>
#include <unistd.h>
#include <bpf/libbpf.h>
#include <bpf/bpf.h>

struct fields_snap {
	unsigned int snd_cwnd, snd_ssthresh, snd_cwnd_cnt, snd_cwnd_clamp;
	unsigned int snd_cwnd_used, snd_cwnd_stamp, prior_cwnd, prior_ssthresh;
	unsigned int packets_out, max_packets_out;
	unsigned char is_cwnd_limited;
};

struct fields_event {
	unsigned long long ts_ns;
	unsigned int callback;
	unsigned int ack, acked, ret;
	struct fields_snap pre, post;
};

static FILE *out;
static volatile int stop;
static void on_alarm(int sig) { stop = 1; }

static int handle_event(void *ctx, void *data, size_t len)
{
	struct fields_event *e = data;
	if (len < sizeof(*e))
		return 0;
	fprintf(out,
		"%llu,%u,%u,%u,%u,"
		"%u,%u,%u,%u,%u,%u,%u,%u,%u,%u,%u,"
		"%u,%u,%u,%u,%u,%u,%u,%u,%u,%u\n",
		e->ts_ns, e->callback, e->ack, e->acked, e->ret,
		e->pre.snd_cwnd, e->pre.snd_ssthresh, e->pre.snd_cwnd_cnt, e->pre.snd_cwnd_clamp,
		e->pre.snd_cwnd_used, e->pre.snd_cwnd_stamp, e->pre.prior_cwnd, e->pre.prior_ssthresh,
		e->pre.packets_out, e->pre.max_packets_out, e->pre.is_cwnd_limited,
		e->post.snd_cwnd, e->post.snd_ssthresh, e->post.snd_cwnd_cnt, e->post.snd_cwnd_clamp,
		e->post.snd_cwnd_used, e->post.snd_cwnd_stamp, e->post.prior_cwnd, e->post.prior_ssthresh,
		e->post.packets_out, e->post.max_packets_out);
	return 0;
}

int main(int argc, char **argv)
{
	if (argc != 4) {
		fprintf(stderr, "usage: %s <map_id> <duration_s> <out_csv>\n", argv[0]);
		return 1;
	}
	int map_id = atoi(argv[1]);
	int duration = atoi(argv[2]);
	out = fopen(argv[3], "w");
	if (!out) { perror("fopen"); return 1; }

	fprintf(out, "ts_ns,callback,ack,acked,ret,"
		"pre_snd_cwnd,pre_snd_ssthresh,pre_snd_cwnd_cnt,pre_snd_cwnd_clamp,"
		"pre_snd_cwnd_used,pre_snd_cwnd_stamp,pre_prior_cwnd,pre_prior_ssthresh,"
		"pre_packets_out,pre_max_packets_out,pre_is_cwnd_limited,"
		"post_snd_cwnd,post_snd_ssthresh,post_snd_cwnd_cnt,post_snd_cwnd_clamp,"
		"post_snd_cwnd_used,post_snd_cwnd_stamp,post_prior_cwnd,post_prior_ssthresh,"
		"post_packets_out,post_max_packets_out\n");

	int map_fd = bpf_map_get_fd_by_id(map_id);
	if (map_fd < 0) { fprintf(stderr, "bpf_map_get_fd_by_id failed\n"); return 1; }

	struct ring_buffer *rb = ring_buffer__new(map_fd, handle_event, NULL, NULL);
	if (!rb) { fprintf(stderr, "ring_buffer__new failed\n"); return 1; }

	signal(SIGALRM, on_alarm);
	alarm(duration);
	while (!stop) {
		int err = ring_buffer__poll(rb, 200);
		if (err < 0 && err != -4)
			break;
	}
	ring_buffer__free(rb);
	fclose(out);
	return 0;
}
