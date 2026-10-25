# ADR-007: Rerunnable steps: cattle steps, GitHub as the session log

Status: **Proposed** — the direction is agreed, the details need investigation (see the end).
Date: 2026-10-22 · Issues: #15 (split from #7) · Related: #4, #6, #9, #13

## Context

A feature moves through the steps `spec` → `plan` → `implement` → `verify` → `review` → `check`.
They should behave like the jobs of a GitHub Actions workflow: serial or parallel, dependent on
earlier steps, blocking or warning only, and rerunnable alone or as a whole workflow.

The runs in #7 showed what breaks today:

- `implement` committed T-1 and T-2, then could not open the PR. Its PR body lived only in a temp file
  on the laptop, so it was lost when the run ended.
- A rerun of `implement` has no rule for work that is already done. It would start again at T-1.
- `implement` pushes only at the end. A crash after T-1 leaves the commit only in the local checkout.

[Scaling Managed Agents](https://www.anthropic.com/research/managed-agents) (Anthropic, 2026) solves the
same problem with "cattle, not pets": the harness and the container can be thrown away, because the
session log outside them is durable. A new harness calls `wake(sessionId)`, reads the log and
"resume[s] from the last event".

## Options

| Option | For | Against |
|--------|-----|---------|
| **A. Own small runner, GitHub as the session log** | No new state store. Same state for a manual and an Actions run. Small. | We build skip and resume ourselves. |
| B. Durable engine (Temporal, DBOS, Restate, LangGraph) | Replay, retries, checkpoints built in. | Its own server or database copies what GitHub already holds. Too heavy for one person. |
| C. GitHub Actions only, now | `needs`, `concurrency`, re-run for free. | No manual runs to learn and debug the flow first (#7 design rule). |
| D. All-or-nothing steps, no skip | Simplest. | Throws away finished work on every rerun; ignores the log. |

How others solve it (research, 2026-10-22):
GitHub Actions (`needs`, `if`, `continue-on-error`, re-run failed jobs),
Prefect / Dagster / Nx / Bazel (skip when the hash of the inputs is the same),
Temporal / Inngest / DBOS (a log of finished steps; a rerun gets the saved result),
Tekton (`runAfter`, `when`, `onError: continue`), LangGraph / Mastra (checkpoint, resume, interrupt for a human),
Kubernetes controllers (observe, then change only what differs),
[gh-aw](https://github.github.com/gh-aw/reference/safe-outputs/) (the agent is read-only; a separate job writes).

## Decision (proposed)

Option A.

1. **Everything that runs is cattle.** Each `claude -p`, `run.py`, the checkout and the temp dir can be
   thrown away. A failed run is run again, never fixed by hand.
2. **GitHub is the only durable state:** Issue and PR comments with markers, and commits on the remote
   feature branch. No pets: nothing on the laptop must survive a run.
3. **A result counts only once it is in GitHub.** Push after each task commit. Post the report as soon
   as the step ends. A file in a temp dir is not an output.
4. **A step reads its state only from GitHub,** never from the local checkout.
5. **Skip:** the marker names the step's input, e.g. `step=verify input=<head sha>`. The runner walks the
   steps in order and runs the first one whose report is missing or stale (its `input=` is not the current
   input), like a Kubernetes controller. `--force` runs a step again.
6. **Resume:** a rerun continues from what GitHub shows. For `implement`: a task with a commit on the
   remote branch whose `Task:` and `Plan:` trailers match is done (open point 3); an open PR is reused.
7. **One step manifest:** `runner/config.toml` grows. It uses the words of Actions (`needs`), not its
   format; Actions does not run one job per step (open point 4):

   ```toml
   [steps.verify]
   needs = ["implement"]
   input = "pr.head"
   max_turns = 60
   ```
8. **Four verdicts:** `pass`, `warn` (the flow goes on, like `continue-on-error`), `fail`, `blocked` (a human must answer).

## Consequences

- A whole-workflow rerun is cheap: finished steps skip.
- Every skill must name its input in the marker and push early. Skills get a few more lines.
- Idempotent means "safe to rerun, ends in the same state", not "same output": an LLM writes different
  text each time. That is why the skip key is the input, not the output.
- `runner/config.toml` turns into the manifest when chaining needs it.
- Order to build: resume in `implement` (6) and push per task (3) first, then markers with inputs and
  skip (5), then the manifest (7). Verdict `warn` and parallel steps come with gates and Actions.

## Needs investigation

These ideas are not robust yet. Each needs a closer look before the status becomes Accepted.

1. **Resume or restart, per step.** Answered (2026-10-25): one rerun rule for all steps, see
   [ADR-005](005-step-interface.md) section 11. A step makes only the missing outputs; in practice only
   `implement` skips work, the other steps run again.
2. **The input of each step.** Answered (2026-10-25): the input is a hash or SHA of exactly what the step reads.

   | Step | `input=` |
   |------|----------|
   | `spec` | sha256 of the PRD Issue body, first 12 characters (the body holds the human's answers too; not `updatedAt`, which changes on every comment) |
   | `plan` | blob SHA of `spec.md` on the remote feature branch |
   | `implement`, first run | blob SHA of `plan.md` on the remote feature branch |
   | `implement`, loop run | PR head SHA at the start of the run |
   | `verify`, `review` | PR head SHA |
   | `check` | merge commit SHA |

   - The runner computes the input with fixed commands before the run and passes it to the skill; the skill
     copies it into its marker. A skill alone in a chat runs the same command. A push during the run cannot
     mislabel the report.
   - Staleness follows the chain: a new `spec.md` makes `plan` stale; a push to the PR makes `verify` stale,
     which is also the fail loop.
   - The runner reruns a stale step on its own only inside the loop (`implement` ↔ `verify` / `review`).
     A stale step before `implement` (a human edited the PRD or `spec.md`) stops the chain with a message,
     e.g. "PRD changed after spec; run with `--force spec`". A new `plan.md` can renumber the tasks, so
     resume in `implement` would skip the wrong work.
3. **Detecting a finished task reliably.** Answered (2026-10-25):
   - The subject stays `T-n: <task title>` for humans. Each task commit also gets two git trailers:
     `Task: T-n` and `Plan: <blob SHA of plan.md>`. The subject is free text the agent writes; a trailer
     is a fixed field.
   - A task is done when `origin/feature/<key>` has a commit with `Task: T-n` and the current `Plan:`.
     One fixed command, not the agent's judgement:
     `git log origin/feature/<key> --format='%(trailers:key=Task,valueonly) %(trailers:key=Plan,valueonly)'`.
     `Plan:` ties the task to one version of the plan: after `--force plan`, the old `T-2` is not the new `T-2`.
   - A done commit is trusted, its tests are not run again: a task is committed only when green, and the
     full test and lint run at the end of `implement` catches anything broken (red → `fail` → the loop).
   - `implement` pushes after each task commit (decision 3); a commit only on the laptop does not count.
   - The skill runs the command, not the runner: only `implement` needs the task list, and the skill must
     work alone in a chat. The runner stays at report level.
   - Loop runs have no task-level resume: they are short, and a rerun takes the fail list again.
   - Gap: a crash between code and commit leaves a dirty tree; the runner stops and a human cleans it.
     A fresh clone per run (open point 8, #9) removes this.
4. **Where the manifest lives and its format.** Answered (2026-10-26):
   - **TOML, in `runner/config.toml`.** The runner is Python (ADR-002) and `tomllib` is in the standard
     library. YAML adds a dependency, only to look like Actions.
   - **Only what the walk needs now (P-2):** `needs` (replaces `NEXT_STEP` in `run.py`) and `input`, a
     name the runner maps to one function: `issue.body`, `file:spec.md`, `file:plan.md`, `pr.head`, `pr.merge`.
     `on_failure` and `loop` come with `warn` and parallel steps (open points 5 and 6).
   - **Two owners.** ai-hub owns the workflow: steps, `needs`, `input`, caps, tools, `denied`; it is
     versioned with the plugin. The target repo owns its facts: test and lint commands and their tool rules.
     The runner reads them only from the target repo's default branch, so a feature branch cannot widen its
     own permissions, and ai-hub `denied` always wins. Built when a second target repo comes; until then
     the `[repos.…]` block in `config.toml` stays.
   - **Actions: one generic job, not one job per step.** The runner walks the steps and knows `needs`.
     Actions gives a trigger (new report, push to the PR, merge), a disposable VM, and
     `concurrency: feature-<issue>` as the lock per feature. The job runs `run.py <issue> --once`; no step
     logic in the workflow YAML (#6). gh-aw is not a manifest format for us; its safe outputs are open point 7.
5. **What `warn` means per step.** Which findings are a warning, and who reads them later?
6. **Parallel `verify` and `review`.** A lock per feature; how `implement` takes two `fail` reports at once.
7. **Who writes to GitHub: the agent or the runner** ("safe outputs"). Ties to #9 and to org policies
   such as "ask before `gh pr create`".
8. **A fresh clone per run** instead of the local checkout (#9).
9. **Is GitHub a rich enough log?** Managed Agents logs every event; we keep only reports and commits.
   Transcripts are #13.
