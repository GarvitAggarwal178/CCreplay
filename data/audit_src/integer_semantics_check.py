"""Cross-checks user/cubic_model.py's cubic_root/fls64 Python port against
the verbatim-C reference (data/audit_src/integer_semantics_check.c,
tcp_cubic.c lines 167-209 copied byte-for-byte) over the same broad
deterministic input range. Writes data/cubic_replay_integer_semantics_test.json.
Run manually: python3 data/audit_src/integer_semantics_check.py
"""
import json
import subprocess
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "user"))
from cubic_model import cubic_root  # noqa: E402

C_OUTPUT_PATH = "/tmp/c_cubic_root_output.txt"


def main():
    if not os.path.exists(C_OUTPUT_PATH):
        print(f"ERROR: {C_OUTPUT_PATH} not found -- run "
              f"'gcc -O2 -o /tmp/integer_semantics_check "
              f"data/audit_src/integer_semantics_check.c && "
              f"/tmp/integer_semantics_check > {C_OUTPUT_PATH}' first",
              file=sys.stderr)
        sys.exit(2)

    mismatches = []
    n_checked = 0
    with open(C_OUTPUT_PATH) as f:
        for line in f:
            a_str, expected_str = line.split()
            a = int(a_str)
            expected = int(expected_str)
            actual = cubic_root(a)
            n_checked += 1
            if actual != expected:
                mismatches.append({"a": a, "expected_c": expected, "actual_python": actual})

    result = {
        "test": "cubic_root integer-semantics isolation",
        "reference": "data/audit_src/integer_semantics_check.c "
                     "(verbatim copy of data/kernel_source_ref/tcp_cubic.c lines 167-209)",
        "n_checked": n_checked,
        "n_mismatches": len(mismatches),
        "pass": len(mismatches) == 0,
        "mismatches": mismatches[:20],
        "range_description": (
            "every integer 0..10000 (exhaustive over the table-lookup path a<64 "
            "and the immediately-following Newton-Raphson path), plus a log-spaced "
            "sweep of milestone values up to 2^62, including the practical ceiling "
            "for cube_factor*(last_max_cwnd-cwnd) under the source's own documented "
            "cwnd<1,000,000-packets precondition"
        ),
    }
    with open("data/cubic_replay_integer_semantics_test.json", "w") as f:
        json.dump(result, f, indent=2)

    print(json.dumps({k: v for k, v in result.items() if k != "mismatches"}, indent=2))
    sys.exit(0 if result["pass"] else 1)


if __name__ == "__main__":
    main()
