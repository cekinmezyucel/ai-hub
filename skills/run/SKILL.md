---
name: run
description: Start the ai-hub runner on a PRD Issue - it runs each step as a fresh headless claude -p and chains them until the feature is done, a step is blocked, or a gate needs a human - and report where it stopped. Use when the user types /ai-hub:run with an Issue number.
argument-hint: <issue> [--step <step>] [--max-runs <n>]
disable-model-invocation: true
---

# run: PRD Issue → runner → where it stopped

This command does no step itself. It starts the runner that ships with this plugin, the same one
GitHub Actions calls. The runner reads the report markers on GitHub, runs the next step as a fresh
`claude -p` with the pinned plugin version, and repeats. All chain logic lives in the runner.

Words follow `../../docs/glossary.md` (relative to this skill's folder).

## Input

- `$ARGUMENTS`: the PRD Issue number, and optionally `--step <step>` or `--max-runs <n>`.
- The current directory is the target repo. Its working tree must be clean.

## Steps

1. No Issue number in the arguments ⇒ ask for it and stop.
2. Run in the background (`run_in_background`), from the repo root, exactly this one command:
   `python3 "${CLAUDE_SKILL_DIR}/../../runner/run.py" $ARGUMENTS`
   Read the first line of its output: `ai-hub runner · plugin <version>`. Tell the human in one line
   that it runs, with that plugin version, and that a step can take many minutes.
3. Wait for the notification that it finished. Do not poll. If the human asks for progress,
   read the last lines of its output.
4. Report from the output:
   - each step that ran, from its `report:` line: step, verdict, link
   - `denied:` lines, if any
   - the last line: `done:`, `stopped:` or `runner:`
   - what the human does next: at the merge gate, merge the PR and run `/ai-hub:run <issue>` again;
     on `blocked`, answer the report (for example with `/ai-hub:prd <issue>`), then run again;
     on a runner error, the error.

## Rules

- **Report, never repair.** Do not run a step's skill yourself, edit files, post on GitHub, merge,
  or rerun the runner on your own. A failed or blocked step is the human's call.
- Pass the arguments as given. Do not add flags.
- Exit codes: `0` done, or the one `--step` posted its report; `1` runner error;
  `2` a step posted no report; `3` stopped (blocked, gate, loop cap or max runs).
