# CCReplay — Unattended Work Instructions

This file governs long unattended Claude Code sessions.

Technical project semantics remain defined by `CLAUDE.md` and `docs/`.

These rules define **how work must be performed**.

## 1. Evidence over PASS

Do not optimize for producing PASS.

Allowed outcomes:

* PASS
* PARTIAL
* FAIL
* INCOMPLETE

A precise FAIL with preserved evidence is better than an unreliable PASS.

## 2. Respect phase time budgets

Every unattended phase has a fixed wall-clock budget.

When a budget expires:

1. stop work on that phase;
2. preserve evidence;
3. commit coherent work;
4. write an `INCOMPLETE` report;
5. name the blocker;
6. update the session index;
7. do not proceed to dependent phases.

Do not spend an entire unattended session rescuing one mismatch.

## 3. Never fit a model to a recorded trace

Replay-controller logic must come from:

* reference source;
* documented controller semantics;
* defensible Replay Contract inputs.

Forbidden:

* sequence-number special cases;
* trace-name special cases;
* magic constants derived from expected output;
* changing formulas because one trace then matches.

Every replay-model correction must identify the source code or recorder bug that proves the correction is valid.

## 4. Raw evidence is immutable

Never manually edit:

`raw/`

Never overwrite an existing run directory.

Every experiment receives a new run ID.

Invalid runs remain stored and are marked invalid.

Derived data belongs under:

`data/`

## 5. Source repos are read-only

Never modify:

* `~/cn-spike`
* `~/cn`
* `~/cn-spike/covegas`

Capture before/after integrity evidence during unattended sessions.

## 6. Documentation precedes semantic implementation changes

If implementation reality requires a semantic change:

1. stop;
2. update relevant docs;
3. add/update ADR;
4. then implement.

If a new controller merely reveals a missing Replay ABI field:

1. document the source evidence;
2. version the ABI;
3. update contract;
4. re-record;
5. continue.

Do not silently change project meaning.

## 7. Preserve primary/auxiliary separation

Primary gate evidence uses the validated primary testbed unless explicitly documented otherwise.

Auxiliary topology changes may be used for rare callback coverage.

Never include auxiliary traces in primary gate pass counts.

## 8. Regression-test supported history

After changes to:

* recorder;
* parser;
* trace format;
* replay engine;

rerun prior supported replay gates on committed traces.

Backward compatibility is a testable property.

## 9. Predictions must exist before results

For prediction-based experiments:

1. write predictions;
2. commit predictions;
3. only then run the experiment.

Never rewrite predictions after seeing results.

Append a separate RESULTS section instead.

## 10. Preserve first mismatch evidence

For every replay mismatch preserve:

* trace;
* event;
* callback;
* shared PRE;
* private PRE;
* arguments;
* time;
* expected result/state;
* actual result/state;
* differing fields;
* local context.

Do not only report aggregate mismatch count.

## 11. No hidden retries

Do not silently repeat failed experiments until one passes.

Every run should have:

* run ID;
* log;
* exit status;
* metadata.

A rerun should state why it was rerun.

## 12. Commit before risky work

Create a clean commit before:

* ABI migration;
* major recorder rewrite;
* topology deviation;
* seeded bug experiment;
* major replay-model refactor.

This preserves a known-good rollback point.

## 13. Never rewrite evidence history

During unattended work:

* do not squash;
* do not amend historical evidence commits;
* do not force-push;
* do not delete failed evidence.

Corrections get new commits.

## 14. A phase is not complete until it has a report

Each completed phase should leave:

* source changes;
* tests;
* raw evidence;
* derived data;
* human-readable report;
* git commit;
* session-index entry.

Do not leave conclusions only in terminal history.

## 15. Stop at prompt boundaries

Do not automatically begin a new major project phase simply because the current one completed early.

Only execute phases explicitly authorized by the active session prompt.

## 16. End-of-session checklist

Before stopping:

* run all required regression tests;
* verify source repos unchanged;
* update session index;
* record latest commit;
* record working-tree status;
* ensure all reports exist;
* state the next recommended step.

## 17. Principle

The repository must allow another person to reconstruct:

> what was believed before the experiment, what was run, what failed, what changed, and why the final conclusion is justified.

If that history cannot be reconstructed, the work is not finished.
