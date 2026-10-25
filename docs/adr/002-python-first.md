# ADR-002: Python first

Status: **Accepted**
Date: 2026-10-25 · Issues: #4, #2

## Context

ai-hub will have code in several parts: the runner (today), an MCP server, an own harness on the
Claude Agent SDK, and an eval suite. One person builds it. Every extra language costs setup, CI,
tooling and attention. The demo app (#2) should use the same language, so one toolchain covers both.

## Options

| Option | For | Against |
|--------|-----|---------|
| **A. Python** | Tier 1 [MCP SDK](https://modelcontextprotocol.io/docs/sdk). Claude Agent SDK. Most eval and data tools. Runs everywhere without a build step. | Weaker typing; packaging needs care. |
| B. TypeScript | Tier 1 MCP SDK; Claude Agent SDK; strong typing. | Fewer eval and data tools; a build step. |
| C. Java | Common at work; an MCP SDK exists. | Heavier setup for small tools and scripts. |
| D. Rust | Fast, safe. | Slow to write; small AI tooling ecosystem. Not needed for this load. |

## Decision

Python for the runner, the MCP server, the harness and the evals. The demo app is Python too
(FastAPI + pytest).

- The runner uses the standard library only (`tomllib`, so Python 3.11+). No install step.
- A part that needs packages gets its own `pyproject.toml` when it starts.
- Java stays an option for a second MCP server, to compare SDKs. Rust: not now.

## Consequences

- One language, one test style, one CI setup for all parts.
- Skills stay language-agnostic: they read the target repo's own commands (P-4). A target repo in
  another language works without a change to ai-hub.
- A move away from Python needs a new ADR.
