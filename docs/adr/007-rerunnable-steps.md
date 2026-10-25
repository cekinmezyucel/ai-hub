# ADR-007: Rerunnable steps: cattle steps, GitHub as the session log

Status: **Accepted** (2026-10-26)
Date: 2026-10-22 · Issues: #15 (split from #7; [design notes](https://github.com/cekinmezyucel/ai-hub/issues/15#issuecomment-6404893740)) · Related: [ADR-004](004-github-session-log-actions-sandbox.md), [ADR-005](005-step-interface.md), #9, #13, #18

## Context

A feature moves through the steps `spec` → `plan` → `implement` → `verify` → `review` → `check`.
Each step must be safe to run again, alone or as part of the whole chain, after a crash or a fix.

The runs in #7 showed what breaks today:

- `implement` committed T-1 and T-2, then could not open the PR. Its PR body lived only in a temp file
  on the laptop, so it was lost when the run ended.
- A rerun of `implement` has no rule for work that is already done. It would start again at T-1.
- `implement` pushes only at the end. A crash after T-1 leaves the commit only in the local checkout.

[Scaling Managed Agents](https://www.anthropic.com/research/managed-agents) (Anthropic, 2026) solves the
same problem with "cattle, not pets": the harness and the container can be thrown away, because the
session log outside them is durable.

## Options

| Option | For | Against |
|--------|-----|---------|
| **A. Own small runner, GitHub as the session log** | No new state store. Same state for a manual and an Actions run. Small. | We build skip and resume ourselves. |
| B. Durable engine (Temporal, DBOS, Restate, LangGraph) | Replay, retries, checkpoints built in. | Its own server or database copies what GitHub already holds. Too heavy for one person. |
| C. GitHub Actions only, now | `needs`, `concurrency`, re-run for free. | No manual runs to learn and debug the flow first (#7 design rule). |
| D. All-or-nothing steps, no skip | Simplest. | Throws away finished work on every rerun; ignores the log. |

## Decision

Option A.

1. **Everything that runs is cattle.** `claude -p`, `run.py`, the checkout and the temp dir can be thrown
   away. Each step run works in a fresh clone. A failed run is run again, never fixed by hand.
2. **GitHub is the only durable state:** report markers on the Issue and PR, and commits on the remote
   feature branch. A step reads its state only from there, and the runner decides only from there.
   Transcripts and traces are for humans (#13, #11), never an input to a decision.
3. **A result counts only once it is on GitHub.** Push after each commit; post the report when the step ends.
4. **One rerun rule for every step:** make only the outputs that are missing (ADR-005 section 11).
   We restart a step and skip finished work; we do not resume its conversation (that is #18).
5. **Each report names its input.** The runner walks the steps in order and runs the first one whose report
   is missing or stale, like a Kubernetes controller. Stale steps rerun on their own only inside the
   `implement` ↔ `verify` / `review` loop; a stale step before `implement` stops the chain for a human.
6. **Keep it simple.** Three verdicts (`pass`, `fail`, `blocked`), no `warn`. Steps run one after the other.
   The agent keeps writing to GitHub until its token leaves the sandbox (#9).

## Consequences

- A whole-chain rerun is cheap: finished steps skip.
- Every skill names its input in the marker and pushes early. Skills get a few more lines.
- Idempotent means "safe to rerun, ends in the same state", not "same output": an LLM writes different
  text each time. That is why staleness is judged on the input, not the output.
- A human's change upstream (the PRD, `spec.md`) never cascades on its own; a human reruns from there.
- GitHub is enough to rerun, not to learn why a step failed: transcripts are #13.
- Two runs on one feature at the same time could duplicate a report: Actions needs a lock per feature (#6).
