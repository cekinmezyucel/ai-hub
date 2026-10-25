# ADR-003: MCP over Streamable HTTP, stateless

Status: **Accepted** · not built yet (roadmap item 3)
Date: 2026-10-25 · Issue: #4 · Related: [ADR-002](002-python-first.md)

## Context

The roadmap has an own MCP server that serves PRD and ADR knowledge to the steps. It must work for a
local chat, for the runner on a laptop, and later for steps in GitHub Actions or another host.
The [MCP transports](https://modelcontextprotocol.io/specification/latest/basic/transports) are
stdio (a local child process) and Streamable HTTP. The older HTTP+SSE transport is deprecated.

## Options

| Option | For | Against |
|--------|-----|---------|
| A. stdio only | Simplest; no network, no auth. | Local only: a remote step cannot reach it. |
| B. Streamable HTTP with sessions (`Mcp-Session-Id`) | Server can keep state per client. | State must live somewhere; harder to scale and restart; sticky routing. |
| **C. Streamable HTTP, stateless** | Any instance answers any request; restart is free; fits "cattle, not pets" (ADR-007). | No server state between requests; features that need a session are out. |

## Decision

Option C. Each request carries all it needs; the server keeps no session.

- The tool logic is plain Python functions with no transport code. The HTTP layer only maps
  requests to them, so a stdio entry point stays a few lines if a local client needs it.
- Security, from the spec: validate the `Origin` header, bind to `127.0.0.1` when local, and add
  auth before any deployment.
- Tools are few, read-only and return small results (README principle 2).

## Consequences

- One server serves a laptop and CI the same way.
- A tool that needs memory between calls must store it outside the server (for example in GitHub).
- Auth is a must before the server leaves `127.0.0.1`; that needs its own decision then.
