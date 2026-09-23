"""Live PR triage routing and its evidence-backed re-entry."""

from unittest.mock import patch

from _support import FileBackendTest


THREAD = {"pr": 901, "url": "https://example.test/pr/901#thread-1", "body": "Cover the retry case", "author": "reviewer"}


class LiveTriageTests(FileBackendTest):
    def test_red_check_routes_inspect_and_next_then_reenters_implementation(self):
        self.seed_record(80, "Testing", "Approval Required")
        self.green_pr(80, number=901, checks="FAILURE")

        inspected = self.invoke("inspect", 80, "--full")
        routed = self.next("--work-item", 80)
        self.assertIn("pdlc guide triage-ci-failure", inspected.stdout)
        self.assertEqual(routed.front_matter("action"), "pdlc-triage")
        self.assertIn("PR #901: FAILURE", routed.stdout)

        result = self.invoke("post_triage", 80, "Implementation", "text:PR #901 failed in production retry handling")
        self.assertEqual(result.code, 0, result.stderr)
        self.assertEqual(self.state(80), ("Implementation", "Changes Required"))
        self.assertIn("Triage target stage: Implementation", self.comments_text(80))
        self.assertIn("Live PR triage", self.invoke("inspect_changes", 80).stdout)
        self.assertEqual(self.next("--work-item", 80).front_matter("action"), "pdlc-implement")

    def test_review_thread_routes_testing_and_blocks_completion(self):
        self.seed_record(81, "Verification", "Approval Required")
        self.green_pr(81, number=901)
        with patch("pdlc.internal.triage.record_open_review_comments", return_value=[THREAD]):
            inspected = self.invoke("inspect", 81, "--full")
            routed = self.next("--work-item", 81)
            refused = self.invoke("post_complete", 81, "text:incomplete")
            result = self.invoke("post_triage", 81, "Testing", f"text:{THREAD['url']} needs a test-only fix")
        self.assertIn("pdlc guide triage-pr-review", inspected.stdout)
        self.assertEqual(routed.front_matter("action"), "pdlc-triage")
        self.assertIn("require triage", refused.stderr)
        self.assertEqual(result.code, 0, result.stderr)
        self.assertEqual(self.state(81), ("Testing", "Changes Required"))
        self.assertEqual(self.next("--work-item", 81).front_matter("action"), "pdlc-test")

    def test_approval_force_cannot_bypass_live_signal(self):
        self.seed_record(82, "Implementation", "Approval Required")
        self.green_pr(82, number=902, checks="ERROR")
        result = self.invoke("post_approve", 82, "text:approved", "--force")
        self.assertEqual(result.code, 1)
        self.assertIn("require triage", result.stderr)
        self.assertEqual(self.state(82), ("Implementation", "Approval Required"))

    def test_no_live_signal_or_disallowed_target_cannot_transition(self):
        self.seed_record(83, "Implementation", "Approval Required")
        self.green_pr(83, number=903)
        empty = self.invoke("post_triage", 83, "Implementation", "text:PR #903 failed")
        self.assertEqual(empty.code, 1)
        self.green_pr(83, number=903, checks="FAILURE")
        wrong = self.invoke("post_triage", 83, "Testing", "text:PR #903 failed")
        self.assertEqual(wrong.code, 1)
        self.assertEqual(self.state(83), ("Implementation", "Approval Required"))

    def test_pre_delivery_gate_ignores_pr_signals(self):
        self.seed_record(84, "Technical Plan", "Approval Required")
        self.green_pr(84, number=904, checks="FAILURE")
        self.assertEqual(self.next("--work-item", 84).front_matter("action"), "human-approval")

    def test_implementation_pending_with_registered_pr_routes_triage(self):
        self.seed_record(85, "Implementation", "Pending")
        self.green_pr(85, number=905, checks="FAILURE")
        self.assertEqual(self.next("--work-item", 85).front_matter("action"), "pdlc-triage")
        result = self.invoke("post_triage", 85, "Implementation", "text:PR #905 failed in production code")
        self.assertEqual(result.code, 0, result.stderr)
        self.assertEqual(self.next("--work-item", 85).front_matter("action"), "pdlc-implement")

    def test_reentry_clears_a_previous_skip_of_the_target_stage(self):
        self.seed_record(86, "Verification", "Approval Required", skipped="Implementation")
        self.green_pr(86, number=906, checks="FAILURE")
        result = self.invoke("post_triage", 86, "Implementation", "text:PR #906 needs production repair")
        self.assertEqual(result.code, 0, result.stderr)
        self.assertEqual(self.fields(86)["Skipped States"], "")
        self.assertEqual(self.next("--work-item", 86).front_matter("action"), "pdlc-implement")

    def test_queue_scan_can_select_triage_from_an_approval_gate(self):
        self.seed_record(87, "Verification", "Approval Required")
        self.green_pr(87, number=907, checks="FAILURE")
        self.seed_record(88, "Product", "Approval Required")
        result = self.next()
        self.assertEqual(result.front_matter("action"), "pdlc-triage")
        self.assertEqual(result.front_matter("work_item_number"), "87")

    def test_changes_required_keeps_handled_thread_with_owner_but_routes_new_thread(self):
        self.seed_record(89, "Verification", "Approval Required")
        self.green_pr(89, number=901)
        later = {**THREAD, "url": "https://example.test/pr/901#thread-2", "body": "Cover cancellation"}
        with patch("pdlc.internal.triage.record_open_review_comments", return_value=[THREAD]) as threads:
            first = self.invoke("post_triage", 89, "Implementation", f"text:{THREAD['url']} needs production work")
            self.assertEqual(first.code, 0, first.stderr)
            self.assertEqual(self.next("--work-item", 89).front_matter("action"), "pdlc-implement")
            threads.return_value = [THREAD, later]
            routed = self.next("--work-item", 89)
            self.assertEqual(routed.front_matter("action"), "pdlc-triage")
            self.assertIn(later["url"], routed.stdout)
            self.assertNotIn(THREAD["url"], routed.stdout)
            second = self.invoke("post_triage", 89, "Implementation", f"text:{later['url']} needs production work")
            self.assertEqual(second.code, 0, second.stderr)
            self.assertEqual(self.next("--work-item", 89).front_matter("action"), "pdlc-implement")
