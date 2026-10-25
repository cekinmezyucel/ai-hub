# ai-hub

> From PRD to production with AI agents: reusable skills, human gates if necessary, verified output.

## Goal

Take a feature from a written PRD to a deployed and verified service, A to Z.
AI agents do the steps where they help.

**North star: no human bottleneck.** A human gate stays only where it is necessary.
When the evidence shows a step is safe without a human, the gate goes.

Built in the open and from scratch, to show how an AI-driven SDLC works in practice:
specs, agents, evals, MCP and sandboxing.

## How it works

**Pattern:** a workflow on the outside, one agent on the inside.
Only `implement` is agentic. Everything else is a fixed step. Gates start closed and open as trust grows.

```
1. prd        idea or Issue -> PRD Issue         human + skill   [gate if necessary]
2. spec       PRD Issue -> spec.md               skill
3. plan       spec.md -> plan.md                 skill           [gate if necessary]
4. implement  plan.md -> commits + draft PR      the only agent, in a sandbox
5. verify     PR + spec.md -> verify report      skill           fail: back to 4 (max N loops)
6. review     PR -> report, PR ready, then merge skill           fail: back to 4 [gate if necessary]
7. deploy     merge -> running service           CI/CD, no AI
8. check      service + spec.md -> check report  skill
```

One name per step: the step, the skill folder, the command, the file it writes and the
`step=` value in its report are all the same word. All terms are in the [glossary](docs/glossary.md).

## Steps are skills

Every step except `deploy` is a standalone skill (one Markdown file) with a clear input and output.
A skill is usable on its own, outside the pipeline. The pipeline only chains them.
Steps hand over only through files and Issue/PR comments, never through chat memory.
Every step ends with one report comment that starts with a marker the pipeline can read:
`<!-- ai-hub step=<step> feature=<feature key> verdict=pass|fail|blocked -->`.

Skills are app-agnostic. They read app facts (test command, structure) from the target repo,
and all apply the same [engineering principles](docs/engineering-principles.md).

```
skills/<step>/SKILL.md                 <- the real product
  prd        idea or Issue  -> PRD Issue
  spec       PRD Issue      -> docs/features/<feature key>/spec.md
  plan       spec.md        -> docs/features/<feature key>/plan.md
  implement  plan.md        -> commits on feature/<feature key> + PR
  verify     PR + spec.md   -> verify report (PR comment)
  review     PR             -> review report (PR comment)
  check      spec.md        -> check report (PRD Issue comment)

Who calls them:
  v0  a human, by hand in Claude Code
  v1  GitHub Actions (claude -p)    same skills, chained
  v2  own harness (Agent SDK)       same skills, loaded from files
```

v0, by hand: this repo is a Claude Code plugin and its own marketplace. Install it once:

```
/plugin install ai-hub --marketplace cekinmezyucel/ai-hub
```

Update after a push with `claude plugin update ai-hub@ai-hub`.
While editing the skills, use the live copy instead: `claude --plugin-dir <path-to-ai-hub>`.

Then, in the target repo:

```
/ai-hub:prd <idea>       # opens PRD Issue #12
/ai-hub:prd 12           # refine: old or blocked Issue #12 becomes a PRD
/ai-hub:spec 12          # feature key 12-<slug>, branch feature/12-<slug>
/ai-hub:plan 12
/ai-hub:implement 12     # opens PR #13
/ai-hub:verify 13        # fail: /ai-hub:implement 13, then verify again
/ai-hub:review 13        # pass: PR ready; merge; CI/CD deploys
/ai-hub:check 12
```

v1, by hand with the runner: one step per run, as a fresh headless `claude -p`.
Tools, turn caps and the plugin version come from [`runner/config.toml`](runner/config.toml).

```
/ai-hub:run 12                       # in a chat in the target repo: starts the runner below, reports where it stopped
/ai-hub:run 12 --step spec           # one step only
```

The command only starts the runner; every step still runs as its own `claude -p`. Without Claude Code:

```
python3 runner/run.py 12 --repo <path-to-target-repo>              # chain until done, blocked or a gate
python3 runner/run.py 12 --step spec --repo <path-to-target-repo>  # one step only
python3 -m unittest discover -s runner     # runner tests
```

## Roadmap

- **v0 – walking skeleton, manual mode.** One PRD becomes a deployed feature on a small demo service.
  Every step runs by hand with the skills. Every step works end to end; none of them well yet.
- **v1 – automate the chain.** GitHub Actions calls the same skills headless. The runner is a disposable sandbox.
- **Then replace one part per round with own code:**
  1. Verify step: tests, LLM judge, tracing and a small eval suite
  2. Own harness with the Claude Agent SDK instead of Claude Code
  3. MCP server in Python (Streamable HTTP) for PRD/ADR knowledge
  4. PRD/spec template as a team standard
  5. Stronger sandbox

  Open after v0: own session store and sandbox, or a managed service?

## Design principles

1. **Start simple.** Fixed workflow by default; agentic only where the steps can't be known in advance.
   Add complexity only when the eval suite shows it helps.
   ([Building effective agents](https://www.anthropic.com/engineering/building-effective-agents))
2. **Context is a budget.** Smallest set of high-signal tokens; few, non-overlapping tools; just-in-time retrieval.
   ([Effective context engineering](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents))
3. **Separate brain, hands and memory.** Harness, sandbox and session log sit behind stable interfaces and can be replaced.
   The sandbox is cattle. Credentials never enter it.
   ([Scaling Managed Agents](https://www.anthropic.com/engineering/managed-agents))
4. **MCP over Streamable HTTP**, stateless. Validate `Origin`, bind to `127.0.0.1` locally, auth before any deployment.
   ([MCP transports](https://modelcontextprotocol.io/specification/latest/basic/transports))
5. **Grade the outcome, not the path.** Code graders first, LLM judge second, read the transcripts. Report pass@1 and pass^3.
   ([Demystifying evals](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents))
6. **No secrets in this repo.** No key files (OIDC), GitHub push protection, a secret scan in CI, a local hook.
   A pushed secret counts as leaked: rotate first.
7. **Human gates only where necessary.** A gate is removed by evidence, not by hope: the verify step passes,
   the eval suite shows the step is consistent (pass^k), and the change is low risk. Every skipped gate stays visible in the log.
8. **Token economy.** Tests on every run, the LLM judge only after tests pass, the full eval suite only when prompts, model,
   harness or tools change. Every run has a turn cap.

## Stack

- Python first (MCP server, harness, evals).
- Claude-first, behind a swappable interface.
- GitHub (Issues, PRs, Actions) as the session log and the first sandbox.

## Status

Early. Planning and decisions happen in [Issues](https://github.com/cekinmezyucel/ai-hub/issues).
Architecture decisions will live in `docs/adr/`.
