"""A UI fragment lands only as the tasks reviewer was handed it."""

from __future__ import annotations

from pathlib import Path

from tests._support import FileBackendTest

FRAGMENT = "## UI\n\nUJ-1 covers the first run.\n"


class UiReviewStampTest(FileBackendTest):
    def _reviewed(self, record: int) -> str:
        self.seed_record(record, "UI", "Pending", slug=f"record-{record}")
        fragment = self.write_file("ui.md", FRAGMENT)
        brief = self.invoke("prompt_tasks_reviewer", record, "--fragment", fragment)
        self.assertEqual(brief.code, 0, brief.stderr)
        return fragment

    def _land(self, record: int, fragment: str):
        return self.invoke("post_tasks", "--work-item", record, "--stage", "UI", "--body", fragment, "--evidence", self.evidence_file())

    def test_a_text_fragment_is_refused(self):
        self.seed_record(60, "UI", "Pending", slug="record-60")
        result = self.invoke("prompt_tasks_reviewer", 60, "--fragment", "text:UJ-1 covers the first run.")
        self.assertEqual(result.code, 1)
        self.assertIn("--fragment takes the UI fragment's FILE", result.stderr)

    def test_the_reviewed_fragment_lands_and_its_stamp_clears(self):
        fragment = self._reviewed(60)
        landed = self._land(60, fragment)
        self.assertEqual(landed.code, 0, landed.stderr)
        # The stamp is spent: re-authoring with the same file needs a fresh review.
        again = self._land(60, fragment)
        self.assertEqual(again.code, 1)
        self.assertIn("has not been reviewed since its last planning pass", again.stderr)

    def test_an_unreviewed_fragment_is_refused_and_nothing_is_written(self):
        self.seed_record(60, "UI", "Pending", slug="record-60")
        fragment = self.write_file("ui.md", FRAGMENT)
        dry = self.invoke("post_tasks", "--work-item", 60, "--stage", "UI", "--body", fragment, "--dry-run")
        self.assertEqual(dry.code, 0, dry.stderr)
        landed = self._land(60, fragment)
        self.assertEqual(landed.code, 1)
        self.assertIn(f"refusing to land: {Path(fragment).resolve()} has not been reviewed", landed.stderr)
        self.assertIn(f"pdlc prompt tasks-reviewer 60 --fragment {Path(fragment).resolve()} --file", landed.stderr)
        self.assertEqual(self.fields(60)["Gate State"], "Pending")

    def test_a_different_file_than_the_reviewed_one_is_refused(self):
        self._reviewed(60)
        other = self.write_file("other-ui.md", FRAGMENT)
        landed = self._land(60, other)
        self.assertEqual(landed.code, 1)
        self.assertIn("has not been reviewed", landed.stderr)

    def test_an_edit_after_review_is_restored_and_kept_beside_it(self):
        fragment = self._reviewed(60)
        Path(fragment).write_text("## UI\n\nUJ-1 edited by the reviewer.\n", encoding="utf-8")
        dry = self.invoke("post_tasks", "--work-item", 60, "--stage", "UI", "--body", fragment, "--dry-run")
        self.assertEqual(dry.code, 1)
        self.assertIn("pdlc restored each file to the version the reviewer was given", dry.stderr)
        self.assertIn(f"pdlc prompt ui-planner 60 --current-journeys-path {Path(fragment).resolve()} --file", dry.stderr)
        self.assertEqual(Path(fragment).read_text(encoding="utf-8"), FRAGMENT)
        self.assertIn("edited by the reviewer", (Path(fragment).parent / "ui.rejected.md").read_text(encoding="utf-8"))
        # Restored, the reviewed file lands.
        self.assertEqual(self._land(60, fragment).code, 0)

    def test_a_planning_pass_keeps_its_edits_and_needs_a_new_review(self):
        fragment = self._reviewed(60)
        brief = self.invoke("prompt_ui_planner", 60, "--current-journeys-path", fragment)
        self.assertEqual(brief.code, 0, brief.stderr)
        Path(fragment).write_text("## UI\n\nUJ-1 revised by the planner.\n", encoding="utf-8")
        landed = self._land(60, fragment)
        self.assertEqual(landed.code, 1)
        self.assertIn("has not been reviewed", landed.stderr)
        self.assertIn("revised by the planner", Path(fragment).read_text(encoding="utf-8"))
