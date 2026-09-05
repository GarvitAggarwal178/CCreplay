#!/bin/bash
# CCReplay professor demo -- OPTIONAL step 4: HISTORICAL A3 REGRESSION.
#
# A real captured Replay ABI v2 CoVegas trace that contains the historical
# off-period trigger: covegas spuriously enters COMPETE mode during a
# cross-traffic OFF period, and ~1 s later the fixed/v4 "A3" settle-latch
# guard fires because the settle-time delivery rate is ~99.6% of the recent
# maximum (no real competitor is depressing it). The reconstructed v3 build
# -- v4's committed source with EXACTLY the A3 guard reverted to an
# unconditional latch -- would latch instead. CCReplay pins the first
# divergence to that one callback.
#
# DISCLOSURE: `reconstructed-v3` is a documented reconstruction (v4 source
# with one conditional reverted), NOT original committed v3 source -- v3's
# src/covegas.bpf.c was never committed to the read-only repo.
#
# Deterministic; offline; ~3 s. NOT part of the main demo -- run last.
set -u
cd "$(dirname "$0")/../.." || exit 2

TRACE=raw/covegas_campaign/rep4.ccr
META=raw/covegas_campaign/rep4.meta.json
if [ ! -f "$TRACE" ]; then
  echo "SKIP -- $TRACE not present (no qualifying historical trace was acquired)."
  exit 0
fi

echo "=============================================================="
echo " CCReplay demo 4/4 (OPTIONAL) -- HISTORICAL A3 REGRESSION"
echo "=============================================================="
echo "TRACE:            $TRACE  (Replay ABI v2, CoVegas; captured, real)"
echo "REFERENCE:        user.covegas_model            (fixed/v4)"
echo "CANDIDATE:        user.covegas_model_v3_latch   (reconstructed v3 -- v4 with the A3 guard reverted)"
echo
echo "This trace contains, in ONE COMPETE episode:"
echo "  * Predicate H: a spurious DELAY->COMPETE transition at seq=9533 during a cross-traffic OFF period"
echo "  * Predicate D: a settle-latch guard evaluation at seq=10421 (~1s later) with"
echo "                 dlv_rate_bps/dlv_rate_max ~= 0.996  ->  the v4 A3 guard FAILS (reverts)"
echo

python3 user/ccreplay_diff.py "$TRACE" "$META" \
  --reference user.covegas_model --candidate user.covegas_model_v3_latch \
  | python3 -c '
import json,sys
d=json.load(sys.stdin)
div=d["divergence"]
print("MATCHING EVENTS BEFORE DIVERGENCE:", d["matched_event_count_before_divergence"])
print()
print("========= FIRST DIVERGENCE =========")
print("EVENT INDEX:", div["first_divergent_event"]["event_index"])
print("SEQ:        ", div["first_divergent_event"]["seq"], " (the Predicate-D settle-latch event)")
print("CALLBACK:   ", div["callback"])
cd=div["private_state_diff"]
for f in ("priv_post_mode","priv_post_dlv_rate_compete"):
    if f in cd:
        print("FIELD:      ", f)
        print("  fixed/v4 (revert):", cd[f]["reference"])
        print("  recon-v3 (latch): ", cd[f]["candidate"])
print("OTHER DIFFERING (computed boundary values):", ", ".join(f for f in div["all_diff_fields"] if f not in ("priv_post_mode","priv_post_dlv_rate_compete")))
print("  (v4 executed revert_to_delay(); v3 executed cubic_growth() -- these are the values each")
print("   implementation COMPUTES AT THIS RECORDED CALLBACK BOUNDARY, not an alternate trajectory)")
print("====================================")
sys.exit(0 if d["result"]=="DIVERGENCE" else 1)
'
RC=$?
echo
if [ "$RC" -eq 0 ]; then
  echo "PASS -- fixed/v4 and reconstructed-v3 first differ at exactly the historical Predicate-D event."
  echo "        NOT a claim about alternate throughput/RTT or a recreated network outcome."
else
  echo "FAIL -- expected a divergence at the historical Predicate-D event."
fi
exit "$RC"
