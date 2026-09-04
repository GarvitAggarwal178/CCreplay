/* Prints exact offsetof()/sizeof() for struct ccr_trace_header and
 * struct ccr_event on this toolchain, so user/ccr_trace.py's Python
 * struct format strings can be derived from ground truth rather than by
 * hand. Re-run whenever bpf/ccr_event.h changes.
 */
#include <stdio.h>
#include <stddef.h>
#include "ccr_event.h"

int main(void)
{
	printf("sizeof(header)=%zu\n", sizeof(struct ccr_trace_header));
	printf("  magic=%zu trace_version=%zu recorder_version=%zu kernel_release=%zu "
	       "ref_impl=%zu callback_manifest=%zu priv_schema=%zu record_size=%zu creation_ts=%zu\n",
	       offsetof(struct ccr_trace_header, magic),
	       offsetof(struct ccr_trace_header, trace_version),
	       offsetof(struct ccr_trace_header, recorder_version),
	       offsetof(struct ccr_trace_header, kernel_release),
	       offsetof(struct ccr_trace_header, reference_impl_id),
	       offsetof(struct ccr_trace_header, callback_manifest),
	       offsetof(struct ccr_trace_header, private_state_schema_id),
	       offsetof(struct ccr_trace_header, record_size),
	       offsetof(struct ccr_trace_header, creation_ts_ns));

	printf("sizeof(event)=%zu\n", sizeof(struct ccr_event));
	printf("  seq=%zu sock_cookie=%zu ts_ns=%zu callback_id=%zu pad0=%zu in_ack=%zu in_acked=%zu\n",
	       offsetof(struct ccr_event, seq), offsetof(struct ccr_event, sock_cookie),
	       offsetof(struct ccr_event, ts_ns), offsetof(struct ccr_event, callback_id),
	       offsetof(struct ccr_event, _pad0), offsetof(struct ccr_event, in_ack),
	       offsetof(struct ccr_event, in_acked));
	printf("  pre_snd_cwnd=%zu pre_snd_ssthresh=%zu pre_snd_cwnd_cnt=%zu pre_snd_cwnd_clamp=%zu "
	       "pre_prior_cwnd=%zu pre_max_packets_out=%zu pre_is_cwnd_limited=%zu\n",
	       offsetof(struct ccr_event, pre_snd_cwnd), offsetof(struct ccr_event, pre_snd_ssthresh),
	       offsetof(struct ccr_event, pre_snd_cwnd_cnt), offsetof(struct ccr_event, pre_snd_cwnd_clamp),
	       offsetof(struct ccr_event, pre_prior_cwnd), offsetof(struct ccr_event, pre_max_packets_out),
	       offsetof(struct ccr_event, pre_is_cwnd_limited));
	printf("  result_valid=%zu result=%zu post_snd_cwnd=%zu post_snd_cwnd_cnt=%zu\n",
	       offsetof(struct ccr_event, result_valid), offsetof(struct ccr_event, result),
	       offsetof(struct ccr_event, post_snd_cwnd), offsetof(struct ccr_event, post_snd_cwnd_cnt));
	return 0;
}
