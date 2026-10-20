---
name: plan
description: Step 3 of ai-hub. Turn spec.md into plan.md - the repo's test and lint commands, small ordered tasks each with a test first, traceability to acceptance criteria, and a risk level. Use when given a feature key or PRD Issue number to plan.
---

# plan: spec.md → plan.md

Step 3 of 8. Says **how** to build the spec, in tasks that `implement` can follow without asking.

Words follow `../../docs/glossary.md` (relative to this skill's folder).

## Input

- The feature key or the PRD Issue number. `spec.md` is in the feature folder on the feature branch.

## Output

- `plan.md` in the feature folder, committed on the feature branch.
- One report on the PRD Issue.

## Steps

1. Read `../../docs/engineering-principles.md`. Cite principles by ID.
2. Switch to the feature branch. Read `spec.md`.
   If its verdict is `blocked`, stop and say so. Do not plan around blocking questions.
3. Explore the target repo:
   - The code the spec touches, and the closest existing feature that looks similar.
   - The test, lint and run commands. Look in CI workflows first, then `Makefile`,
     `pyproject.toml`, `package.json`, `CLAUDE.md` / `AGENTS.md`, `README`.
4. Write `plan.md` with the template below.
5. Check the "Done when" list. Fix the plan until every item is true.
6. Commit (`plan: <feature key>`) and push.
7. Post the report: `gh issue comment <issue> --body-file <file>`.

## Rules

- **Commands are facts, not guesses.** Write only commands you found in the repo, with the file you found them in.
  No test command found ⇒ write `unknown` and the verdict is `blocked`: `verify` cannot work without it.
- **Small tasks (P-13).** One task = one sitting, leaves the repo green, could ship alone.
  Prefer vertical slices (one behaviour end to end) over layers (all models, then all routes).
- **Test first (P-3).** Each task names the test that is written first and what it asserts.
- **Smoke checks.** If the repo has smoke checks that run against production (for example `smoke/`),
  each `AC-n` that is safe to check live gets one, following the repo's naming rule. `check` reads them.
- **Copy existing patterns (P-4).** For each new file, name the existing file whose pattern it follows.
- **No scope creep (P-2).** No task outside the spec. Refactor only when a task needs it, and say why.
- **Risk:**
  - `high`: auth, permissions, payments, deletes, data migrations, secrets handling, breaking the contract.
  - `medium`: new contract (endpoint, config key), new dependency, schema change without data loss.
  - `low`: everything else.

## Template

```markdown
# Plan: <title>

Feature: <feature key> · Spec: ./spec.md · Risk: low | medium | high — <one-line reason> · Verdict: pass | blocked

## Commands
| Purpose | Command | Found in |
|---------|---------|----------|
| test    | `…`     | `.github/workflows/ci.yml` |
| lint    | `…`     | … |
| run     | `…`     | … |

## Approach
<3–6 lines: key decisions, and one alternative you rejected and why>

## Tasks
### T-1 <short title>
- Covers: AC-1, AC-2
- Files: `path` (new | change) — pattern from `path`
- Test first: `<test file>` — asserts …
- Done when: …

### T-2 …

## Traceability
| AC   | Tasks | Tests |
|------|-------|-------|
| AC-1 | T-1   | `tests/…::test_…` |

## Risks and rollback
- …
```

## Done when

- Every `AC-n` in the spec is in the traceability table with at least one task and one test.
- Every task covers at least one `AC-n`, or names the principle that needs it.
- Every command has a "Found in" source, or is `unknown`.
- The risk follows the rules above.

## Report

```markdown
<!-- ai-hub step=plan feature=<feature key> verdict=pass|blocked risk=low|medium|high -->
**plan** · pass | blocked · `docs/features/<feature key>/plan.md` · <n> tasks · risk <level>

<if blocked: what a human must provide>
```
