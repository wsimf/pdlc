"""Backend-independent validation in `pdlc post tasks`, `pdlc post plan`, and
`pdlc post write` — coverage, dependency, identity, and section-shape rules,
plus the re-author-in-place / return-to-Stale guard."""

import json

from _support import FileBackendTest


class PostTasksValidationTests(FileBackendTest):
    def setUp(self):
        super().setUp()
        self.seed_record(30, "Tasks", "Pending")
        self.seed_task(30, 301, "TASK-001", "OPEN", "WORK-30-TASK-001 Old wording")
        self.seed_task(30, 309, "TASK-009", "OPEN", "WORK-30-TASK-009 Dropped")
        self.body_file = self.write_file("task-body.md", "task body\n")

    def _dry_run(self, tasks):
        manifest = self.write_file("m.json", json.dumps(tasks))
        return self.invoke("post_tasks", "--work-item", 30, "--stage", "Tasks",
                           "--manifest", manifest, "--dry-run")

    def test_valid_breakdown_assigns_ids_orders_and_flags_orphans(self):
        result = self._dry_run([
            {"id": "TASK-001", "title": "Reworded", "body": self.body_file,
             "ui": False, "covers": ["FR-1", "C-1"]},
            {"title": "Ship the journey", "body": self.body_file, "ui": True,
             "covers": ["FR-2", "UJ-1"], "depends": ["TASK-001"]},
        ])
        self.assertEqual(result.code, 0, result.stderr)
        self.assertEqual(result.json["tasks"][1]["id"], "TASK-010")
        self.assertEqual(result.json["order"], ["TASK-001", "TASK-010"])
        self.assertEqual(result.json["orphans"], ["TASK-009"])

    def test_rejections(self):
        cases = [
            ("covers FR-99, which the parent does not declare",
             [{"id": "TASK-001", "title": "Typo", "body": self.body_file, "covers": ["FR-99"]}]),
            ("is a UI task but covers no UJ-*",
             [{"id": "TASK-001", "title": "U", "body": self.body_file, "ui": True, "covers": ["FR-1"]}]),
            ("dependency cycle", [
                {"id": "TASK-001", "title": "A", "body": self.body_file, "ui": True,
                 "covers": ["FR-1", "UJ-1"], "depends": ["TASK-002"]},
                {"id": "TASK-002", "title": "B", "body": self.body_file,
                 "covers": ["FR-2"], "depends": ["TASK-001"]},
            ]),
            ("duplicate task id: TASK-001", [
                {"id": "TASK-001", "title": "A", "body": self.body_file, "ui": True, "covers": ["FR-1", "UJ-1"]},
                {"id": "TASK-001", "title": "B", "body": self.body_file, "covers": ["FR-2"]},
            ]),
        ]
        for needle, tasks in cases:
            with self.subTest(needle=needle):
                result = self._dry_run(tasks)
                self.assertEqual(result.code, 1)
                self.assertIn(needle, result.stderr)

    def test_approval_required_record_must_return_to_stale_before_dry_run(self):
        self.seed_record(31, "Tasks", "Approval Required")
        manifest = self.write_file("m2.json", json.dumps([
            {"id": "TASK-001", "title": "A", "body": self.body_file, "ui": True, "covers": ["FR-1", "UJ-1"]}
        ]))
        dry = self.invoke("post_tasks", "--work-item", 31, "--stage", "Tasks",
                          "--manifest", manifest, "--dry-run")
        self.assertEqual(dry.code, 1)
        self.assertIn("return it to Stale with pdlc post invalidate", dry.stderr)
        reauth = self.invoke("post_tasks", "--work-item", 31, "--stage", "Tasks",
                             "--manifest", manifest, "--evidence", self.evidence_file())
        self.assertEqual(reauth.json["gateState"], "Approval Required")
        self.assertNotIn("PDLC-INVALIDATED", self.comments_text(31))

    def test_ui_applicability_must_be_explicit(self):
        self.seed_record(32, "UI", "Pending")
        ok = self.write_file("ui-ok.md", "## UI\n\nUJ-1 covers the first run.\n")
        result = self.invoke("post_tasks", "--work-item", 32, "--stage", "UI",
                             "--body", ok, "--dry-run")
        self.assertEqual(result.json["journeys"], ["UJ-1"])
        vague = self.write_file("vague.md", "Some prose that decides nothing.\n")
        rejected = self.invoke("post_tasks", "--work-item", 32, "--stage", "UI",
                               "--body", vague, "--dry-run")
        self.assertEqual(rejected.code, 1)
        self.assertIn("UI applicability must be explicit", rejected.stderr)


class PostPlanValidationTests(FileBackendTest):
    def setUp(self):
        super().setUp()
        self.seed_record(40, "Technical Plan", "Pending")
        self.seed_task(40, 401, "TASK-001", "OPEN", "WORK-40-TASK-001 One")
        self.seed_task(40, 402, "TASK-002", "OPEN", "WORK-40-TASK-002 Two")
        # TASK-002 already carries a plan comment.
        comment = {
            "body": "## Technical Plan\n\nalready planned\n",
            "createdAt": "2026-01-01T00:00:00Z", "url": "u", "author": {"login": "x"},
        }
        (self.records_dir() / "40" / "tasks" / "402" / "comments.jsonl").write_text(
            json.dumps(comment) + "\n"
        )
        self.plan_body = self.write_file("plan-body.md", "Files: CoreService.swift\n")

    def _dry_run(self, entries):
        manifest = self.write_file("pm.json", json.dumps(entries))
        return self.invoke("post_plan", "--work-item", 40, "--manifest", manifest, "--dry-run")

    def test_only_the_unplanned_task_is_targeted(self):
        result = self._dry_run([{"id": "TASK-001", "plan": self.plan_body}])
        self.assertEqual(result.code, 0, result.stderr)
        self.assertEqual(result.json["targeted"], ["TASK-001"])
        self.assertEqual(result.json["alreadyPlanned"], ["TASK-002"])

    def test_empty_plan_file_is_rejected(self):
        empty = self.write_file("empty.md", "\n")
        result = self._dry_run([{"id": "TASK-001", "plan": empty}])
        self.assertEqual(result.code, 1)
        self.assertIn("the plan file for TASK-001 is empty", result.stderr)

    def test_unknown_task_is_rejected(self):
        result = self._dry_run([{"id": "TASK-404", "plan": self.plan_body}])
        self.assertEqual(result.code, 1)
        self.assertIn("no such task on this record: TASK-404", result.stderr)


class PostWriteReconstructionTests(FileBackendTest):
    def test_only_the_three_owned_sections_are_replaced(self):
        self.seed_record(50, "Product", "Stale", body=(
            "## Product\nold\n\n## UI\nowned later\n\n## Decisions\nold\n\n## Open Questions\nold\n"
        ))
        rewrite = self.write_file(
            "rewrite.md",
            "## Product\nnew product\n\n## Decisions\nnew decision\n\n## Open Questions\nnew question\n",
        )
        result = self.invoke("post_write", "--work-item", 50,
                             "--evidence", self.evidence_file(), "--body", rewrite)
        self.assertEqual(result.code, 0, result.stderr)
        body = self.body(50)
        self.assertIn("new product", body)
        self.assertIn("owned later", body)
        self.assertEqual(self.fields(50)["Gate State"], "Approval Required")

    def test_approval_required_record_is_reauthored_in_place(self):
        self.seed_record(51, "Product", "Approval Required")
        reauthor = self.write_file(
            "reauthor.md", "## Product\nrevised\n\n## Decisions\nd\n\n## Open Questions\nq\n"
        )
        result = self.invoke("post_write", "--work-item", 51,
                             "--evidence", self.evidence_file(), "--body", reauthor)
        self.assertEqual(result.json["gateState"], "Approval Required")
        self.assertIn("revised", self.body(51))
        self.assertNotIn("PDLC-INVALIDATED", self.comments_text(51))
