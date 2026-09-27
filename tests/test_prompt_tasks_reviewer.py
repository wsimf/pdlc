"""`pdlc prompt tasks-reviewer` renders the brief for a UI fragment or Tasks breakdown."""

from __future__ import annotations

import json
from unittest import mock

from tests._support import FileBackendTest


class PromptTasksReviewerTest(FileBackendTest):
    def test_removed_task_lookup_requires_exactly_one_result(self):
        self.seed_record(60, "Tasks", "Pending", slug="record-60")
        manifest = self.write_file(
            "manifest.json",
            json.dumps([{"id": "TASK-001", "number": 42, "action": "remove", "reason": "Superseded"}]),
        )
        for matches in ([], [{"title": "First"}, {"title": "Second"}]):
            with self.subTest(count=len(matches)):
                with mock.patch("pdlc.commands.prompt.tasks_by_number", return_value=matches):
                    result = self.invoke("prompt_tasks_reviewer", 60, "--manifest", manifest)
                self.assertNotEqual(result.code, 0)
                self.assertEqual(result.stdout, "")
                self.assertIn(
                    f"removed task TASK-001 (issue 42): expected one stored task, found {len(matches)}",
                    result.stderr,
                )

    def test_a_manifest_carries_every_task_body_in_full(self):
        self.seed_record(60, "Tasks", "Pending", slug="record-60")
        task_body = self.write_file("task1.md", "## Scope\nBuild the seam.\n\nCovers FR-1.\n")
        manifest = self.write_file(
            "manifest.json",
            json.dumps([{"id": "TASK-001", "title": "Build it", "body": task_body, "ui": False, "covers": ["FR-1"]}]),
        )
        result = self.invoke("prompt_tasks_reviewer", 60, "--manifest", manifest)
        self.assertEqual(result.code, 0, result.stderr)
        self.assertIn("Review the supplied local artifact", result.stdout)
        self.assertIn("### TASK-001 — Build it", result.stdout)
        self.assertIn("Build the seam.", result.stdout)
        self.assertIn("FR-1: The record lands.", result.stdout)
        self.assertIn("none, first review", result.stdout)
        self.assertNotIn("{{", result.stdout)

    def test_an_unchanged_entry_is_noted_rather_than_dumped(self):
        self.seed_record(60, "Tasks", "Pending", slug="record-60")
        manifest = self.write_file(
            "manifest.json", json.dumps([{"id": "TASK-001", "unchanged": True, "covers": ["FR-1"]}]),
        )
        result = self.invoke("prompt_tasks_reviewer", 60, "--manifest", manifest)
        self.assertEqual(result.code, 0, result.stderr)
        self.assertIn("(unchanged — carried forward from the record)", result.stdout)

    def test_a_fragment_is_inlined_directly(self):
        self.seed_record(60, "UI", "Pending", slug="record-60")
        result = self.invoke("prompt_tasks_reviewer", 60, "--fragment", "text:**UI Phase:** Not required.")
        self.assertEqual(result.code, 0, result.stderr)
        self.assertIn("**UI Phase:** Not required.", result.stdout)

    def test_findings_render_for_a_re_review(self):
        self.seed_record(60, "UI", "Pending", slug="record-60")
        result = self.invoke(
            "prompt_tasks_reviewer", 60, "--fragment", "text:content", "--findings", "text:tighten UJ-1",
        )
        self.assertIn("tighten UJ-1", result.stdout)
        self.assertNotIn("none, first review", result.stdout)

    def test_refuses_when_both_or_neither_artifact_flag_is_given(self):
        self.seed_record(60, "Tasks", "Pending", slug="record-60")
        result = self.invoke("prompt_tasks_reviewer", 60)
        self.assertNotEqual(result.code, 0)
        self.assertIn("exactly one of --manifest or --fragment", result.stderr)
