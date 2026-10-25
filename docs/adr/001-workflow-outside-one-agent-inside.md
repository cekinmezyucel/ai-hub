# ADR-001: A workflow outside, one agent inside

Status: **Accepted**
Date: 2026-10-25 · Issue: #4 · Related: [ADR-005](005-step-interface.md), [ADR-007](007-rerunnable-steps.md)

## Context

ai-hub takes a feature from PRD to production. Most of that path is known in advance: write a spec,
plan it, build it, check it, review it, deploy it, check production. Only building the code needs
open-ended work: the agent cannot know which files to touch and which commands to run before it starts.

[Building effective agents](https://www.anthropic.com/engineering/building-effective-agents) says:
use a workflow when the steps are known, an agent when they are not, and start with the simplest one.

## Options

| Option | For | Against |
|--------|-----|---------|
| A. One agent does the whole path | Least code. | Hard to test, hard to gate, hard to rerun one part. One bad turn can spoil the rest. Large context. |
| B. Many agents: an orchestrator hands work to sub-agents | Flexible. | More moving parts and tokens; failures are hard to trace. Not needed while the path is fixed. |
| **C. A fixed workflow of steps; only `implement` is an agent** | Each step has one input, one output and a report, so it can be tested, gated and rerun alone. Context per step stays small. | The workflow must change by hand when the path changes. |

## Decision

Option C.

- The workflow is the fixed sequence `prd` → `spec` → `plan` → `implement` → `verify` → `review` →
  `deploy` → `check`. The runner chains the steps; it holds no step logic.
- `implement` is the only agent: it decides its own tool calls inside a turn cap and a tool allowlist.
- The other steps are skills with fixed steps. They use the model to write and judge, not to choose
  what to do next.
- `deploy` has no AI: it is CI/CD.
- A `fail` from `verify` or `review` goes back to `implement`, up to a loop cap. This is the only loop.
- Human gates sit between steps, start closed, and open only on evidence (README principle 7).

## Consequences

- Each step can be tested and measured alone (eval suite, #10).
- Tools are given per step (`runner/config.toml`): only `implement` gets broad write access.
- Adding agent freedom is a later choice, made only when the eval suite shows it helps.
- The step contract (input, output, report, verdicts) must be written down once: ADR-005.
