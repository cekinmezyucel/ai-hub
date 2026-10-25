# ADR-000: Repo structure and ADR format

Status: **Accepted**
Date: 2026-10-25 · Issue: #4

## Context

ai-hub is a Claude Code plugin, its own marketplace, and the home of the runner. The skills are the
product; everything else supports them. Decisions so far live in Issues and chat, and they get lost
when an Issue closes. A reader (or an agent) needs one place to find why things are the way they are.

## Options

**Repo structure**

| Option | For | Against |
|--------|-----|---------|
| A. One repo per part (skills, runner, MCP server, evals) | Clear borders. | Versions must match across repos; one change touches many repos. |
| **B. One repo: plugin at the root, other parts in their own folders** | One version, one history. The plugin and the runner change together. | The root must stay a valid plugin. |

**Where decisions live**

| Option | For | Against |
|--------|-----|---------|
| A. Issues only | Already there. | Closed Issues are hard to find; no current state. |
| **B. ADR files in `docs/adr/`, linked from the Issue** | Versioned with the code; an agent can read them. | One more file per decision. |

## Decision

One repo. The plugin lives at the root, so the marketplace can install it from GitHub.

```
.claude-plugin/        plugin.json (the version) and marketplace.json
skills/<step>/SKILL.md the steps; one folder per step, plus run
runner/                run.py, config.toml, tests: one step per headless claude -p
docs/glossary.md       the shared words
docs/engineering-principles.md   P-1 … P-14, cited in every report
docs/adr/NNN-<slug>.md the decisions
.github/workflows/     CI for this repo
.githooks/             local git hooks (core.hooksPath)
```

Later parts (MCP server, harness, evals) get their own top-level folder when they start.

**ADR format.** One short file per decision, `NNN-<slug>.md`, numbered in order, never renumbered.

```
# ADR-NNN: <decision as a short sentence>
Status: Proposed | Accepted | Superseded by ADR-NNN
Date: <yyyy-mm-dd> · Issue(s): #n · Related: …
## Context        why a decision is needed now
## Options        a table: option, for, against; the chosen one in bold
## Decision       what we do
## Consequences   what gets easier, what gets harder, what is still open
```

- **Proposed:** a draft. It may end with "Needs investigation".
- **Accepted:** we work this way. Change it only with a new ADR, or by editing it with a note in the Issue.
- **Superseded:** kept for history, with a link to the ADR that replaces it.

Write an ADR when a decision is hard to undo, shapes more than one part, or was argued about.
Small choices stay in the Issue.

## Consequences

- Each decision has one home that an agent can read with the code.
- Old decisions stay readable; a change is a new file, not a lost edit.
- The plugin root also holds files that are not part of the plugin (`runner/`, `docs/`). The plugin
  ignores them; the runner and the skills read them by relative path.
