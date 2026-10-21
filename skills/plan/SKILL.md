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

## Stop rules

The same in a chat and in a headless run (`claude -p`).

- **Never ask and wait.** If you need a human answer to go on, end with verdict `blocked`
  and put the question in the report.
- **Stop after the report.** Do not offer, suggest or start the next step. The caller chains the steps.

## Done when

- Every `AC-n` in the spec is in the traceability table with at least one task and one test.
- Every task covers at least one `AC-n`, or names the principle that needs it.
- Every command has a "Found in" source, or is `unknown`.
- The risk follows the rules above.

## Links and labels

The PRD Issue is where a human navigates from. The same rules in every step.

- In the report, write each file as a link to it on its branch:
  `[<path>](https://github.com/<owner>/<repo>/blob/<branch>/<path>)`, with `#L<n>` for a line.
  Write a PR as `#<pr>` and a CI run as its URL. Commit SHAs link by themselves.
- After posting, set the `blocked` label on the PRD Issue: verdict `blocked` ⇒
  `gh issue edit <issue> --add-label blocked`, any other verdict ⇒ `--remove-label blocked` if it is there.
  If the repo has no such label, create it first:
  `gh label create blocked --color B60205 --description "ai-hub: a human must answer"`.
- On `pass`, also set the risk label: `gh issue edit <issue> --add-label "risk: <level>"`, and remove
  any other `risk: …` label. Create it first if missing (low `0E8A16`, medium `FBCA04`, high `B60205`).

## Report

```markdown
<!-- ai-hub step=plan feature=<feature key> verdict=pass|blocked risk=low|medium|high -->
**plan** · pass | blocked · [plan.md](<link>) · <n> tasks · risk <level>

<if blocked: what a human must provide>
```
