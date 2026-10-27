#!/bin/bash
# CCReplay professor demo -- step 3: CHECKPOINT + SUFFIX REPRODUCER.
# The same seeded divergence from demo 2, reproduced by replaying ONLY the
# suffix of events from a private-state checkpoint taken at event 1500
# through the divergence at event 1704 -- 205 events (1500..1704 inclusive),
# every one of them, in order. This is a reproducer, NOT minimization: events
# [0..1499] are fully accounted for by the saved pre-event state, not skipped
# or deleted.
# Deterministic; offline; ~2 s.
set -u
cd "$(dirname "$0")/../.." || exit 2

TRACE=raw/cubic_replay/primary/rep1.ccr
CKPT=runtime/demo/demo_checkpoints.json

echo "=============================================================="
echo " CCReplay demo 3/3 -- CHECKPOINT + SUFFIX REPRODUCER"
echo "=============================================================="
echo "TRACE:            $TRACE"
echo "REFERENCE:        user.cubic_model"
echo "CANDIDATE:        user.cubic_model_bug_ssthresh"
echo "CHECKPOINT EVERY: 500 events"
echo

mkdir -p runtime/demo
python3 user/ccreplay_checkpoint.py "$TRACE" \
  --reference user.cubic_model --candidate user.cubic_model_bug_ssthresh \
  --interval 500 --save-checkpoints-to "$CKPT" \
  | python3 -c '
import json,sys
d=json.load(sys.stdin)
D=d["first_divergence_full_run"]
sd=d["suffix_replay_divergence"]
ck=d["nearest_checkpoint"]
print("FULL TRACE DIVERGENCE:  event_index=%s seq=%s callback=%s field=%s"
      % (D["event_index"], D["seq"], D["callback"], ",".join(D["diff_fields"])))
print("CHECKPOINT (state before): next_event_index=%s next_seq=%s" % (ck["next_event_index"], ck["next_seq"]))
print("REPLAYED SUFFIX LENGTH: %s  (events %d..%d, every one, in order)"
      % (d["suffix_length"], ck["next_event_index"], D["event_index"]))
print("REPRODUCED DIVERGENCE:  event_index=%s seq=%s field=%s"
      % (sd["event_index"], sd["seq"], ",".join(sd["diff_fields"])))
print("IDENTICAL RESULT:      ", d["reproduced_same_divergence"])
sys.exit(0 if d["reproduced_same_divergence"] else 1)
'
RC=$?
echo
[ "$RC" -eq 0 ] && echo "PASS -- suffix replay reproduces the identical first divergence." \
               || echo "FAIL -- suffix replay did not reproduce the divergence."
exit "$RC"
