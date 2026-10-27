"""Isolated inputs and trusted schemas shared by session/validation adapters.

The existing controller models remain the sole implementation of CC equations.
"""
from copy import deepcopy
from user.ccreplay_diff import _initial_state


def required_fields(trusted, event, reference, candidate):
    cb = event['callback_id']
    if hasattr(trusted, 'COMPARISON_FIELDS'):
        return list(trusted.COMPARISON_FIELDS[cb])
    # Preserve the existing reference-oracle comparison arm (ADR-023).
    # Validate each side's own active arm separately below; comparing a union
    # would incorrectly compare a field that is dead in the reference mode.
    return list(trusted.comparison_fields(cb, event.get('priv_pre_mode'), reference.get('priv_post_mode')))



def iterate(events, reference, candidate, trusted, mode):
    if mode not in ('A', 'B'):
        raise ValueError('Mode must be A or B')
    ref_state, cand_state = deepcopy(_initial_state(reference)), deepcopy(_initial_state(candidate))
    pre_fn = getattr(trusted, 'private_pre_from_event', lambda e: None)
    for index, event in enumerate(events):
        rp = deepcopy(pre_fn(event) if mode == 'A' else ref_state)
        cp = deepcopy(pre_fn(event) if mode == 'A' else cand_state)
        # Never let custom code mutate recorded/cache/reference inputs.
        ref, rn = reference.transition(deepcopy(event), deepcopy(rp))
        cand, cn = candidate.transition(deepcopy(event), deepcopy(cp))
        fields = required_fields(trusted, event, ref, cand)
        for side, computed in [('reference', ref), ('candidate', cand)]:
            required = required_fields(trusted, event, computed, computed)
            missing = [f for f in required if f not in computed]
            if missing:
                raise ValueError(f'{side} missing required fields at index {index}: {missing}')
        diffs = [f for f in fields if ref.get(f) != cand.get(f)]
        yield index, event, ref, cand, rp, cp, rn, cn, fields, diffs, mode == 'B' and rp != cp
        ref_state, cand_state = deepcopy(rn), deepcopy(cn)
