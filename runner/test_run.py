import io
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timezone
from pathlib import Path

import run

CONFIG = run.load_config(Path(__file__).with_name("config.toml"))
DEMO = "cekinmezyucel/ai-hub-demo"


class ParseMarkers(unittest.TestCase):
    def test_reads_marker_fields(self):
        body = "<!-- ai-hub step=spec feature=12-short-links verdict=pass -->\n**spec** · pass"
        self.assertEqual(
            run.parse_markers(body),
            [{"step": "spec", "feature": "12-short-links", "verdict": "pass"}],
        )

    def test_ignores_other_comments(self):
        self.assertEqual(run.parse_markers("<!-- some other tool -->\nLooks good"), [])


class NewReport(unittest.TestCase):
    start = datetime(2026, 10, 21, 18, 0, tzinfo=timezone.utc)

    def post(self, body, at):
        return {"body": body, "createdAt": at, "url": "u"}

    def test_finds_the_step_report_posted_after_start(self):
        posts = [
            self.post("<!-- ai-hub step=spec feature=f verdict=blocked -->", "2026-10-21T17:00:00Z"),
            self.post("<!-- ai-hub step=spec feature=f verdict=pass -->", "2026-10-21T18:05:00Z"),
        ]
        self.assertEqual(run.new_report(posts, "spec", self.start)["verdict"], "pass")

    def test_ignores_old_reports_and_other_steps(self):
        posts = [
            self.post("<!-- ai-hub step=spec feature=f verdict=pass -->", "2026-10-21T17:00:00Z"),
            self.post("<!-- ai-hub step=plan feature=f verdict=pass -->", "2026-10-21T18:05:00Z"),
        ]
        self.assertIsNone(run.new_report(posts, "spec", self.start))


class AllowedTools(unittest.TestCase):
    def test_spec_can_comment_and_push_but_not_run_tests(self):
        tools = run.allowed_tools(CONFIG, "spec", DEMO)
        self.assertIn("Bash(gh issue comment:*)", tools)
        self.assertIn("Bash(git push:*)", tools)
        self.assertNotIn("Bash(pytest:*)", tools)

    def test_verify_gets_the_repo_test_commands(self):
        self.assertIn("Bash(pytest:*)", run.allowed_tools(CONFIG, "verify", DEMO))

    def test_unknown_repo_gets_no_repo_tools(self):
        self.assertNotIn("Bash(pytest:*)", run.allowed_tools(CONFIG, "verify", "someone/else"))


class StepArgument(unittest.TestCase):
    def test_issue_steps_take_the_issue(self):
        self.assertEqual(run.step_argument("spec", 12, None), "12")

    def test_pr_steps_take_the_pr(self):
        self.assertEqual(run.step_argument("verify", 12, 13), "13")

    def test_pr_step_without_a_pr_fails(self):
        with self.assertRaises(run.RunnerError):
            run.step_argument("review", 12, None)

    def test_implement_takes_the_pr_once_it_exists(self):
        self.assertEqual(run.step_argument("implement", 12, None), "12")
        self.assertEqual(run.step_argument("implement", 12, 13), "13")


class ClaudeCommand(unittest.TestCase):
    def test_runs_the_step_with_only_the_pinned_plugin(self):
        cmd = run.claude_command(CONFIG, "spec", "12", DEMO, Path("/plugin"), Path("/tmp/run"))
        self.assertEqual(cmd[:3], ["claude", "-p", "/ai-hub:spec 12"])
        self.assertEqual(cmd[cmd.index("--plugin-dir") + 1], "/plugin")
        self.assertEqual(cmd[cmd.index("--setting-sources") + 1], "project,local")
        self.assertEqual(cmd[cmd.index("--max-turns") + 1], "30")
        self.assertIn("--strict-mcp-config", cmd)

    def test_tells_the_agent_one_command_per_call_and_where_temp_files_go(self):
        cmd = run.claude_command(CONFIG, "spec", "12", DEMO, Path("/plugin"), Path("/tmp/run"))
        prompt = cmd[cmd.index("--append-system-prompt") + 1]
        self.assertIn("one command per Bash call", prompt)
        self.assertIn("only under /tmp/run", prompt)


class StepEnv(unittest.TestCase):
    def test_drops_the_parent_session_but_keeps_the_rest(self):
        env = {"PATH": "/bin", "CLAUDECODE": "1", "CLAUDE_EFFORT": "high", "CLAUDE_CODE_SESSION_ID": "x"}
        self.assertEqual(run.step_env(env), {"PATH": "/bin"})


def history(*steps):
    """Markers oldest first, from "step:verdict" strings."""
    return [dict(zip(("step", "verdict"), s.split(":"))) for s in steps]


OPEN_PR = {"number": 13, "state": "OPEN", "mergeCommit": None}
MERGED_PR = {"number": 13, "state": "MERGED", "mergeCommit": "abc1234"}


class NextAction(unittest.TestCase):
    def next(self, steps, pr=None, loop_cap=3):
        return run.next_action(history(*steps), pr, loop_cap)

    def test_new_issue_starts_with_spec(self):
        self.assertEqual(self.next([]), ("run", "spec"))
        self.assertEqual(self.next(["prd:pass"]), ("run", "spec"))

    def test_pass_moves_to_the_next_step(self):
        self.assertEqual(self.next(["spec:pass"]), ("run", "plan"))
        self.assertEqual(self.next(["spec:pass", "plan:pass"]), ("run", "implement"))
        self.assertEqual(self.next(["implement:pass"], OPEN_PR), ("run", "verify"))
        self.assertEqual(self.next(["implement:pass", "verify:pass"], OPEN_PR), ("run", "review"))

    def test_blocked_stops_for_a_human(self):
        self.assertEqual(self.next(["spec:blocked"])[0], "stop")

    def test_answered_block_runs_the_step_again(self):
        self.assertEqual(self.next(["spec:blocked", "prd:pass"]), ("run", "spec"))

    def test_fail_goes_back_to_implement(self):
        self.assertEqual(self.next(["implement:pass", "verify:fail"], OPEN_PR), ("run", "implement"))
        self.assertEqual(self.next(["verify:pass", "review:fail"], OPEN_PR), ("run", "implement"))

    def test_loop_stops_at_the_cap(self):
        steps = ["verify:fail", "implement:pass", "verify:fail", "implement:pass", "review:fail"]
        self.assertEqual(self.next(steps, OPEN_PR, loop_cap=3)[0], "stop")
        self.assertEqual(self.next(steps, OPEN_PR, loop_cap=4), ("run", "implement"))

    def test_review_pass_stops_at_the_merge_gate(self):
        kind, reason = self.next(["verify:pass", "review:pass"], OPEN_PR)
        self.assertEqual(kind, "stop")
        self.assertIn("merge", reason)

    def test_after_the_merge_waits_for_ci_then_checks(self):
        self.assertEqual(self.next(["verify:pass", "review:pass"], MERGED_PR), ("wait_ci", "abc1234"))

    def test_check_pass_is_done(self):
        self.assertEqual(self.next(["review:pass", "check:pass"], MERGED_PR)[0], "done")

    def test_check_fail_stops(self):
        self.assertEqual(self.next(["review:pass", "check:fail"], MERGED_PR)[0], "stop")


class CheckoutTarget(unittest.TestCase):
    def test_spec_starts_from_the_default_branch(self):
        self.assertEqual(run.checkout_target("spec", None, "main"), "main")

    def test_later_steps_work_on_the_feature_branch(self):
        self.assertEqual(run.checkout_target("plan", "feature/5-x", "main"), "feature/5-x")

    def test_check_reads_the_default_branch(self):
        self.assertEqual(run.checkout_target("check", "feature/5-x", "main"), "main")


class Handover(unittest.TestCase):
    """Two clones of one origin: the runner's checkout, and the place where the last step ran."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        self.sh(root, "git", "init", "-q", "--bare", "-b", "main", "origin.git")
        for name in ("local", "elsewhere"):
            self.sh(root, "git", "clone", "-q", "origin.git", name)
            self.sh(root / name, "git", "config", "user.email", "t@t")
            self.sh(root / name, "git", "config", "user.name", "t")
        self.local, self.elsewhere = root / "local", root / "elsewhere"
        self.commit(self.elsewhere, "readme")
        self.sh(self.elsewhere, "git", "push", "-q", "origin", "main")

    def sh(self, cwd, *args):
        subprocess.run(args, cwd=cwd, check=True, capture_output=True)

    def commit(self, cwd, name):
        (cwd / name).write_text(name)
        self.sh(cwd, "git", "add", name)
        self.sh(cwd, "git", "commit", "-q", "-m", name)

    def head(self, cwd):
        return run.git(["rev-parse", "HEAD"], cwd)

    def test_next_step_starts_from_the_pushed_feature_branch(self):
        self.sh(self.elsewhere, "git", "switch", "-q", "-c", "feature/5-x")
        self.commit(self.elsewhere, "spec.md")
        self.sh(self.elsewhere, "git", "push", "-q", "origin", "feature/5-x")
        with redirect_stdout(io.StringIO()):
            run.prepare_checkout("plan", 5, self.local, "main")
        self.assertEqual(run.git(["branch", "--show-current"], self.local), "feature/5-x")
        self.assertEqual(self.head(self.local), self.head(self.elsewhere))

    def test_check_fast_forwards_the_default_branch(self):
        self.sh(self.local, "git", "fetch", "-q")
        self.sh(self.local, "git", "switch", "-q", "main")
        self.commit(self.elsewhere, "merge")
        self.sh(self.elsewhere, "git", "push", "-q", "origin", "main")
        with redirect_stdout(io.StringIO()):
            run.prepare_checkout("check", 5, self.local, "main")
        self.assertEqual(self.head(self.local), self.head(self.elsewhere))

    def test_local_commits_not_on_github_stop_the_run(self):
        self.sh(self.local, "git", "fetch", "-q")
        self.sh(self.local, "git", "switch", "-q", "main")
        self.commit(self.local, "unpushed")
        with self.assertRaisesRegex(run.RunnerError, "not on GitHub"):
            run.prepare_checkout("spec", 5, self.local, "main")

    def test_a_step_that_did_not_push_stops_the_chain(self):
        self.sh(self.local, "git", "fetch", "-q")
        self.sh(self.local, "git", "switch", "-q", "main")
        run.check_pushed("plan", self.local)
        self.commit(self.local, "plan.md")
        with self.assertRaisesRegex(run.RunnerError, "plan left 1 commit"):
            run.check_pushed("plan", self.local)


if __name__ == "__main__":
    unittest.main()
