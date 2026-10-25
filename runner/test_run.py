import unittest
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


if __name__ == "__main__":
    unittest.main()
