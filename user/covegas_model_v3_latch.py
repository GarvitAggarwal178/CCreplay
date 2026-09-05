"""Reconstructed CoVegas v3 settle-latch candidate (A3-only difference).

Phase 3 of docs/session/OVERNIGHT_EVIDENCE_PIPELINE.md. Predictions were
precommitted in data/a3_reconstructed_candidate_predictions.md BEFORE this
file existed.

This module is IDENTICAL to user/covegas_model.py (the fixed/v4 reference)
except for EXACTLY ONE semantic behaviour: the A3 settle-latch guard.

  fixed/v4 (user/covegas_model.py handle_compete_mode, lines 366-373):
      if ca["dlv_rate_compete"] == 0:
          elapsed_jiffies = u32(u32(jiffies_now) - ca["compete_enter_jiffies"])
          if elapsed_jiffies >= (RATE_SETTLE_MS * CONFIG_HZ) // 1000 and ca["dlv_rate_bps"]:
              if ca["dlv_rate_bps"] < (ca["dlv_rate_max"] * 3) // 4:     # <-- A3 guard
                  ca["dlv_rate_compete"] = ca["dlv_rate_bps"]           #     latch
              else:
                  cwnd, ca = revert_to_delay(ca, pre, jiffies_now)      #     v4/A3: back out
                  return cwnd, cwnd_cnt, ca

  reconstructed v3 (this file):
      if ca["dlv_rate_compete"] == 0:
          elapsed_jiffies = u32(u32(jiffies_now) - ca["compete_enter_jiffies"])
          if elapsed_jiffies >= (RATE_SETTLE_MS * CONFIG_HZ) // 1000 and ca["dlv_rate_bps"]:
              ca["dlv_rate_compete"] = ca["dlv_rate_bps"]               # unconditional latch

A1 (targeted cwnd-on-revert) and A2 (detection hold) live in
revert_to_delay() / handle_delay_mode() and are UNCHANGED (still v4).
No changed constants. No refactor. No parser/recorder change.

Everything else -- init, cong_avoid dispatch (cwnd-limited gate,
handle_minrtt_probe, mode dispatch), ssthresh, undo_cwnd, pkts_acked,
cubic_growth, bictcp_update, update_dlv_rate, the comparison schema -- is
imported unchanged from user.covegas_model and used verbatim.
"""
from user import covegas_model as _base
from user.covegas_model import (  # noqa: F401  -- re-export for callers/tools
    u32, s32, u64, MASK32,
    MODE_DELAY, MODE_COMPETE,
    RATE_SETTLE_MS, RATE_JUMP_NUM, RATE_JUMP_DEN, CONFIG_HZ,
    CCR_CB_SSTHRESH, CCR_CB_CONG_AVOID, CCR_CB_UNDO_CWND, CCR_CB_INIT, CCR_CB_PKTS_ACKED,
    CALLBACK_NAMES,
    ALL_PRIVATE_FIELDS, DEDICATED_FIELDS, DELAY_ARM_FIELDS, CUBIC_ARM_FIELDS,
    INITIAL_PRIVATE_STATE,
    pre_from_event, private_pre_from_event,
    revert_to_delay, cubic_growth,
    comparison_fields,
)

MODEL_ID = "covegas_reconstructed_v3_latch"


def handle_compete_mode(ca, pre, acked, jiffies_now):
    """v3 reconstruction: the A3 guard is removed. Once the settle
    prerequisites hold, latch dlv_rate_compete UNCONDITIONALLY and continue
    to cubic_growth (never revert on the settle check).

    Byte-for-byte identical to user.covegas_model.handle_compete_mode except
    the two lines
        if ca["dlv_rate_bps"] < (ca["dlv_rate_max"] * 3) // 4:
        ... else: revert_to_delay(...) ; return
    are replaced by the single unconditional assignment.
    """
    ca = dict(ca)
    cwnd = pre["snd_cwnd"]
    cwnd_cnt = pre["snd_cwnd_cnt"]

    if ca["dlv_rate_compete"] == 0:
        elapsed_jiffies = u32(u32(jiffies_now) - ca["compete_enter_jiffies"])
        if elapsed_jiffies >= (RATE_SETTLE_MS * CONFIG_HZ) // 1000 and ca["dlv_rate_bps"]:
            ca["dlv_rate_compete"] = ca["dlv_rate_bps"]          # v3: unconditional latch
    elif ca["dlv_rate_bps"] > (RATE_JUMP_NUM * ca["dlv_rate_compete"]) // RATE_JUMP_DEN:
        cwnd, ca = revert_to_delay(ca, pre, jiffies_now)          # rate-jump revert -- unchanged from v4
        return cwnd, cwnd_cnt, ca

    cwnd2, cwnd_cnt2, ca = cubic_growth(ca, pre, acked, jiffies_now)
    return cwnd2, cwnd_cnt2, ca


def transition(event, ca):
    """Delegates to user.covegas_model.transition with handle_compete_mode
    swapped to this module's version for the duration of the call.

    The swap is local and reversible (restored in `finally`); the base
    module is not persistently modified, so a fixed/v4 model loaded in the
    same process is unaffected. This is deliberately NOT a copy of the ~115
    line base transition() -- copying it would risk silent drift and would
    be an 'unrelated refactor'. The one and only semantic change is
    handle_compete_mode above.
    """
    _saved = _base.handle_compete_mode
    _base.handle_compete_mode = handle_compete_mode
    try:
        return _base.transition(event, ca)
    finally:
        _base.handle_compete_mode = _saved
