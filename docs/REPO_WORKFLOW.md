# CCReplay — Repository Workflow and Presentation Conventions

The repository should be understandable by:

* the project author;
* a professor;
* a future collaborator;
* someone reviewing the GitHub history.

The repository should tell one coherent story:

```text
problem
→ Replay Contract
→ lossless recorder
→ exact Reno transition replay
→ stateful CUBIC replay
→ differential debugger
→ regression localization
```

## Repository structure

Preferred structure:

```text
ccreplay/
├── README.md
├── CLAUDE.md
├── INSTRUCTIONS.md
├── REPORT_OVERNIGHT_INDEX.md
│
├── docs/
│   ├── PROJECT.md
│   ├── ARCHITECTURE.md
│   ├── SEMANTICS.md
│   ├── REPLAY_ABI.md
│   ├── RECORDER.md
│   ├── REPLAY_ENGINE.md
│   ├── DIFFERENTIAL_DEBUGGER.md
│   ├── CORRECTNESS_ORACLES.md
│   ├── GATES.md
│   ├── EVALUATION.md
│   ├── CASE_STUDIES.md
│   ├── PRIOR_ART.md
│   ├── LIMITATIONS.md
│   ├── ROADMAP.md
│   ├── PROVENANCE.md
│   ├── DECISIONS.md
│   └── REPO_WORKFLOW.md
│
├── bpf/
├── user/
├── controllers/
├── scripts/
├── tests/
│
├── raw/
│   ├── r0/
│   ├── r1/
│   ├── r2/
│   ├── r3/
│   │   ├── primary/
│   │   └── auxiliary/
│   ├── n0_overhead/
│   └── case_studies/
│
├── data/
│   ├── capability/
│   ├── r3/
│   ├── n0_overhead/
│   └── case_studies/
│
└── plots/
```

Do not place large raw traces or experiment logs at repository root.

---

# Naming conventions

## Code/data

Use:

`lowercase_snake_case`

Examples:

```text
ccrec_cubic.bpf.c
ccr_trace.py
cubic_model.py
r3_model_changes.md
r3_callback_coverage.csv
```

Avoid:

```text
new.py
new2.py
final_fixed.py
test_latest.sh
results_new.csv
```

## Human-facing reports

Use uppercase report names:

```text
REPORT_GATE_R3_CUBIC.md
REPORT_DIFFERENTIAL_DEBUGGER.md
REPORT_CONTROLLED_REGRESSION_CASE_STUDY.md
REPORT_CHECKPOINT_REPRODUCER.md
```

## Run IDs

Every experiment gets a stable run ID.

Examples:

```text
r3_primary_rep01
r3_primary_rep02
r3_aux_reorder_rep01

n0_stats_on_rep01
n0_stats_off_rep01

n5_bug_ssthresh_rep01
n5_bug_epoch_reset_rep01
n5_bug_dormant_control_rep01
```

The run ID should appear in:

* raw trace filename;
* metadata filename;
* run log;
* derived data row.

---

# Raw-data rules

Files under `raw/` are immutable.

Example:

```text
raw/r3/primary/
    r3_primary_rep01.ccr
    r3_primary_rep01_metadata.json
    r3_primary_rep01_run.log
```

If parser logic changes:

* keep raw trace;
* regenerate derived data under `data/`.

Never modify the original trace.

Invalid runs stay stored.

Metadata should state:

```text
valid: true/false
invalid_reason:
```

---

# Derived-data rules

Use machine-readable formats where practical:

* CSV;
* JSON;
* JSONL.

Examples:

```text
data/r3/r3_callback_coverage.csv
data/r3/r3_replay_summary.json
data/r3/r3_integer_semantics_test.json
```

Derived outputs must be reproducible from raw evidence.

---

# Report structure

Major reports should generally contain:

```text
# Report title

## Status

## Question

## Precommitted expectation / hypothesis

## Environment

## Implementation / method

## Evidence

## Failures and deviations

## Result

## Limitations

## Gate verdict

## Reproduction paths

## Relevant commits
```

Put:

`PASS / PARTIAL / FAIL / INCOMPLETE`

near the top.

Do not make readers search 20 pages for the verdict.

---

# Git commit style

Use:

```text
<type>(<scope>): <imperative summary>
```

Recommended types:

* `docs`
* `feat`
* `fix`
* `test`
* `exp`
* `refactor`
* `chore`

Examples:

```text
docs(r3): precommit CUBIC contract predictions

feat(recorder): add ABI v1 CUBIC private-state capture

test(cubic): add fixed-point cube-root oracle

exp(r3): record three lossless primary CUBIC traces

fix(replay): match reference CUBIC epoch reset semantics

feat(diff): report first divergent callback result

exp(n5): run seeded epoch-reset regression

feat(repro): add checkpoint suffix reproducer
```

Avoid:

```text
update
stuff
fixes
working now
final
final2
```

---

# Commit-content rules

Prefer one conceptual change per commit.

Avoid combining in one opaque commit:

* recorder rewrite;
* replay-model change;
* experiment results;
* report changes.

Prediction files must be committed before experiment execution.

Reports should reference relevant commit hashes when useful.

---

# Evidence history

Do not rewrite evidence history during development.

Avoid:

* squashing failed experiments;
* amending earlier prediction commits;
* force-pushing;
* deleting evidence commits.

If an earlier conclusion becomes wrong:

create a corrective commit.

The historical mistake and correction are useful evidence of engineering discipline.

---

# Experimental branches

A linear history is acceptable.

For risky temporary work, optional branch names:

```text
exp/r3-clock-instrumentation
exp/n0-ringbuf-nowakeup
exp/r3-split-record-prototype
```

Do not leave essential finished work stranded on unnamed branches.

---

# Milestone tags

Optional Git tags:

```text
phase1-r0-r2-pass
r3-pass
debugger-demo
semester-final
```

Tags should mark meaningful stable milestones.

---

# `.gitignore`

Do not commit routine:

* object files;
* build directories;
* caches;
* editor files;
* temporary logs;
* secrets;
* huge disposable traces.

Raw evidence policy should be intentional.

If representative traces are small enough, keeping some in-repo is useful.

If raw data becomes large, document external storage/reproduction clearly.

---

# README policy

README should answer:

1. What is CCReplay?
2. What problem does it solve?
3. How does it work?
4. What does it explicitly not claim?
5. What is the latest stable gate status?
6. What is the current demo?
7. Where are the detailed docs?

Do not use README as a daily lab notebook.

Chronology belongs in:

* reports;
* commits;
* `REPORT_OVERNIGHT_INDEX.md`.

---

# Experiment metadata

Every important network experiment should preserve:

* run ID;
* date/time;
* kernel;
* git commit;
* controller implementation ID;
* Replay ABI version;
* callback manifest;
* topology;
* qdisc configuration/readback;
* offload state;
* duration;
* exit status;
* drop count;
* sequence-gap count;
* trace path.

---

# Prediction files

Experiments involving predictions use separate files.

Examples:

```text
data/r3_contract_predictions.md
data/n5_predictions.md
```

Structure:

```text
# Predictions

## Prediction P1
...

## Prediction P2
...

---

# Results

Appended only after the prediction commit exists.
```

Never rewrite prediction wording after observing results.

---

# Model-change log

For CUBIC replay maintain:

`data/r3_model_changes.md`

Every replay-model change should record:

```text
## Change N

Mismatch:
Category: A / B / C

Reference source:
file:
line/region:

Problem:

Change:

Why justified:

Trace re-record required: YES / NO

Commit:
```

This protects the project against accusations of fitting the model to the data.

---

# Overnight session index

Maintain:

`REPORT_OVERNIGHT_INDEX.md`

Suggested table:

| Phase | Status                       | Duration | Report | Commit | Continue? |
| ----- | ---------------------------- | -------: | ------ | ------ | --------- |
| N0    | COMPLETE                     |          |        |        |           |
| R3    | PASS/PARTIAL/FAIL/INCOMPLETE |          |        |        |           |
| N4    |                              |          |        |        |           |
| N5    |                              |          |        |        |           |
| N6    |                              |          |        |        |           |

If work stops early, state why.

---

# GitHub presentation principle

Someone opening the repo should not see:

> "a giant collection of random congestion-control experiments."

They should see:

> "a coherent systems project that defines a replay boundary, proves it works, then builds a debugger on top."

Organize every directory and report around that narrative.

---

# Morning review order

Review overnight work in this order:

1. **Did all Phase-1 tests and Reno v0 replay still pass at end of night?**
2. Were read-only source repositories unchanged?
3. What was the R3 verdict?
4. Did CUBIC private state evolve nontrivially?
5. Was R3 model development source-justified rather than trace-fitted?
6. Which predicted Replay Contract inputs were confirmed?
7. Which unexpected Replay Contract inputs were discovered?
8. Were any clock-ambiguous events observed?
9. Did reference-vs-reference produce zero divergence?
10. Did seeded positive bugs localize correctly?
11. Did the dormant-defect negative control produce NO divergence?
12. Did checkpoint+suffix reproduce the same first divergence?
13. Are reports and commits easy to navigate?

Only after these questions are answered should the historical CoVegas case study begin.

---

# Public-Facing Filename Rule

Repository filenames must make sense to a third party who has NOT followed the project's internal
gate numbering or development chronology.

Internal labels such as:

* `R0`
* `R1`
* `R2`
* `R3`
* `N0`
* `N4`
* `night`
* `overnight`
* `batch`
* `phase2`

may appear inside reports for chronology, but SHOULD NOT be the primary meaning of a committed
public-facing filename.

Prefer filenames that describe WHAT the file contains.

## Bad

```text
r3-night-batch.md
r3_results.md
n0_report.md
phase2_test.md
overnight_debug.md
r3_data.csv
n5_predictions.md
final_results2.md
```

A new reader cannot understand these names without knowing our internal roadmap.

## Good

```text
REPORT_CUBIC_REPLAY_FIDELITY.md
REPORT_RECORDER_OVERHEAD_ANALYSIS.md
REPORT_DIFFERENTIAL_DEBUGGER.md
REPORT_CONTROLLED_REGRESSION_CASE_STUDY.md
REPORT_CHECKPOINT_REPRODUCER.md

cubic_replay_contract_predictions.md
cubic_replay_model_changes.md
cubic_callback_coverage_plan.md
cubic_integer_semantics_test.json

recorder_overhead_summary.csv
cubic_replay_summary.json
controlled_regression_predictions.md
```

## Internal gate IDs may be secondary

It is fine for the report itself to say:

```text
Gate: R3
Status: PASS
```

But the filename should remain:

```text
REPORT_CUBIC_REPLAY_FIDELITY.md
```

not:

```text
REPORT_R3.md
```

Likewise:

```text
data/r3_contract_predictions.md
```

should preferably become:

```text
data/cubic_replay_contract_predictions.md
```

and:

```text
data/r3_model_changes.md
```

should become:

```text
data/cubic_replay_model_changes.md
```

## Directory names

Short internal directory names are acceptable where they help organization, but public-facing
structure should still be understandable.

Prefer:

```text
raw/cubic_replay/primary/
raw/cubic_replay/auxiliary/

data/cubic_replay/
data/recorder_overhead/
data/controlled_regressions/
```

over:

```text
raw/r3/
data/n0/
data/n5/
```

If existing historical directories already use gate IDs, do NOT rename them destructively just for
aesthetics.

Use clearer names for new work going forward.

## Report naming pattern

Prefer:

```text
REPORT_<DESCRIPTIVE_TOPIC>.md
```

Examples:

```text
REPORT_PHASE1_RENO_REPLAY_VALIDATION.md
REPORT_RECORDER_OVERHEAD_ANALYSIS.md
REPORT_CUBIC_REPLAY_FIDELITY.md
REPORT_DIFFERENTIAL_DEBUGGER.md
REPORT_CONTROLLED_REGRESSION_CASE_STUDY.md
REPORT_CHECKPOINT_REPRODUCER.md
REPORT_HISTORICAL_COVEGAS_REGRESSION.md
```

The filename should answer:

> "What will I learn if I open this file?"

without requiring knowledge of project-internal gate numbers.

## Commit messages follow the same principle

Prefer:

```text
exp(cubic-replay): validate exact stateful CUBIC replay

feat(diff): add first-divergence localization

test(cubic): validate fixed-point cube-root semantics

docs(replay-abi): add CUBIC callback and private-state contract
```

over:

```text
r3 done
night batch
n4 complete
phase 2 fixes
```

Gate IDs may be included secondarily when useful:

```text
exp(cubic-replay): pass CUBIC fidelity gate (R3)
```

## Final check before every commit

Before committing a new file, ask:

> Would someone opening this repository six months from now understand roughly what this file
> contains from its name alone?

If NO, rename it before committing.

Do not rename old evidence in a way that breaks provenance, report references, or reproducibility
merely for aesthetics. Apply this rule prospectively and perform intentional cleanup only when
references can be updated safely.

---

## Application to Phase 1 (R0/R1/R2, Reno)

This document was adopted **after** Phase 1 (recorder viability, Reno event-local replay, Reno
stateful replay) was already complete and committed. Per its own rules, Phase 1's evidence was not
rewritten:

- `raw/r0/` keeps its gate-ID directory name (historical, per "Directory names" leniency above).
- The three recorded traces (`raw/r0/rep{1,2,3}.ccr` etc.) keep their existing filenames —
  immutable raw evidence already referenced by committed report prose.
- Git history from Phase 1 (`milestone N: ...` commit messages) was not rewritten, amended, or
  squashed — only new commits follow the `<type>(<scope>): <summary>` style from this point
  forward.

What *was* safely renamed on adoption, with every reference updated in the same commit:

- `REPORT_GATES_R0_R1_R2.md` → `REPORT_PHASE1_RENO_REPLAY_VALIDATION.md` (the report's own
  self-referencing "REPORT PATH" line, and the one other file that named it,
  `user/replay_r2.py`'s module docstring, were both updated).
- `data/r1_result.json` → `data/reno_event_local_replay_result.json`;
  `data/r2_result.json` → `data/reno_stateful_replay_result.json`.

Future phases (CUBIC replay, differential debugger, regression case studies) follow this document
from their first commit.
