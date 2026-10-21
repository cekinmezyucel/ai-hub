"""ai-hub runner: run one step of a feature as a fresh headless Claude Code process.

    python runner/run.py <issue> --step <step> [--repo <path>]

Run it from the target repo, or pass --repo. The step reads its input only from files and
Issue/PR comments, posts its report and exits. The runner then looks for that report.
"""

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import tomllib
from datetime import datetime, timezone
from pathlib import Path

STEPS = ["spec", "plan", "implement", "verify", "review", "check"]
ISSUE_STEPS = {"spec", "plan", "check"}
PR_STEPS = {"verify", "review"}
MARKER = re.compile(r"<!--\s*ai-hub\s+(.*?)\s*-->")
CONFIG_FILE = Path(__file__).with_name("config.toml")
PLUGIN_CACHE = Path("~/.claude/plugins/cache/ai-hub/ai-hub").expanduser()


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
    prs = gh_json(["pr", "list", "--state", "open", "--json", "number,headRefName"], cwd)
    numbers = [p["number"] for p in prs if p["headRefName"].startswith(f"feature/{issue}-")]
    if len(numbers) > 1:
        raise RunnerError(f"more than one open PR for Issue #{issue}: {numbers}")
    return numbers[0] if numbers else None


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


def run_step(cmd, cwd, log_file):
    result = None
    with open(log_file, "w") as log, subprocess.Popen(cmd, cwd=cwd, stdout=subprocess.PIPE, text=True) as proc:
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
    posts = gh_json(["issue", "view", str(issue), "--json", "comments"], cwd)["comments"]
    if pr is not None:
        data = gh_json(["pr", "view", str(pr), "--json", "body,createdAt,url,comments"], cwd)
        posts += [{"body": data["body"], "createdAt": data["createdAt"], "url": data["url"]}, *data["comments"]]
    return posts


def main(argv=None):
    parser = argparse.ArgumentParser(description="Run one ai-hub step on a PRD Issue.")
    parser.add_argument("issue", type=int, help="PRD Issue number in the target repo")
    parser.add_argument("--step", required=True, choices=STEPS)
    parser.add_argument("--repo", type=Path, default=Path.cwd(), help="target repo checkout (default: cwd)")
    args = parser.parse_args(argv)

    try:
        config = load_config(CONFIG_FILE)
        cwd = args.repo.resolve()
        check_clean(cwd)
        repo = gh_json(["repo", "view", "--json", "nameWithOwner"], cwd)["nameWithOwner"]
        if subprocess.run(["gh", "issue", "view", str(args.issue)], cwd=cwd, capture_output=True).returncode:
            raise RunnerError(f"no Issue #{args.issue} in {repo}")
        pr = find_pr(args.issue, cwd)
        arg = step_argument(args.step, args.issue, pr)
        tmp_dir = Path(tempfile.mkdtemp(prefix=f"ai-hub-{args.step}-"))
        cmd = claude_command(config, args.step, arg, repo, plugin_dir(config), tmp_dir)

        start = datetime.now(timezone.utc).replace(microsecond=0)
        log_dir = Path(config["log_dir"]).expanduser()
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / f"{repo.replace('/', '_')}-{args.issue}-{args.step}-{start:%Y%m%dT%H%M%SZ}.jsonl"

        print(f"{repo}#{args.issue} · {args.step} {arg} · plugin {config['plugin_version']}")
        result = run_step(cmd, cwd, log_file)

        print(f"\n{result.get('result', '').strip()}\n")
        for denial in result.get("permission_denials", []):
            tool_input = denial["tool_input"]
            print(f"denied: {denial['tool_name']}: {tool_input.get('command') or tool_input.get('file_path') or ''}")
        print(f"{result['num_turns']} turns · {result['duration_ms'] / 1000:.0f} s · ${result['total_cost_usd']:.2f}")
        print(f"log: {log_file}")

        report = new_report(posts_for(args.issue, find_pr(args.issue, cwd), cwd), args.step, start)
        if report is None:
            print(f"no new {args.step} report on #{args.issue} or its PR")
            return 2
        print(f"report: {args.step} · {report.get('verdict')} · {report['url']}")
        return 0
    except (RunnerError, subprocess.CalledProcessError) as e:
        print(f"runner: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
