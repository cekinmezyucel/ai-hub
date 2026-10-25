"""ai-hub runner: move a feature forward, each step as a fresh headless Claude Code process.

    python runner/run.py <issue> [--step <step>] [--repo <path>]

Run it from the target repo, or pass --repo. With --step, it runs that one step. Without it, it
chains: it reads the last report marker from GitHub, runs the next step, and repeats until the
feature is done, a step is blocked, or a gate needs a human. Each step reads its input only from
files and Issue/PR comments, posts its report and exits. The runner then looks for that report.
"""

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import tomllib
from datetime import datetime, timezone
from pathlib import Path

STEPS = ["spec", "plan", "implement", "verify", "review", "check"]
ISSUE_STEPS = {"spec", "plan", "check"}
PR_STEPS = {"verify", "review"}
MARKER = re.compile(r"<!--\s*ai-hub\s+(.*?)\s*-->")
CONFIG_FILE = Path(__file__).with_name("config.toml")
PLUGIN_CACHE = Path("~/.claude/plugins/cache/ai-hub/ai-hub").expanduser()
# Set by a Claude Code session for its child processes. A step started from /ai-hub:run must not
# inherit them: it would run as that session's child, with its effort level.
PARENT_SESSION_ENV = {
    "CLAUDECODE",
    "CLAUDE_PID",
    "CLAUDE_EFFORT",
    "CLAUDE_CODE_ENTRYPOINT",
    "CLAUDE_CODE_EXECPATH",
    "CLAUDE_CODE_SESSION_ID",
    "CLAUDE_CODE_CHILD_SESSION",
    "CLAUDE_CODE_SESSION_ATTENDED",
    "CLAUDE_CODE_MESSAGING_SOCKET",
    "CLAUDE_CODE_MESSAGING_TOKEN",
}


class RunnerError(Exception):
    pass


def load_config(path):
    with open(path, "rb") as f:
        return tomllib.load(f)


def parse_markers(body):
    """All ai-hub report markers in a comment body, as dicts of their key=value fields."""
    return [dict(f.split("=", 1) for f in m.split() if "=" in f) for m in MARKER.findall(body or "")]


def new_report(posts, step, since):
    """The newest report of this step posted after `since`, or None."""
    found = None
    for post in posts:
        if datetime.fromisoformat(post["createdAt"]) < since:
            continue
        for marker in parse_markers(post["body"]):
            if marker.get("step") == step:
                found = {**marker, "url": post.get("url", "")}
    return found


def allowed_tools(config, step, repo):
    tools = list(config["tools"]["common"])
    step_config = config["steps"][step]
    for group in step_config.get("groups", []):
        if group == "repo":
            tools += config.get("repos", {}).get(repo, {}).get("tools", [])
        else:
            tools += config["tools"]["groups"][group]
    return tools + step_config.get("tools", [])


def step_argument(step, issue, pr):
    """What the skill gets: the PRD Issue, or the PR for the steps that work on a PR."""
    if step in ISSUE_STEPS:
        return str(issue)
    if pr is None:
        if step in PR_STEPS:
            raise RunnerError(f"{step} needs a PR, but no open PR is on a feature/{issue}-* branch")
        return str(issue)
    return str(pr)


def claude_command(config, step, arg, repo, plugin_dir, tmp_dir):
    cmd = ["claude", "-p", f"/ai-hub:{step} {arg}"]
    cmd += ["--output-format", "stream-json", "--verbose"]
    cmd += ["--max-turns", str(config["steps"][step]["max_turns"])]
    # User settings are left out so only the pinned ai-hub plugin loads. User CLAUDE.md still loads.
    cmd += ["--setting-sources", "project,local", "--plugin-dir", str(plugin_dir), "--strict-mcp-config"]
    cmd += ["--permission-mode", "acceptEdits", "--add-dir", str(tmp_dir)]
    cmd += ["--append-system-prompt", config["system_prompt"].strip().format(tmp_dir=tmp_dir)]
    if config.get("model"):
        cmd += ["--model", config["model"]]
    cmd += ["--allowedTools", *allowed_tools(config, step, repo)]
    cmd += ["--disallowedTools", *config["tools"]["denied"]]
    return cmd


def gh_json(args, cwd):
    out = subprocess.run(["gh", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout
    return json.loads(out)


def find_pr(issue, cwd):
    """The feature's PR as {number, state, mergeCommit}: the open one, else the newest merged or closed one."""
    fields = "number,headRefName,state,mergeCommit"
    prs = gh_json(["pr", "list", "--state", "all", "--json", fields], cwd)
    prs = [p for p in prs if p["headRefName"].startswith(f"feature/{issue}-")]
    open_prs = [p for p in prs if p["state"] == "OPEN"]
    if len(open_prs) > 1:
        raise RunnerError(f"more than one open PR for Issue #{issue}: {[p['number'] for p in open_prs]}")
    pr = open_prs[0] if open_prs else max(prs, key=lambda p: p["number"], default=None)
    if pr is None:
        return None
    merge = pr.get("mergeCommit") or {}
    return {"number": pr["number"], "state": pr["state"], "mergeCommit": merge.get("oid")}


def open_pr_number(pr):
    return pr["number"] if pr and pr["state"] == "OPEN" else None


NEXT_STEP = {"prd": "spec", "spec": "plan", "plan": "implement", "implement": "verify", "verify": "review"}


def next_action(history, pr, loop_cap):
    """What the chain does next, from the markers (oldest first) and the PR state.

    Returns ("run", step), ("wait_ci", merge commit), ("stop", reason) or ("done", reason).
    """
    if not history:
        return ("run", "spec")
    last = history[-1]
    step, verdict = last.get("step"), last.get("verdict")
    if verdict == "blocked":
        return ("stop", f"{step} is blocked: a human must answer its report")
    if verdict == "fail" and step in ("verify", "review"):
        loops = sum(1 for m in history if m.get("step") in ("verify", "review") and m.get("verdict") == "fail")
        if loops >= loop_cap:
            return ("stop", f"loop cap reached: {loops} verify/review fails (loop_cap = {loop_cap})")
        return ("run", "implement")
    if verdict != "pass":
        return ("stop", f"{step} ended with verdict {verdict}: a human must look")
    if step in NEXT_STEP:
        return ("run", NEXT_STEP[step])
    if step == "review":
        if pr and pr["state"] == "MERGED":
            return ("wait_ci", pr["mergeCommit"])
        if pr and pr["state"] == "OPEN":
            return ("stop", f"gate: review passed, merge PR #{pr['number']}, then run again")
        return ("stop", "review passed, but no open or merged PR was found")
    if step == "check":
        return ("done", "check passed: the feature is done")
    return ("stop", f"unknown step in marker: {step}")


def plugin_dir(config):
    """The ai-hub plugin at the config version. AI_HUB_PLUGIN_DIR overrides it, e.g. a live checkout."""
    path = Path(os.environ.get("AI_HUB_PLUGIN_DIR") or PLUGIN_CACHE / config["plugin_version"]).expanduser()
    manifest = path / ".claude-plugin" / "plugin.json"
    if not manifest.is_file():
        raise RunnerError(f"no ai-hub plugin at {path}. Run: claude plugin update ai-hub@ai-hub")
    version = json.loads(manifest.read_text())["version"]
    if version != config["plugin_version"]:
        raise RunnerError(f"plugin at {path} is {version}, config wants {config['plugin_version']}")
    return path


def check_clean(cwd):
    status = subprocess.run(["git", "status", "--porcelain"], cwd=cwd, check=True, capture_output=True, text=True)
    if status.stdout.strip():
        raise RunnerError(f"working tree in {cwd} is not clean. State lives in GitHub: commit or stash first")


def describe(event):
    """One short line per tool call, so a human can follow the run."""
    if event.get("type") != "assistant":
        return []
    lines = []
    for block in event["message"].get("content", []):
        if block.get("type") == "tool_use":
            args = block["input"]
            detail = args.get("command") or args.get("file_path") or args.get("pattern") or ""
            lines.append(f"  → {block['name']}: {detail.splitlines()[0][:120] if detail else ''}")
    return lines


def step_env(env):
    """The environment of a step: the runner's own, without the variables of a parent Claude Code session."""
    return {k: v for k, v in env.items() if k not in PARENT_SESSION_ENV}


def run_step(cmd, cwd, log_file):
    result = None
    env = step_env(os.environ)
    with open(log_file, "w") as log, subprocess.Popen(cmd, cwd=cwd, env=env, stdout=subprocess.PIPE, text=True) as proc:
        for line in proc.stdout:
            log.write(line)
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            for out in describe(event):
                print(out, flush=True)
            if event.get("type") == "result":
                result = event
    if result is None:
        raise RunnerError(f"claude exited with {proc.returncode} and no result. Log: {log_file}")
    return result


def posts_for(issue, pr, cwd):
    """The Issue body and comments, plus the PR body and comments: everything a report can be in."""
    data = gh_json(["issue", "view", str(issue), "--json", "body,createdAt,url,comments"], cwd)
    posts = [{"body": data["body"], "createdAt": data["createdAt"], "url": data["url"]}, *data["comments"]]
    if pr is not None:
        data = gh_json(["pr", "view", str(pr), "--json", "body,createdAt,url,comments"], cwd)
        posts += [{"body": data["body"], "createdAt": data["createdAt"], "url": data["url"]}, *data["comments"]]
    return posts


def history_for(posts):
    """All report markers, oldest first."""
    dated = [(datetime.fromisoformat(p["createdAt"]), m) for p in posts for m in parse_markers(p["body"])]
    return [m for _, m in sorted(dated, key=lambda d: d[0])]


def wait_for_ci(sha, cwd, tries=10):
    """Wait, without an agent, until every CI run for the merge commit has finished."""
    for _ in range(tries):
        runs = gh_json(["run", "list", "--commit", sha, "--json", "databaseId,status,workflowName"], cwd)
        if runs:
            break
        print(f"waiting for CI runs on {sha[:7]} to start …", flush=True)
        time.sleep(30)
    else:
        raise RunnerError(f"no CI run started for {sha[:7]}")
    for r in runs:
        if r["status"] != "completed":
            print(f"waiting for {r['workflowName']} (run {r['databaseId']}) …", flush=True)
            subprocess.run(["gh", "run", "watch", str(r["databaseId"])], cwd=cwd, capture_output=True)


def run_one(config, step, issue, cwd, repo):
    """Run one step as a fresh claude -p. Returns its new report, or None if it posted none."""
    check_clean(cwd)
    arg = step_argument(step, issue, open_pr_number(find_pr(issue, cwd)))
    tmp_dir = Path(tempfile.mkdtemp(prefix=f"ai-hub-{step}-"))
    cmd = claude_command(config, step, arg, repo, plugin_dir(config), tmp_dir)

    start = datetime.now(timezone.utc).replace(microsecond=0)
    log_dir = Path(config["log_dir"]).expanduser()
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"{repo.replace('/', '_')}-{issue}-{step}-{start:%Y%m%dT%H%M%SZ}.jsonl"

    print(f"\n{repo}#{issue} · {step} {arg} · plugin {config['plugin_version']}")
    result = run_step(cmd, cwd, log_file)

    print(f"\n{result.get('result', '').strip()}\n")
    for denial in result.get("permission_denials", []):
        tool_input = denial["tool_input"]
        print(f"denied: {denial['tool_name']}: {tool_input.get('command') or tool_input.get('file_path') or ''}")
    print(f"{result['num_turns']} turns · {result['duration_ms'] / 1000:.0f} s · ${result['total_cost_usd']:.2f}")
    print(f"log: {log_file}")

    pr = find_pr(issue, cwd)
    report = new_report(posts_for(issue, pr and pr["number"], cwd), step, start)
    if report is None:
        print(f"no new {step} report on #{issue} or its PR")
    else:
        print(f"report: {step} · {report.get('verdict')} · {report['url']}")
    return report


def chain(config, issue, cwd, repo, max_runs):
    """Run step after step until done, blocked, a gate, or max_runs. Every decision is read from GitHub."""
    for _ in range(max_runs):
        pr = find_pr(issue, cwd)
        kind, value = next_action(history_for(posts_for(issue, pr and pr["number"], cwd)), pr, config["loop_cap"])
        if kind == "wait_ci":
            wait_for_ci(value, cwd)
            kind, value = "run", "check"
        if kind == "done":
            print(f"\ndone: {value}")
            return 0
        if kind == "stop":
            print(f"\nstopped: {value}")
            return 3
        if run_one(config, value, issue, cwd, repo) is None:
            return 2
    print(f"\nstopped: max {max_runs} runs in one chain")
    return 3


def main(argv=None):
    parser = argparse.ArgumentParser(description="Move a PRD Issue forward: one step, or a chain of steps.")
    parser.add_argument("issue", type=int, help="PRD Issue number in the target repo")
    parser.add_argument("--step", choices=STEPS, help="run only this step (default: chain from the last report)")
    parser.add_argument("--repo", type=Path, default=Path.cwd(), help="target repo checkout (default: cwd)")
    parser.add_argument("--max-runs", type=int, default=12, help="most steps one chain may run (default: 12)")
    args = parser.parse_args(argv)

    try:
        config = load_config(CONFIG_FILE)
        cwd = args.repo.resolve()
        repo = gh_json(["repo", "view", "--json", "nameWithOwner"], cwd)["nameWithOwner"]
        if subprocess.run(["gh", "issue", "view", str(args.issue)], cwd=cwd, capture_output=True).returncode:
            raise RunnerError(f"no Issue #{args.issue} in {repo}")
        if args.step:
            return 0 if run_one(config, args.step, args.issue, cwd, repo) else 2
        return chain(config, args.issue, cwd, repo, args.max_runs)
    except (RunnerError, subprocess.CalledProcessError) as e:
        print(f"runner: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
