---
name: check
description: Step 8 of ai-hub. After deploy, run safe smoke checks against the running service for each acceptance criterion in spec.md, and post a pass/fail check report on the PRD Issue. Use when given a feature key or PRD Issue number to check in production.
---

# check: running service + spec.md → check report

Step 8 of 8. Runs after `deploy`. Answers one question: does the feature work where users are?
It changes nothing: no code, no config, no data it did not create.

Words follow `../../docs/glossary.md` (relative to this skill's folder).

## Input

- The feature key or the PRD Issue number.
- The base URL of the running service. If not given, look in `README`, `CLAUDE.md` / `AGENTS.md`
  and the deploy workflow. Not found ⇒ verdict `blocked`.

## Output

- One report on the PRD Issue.

## Steps

1. Read `../../docs/engineering-principles.md`. Cite principles by ID.
2. Read `spec.md` from the feature folder on the default branch (the feature is merged).
3. Confirm the deployed version contains the merge: use a version or health endpoint if the service has one.
   If you cannot confirm it, say so in the report.
4. For each `AC-n`, decide if it is safe to check live (see rules). If yes, run the smallest request
   that shows the **Then** part, and record the request and the response lines that matter.
5. Post the report: `gh issue comment <issue> --body-file <file>`.

## Rules

- **Production is not a test bed.** Prefer read-only requests.
  Write requests only when `spec.md` or `plan.md` names safe test data; delete what you created.
- No load tests. No real user data. No guessing endpoints that are not in the contract.
- Credentials come from the environment. Never print them (P-6).
- An `AC-n` that is not safe to check live is `not checked`, with the reason. It does not fail the check.
- **Verdict:** `pass` when every checked `AC-n` passes and at least one was checked.
  `fail` when any checked `AC-n` fails: a human decides on rollback or a new feature.
  `blocked` when the service cannot be reached or the base URL is unknown.

## Done when

- Every `AC-n` is `pass`, `fail` or `not checked`, with evidence or a reason.
- All test data you created is deleted.
- The report is posted.

## Report

```markdown
<!-- ai-hub step=check feature=<feature key> verdict=pass|fail|blocked -->
## check · pass | fail | blocked

Service: <base URL> · Version: <version, or "not confirmed">

| AC   | Result      | Evidence |
|------|-------------|----------|
| AC-1 | pass        | `GET /…` → 200, body has … |
| AC-2 | not checked | writes data, no safe test data |
```
