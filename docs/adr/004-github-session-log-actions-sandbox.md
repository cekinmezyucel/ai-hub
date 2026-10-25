# ADR-004: GitHub as the session log, the Actions runner as the sandbox (v1)

Status: **Accepted** · the sandbox part is confirmed or changed by #6
Date: 2026-10-25 · Issues: #4, #6 · Related: [ADR-007](007-rerunnable-steps.md), #9, #13

## Context

Each step runs as a fresh `claude -p` with no chat memory (README "Steps are skills"). So the state of
a feature must live outside the run: which steps ran, with what verdict, and their output.
A step must also run somewhere that can be thrown away, because it runs code and commands it chose.
In v0 the steps ran in a chat on a laptop; in v1 GitHub Actions runs them (#6).

## Options

**Session log: where the state of a feature lives**

| Option | For | Against |
|--------|-----|---------|
| A. Local files or a local database | Fast; any format. | Lost with the machine; a laptop run and an Actions run see different state. |
| B. A hosted store (database, durable engine) | Built for state. | A new account, cost and secret; copies what GitHub already holds. |
| **C. GitHub: Issues, PRs, comments with markers, branches** | Already there; humans read the same log; a laptop run and an Actions run see the same state. | API rate limits; comments are public; we parse markers ourselves. |

**Sandbox: where a step runs (v1)**

| Option | For | Against |
|--------|-----|---------|
| A. The laptop | Easy to debug. | Real credentials and disk; not disposable (#9). |
| **B. A GitHub Actions runner** | A fresh VM per job, thrown away after; free for public repos; the code is already there. | The job token and secrets are inside the VM; network is open by default. |
| C. Own container or sandbox runtime | Hard boundaries, network allowlist. | More to build; later (#9). |

## Decision

- **Session log: GitHub.** Each step ends with one report comment that starts with
  `<!-- ai-hub step=… feature=… verdict=… -->`. Files hand over through the feature branch.
  The runner reads only these to choose the next step. Nothing is kept on the machine between runs.
- **Sandbox, v1: the Actions runner.** One job per step, thrown away after. The laptop stays for
  manual runs and debugging, with the same runner and config.

## Consequences

- A feature can move forward by hand and by Actions, also mixed (#6).
- A step must push before it ends, or its work is lost (the runner checks this).
- The full transcript is not in GitHub; only the report is. Keeping transcripts is #13.
- The Actions runner is not a hard sandbox: the job token sits inside it. Scoped tokens and network
  limits come with #9.
- Rerun and resume rules on top of this log are ADR-007.
