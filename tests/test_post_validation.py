"""Backend-independent validation in `pdlc post tasks`, `pdlc post plan`, and
`pdlc post write` — coverage, dependency, identity, and section-shape rules,
plus the re-author-in-place / return-to-Stale guard — and the gate guards every
`pdlc post` command applies at Review Required and Decision Required."""

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

    def test_manifest_field_types_are_rejected_without_traceback(self):
        result = self._dry_run([{"id": 1, "title": "Bad", "body": self.body_file,
                                 "ui": False, "covers": ["FR-1"]}])
        self.assertEqual(result.code, 1)
        self.assertIn("id must be a string", result.stderr)

        result = self._dry_run([{"id": "TASK-001", "title": "Bad", "body": self.body_file,
                                 "ui": False, "covers": "FR-1"}])
        self.assertEqual(result.code, 1)
        self.assertIn("covers must be an array of strings", result.stderr)

        result = self._dry_run([{"id": "TASK-nope", "title": "Bad", "body": self.body_file,
                                 "ui": False, "covers": ["FR-1"]}])
        self.assertEqual(result.code, 1)
        self.assertIn("malformed task id", result.stderr)

        result = self._dry_run([{"id": "TASK-001", "title": "Bad", "body": self.body_file,
                                 "ui": False, "covers": ["FR-1"], "depends": [1]}])
        self.assertEqual(result.code, 1)
        self.assertIn("depends must be an array of strings", result.stderr)

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

    def test_review_and_changes_required_land_at_approval_required(self):
        for number, gate in ((33, "Review Required"), (34, "Changes Required")):
            with self.subTest(gate=gate):
                self.seed_record(number, "Tasks", gate)
                manifest = self.write_file(f"m{number}.json", json.dumps([
                    {"title": "A", "body": self.body_file, "ui": True, "covers": ["FR-1", "UJ-1"]}
                ]))
                dry = self.invoke("post_tasks", "--work-item", number, "--stage", "Tasks",
                                  "--manifest", manifest, "--dry-run")
                self.assertEqual(dry.code, 0, dry.stderr)
                self.assertEqual(self.fields(number)["Gate State"], gate)
                landed = self.invoke("post_tasks", "--work-item", number, "--stage", "Tasks",
                                     "--manifest", manifest, "--evidence", self.evidence_file())
                self.assertEqual(landed.code, 0, landed.stderr)
                self.assertEqual(self.fields(number)["Gate State"], "Approval Required")

    def test_decision_required_points_at_the_decisions_guide(self):
        self.seed_record(35, "Tasks", "Decision Required")
        manifest = self.write_file("m35.json", json.dumps([
            {"title": "A", "body": self.body_file, "ui": True, "covers": ["FR-1", "UJ-1"]}
        ]))
        result = self.invoke("post_tasks", "--work-item", 35, "--stage", "Tasks",
                             "--manifest", manifest, "--evidence", self.evidence_file())
        self.assertEqual(result.code, 1)
        self.assertIn("pdlc guide decisions", result.stderr)
        self.assertEqual(self.fields(35)["Gate State"], "Decision Required")

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
        self.plan_body = self.write_file("plan-body.md", "Files: core_service.py\n")

    def _dry_run(self, entries):
        manifest = self.write_file("pm.json", json.dumps(entries))
        return self.invoke("post_plan", "--work-item", 40, "--manifest", manifest, "--dry-run")

    def test_only_the_unplanned_task_is_targeted(self):
        result = self._dry_run([{"id": "TASK-001", "plan": self.plan_body}])
        self.assertEqual(result.code, 0, result.stderr)
        self.assertEqual(result.front_matter("Verdict"), "Pass")
        self.assertEqual(result.front_matter("Targeted"), "TASK-001")
        self.assertEqual(result.front_matter("Already planned"), "TASK-002")
        self.assertIn("## Warnings", result.stdout)
        self.assertIn("None.", result.stdout)

    def test_empty_plan_file_is_rejected(self):
        empty = self.write_file("empty.md", "\n")
        result = self._dry_run([{"id": "TASK-001", "plan": empty}])
        self.assertEqual(result.code, 1)
        self.assertEqual(result.front_matter("Verdict"), "Fail")
        self.assertIn("the plan file for TASK-001 is empty", result.stdout)

    def test_unknown_task_is_rejected(self):
        result = self._dry_run([{"id": "TASK-404", "plan": self.plan_body}])
        self.assertEqual(result.code, 1)
        self.assertEqual(result.front_matter("Verdict"), "Fail")
        self.assertIn("no such task on this record: TASK-404", result.stdout)

    def test_approval_required_dry_run_warns_instead_of_blocking(self):
        self.seed_record(41, "Technical Plan", "Approval Required")
        self.seed_task(41, 411, "TASK-001", "OPEN", "WORK-41-TASK-001 One")
        result = self.invoke(
            "post_plan", "--work-item", 41,
            "--manifest", self.write_file("pm41.json", json.dumps(
                [{"id": "TASK-001", "plan": self.plan_body}]
            )),
            "--dry-run",
        )
        self.assertEqual(result.code, 0, result.stdout)
        self.assertEqual(result.front_matter("Verdict"), "Pass")
        self.assertIn("Approval Required", result.stdout)
        self.assertIn("overwrite", result.stdout)
        self.assertEqual(self.fields(41)["Gate State"], "Approval Required")

    def test_changes_required_lands_like_stale(self):
        self.seed_record(42, "Technical Plan", "Changes Required")
        self.seed_task(42, 421, "TASK-001", "OPEN", "WORK-42-TASK-001 One")
        evidence = self.write_file("plan-evidence.md", "Re-planned after the resolved decision.\n")
        result = self.invoke(
            "post_plan", "--work-item", 42,
            "--manifest", self.write_file("pm42.json", json.dumps(
                [{"id": "TASK-001", "plan": self.plan_body}]
            )),
            "--evidence", evidence,
        )
        self.assertEqual(result.code, 0, result.stderr)
        self.assertEqual(result.json["planned"], ["TASK-001"])
        self.assertEqual(self.fields(42)["Status"], "Technical Plan")
        self.assertEqual(self.fields(42)["Gate State"], "Approval Required")

    def test_review_required_re_lands_at_approval_required(self):
        self.seed_record(43, "Technical Plan", "Review Required")
        self.seed_task(43, 431, "TASK-001", "OPEN", "WORK-43-TASK-001 One")
        manifest = self.write_file("pm43.json", json.dumps(
            [{"id": "TASK-001", "plan": self.plan_body}]
        ))
        dry = self.invoke("post_plan", "--work-item", 43, "--manifest", manifest, "--dry-run")
        self.assertEqual(dry.code, 0, dry.stderr)
        self.assertEqual(self.fields(43)["Gate State"], "Review Required")
        evidence = self.write_file("plan-evidence-43.md", "Reviewed the published plan.\n")
        result = self.invoke("post_plan", "--work-item", 43, "--manifest", manifest, "--evidence", evidence)
        self.assertEqual(result.code, 0, result.stderr)
        self.assertEqual(self.fields(43)["Gate State"], "Approval Required")

    def test_blocking_gates_are_refused_without_writing(self):
        for number, gate, expected in (
            (44, "Decision Required", "pdlc guide decisions"),
            (45, "Approved", "cannot land Technical Plan from Gate State: Approved"),
        ):
            with self.subTest(gate=gate):
                self.seed_record(number, "Technical Plan", gate)
                self.seed_task(number, number * 10 + 1, "TASK-001", "OPEN", f"WORK-{number}-TASK-001 One")
                result = self.invoke(
                    "post_plan", "--work-item", number,
                    "--manifest", self.write_file(f"pm{number}.json", json.dumps(
                        [{"id": "TASK-001", "plan": self.plan_body}]
                    )),
                    "--dry-run",
                )
                self.assertEqual(result.code, 1)
                self.assertIn(expected, result.stderr)
                self.assertEqual(self.fields(number)["Gate State"], gate)


class PostWriteReconstructionTests(FileBackendTest):
    def _rewrite(self, number):
        rewrite = self.write_file(
            f"rewrite-{number}.md",
            "## Product\nnew product\n\n## Decisions\nnew decision\n\n## Open Questions\nnew question\n",
        )
        return self.invoke("post_write", "--work-item", number,
                           "--evidence", self.evidence_file(), "--body", rewrite)

    def test_review_required_re_lands_at_approval_required(self):
        self.seed_record(52, "Product", "Review Required", body="## Product\nold\n")
        result = self._rewrite(52)
        self.assertEqual(result.code, 0, result.stderr)
        self.assertEqual(self.fields(52)["Gate State"], "Approval Required")

    def test_decision_required_points_at_the_decisions_guide(self):
        self.seed_record(53, "Product", "Decision Required", body="## Product\nold\n")
        result = self._rewrite(53)
        self.assertEqual(result.code, 1)
        self.assertIn("pdlc guide decisions", result.stderr)
        self.assertEqual(self.fields(53)["Gate State"], "Decision Required")

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


class DecisionRequiredGuardTests(FileBackendTest):
    def test_approve_and_ci_point_at_the_decisions_guide(self):
        self.seed_record(60, "Implementation", "Decision Required")
        for command, args in (
            ("post_approve", (60, self.evidence_file())),
            ("post_ci", (60,)),
        ):
            with self.subTest(command=command):
                result = self.invoke(command, *args)
                self.assertEqual(result.code, 1)
                self.assertIn("pdlc guide decisions", result.stderr)
        self.assertEqual(self.fields(60)["Gate State"], "Decision Required")


class DecisionRequiredEveryCommandTests(FileBackendTest):
    """Every stage-work `pdlc post` command refuses Decision Required with a
    pointer to the decisions guide, and leaves the gate untouched."""

    def _assert_refused(self, number, stage, command, *args):
        self.seed_record(number, stage, "Decision Required")
        result = self.invoke(command, *args)
        self.assertEqual(result.code, 1, result.stdout)
        self.assertIn("pdlc guide decisions", result.stderr)
        self.assertEqual(self.fields(number)["Gate State"], "Decision Required")

    def test_implement(self):
        self._assert_refused(61, "Implementation", "post_implement", 61, self.evidence_file())

    def test_test(self):
        traceability = self.write_file("trace.md", "FR-1 -> tests/test_x.py\n")
        self._assert_refused(62, "Testing", "post_test", 62, self.evidence_file(), "--traceability", traceability)

    def test_review(self):
        self._assert_refused(63, "Testing", "post_review", 63, "approval-required", self.evidence_file())

    def test_verify(self):
        report = self.write_file("report.md", "Findings.\n")
        self._assert_refused(64, "Verification", "post_verify", 64, report, "--recommendation", "Changes Required")

    def test_complete(self):
        self._assert_refused(65, "Verification", "post_complete", 65, self.evidence_file())

    def test_skip_declares_without_clearing_the_decision(self):
        # `post skip` only records Skipped States; it never moves the gate, so
        # the open decision still holds the stage until the driver resolves it.
        self.seed_record(66, "UI", "Decision Required")
        result = self.invoke("post_skip", "--work-item", 66, "--state", "UI")
        self.assertEqual(result.code, 0, result.stderr)
        self.assertEqual(self.fields(66)["Gate State"], "Decision Required")
        due = self.invoke("inspect", 66)
        self.assertIn("UI.DecisionRequired", due.stdout)


class DecisionRequiredExitTests(FileBackendTest):
    def test_invalidate_still_leaves_decision_required(self):
        self.seed_record(67, "Technical Plan", "Decision Required")
        result = self.invoke("post_invalidate", 67, "Tasks", self.evidence_file())
        self.assertEqual(result.code, 0, result.stderr)
        self.assertEqual((self.fields(67)["Status"], self.fields(67)["Gate State"]), ("Tasks", "Stale"))


class PostTasksUiGateTests(FileBackendTest):
    def test_ui_review_and_changes_required_land_at_approval_required(self):
        body = self.write_file("ui.md", "## UI\n\nUJ-1 covers the first run.\n")
        for number, gate in ((36, "Review Required"), (37, "Changes Required")):
            with self.subTest(gate=gate):
                self.seed_record(number, "UI", gate)
                dry = self.invoke("post_tasks", "--work-item", number, "--stage", "UI", "--body", body, "--dry-run")
                self.assertEqual(dry.code, 0, dry.stderr)
                self.assertEqual(self.fields(number)["Gate State"], gate)
                landed = self.invoke("post_tasks", "--work-item", number, "--stage", "UI",
                                     "--body", body, "--evidence", self.evidence_file())
                self.assertEqual(landed.code, 0, landed.stderr)
                self.assertEqual(self.fields(number)["Gate State"], "Approval Required")
