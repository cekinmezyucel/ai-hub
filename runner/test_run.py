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
        cmd = run.claude_command(CONFIG, "spec", "12", "abc", DEMO, Path("/plugin"), Path("/tmp/run"))
        self.assertEqual(cmd[:3], ["claude", "-p", "/ai-hub:spec 12 input=abc"])
        self.assertEqual(cmd[cmd.index("--plugin-dir") + 1], "/plugin")
        self.assertEqual(cmd[cmd.index("--setting-sources") + 1], "project,local")
        self.assertEqual(cmd[cmd.index("--max-turns") + 1], "30")
        self.assertIn("--strict-mcp-config", cmd)

    def test_tells_the_agent_one_command_per_call_and_where_temp_files_go(self):
        cmd = run.claude_command(CONFIG, "spec", "12", "abc", DEMO, Path("/plugin"), Path("/tmp/run"))
        prompt = cmd[cmd.index("--append-system-prompt") + 1]
        self.assertIn("one command per Bash call", prompt)
        self.assertIn("only under /tmp/run", prompt)


class StepEnv(unittest.TestCase):
    def test_drops_the_parent_session_but_keeps_the_rest(self):
        env = {"PATH": "/bin", "CLAUDECODE": "1", "CLAUDE_EFFORT": "high", "CLAUDE_CODE_SESSION_ID": "x"}
        self.assertEqual(run.step_env(env), {"PATH": "/bin"})


class StepOrder(unittest.TestCase):
    def test_follows_needs(self):
        self.assertEqual(run.step_order(CONFIG), ["spec", "plan", "implement", "verify", "review", "check"])

    def test_a_cycle_is_an_error(self):
        steps = {"a": {"needs": ["b"]}, "b": {"needs": ["a"]}}
        with self.assertRaisesRegex(run.RunnerError, "cycle"):
            run.step_order({"steps": steps})


ORDER = run.step_order(CONFIG)
# The current input of each step, as the runner computes it from GitHub.
INPUTS = {"spec": "body1", "plan": "spec1", "implement": "plan1", "verify": "head1", "review": "head1", "check": "merge1"}


def history(*steps):
    """Markers oldest first, from "step:verdict" strings. Each names the current input of its step,
    unless it ends with ":old" (an older input) or ":-" (no input)."""
    markers = []
    for s in steps:
        step, verdict, *rest = s.split(":")
        marker = {"step": step, "verdict": verdict}
        if rest != ["-"]:
            marker["input"] = rest[0] if rest else INPUTS.get(step, "x")
        markers.append(marker)
    return markers


OPEN_PR = {"number": 13, "state": "OPEN", "head": "head1", "mergeCommit": None}
MERGED_PR = {"number": 13, "state": "MERGED", "head": "head1", "mergeCommit": "merge1"}
DONE_TO_IMPLEMENT = ["spec:pass", "plan:pass", "implement:pass"]


class NextAction(unittest.TestCase):
    def next(self, steps, pr=None, loop_cap=3, inputs=INPUTS):
        return run.next_action(ORDER, history(*steps), inputs, pr, loop_cap)

    def test_new_issue_starts_with_spec(self):
        self.assertEqual(self.next([]), ("run", "spec"))
        self.assertEqual(self.next(["prd:pass"]), ("run", "spec"))

    def test_runs_the_first_missing_step(self):
        self.assertEqual(self.next(["spec:pass"]), ("run", "plan"))
        self.assertEqual(self.next(["spec:pass", "plan:pass"]), ("run", "implement"))
        self.assertEqual(self.next(DONE_TO_IMPLEMENT, OPEN_PR), ("run", "verify"))
        self.assertEqual(self.next([*DONE_TO_IMPLEMENT, "verify:pass"], OPEN_PR), ("run", "review"))

    def test_blocked_stops_for_a_human(self):
        self.assertEqual(self.next(["spec:blocked"])[0], "stop")

    def test_answered_block_runs_the_step_again(self):
        self.assertEqual(self.next(["spec:blocked:old", "prd:pass"]), ("run", "spec"))
        self.assertEqual(self.next(["spec:pass:old", "plan:blocked", "prd:pass"]), ("run", "spec"))
        self.assertEqual(self.next(["spec:pass", "plan:blocked", "prd:pass"]), ("run", "plan"))

    def test_stale_step_before_implement_stops_for_a_human(self):
        kind, reason = self.next(["spec:pass:old", "plan:pass"])
        self.assertEqual(kind, "stop")
        self.assertIn("--step spec", reason)

    def test_a_report_without_input_is_stale(self):
        self.assertEqual(self.next(["spec:pass:-"])[0], "stop")

    def test_changed_plan_after_implement_stops_even_after_prd(self):
        steps = ["spec:pass", "plan:pass", "implement:pass:old", "prd:pass"]
        self.assertEqual(self.next(steps, OPEN_PR)[0], "stop")

    def test_a_push_makes_verify_and_review_run_again(self):
        self.assertEqual(self.next([*DONE_TO_IMPLEMENT, "verify:pass:old"], OPEN_PR), ("run", "verify"))
        steps = [*DONE_TO_IMPLEMENT, "verify:pass", "review:pass:old"]
        self.assertEqual(self.next(steps, OPEN_PR), ("run", "review"))

    def test_fail_goes_back_to_implement(self):
        self.assertEqual(self.next([*DONE_TO_IMPLEMENT, "verify:fail"], OPEN_PR), ("run", "implement"))
        self.assertEqual(self.next([*DONE_TO_IMPLEMENT, "verify:pass", "review:fail"], OPEN_PR), ("run", "implement"))

    def test_the_fix_pushed_by_implement_makes_verify_run_again(self):
        steps = [*DONE_TO_IMPLEMENT, "verify:fail:old", "implement:pass"]
        self.assertEqual(self.next(steps, OPEN_PR), ("run", "verify"))

    def test_implement_without_a_fix_stops(self):
        steps = [*DONE_TO_IMPLEMENT, "verify:fail", "implement:pass"]
        self.assertEqual(self.next(steps, OPEN_PR)[0], "stop")

    def test_loop_stops_at_the_cap(self):
        steps = [*DONE_TO_IMPLEMENT, "verify:fail:old", "implement:pass", "verify:fail:old", "implement:pass",
                 "verify:pass", "review:fail"]
        self.assertEqual(self.next(steps, OPEN_PR, loop_cap=3)[0], "stop")
        self.assertEqual(self.next(steps, OPEN_PR, loop_cap=4), ("run", "implement"))

    def test_review_pass_stops_at_the_merge_gate(self):
        kind, reason = self.next([*DONE_TO_IMPLEMENT, "verify:pass", "review:pass"], OPEN_PR)
        self.assertEqual(kind, "stop")
        self.assertIn("merge", reason)

    def test_after_the_merge_waits_for_ci_then_checks(self):
        steps = [*DONE_TO_IMPLEMENT, "verify:pass", "review:pass"]
        self.assertEqual(self.next(steps, MERGED_PR), ("wait_ci", "merge1"))

    def test_check_pass_is_done(self):
        steps = [*DONE_TO_IMPLEMENT, "verify:pass", "review:pass", "check:pass"]
        self.assertEqual(self.next(steps, MERGED_PR)[0], "done")

    def test_check_fail_stops(self):
        steps = [*DONE_TO_IMPLEMENT, "verify:pass", "review:pass", "check:fail"]
        self.assertEqual(self.next(steps, MERGED_PR)[0], "stop")


class Inputs(unittest.TestCase):
    def test_spec_input_follows_the_issue_body(self):
        self.assertEqual(run.body_hash("a"), run.body_hash("a"))
        self.assertNotEqual(run.body_hash("a"), run.body_hash("a "))
        self.assertEqual(len(run.body_hash(None)), 12)

    def test_steps_after_spec_have_no_input_before_the_feature_branch(self):
        inputs = run.current_inputs(CONFIG, "body", None, None, DEMO, ".")
        self.assertEqual(inputs["spec"], run.body_hash("body"))
        self.assertEqual({inputs[s] for s in ("plan", "implement", "verify", "review", "check")}, {None})

    def test_pr_steps_read_the_open_pr_and_check_the_merge(self):
        inputs = run.current_inputs(CONFIG, "body", None, OPEN_PR, DEMO, ".")
        self.assertEqual((inputs["verify"], inputs["review"], inputs["check"]), ("head1", "head1", None))
        inputs = run.current_inputs(CONFIG, "body", None, MERGED_PR, DEMO, ".")
        self.assertEqual((inputs["verify"], inputs["check"]), ("head1", "merge1"))
        closed = {**OPEN_PR, "state": "CLOSED"}
        self.assertIsNone(run.current_inputs(CONFIG, "body", None, closed, DEMO, ".")["verify"])

    def test_the_report_must_name_the_input_passed_in(self):
        run.check_input("verify", {"input": "abc"}, "abc")
        with self.assertRaisesRegex(run.RunnerError, "input=def, expected abc"):
            run.check_input("verify", {"input": "def"}, "abc")
        with self.assertRaisesRegex(run.RunnerError, "input=None"):
            run.check_input("verify", {}, "abc")


class CheckoutTarget(unittest.TestCase):
    def test_spec_starts_from_the_default_branch(self):
        self.assertEqual(run.checkout_target("spec", None, "main"), "main")

    def test_later_steps_work_on_the_feature_branch(self):
        self.assertEqual(run.checkout_target("plan", "feature/5-x", "main"), "feature/5-x")

    def test_check_reads_the_default_branch(self):
        self.assertEqual(run.checkout_target("check", "feature/5-x", "main"), "main")


class FreshClone(unittest.TestCase):
    """An origin, the place where the last step ran, and a fresh clone for the next step."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.sh(self.root, "git", "init", "-q", "--bare", "-b", "main", "origin.git")
        self.origin = f"file://{self.root / 'origin.git'}"
        self.sh(self.root, "git", "clone", "-q", self.origin, "elsewhere")
        self.elsewhere = self.root / "elsewhere"
        self.commit(self.elsewhere, "readme")
        self.sh(self.elsewhere, "git", "push", "-q", "origin", "main")

    def sh(self, cwd, *args):
        subprocess.run(args, cwd=cwd, check=True, capture_output=True)

    def commit(self, cwd, name):
        (cwd / name).write_text(name)
        self.sh(cwd, "git", "add", name)
        self.sh(cwd, "git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", name)

    def head(self, cwd):
        return run.git(["rev-parse", "HEAD"], cwd)

    def clone(self, step, setup=()):
        dest = self.root / f"run-{step}"
        with redirect_stdout(io.StringIO()):
            run.prepare_clone(step, 5, self.origin, dest, "main", setup)
        return dest

    def test_next_step_starts_from_the_pushed_feature_branch(self):
        self.sh(self.elsewhere, "git", "switch", "-q", "-c", "feature/5-x")
        self.commit(self.elsewhere, "spec.md")
        self.sh(self.elsewhere, "git", "push", "-q", "origin", "feature/5-x")
        dest = self.clone("plan")
        self.assertEqual(run.git(["branch", "--show-current"], dest), "feature/5-x")
        self.assertEqual(self.head(dest), self.head(self.elsewhere))

    def test_check_reads_the_default_branch(self):
        self.sh(self.elsewhere, "git", "push", "-q", "origin", "main:feature/5-x")
        self.commit(self.elsewhere, "merge")
        self.sh(self.elsewhere, "git", "push", "-q", "origin", "main")
        dest = self.clone("check")
        self.assertEqual(run.git(["branch", "--show-current"], dest), "main")
        self.assertEqual(self.head(dest), self.head(self.elsewhere))

    def test_spec_starts_on_the_default_branch_and_setup_runs(self):
        dest = self.clone("spec", ["git config core.hooksPath .githooks"])
        self.assertEqual(run.git(["branch", "--show-current"], dest), "main")
        self.assertEqual(run.git(["config", "core.hooksPath"], dest), ".githooks")

    def test_two_feature_branches_for_one_issue_stop_the_run(self):
        self.sh(self.elsewhere, "git", "push", "-q", "origin", "main:feature/5-a", "main:feature/5-b")
        with self.assertRaisesRegex(run.RunnerError, "more than one feature branch"):
            self.clone("plan")

    def test_a_step_that_did_not_push_stops_the_chain(self):
        dest = self.clone("plan")
        run.check_pushed("plan", dest)
        self.commit(dest, "plan.md")
        with self.assertRaisesRegex(run.RunnerError, "plan left 1 commit"):
            run.check_pushed("plan", dest)


if __name__ == "__main__":
    unittest.main()
