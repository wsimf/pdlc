"""`pdlc next` routing: per-item lookups, the queue scan, Complete records,
and the retry loop's give-up path."""

import importlib
import unittest.mock

from _support import FileBackendTest

next_command = importlib.import_module("pdlc.commands.next")


class RoutingTests(FileBackendTest):
    def _seed_lifecycle_spread(self) -> None:
        self.seed_record(14, "Product", "Changes Required")
        self.seed_record(15, "Product", "Approval Required")
        self.seed_record(16, "Complete", "Approved")
        self.seed_record(17, "UI", "Pending")
        self.seed_record(18, "Tasks", "Pending")
        self.seed_record(19, "Technical Plan", "Pending")
        self.seed_record(20, "Implementation", "Pending")
        self.seed_record(21, "Testing", "Pending")
        self.seed_record(22, "Verification", "Pending")

    def test_queue_scan_skips_product_and_dispatches_first_autonomous(self):
        self._seed_lifecycle_spread()
        result = self.next()
        self.assertEqual(result.code, 0)
        self.assertEqual(result.front_matter("action"), "pdlc-tasks")
        self.assertEqual(result.front_matter("work_item_number"), "17")

    def test_queue_scan_ignores_drafts_and_resolves_only_the_selected_issue(self):
        def summary(number: int, status: str, gate: str) -> dict:
            return {
                "id": f"PVTI_{number}",
                "content": {"number": number, "title": f"Work {number}", "url": "u"},
                "Status": status,
                "Gate State": gate,
                "Lifecycle": "Planning",
                "Skipped States": "",
                "workType": "feature",
            }

        selected = summary(17, "UI", "Pending")
        queue = [
            {"id": "PVTI_draft", "content": {}},
            summary(15, "Product", "Approval Required"),
            selected,
            summary(18, "Tasks", "Pending"),
        ]
        with (
            unittest.mock.patch.object(next_command, "queue_items", return_value=queue),
            unittest.mock.patch.object(next_command, "resolve_item", return_value=selected) as resolve,
        ):
            result = next_command.scan_for_candidate()

        self.assertEqual(result, selected)
        resolve.assert_called_once_with("17")

    def test_product_changes_required_stops_for_human_input(self):
        self._seed_lifecycle_spread()
        result = self.next("--work-item", 14)
        self.assertEqual(result.front_matter("action"), "human-input")
        self.assertEqual(result.front_matter("current_status"), "Product.ChangesRequired")
        self.assertIsNone(result.front_matter("next_status"))

    def test_queue_scan_surfaces_product_as_human_input_when_no_autonomous_work_exists(self):
        self.seed_record(14, "Product", "Changes Required")
        result = self.next("loop")
        self.assertEqual(result.front_matter("action"), "human-input")
        self.assertEqual(result.front_matter("work_item_number"), "14")
        self.assertIsNone(result.front_matter("attempts"))
        self.assertIn("invoke `pdlc-write`", result.stdout)
        self.assertNotIn("retrying", result.stderr)

    def test_product_approval_required_stops_for_human(self):
        self._seed_lifecycle_spread()
        result = self.next("--work-item", 15)
        self.assertEqual(result.front_matter("action"), "human-approval")
        self.assertIsNone(result.front_matter("next_status"))

    def test_each_stage_routes_to_its_specialist(self):
        self._seed_lifecycle_spread()
        for number, action in (
            (17, "pdlc-tasks"),
            (18, "pdlc-tasks"),
            (19, "pdlc-plan"),
            (20, "pdlc-implement"),
            (21, "pdlc-test"),
            (22, "pdlc-verify"),
        ):
            with self.subTest(number=number):
                result = self.next("--work-item", number)
                self.assertEqual(result.front_matter("action"), action)

    def test_complete_record_reports_done(self):
        self._seed_lifecycle_spread()
        result = self.next("--work-item", 16)
        self.assertEqual(result.front_matter("action"), "none")
        self.assertIn("# Complete", result.stdout)

    def test_loop_gives_up_and_reports_attempt_count(self):
        self.seed_record(16, "Complete", "Approved")
        self.configure(
            max_attempts=3,
            initial_delay_seconds=0,
            max_delay_seconds=0,
        )
        result = self.next("loop")
        self.assertEqual(result.front_matter("action"), "none")
        self.assertEqual(result.front_matter("attempts"), "3")
        self.assertIn("Invoke this script again", result.stdout)

    def test_unknown_state_is_blocked(self):
        self.seed_record(30, "Implementation", "Bogus Gate")
        result = self.next("--work-item", 30)
        self.assertEqual(result.front_matter("action"), "blocked")

    def test_unknown_stage_is_blocked(self):
        self.seed_record(34, "Unknown", "Pending")
        result = self.next("--work-item", 34)
        self.assertEqual(result.front_matter("action"), "blocked")

    def test_legacy_record_without_type_routes_as_feature(self):
        self.seed_record(31, "Implementation", "Pending")
        result = self.next("--work-item", 31)
        self.assertEqual(result.front_matter("action"), "pdlc-implement")

    def test_known_unavailable_bug_type_is_blocked(self):
        self.seed_record(32, "Implementation", "Pending", work_type="bug")
        result = self.next("--work-item", 32)
        self.assertEqual(result.front_matter("action"), "blocked")
        self.assertIn("Workflow unavailable for work type: bug", result.stdout)

    def test_unknown_work_type_is_blocked(self):
        self.seed_record(33, "Implementation", "Pending", work_type="chore")
        result = self.next("--work-item", 33)
        self.assertEqual(result.front_matter("action"), "blocked")
        self.assertIn("Stop here and let the user know this workflow is not supported", result.stdout)
        self.assertIn("Unknown work type: chore", result.stdout)
