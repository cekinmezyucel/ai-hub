---
name: check
description: Step 8 of ai-hub. After deploy, check each acceptance criterion in spec.md against the running service - with safe live requests, or by reading the smoke check job when the service runs inside CI - and post a pass/fail check report on the PRD Issue. Use when given a feature key or PRD Issue number to check in production.
---

# check: running service + spec.md → check report

Step 8 of 8. Runs after `deploy`. Answers one question: does the feature work where users are?
It changes nothing: no code, no config, no data it did not create.

Words follow `../../docs/glossary.md` (relative to this skill's folder).

## Input

- The feature key or the PRD Issue number.
- Where production is. Look in `README`, `CLAUDE.md` / `AGENTS.md` and the deploy workflow. One of:
  - **Hosted:** the base URL of the running service.
  - **In CI:** the service runs only inside a CI job that starts it and runs smoke checks against it.
    You need the workflow and job name.
  - Not found ⇒ verdict `blocked`.

## Output

- One report on the PRD Issue.

## Steps

1. Read `../../docs/engineering-principles.md`. Cite principles by ID.
2. Read `spec.md` from the feature folder on the default branch (the feature is merged).
3. Confirm production runs the merge:
   - Hosted: use a version or health endpoint if the service has one.
   - In CI: find the run of the smoke check job for the merge commit
     (`gh run list --workflow <file> --commit <full sha>`). It must be `completed`.
   - If you cannot confirm it, say so in the report.
4. Check each `AC-n`:
   - Hosted: decide if it is safe to check live (see rules). If yes, run the smallest request
     that shows the **Then** part, and record the request and the response lines that matter.
   - In CI: read the smoke check log (`gh run view <run id> --log --job <job id>`). Find the smoke test
     for this `AC-n` by the repo's naming rule, and record its name and result. No smoke test ⇒ `not checked`.
5. Post the report: `gh issue comment <issue> --body-file <file>`.

## Rules

- **Production is not a test bed.** Prefer read-only requests.
  Write requests only when `spec.md` or `plan.md` names safe test data; delete what you created.
- No load tests. No real user data. No guessing endpoints that are not in the contract.
- Credentials come from the environment. Never print them (P-6).
- An `AC-n` that is not safe to check live, or has no smoke test, is `not checked`, with the reason.
  It does not fail the check.
- In CI, a smoke test counts only if it ran against the started service in the smoke check job.
  Unit test results are `verify` evidence, not `check` evidence.
- **Verdict:** `pass` when every checked `AC-n` passes and at least one was checked.
  `fail` when any checked `AC-n` fails: a human decides on rollback or a new feature.
  `blocked` when the service cannot be reached, production is unknown, or the smoke check job did not run.

## Stop rules

The same in a chat and in a headless run (`claude -p`).

- **Never ask and wait.** If you need a human answer to go on, end with verdict `blocked`
  and put the question in the report.
- **Stop after the report.** Do not offer, suggest or start the next step. The caller chains the steps.

## Done when

- Every `AC-n` is `pass`, `fail` or `not checked`, with evidence or a reason.
- All test data you created is deleted.
- The report is posted.

## Report

```markdown
<!-- ai-hub step=check feature=<feature key> verdict=pass|fail|blocked -->
## check · pass | fail | blocked

Service: <base URL, or CI run URL> · Version: <version or commit, or "not confirmed">

| AC   | Result      | Evidence |
|------|-------------|----------|
| AC-1 | pass        | `GET /…` → 200, body has … |
| AC-2 | pass        | `smoke/test_12_link_expiry.py::test_ac_2_expired_link_returns_410` PASSED |
| AC-3 | not checked | writes data, no safe test data |
```
