#!/bin/bash
# CCReplay professor demo -- step 2: SEEDED FIRST DIVERGENCE.
# The known-good CUBIC reference vs. a one-line variant with a deliberate
# defect in the ssthresh reduction (N5 seeded bug 1). CCReplay reports the
# FIRST callback transition at which the two implementations stop agreeing.
# Deterministic; offline; ~1 s.
set -u
cd "$(dirname "$0")/../.." || exit 2

TRACE=raw/cubic_replay/primary/rep1.ccr
META=raw/cubic_replay/primary/rep1.meta.json

echo "=============================================================="
echo " CCReplay demo 2/3 -- SEEDED FIRST DIVERGENCE"
echo "=============================================================="
echo "TRACE:            $TRACE  (Replay ABI v1, CUBIC)"
echo "REFERENCE:        user.cubic_model              (known good)"
echo "CANDIDATE:        user.cubic_model_bug_ssthresh (seeded: wrong ssthresh reduction, +1)"
echo

python3 user/ccreplay_diff.py "$TRACE" "$META" \
  --reference user.cubic_model --candidate user.cubic_model_bug_ssthresh \
  | python3 -c '
import json,sys
d=json.load(sys.stdin)
div=d["divergence"]
print("MATCHING EVENTS BEFORE DIVERGENCE:", d["matched_event_count_before_divergence"])
print()
print("========= FIRST DIVERGENCE =========")
print("EVENT INDEX:", div["first_divergent_event"]["event_index"])
print("SEQ:        ", div["first_divergent_event"]["seq"])
print("CALLBACK:   ", div["callback"])
for f,vv in {**div.get("callback_result_diff",{}), **div.get("controller_owned_state_diff",{}), **div.get("private_state_diff",{})}.items():
    print("FIELD:      ", f)
    print("  REFERENCE:", vv["reference"])
    print("  CANDIDATE:", vv["candidate"])
print("====================================")
print()
pre={k:v for k,v in div["shared_pre"].items() if k in ("pre_snd_cwnd","pre_snd_ssthresh","pre_snd_cwnd_cnt")}
print("PRE context at the divergent event:", pre)
sys.exit(0 if d["result"]=="DIVERGENCE" else 1)
'
RC=$?
echo
[ "$RC" -eq 0 ] && echo "PASS -- first divergence localized to one callback + one field." \
               || echo "FAIL -- expected a divergence, got none."
exit "$RC"
