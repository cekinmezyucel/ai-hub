# ADR-006: Secret protection in layers

Status: **Accepted**
Date: 2026-10-25 · Issues: #3, #4 · Related: #9 (sandbox and credentials), [SECURITY.md](../../SECURITY.md)

## Context

ai-hub and ai-hub-demo are public. Neither holds a secret today, and the demo app needs none.
A secret can still get in: a human pastes a token into a file, or an agent step writes one into a
commit, a PR comment or a CI log. Agent steps run with real credentials (the `gh` token of the person
who runs them, later `GITHUB_TOKEN` and `ANTHROPIC_API_KEY` in Actions).

Pushed means leaked. So the layers must stop a secret before the push, and catch it after the push
when an earlier layer was skipped.

## Options

**CI scan**

| Option | For | Against |
|--------|-----|---------|
| A. gitleaks binary, version and SHA-256 pinned | Strongest supply-chain guard; MIT license. | We bump it by hand, or build a bump bot. |
| B. A bot opens a PR for each new gitleaks release | Pinned and current. | Needs the "Actions can create PRs" setting and one more workflow to maintain. |
| **C. `gitleaks/gitleaks-action@v3`** | Nothing to maintain: each action release brings its gitleaks version. Comments on the PR line. No key for a personal account. | The `@v3` tag can move; the action has its own license since v2. |

**Sharing between repos**

| Option | For | Against |
|--------|-----|---------|
| A. One reusable workflow in ai-hub, called with `uses: …@main` | One place to change. | Demo CI depends on ai-hub `main`; permissions must match on both sides. With option C there is almost nothing left to share. |
| **B. Each repo has its own small `gitleaks.yml`** | Readable alone, no cross-repo break. | A copy per repo (about 20 lines). |

**Local hook**

| Option | For | Against |
|--------|-----|---------|
| A. `pre-commit` framework | Common. | A Python tool to install in every repo; its gitleaks hook needs Go or Docker. |
| B. Global `core.hooksPath` | One setup for every repo on the machine. | Turns off the hooks of all other repos (husky at work). |
| **C. `.githooks/pre-commit` in the repo + `core.hooksPath .githooks`** | No extra tool. One hooks dir for every branch and worktree of a clone. | Set once per clone; a fresh clone has no hook. |

## Decision

Five layers, strongest first:

| # | Layer | What | Can be skipped? |
|---|-------|------|-----------------|
| 1 | No secrets exist | No deploy keys: the app runs inside Actions. A real host later deploys with OIDC. Runtime secrets only in Actions secrets | Nothing to leak |
| 2 | GitHub push protection | Secret scanning and push protection on, in both repos | No (server side) |
| 3 | CI scan | `gitleaks.yml` with `gitleaks-action@v3` on every PR and push to `main`, full history. Required check `gitleaks` on ai-hub-demo `main` (ruleset, admin bypass) | No, for PR merges |
| 4 | Local hook | `.githooks/pre-commit` runs `gitleaks git --pre-commit --staged`; it blocks the commit when gitleaks is missing | Yes (`--no-verify`) |
| 5 | Agent limits | `.claude/settings.json` denies `Read(**/.env*)`. Runner steps may not read `.env*` with Bash or commit with `--no-verify` / `-n` | Only by a human |

The leak plan is in [SECURITY.md](../../SECURITY.md): rotate first, rewrite history second.

No template repo yet. A new target repo copies `gitleaks.yml`, `.githooks/pre-commit` and
`.claude/settings.json`. When a third repo comes, a `/ai-hub:setup` skill can write them.

## Consequences

- No version to maintain. A new gitleaks rule can fail CI one day on old history; then we add an
  allowlist entry or fix the finding.
- In ai-hub we push straight to `main`, so the CI scan only reports after the push. There, layers 2
  and 4 are the ones that block.
- The hook needs `git config core.hooksPath .githooks` once per clone, and `brew install gitleaks`.
  A branch made from a commit before the hook existed has no hook; layer 3 covers it.
- The agent denies are prefix rules. They stop mistakes, not a determined agent. Taking real
  credentials out of the agent's reach is #9.
- An organization repo needs a free `GITLEAKS_LICENSE` key from gitleaks.io for the action.
