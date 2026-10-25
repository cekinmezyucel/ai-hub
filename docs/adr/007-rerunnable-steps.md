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
5. **Skip:** the marker names the step's input, e.g. `step=verify input=<head sha>`. The runner skips a
   step whose marker for the same input exists. `--force` runs it again.
6. **Resume:** a rerun continues from what GitHub shows. For `implement`: a task with a `T-n:` commit on
   the remote branch is done; an open PR for the branch is reused.
7. **One step manifest,** shaped like a GitHub Actions job, so each step can become one Actions job later (#6):

   ```yaml
   verify:
     skill: ai-hub:verify
     needs: [implement]
     skip_key: pr.head_sha
     on_failure: block          # or warn
     loop: {with: implement, max: 3}
     tools: [...]
     caps: {max_turns: 60, max_budget_usd: 2}
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

1. **Resume or restart, per step.** `implement` is long, so resume pays off. `spec`, `plan`, `verify`, `review`
   write one thing each: maybe all-or-nothing is simpler and safer for them.
2. **The input of each step.** What is the skip key: `spec` (Issue body and answers? `updatedAt`?),
   `plan` (blob SHA of `spec.md`), `implement` (blob SHA of `plan.md`), `verify` / `review` (PR head SHA),
   `check` (merge commit and smoke run)? What happens when a human edits the Issue later?
3. **Detecting a finished task reliably.** Commit subject `T-n:` or a `Task: T-n` trailer? What if the
   commit exists but its tests now fail? Explicit commands, not the agent's judgement.
4. **Where the manifest lives and its format.** In ai-hub or in the target repo? YAML or TOML?
   How exactly does it map to Actions jobs or a gh-aw workflow?
5. **What `warn` means per step.** Which findings are a warning, and who reads them later?
6. **Parallel `verify` and `review`.** A lock per feature; how `implement` takes two `fail` reports at once.
7. **Who writes to GitHub: the agent or the runner** ("safe outputs"). Ties to #9 and to org policies
   such as "ask before `gh pr create`".
8. **A fresh clone per run** instead of the local checkout (#9).
9. **Is GitHub a rich enough log?** Managed Agents logs every event; we keep only reports and commits.
   Transcripts are #13.
