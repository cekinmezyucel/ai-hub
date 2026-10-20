# Glossary

The shared language of ai-hub. Skills, commands, files, comments and docs use only these words.
If a new term is needed, add it here first.

## The sequence

| # | Step        | Command             | Input → output                                   | Done by |
|---|-------------|---------------------|--------------------------------------------------|---------|
| 1 | `prd`       | `/ai-hub:prd`       | idea → PRD Issue                                 | human + skill |
| 2 | `spec`      | `/ai-hub:spec`      | PRD Issue → `spec.md`                            | skill |
| 3 | `plan`      | `/ai-hub:plan`      | `spec.md` → `plan.md`                            | skill |
| 4 | `implement` | `/ai-hub:implement` | `plan.md` → commits + PR                         | agent |
| 5 | `verify`    | `/ai-hub:verify`    | PR + `spec.md` → verify report                   | skill |
| 6 | `review`    | `/ai-hub:review`    | PR → review report, then merge                   | skill + gate |
| 7 | `deploy`    | –                   | merge → running service                          | CI/CD, no AI |
| 8 | `check`     | `/ai-hub:check`     | running service + `spec.md` → check report       | skill |

A `fail` from `verify` or `review` goes back to `implement`.

## Terms

| Term | Meaning |
|------|---------|
| **target repo** | The repo a feature is built in. Not ai-hub. |
| **feature** | One PRD and everything built for it. |
| **feature key** | `<issue>-<slug>`, for example `12-bookmark-tags`. `<issue>` is the PRD Issue number. `<slug>` is 2–5 lowercase words from the Issue title, joined with `-`. Set once by `spec`, never changed. |
| **feature branch** | `feature/<feature key>`. All commits of one feature. |
| **feature folder** | `docs/features/<feature key>/` in the target repo. Holds `spec.md` and `plan.md`. |
| **step** | One stage of the sequence. Its name is also the skill name, the command name and the `step=` value. |
| **skill** | The instructions for one step: `skills/<step>/SKILL.md`. Usable alone, outside the pipeline. |
| **pipeline** | Runs the steps in order. Only orchestrates; holds no step logic. |
| **PRD** | Product requirements: the why and what, from the user's view. Lives as the PRD Issue. |
| **spec** | The testable what: scope, acceptance criteria, contract. File `spec.md`. |
| **plan** | The how: commands, tasks, traceability. File `plan.md`. |
| **contract** | The public interface of a feature: endpoints, data shapes, errors, CLI flags, config keys. |
| **report** | The one comment each step posts when it ends. Starts with a marker. |
| **marker** | First line of every report: `<!-- ai-hub step=<step> feature=<feature key> verdict=<verdict> -->`. Lets the pipeline read the result. |
| **verdict** | The result of a step: `pass` (next step may run), `fail` (go back to `implement`), `blocked` (a human must answer first). |
| **done when** | The list at the end of each skill, and in each task of `plan.md`. Every item must be true before the step posts its report. |
| **done** | A step is done when its "Done when" list is true and its report is posted; the verdict then says what comes next. A feature is done when `check` posts `pass` on the PRD Issue. |
| **gate** | A point where a human must approve before the next step. Removed only by evidence (README principle 7). |
| **loop** | `implement` → `verify` (→ `review`) and back on `fail`. The pipeline caps the number of loops. |
| **risk** | `low`, `medium` or `high`. Set by `plan`. Gates use it. |
| **evidence** | What backs a claim: a command with its result, a test name, or a `file:line`. |

## IDs

| ID     | Meaning | Defined in |
|--------|---------|------------|
| `AC-n` | Acceptance criterion | `spec.md` |
| `A-n`  | Assumption | `spec.md` |
| `Q-n`  | Open question | `spec.md` |
| `T-n`  | Task | `plan.md` |
| `P-n`  | Engineering principle | [engineering-principles.md](engineering-principles.md) |
