# ai-hub

> From PRD to production with AI agents: reusable skills, human gates, verified output.

## Goal

Take a feature from a written PRD to a deployed and verified service, A to Z.
AI agents do the steps where they help. A human makes the decisions.

Built in the open and from scratch, to show how an AI-driven SDLC works in practice:
specs, agents, evals, MCP and sandboxing.

## How it works

**Pattern:** a workflow on the outside, one agent on the inside.
Only the coding step is agentic. Everything else is a fixed step with a human gate.

```
1. PRD          a human writes it                 [gate: approve]
2. Plan         LLM: PRD -> spec + tasks          [gate: approve]
3. Code         agent in a sandbox                <- the only agent
4. Verify       tests + LLM judge vs PRD criteria -> back to 3 (max N loops)
5. PR           a human reviews and merges        [gate]
6. Deploy       normal CI/CD, no AI
7. Prod check   smoke test vs acceptance criteria
```

## Steps are skills

Each step is a standalone skill (one Markdown file) with a clear input and output.
A skill is usable on its own, outside the pipeline. The pipeline only chains them.
Steps hand over only through files and Issue/PR comments, never through chat memory.

```
skills/ (one Markdown file per step)   <- the real product
  spec    : PRD Issue  -> spec.md
  plan    : spec.md    -> plan.md
  review  : PR diff    -> review comment
  verify  : PR + spec  -> pass/fail report

Who calls them:
  v0  a human, by hand in Claude Code
  v1  GitHub Actions (claude -p)    same skills, chained
  v2  own harness (Agent SDK)       same skills, loaded from files
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
7. **Token economy.** Tests on every run, the LLM judge only after tests pass, the full eval suite only when prompts, model,
   harness or tools change. Every run has a turn cap.

## Stack

- Python first (MCP server, harness, evals).
- Claude-first, behind a swappable interface.
- GitHub (Issues, PRs, Actions) as the session log and the first sandbox.

## Status

Early. Planning and decisions happen in [Issues](https://github.com/cekinmezyucel/ai-hub/issues).
Architecture decisions will live in `docs/adr/`.
