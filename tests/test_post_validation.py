"""Backend-independent validation in `pdlc post tasks`, `pdlc post plan`, and
`pdlc post write` — coverage, dependency, identity, and section-shape rules,
plus the re-author-in-place / return-to-Stale guard — and the gate guards every
`pdlc post` command applies at Review Required and Decision Required."""

import json
from pathlib import Path
from unittest import mock

from _support import TASK_BODY_DEFAULT, FileBackendTest
from pdlc.domain.lifecycle import PdlcError
from pdlc.domain.task_artifact import snapshot, stored_fields
from pdlc.internal.workitem import subissues_for


class PostTasksValidationTests(FileBackendTest):
    def setUp(self):
        super().setUp()
        self.seed_record(30, "Tasks", "Pending")
        self.seed_task(30, 301, "TASK-001", "OPEN", "WORK-30-TASK-001 Old wording")
        self.seed_task(30, 309, "TASK-009", "OPEN", "WORK-30-TASK-009 Dropped")
        self.body_file = self.write_file("task-body.md", "**Type:** AFK\n**Scope:**\nLand the task.\n\n**Acceptance Criteria:**\n- [ ] The task works.\n")
        self.body_count = 0

    def _body(self, requirements: str, *, journeys: str = "", blocked: str = "None") -> str:
        self.body_count += 1
        journey_line = f"**UI Journeys:** {journeys}\n" if journeys else ""
        return self.write_file(
            f"task-body-{self.body_count}.md",
            f"**Blocked by:** {blocked}\n**Type:** AFK\n**Requirements Covered:** {requirements}\n{journey_line}\n**Scope:**\nLand the task.\n\n**Acceptance Criteria:**\n- [ ] The task works.\n",
        )

    def _retain(self, task_id: str, **fields) -> dict:
        """A retain entry naming the seeded TASK-001, so re-landing it edits
        that task instead of tripping the id-needs-an-action refusal."""
        stored = next(task for task in subissues_for("30") if task.get("taskId") == task_id)
        entry = {"id": task_id, "number": stored["number"], "action": "retain",
                  "baseline": snapshot(stored_fields(stored))}
        entry.update(fields)
        return entry

    def _dry_run(self, tasks):
        manifest = self.write_file("m.json", json.dumps(tasks))
        return self.invoke("post_tasks", "--work-item", 30, "--stage", "Tasks",
                           "--manifest", manifest, "--dry-run")

    def test_valid_breakdown_assigns_ids_orders_and_flags_orphans(self):
        # TASK-009 is not carried forward by this breakdown, so it must be
        # explicitly descoped: the orphan check refuses a silent drop.
        task_009 = next(task for task in subissues_for("30") if task.get("taskId") == "TASK-009")
        result = self._dry_run([
            self._retain("TASK-001", title="Reworded", body=self._body("FR-1, C-1"),
                         type="core", covers=["FR-1", "C-1"]),
            {"title": "Ship the journey", "body": self._body("FR-2", journeys="UJ-1", blocked="TASK-001"), "type": "ui",
             "covers": ["FR-2", "UJ-1"], "depends": ["TASK-001"]},
            {"id": "TASK-009", "number": task_009["number"], "action": "remove",
             "baseline": snapshot(stored_fields(task_009)), "reason": "Descoped"},
        ])
        self.assertEqual(result.code, 0, result.stderr)
        self.assertEqual(result.json["tasks"][1]["id"], "TASK-010")
        self.assertEqual(result.json["order"], ["TASK-001", "TASK-010"])
        self.assertEqual(result.json["removed"], ["TASK-009"])

    def test_body_structure_is_checked_before_publication(self):
        base = "**Blocked by:** None\n**Type:** AFK\n**Requirements Covered:** FR-1, FR-2, C-1\n**UI Journeys:** UJ-1\n\n**Scope:**\nDo work.\n\n**Acceptance Criteria:**\n- [ ] It works.\n"
        cases = [
            (base.replace("**Blocked by:** None\n", ""), "add **Blocked by:** None"),
            (base.replace("**Blocked by:** None", "**Blocked by:** later"), "**Blocked by:** must say None"),
            (base.replace("**Requirements Covered:** FR-1, FR-2, C-1\n", ""), "add **Requirements Covered:**"),
            (base.replace("**UI Journeys:** UJ-1\n", "").replace("FR-1, FR-2, C-1", "FR-1, FR-2, C-1, UJ-1"), "add **UI Journeys:**"),
            (base.replace("**Type:** AFK\n", ""), "add **Type:** AFK or HITL"),
            (base.replace("**Type:** AFK", "**Type:** maybe"), "add **Type:** AFK or HITL"),
            (base.replace("Do work.\n", ""), "add a nonempty **Scope:** section"),
            (base.replace("- [ ] It works.", "- [ ] "), "add at least one nonempty `- [ ]` item"),
        ]
        for body, message in cases:
            with self.subTest(message=message):
                path = self.write_file("invalid-task.md", body)
                result = self._dry_run([self._retain("TASK-001", title="Complete the record", body=path,
                                         type="ui", covers=["FR-1", "FR-2", "C-1", "UJ-1"])])
                self.assertEqual(result.code, 1)
                self.assertIn(f"TASK-001 body: {message}", result.stderr)
                self.assertEqual(self.fields(30)["Gate State"], "Pending")

    def test_invalid_body_does_not_publish_or_rewrite_a_task(self):
        manifest = self.write_file("invalid-body.json", json.dumps([
            self._retain("TASK-001", title="Changed", body=self.body_file,
                         type="ui", covers=["FR-1", "FR-2", "C-1", "UJ-1"]),
        ]))
        result = self.invoke("post_tasks", "--work-item", 30, "--stage", "Tasks",
                             "--manifest", manifest, "--evidence", self.evidence_file())
        self.assertEqual(result.code, 1)
        self.assertIn("TASK-001 body: add **Blocked by:** None", result.stderr)
        self.assertEqual(self.fields(30)["Gate State"], "Pending")
        self.assertEqual(self.task_meta(30, 301)["title"], "WORK-30-TASK-001 Old wording")

    def test_every_product_identifier_needs_task_coverage(self):
        result = self._dry_run([self._retain("TASK-001", title="Complete the record", body=self._body("FR-1", journeys="UJ-1"),
                                 type="ui", covers=["FR-1", "UJ-1"])])
        self.assertEqual(result.code, 1)
        self.assertIn("no task covers FR-2; add it to a task's covers and Requirements Covered line", result.stderr)
        self.assertIn("no task covers C-1; add it to a task's covers and Requirements Covered line", result.stderr)

    def test_rejections(self):
        cases = [
            ("covers FR-99, which the parent does not declare",
             [self._retain("TASK-001", title="Typo", body=self.body_file, type="core", covers=["FR-99"])]),
            ("is a UI task but covers no UJ-*",
             [self._retain("TASK-001", title="U", body=self.body_file, type="ui", covers=["FR-1"])]),
            ("dependency cycle", [
                self._retain("TASK-001", title="A", body=self.body_file, type="ui",
                             covers=["FR-1", "UJ-1"], depends=["TASK-002"]),
                {"id": "TASK-002", "action": "create", "title": "B", "body": self.body_file, "type": "core",
                 "covers": ["FR-2"], "depends": ["TASK-001"]},
            ]),
            ("duplicate task id: TASK-001", [
                self._retain("TASK-001", title="A", body=self.body_file, type="ui", covers=["FR-1", "UJ-1"]),
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

        result = self._dry_run([self._retain("TASK-001", title="Bad", body=self.body_file,
                                 type="core", covers="FR-1")])
        self.assertEqual(result.code, 1)
        self.assertIn("covers must be an array of strings", result.stderr)

        result = self._dry_run([{"id": "TASK-nope", "action": "create", "title": "Bad", "body": self.body_file,
                                 "type": "core", "covers": ["FR-1"]}])
        self.assertEqual(result.code, 1)
        self.assertIn("malformed task id", result.stderr)

        result = self._dry_run([self._retain("TASK-001", title="Bad", body=self.body_file,
                                 type="core", covers=["FR-1"], depends=[1])])
        self.assertEqual(result.code, 1)
        self.assertIn("depends must be an array of strings", result.stderr)

    def test_approval_required_record_must_return_to_stale_before_dry_run(self):
        self.seed_record(31, "Tasks", "Approval Required")
        manifest = self.write_file("m2.json", json.dumps([
            {"id": "TASK-001", "action": "create", "title": "A", "body": self._body("FR-1, FR-2, C-1", journeys="UJ-1"), "type": "ui", "covers": ["FR-1", "FR-2", "C-1", "UJ-1"]}
        ]))
        dry = self.invoke("post_tasks", "--work-item", 31, "--stage", "Tasks",
                          "--manifest", manifest, "--dry-run")
        self.assertEqual(dry.code, 1)
        self.assertIn("return it to Stale with pdlc post invalidate", dry.stderr)
        self.mark_tasks_reviewed(31, manifest)
        reauth = self.invoke("post_tasks", "--work-item", 31, "--stage", "Tasks",
                             "--manifest", manifest, "--evidence", self.evidence_file())
        self.assertEqual(reauth.json["gateState"], "Approval Required")
        self.assertNotIn("PDLC-INVALIDATED", self.comments_text(31))

    def test_review_and_changes_required_land_at_approval_required(self):
        for number, gate in ((33, "Review Required"), (34, "Changes Required")):
            with self.subTest(gate=gate):
                self.seed_record(number, "Tasks", gate)
                manifest = self.write_file(f"m{number}.json", json.dumps([
                    {"title": "A", "body": self._body("FR-1, FR-2, C-1", journeys="UJ-1"), "type": "ui", "covers": ["FR-1", "FR-2", "C-1", "UJ-1"]}
                ]))
                dry = self.invoke("post_tasks", "--work-item", number, "--stage", "Tasks",
                                  "--manifest", manifest, "--dry-run")
                self.assertEqual(dry.code, 0, dry.stderr)
                self.assertEqual(self.fields(number)["Gate State"], gate)
                self.mark_tasks_reviewed(number, manifest)
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

    def test_ui_journeys_are_required_without_the_no_ui_flag(self):
        self.seed_record(32, "UI", "Pending")
        ok = self.write_file("ui-ok.md", "## UI\n\nUJ-1 covers the first run.\n")
        result = self.invoke("post_tasks", "--work-item", 32, "--stage", "UI",
                             "--body", ok, "--dry-run")
        self.assertEqual(result.json["journeys"], ["UJ-1"])
        self.assertIs(result.json["uiRequired"], True)
        vague = self.write_file("vague.md", "Some prose that decides nothing.\n")
        rejected = self.invoke("post_tasks", "--work-item", 32, "--stage", "UI",
                               "--body", vague, "--dry-run")
        self.assertEqual(rejected.code, 1)
        self.assertIn("--no-ui", rejected.stderr)

    def test_no_ui_lands_a_rationale_the_wording_cannot_break(self):
        self.seed_record(33, "UI", "Pending")
        # The phrasing is deliberately none of the sentences the old regex
        # accepted: the flag carries applicability, the fragment carries why.
        body = self.write_file("no-ui.md", "**UI Phase:** Not required — the sync runs headless.\n")
        result = self.invoke("post_tasks", "--work-item", 33, "--stage", "UI",
                             "--body", body, "--no-ui", "--dry-run")
        self.assertEqual(result.code, 0)
        self.assertIs(result.json["uiRequired"], False)
        self.assertEqual(result.json["journeys"], [])

    def test_no_ui_is_refused_against_a_fragment_naming_journeys(self):
        self.seed_record(34, "UI", "Pending")
        body = self.write_file("both.md", "UJ-1 covers the first run.\n")
        result = self.invoke("post_tasks", "--work-item", 34, "--stage", "UI",
                             "--body", body, "--no-ui", "--dry-run")
        self.assertEqual(result.code, 1)
        self.assertIn("UJ-1", result.stderr)

    def test_no_ui_is_refused_on_the_tasks_stage(self):
        self.seed_record(36, "Tasks", "Pending")
        manifest = self.write_file("m36.json", json.dumps([
            {"title": "A", "body": self.body_file, "ui": False, "covers": ["FR-1"]}
        ]))
        result = self.invoke("post_tasks", "--work-item", 36, "--stage", "Tasks",
                             "--manifest", manifest, "--no-ui", "--dry-run")
        self.assertEqual(result.code, 1)
        self.assertIn("--no-ui is only valid with --stage UI", result.stderr)


class PostPlanValidationTests(FileBackendTest):
    def setUp(self):
        super().setUp()
        self.seed_record(40, "Technical Plan", "Pending")
        self.seed_task(40, 401, "TASK-001", "OPEN", "WORK-40-TASK-001 One", body=TASK_BODY_DEFAULT)
        self.seed_task(40, 402, "TASK-002", "OPEN", "WORK-40-TASK-002 Two", body=TASK_BODY_DEFAULT)
        # TASK-002 already carries a plan comment.
        self.seed_plan_comment(40, 402, "already planned\n")

    def _dry_run(self, manifest, record=40):
        return self.invoke("post_plan", "--work-item", record, "--manifest", manifest, "--dry-run")

    def _post(self, manifest, record=40):
        return self.invoke("post_plan", "--work-item", record, "--manifest", manifest, "--evidence", self.evidence_file())

    def _entries(self, manifest):
        return json.loads(Path(manifest).read_text(encoding="utf-8"))

    def test_only_the_changed_plan_is_targeted(self):
        result = self._dry_run(self.plan_manifest(40, {"TASK-001": "Files: core_service.py"}))
        self.assertEqual(result.code, 0, result.stdout)
        self.assertEqual(result.front_matter("Verdict"), "Pass")
        self.assertEqual(result.front_matter("Targeted"), "TASK-001")
        self.assertEqual(result.front_matter("Already planned"), "TASK-002")
        self.assertIn("## Warnings\n\nNone.", result.stdout)

    def test_a_placeholder_plan_is_empty(self):
        result = self._dry_run(self.plan_manifest(40, {}))
        self.assertEqual(result.code, 1)
        self.assertEqual(result.front_matter("Verdict"), "Fail")
        self.assertIn("TASK-001", result.stdout)
        self.assertIn("the tech plan is empty", result.stdout)

    def test_a_heading_in_the_plan_is_rejected(self):
        result = self._dry_run(self.plan_manifest(40, {"TASK-001": "## Steps\n1. Touch core."}))
        self.assertEqual(result.code, 1)
        self.assertIn("must be heading-free", result.stdout)

    def test_a_task_body_edit_fails_the_dry_run_and_is_refused(self):
        manifest = self.reviewed_plan_manifest(40, {"TASK-001": "Touch core."})
        task_file = Path(self._entries(manifest)[0]["file"])
        # The planner, not the reviewer, edits: a new pass clears the review stamp.
        self.invoke("prompt_tech_planner", 40, "--current-plan-manifest-path", manifest)
        task_file.write_text(task_file.read_text().replace("- ok", "- ok, and more"))
        dry = self._dry_run(manifest)
        self.assertEqual(dry.code, 1)
        self.assertIn("TASK-001: the task body between `--- BEGIN TASK ---` and `--- END TASK ---` was edited", dry.stdout)
        self.review_plans(40, manifest)
        result = self._post(manifest)
        self.assertEqual(result.code, 1)
        self.assertIn("was edited", result.stderr)
        self.assertEqual(self.fields(40)["Gate State"], "Pending")

    def test_text_outside_the_blocks_is_rejected(self):
        manifest = self.plan_manifest(40, {"TASK-001": "Touch core."})
        task_file = Path(self._entries(manifest)[0]["file"])
        task_file.write_text(task_file.read_text() + "\nNotes for the driver.\n")
        result = self._dry_run(manifest)
        self.assertEqual(result.code, 1)
        self.assertIn("text outside the task and tech plan blocks", result.stdout)

    def test_a_task_changed_on_the_record_is_stale(self):
        manifest = self.plan_manifest(40, {"TASK-001": "Touch core."})
        self.seed_plan_comment(40, 401, "someone else's plan")
        result = self._dry_run(manifest)
        self.assertEqual(result.code, 1)
        self.assertIn("TASK-001 changed on the record after this manifest was generated", result.stdout)

    def test_the_manifest_names_exactly_the_open_unimplemented_tasks(self):
        manifest = self.plan_manifest(40, {"TASK-001": "Touch core."})
        entries = self._entries(manifest)
        Path(manifest).write_text(json.dumps(entries[:1]))
        result = self._dry_run(manifest)
        self.assertEqual(result.code, 1)
        self.assertIn("TASK-002 is open and unimplemented but missing from the manifest", result.stdout)

    def test_a_hand_written_manifest_is_refused(self):
        plan = self.write_file("plan.md", "Files: core_service.py\n")
        manifest = self.write_file("pm.json", json.dumps([{"id": "TASK-001", "plan": plan}]))
        result = self._dry_run(manifest)
        self.assertEqual(result.code, 1)
        self.assertIn("the manifest is not the one pdlc generated", result.stderr)
        self.assertIn("TASK-001 needs its generated 'number'", result.stderr)
        self.assertIn("pdlc prompt tech-planner 40", result.stderr)

    def test_an_unreviewed_manifest_is_refused_without_writing(self):
        manifest = self.plan_manifest(40, {"TASK-001": "Touch core."})
        result = self._post(manifest)
        self.assertEqual(result.code, 1)
        self.assertIn("has not been reviewed since its last planning pass", result.stderr)
        self.assertIn(f"pdlc prompt plan-reviewer 40 --manifest {Path(manifest).resolve()} --file", result.stderr)
        self.assertEqual(self.fields(40)["Gate State"], "Pending")
        self.assertNotIn("Touch core.", self.task_comments_text(40, 401))

    def test_a_reviewer_edit_is_restored_and_refused(self):
        manifest = self.reviewed_plan_manifest(40, {"TASK-001": "Touch core."})
        task_file = Path(self._entries(manifest)[0]["file"])
        reviewed = task_file.read_text()
        self.write_plan(task_file, "The reviewer's own plan.")
        result = self._post(manifest)
        self.assertEqual(result.code, 1)
        self.assertIn("changed after its brief was written", result.stderr)
        self.assertIn(str(task_file.resolve()), result.stderr)
        self.assertIn("Discard that review's verdict and findings", result.stderr)
        self.assertEqual(task_file.read_text(), reviewed)
        rejected = task_file.with_name(f"{task_file.stem}.rejected.md")
        self.assertIn("The reviewer's own plan.", rejected.read_text())
        self.assertEqual(self.fields(40)["Gate State"], "Pending")
        # The restored files are what was reviewed, so they land once reviewed again.
        self.review_plans(40, manifest)
        self.assertEqual(self._post(manifest).code, 0)

    def test_a_reviewed_plan_lands_and_rebases_the_manifest(self):
        manifest = self.reviewed_plan_manifest(40, {"TASK-001": "Touch core."})
        result = self._post(manifest)
        self.assertEqual(result.code, 0, result.stderr)
        self.assertEqual(result.json["planned"], ["TASK-001"])
        self.assertEqual(result.json["alreadyPlanned"], ["TASK-002"])
        self.assertIn("Touch core.", self.task_comments_text(40, 401))
        self.assertEqual(self.task_comments_text(40, 402).count("## Technical Plan"), 1)
        self.assertEqual(self.fields(40)["Gate State"], "Approval Required")
        # Reused, the rebased manifest reads as unchanged rather than stale.
        again = self._dry_run(manifest)
        self.assertEqual(again.code, 0, again.stdout)
        self.assertEqual(again.front_matter("Targeted"), "None")

    def test_a_retry_after_a_partial_landing_skips_the_plans_that_landed(self):
        self.seed_record(46, "Technical Plan", "Pending")
        self.seed_task(46, 461, "TASK-001", "OPEN", "WORK-46-TASK-001 One", body=TASK_BODY_DEFAULT)
        self.seed_task(46, 462, "TASK-002", "OPEN", "WORK-46-TASK-002 Two", body=TASK_BODY_DEFAULT)
        manifest = self.reviewed_plan_manifest(46, {"TASK-001": "Plan one.", "TASK-002": "Plan two."})
        from pdlc.commands import post_plan
        real = post_plan.post_comment
        calls = []

        def flaky(ref, body, marker=None):
            calls.append(ref)
            if len(calls) == 2:
                raise PdlcError("host down")
            return real(ref, body, marker) if marker else real(ref, body)

        with mock.patch.object(post_plan, "post_comment", side_effect=flaky):
            failed = self._post(manifest, record=46)
        self.assertEqual(failed.code, 1)
        self.assertIn("Plan one.", self.task_comments_text(46, 461))
        retry = self._post(manifest, record=46)
        self.assertEqual(retry.code, 0, retry.stderr)
        self.assertEqual(retry.json["planned"], ["TASK-002"])
        self.assertEqual(self.task_comments_text(46, 461).count("## Technical Plan"), 1)

    def test_approval_required_dry_run_warns_instead_of_blocking(self):
        self.seed_record(41, "Technical Plan", "Approval Required")
        self.seed_task(41, 411, "TASK-001", "OPEN", "WORK-41-TASK-001 One", body=TASK_BODY_DEFAULT)
        result = self._dry_run(self.plan_manifest(41, {"TASK-001": "Touch core."}), record=41)
        self.assertEqual(result.code, 0, result.stdout)
        self.assertEqual(result.front_matter("Verdict"), "Pass")
        self.assertIn("Approval Required", result.stdout)
        self.assertIn("overwrite", result.stdout)
        self.assertEqual(self.fields(41)["Gate State"], "Approval Required")

    def test_changes_required_lands_like_stale(self):
        self.seed_record(42, "Technical Plan", "Changes Required")
        self.seed_task(42, 421, "TASK-001", "OPEN", "WORK-42-TASK-001 One", body=TASK_BODY_DEFAULT)
        result = self._post(self.reviewed_plan_manifest(42, {"TASK-001": "Touch core."}), record=42)
        self.assertEqual(result.code, 0, result.stderr)
        self.assertEqual(result.json["planned"], ["TASK-001"])
        self.assertEqual(self.fields(42)["Status"], "Technical Plan")
        self.assertEqual(self.fields(42)["Gate State"], "Approval Required")

    def test_review_required_re_lands_the_published_plan_at_approval_required(self):
        self.seed_record(43, "Technical Plan", "Review Required")
        self.seed_task(43, 431, "TASK-001", "OPEN", "WORK-43-TASK-001 One", body=TASK_BODY_DEFAULT)
        self.seed_plan_comment(43, 431, "Published without review.")
        # The published plan is reviewed as it stands: no file is edited.
        manifest = self.reviewed_plan_manifest(43, {})
        dry = self._dry_run(manifest, record=43)
        self.assertEqual(dry.code, 0, dry.stdout)
        self.assertEqual(dry.front_matter("Targeted"), "None")
        self.assertEqual(self.fields(43)["Gate State"], "Review Required")
        result = self._post(manifest, record=43)
        self.assertEqual(result.code, 0, result.stderr)
        self.assertEqual(result.json["planned"], [])
        self.assertEqual(self.fields(43)["Gate State"], "Approval Required")

    def test_blocking_gates_are_refused_without_writing(self):
        for number, gate, expected in (
            (44, "Decision Required", "pdlc guide decisions"),
            (45, "Approved", "cannot land Technical Plan from Gate State: Approved"),
        ):
            with self.subTest(gate=gate):
                self.seed_record(number, "Technical Plan", gate)
                self.seed_task(number, number * 10 + 1, "TASK-001", "OPEN", f"WORK-{number}-TASK-001 One", body=TASK_BODY_DEFAULT)
                result = self._dry_run(self.plan_manifest(number, {"TASK-001": "Touch core."}), record=number)
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

    def test_uninitialized_record_is_initialized_in_place(self):
        self.seed_record(55, "", "", body="Product manager brief: ship offline routes.\n")
        meta_path = self.records_dir() / "55" / "meta.json"
        meta = json.loads(meta_path.read_text())
        meta["fields"].update({"Lifecycle": "", "Slug": ""})
        meta_path.write_text(json.dumps(meta))

        result = self._rewrite(55)

        self.assertEqual(result.code, 0, result.stderr)
        self.assertEqual(self.fields(55)["Status"], "Product")
        self.assertEqual(self.fields(55)["Gate State"], "Approval Required")
        self.assertEqual(self.fields(55)["Lifecycle"], "Planning")
        self.assertEqual(self.fields(55)["Slug"], "record-55")
        self.assertIn("Product manager brief: ship offline routes.", self.body(55))
        self.assertIn("PDLC-PRODUCT", self.comments_text(55))

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

    def test_omitted_open_questions_leaves_the_existing_section_untouched(self):
        self.seed_record(54, "Product", "Stale", body=(
            "## Product\nold\n\n## Decisions\nold\n\n## Open Questions\nkept question\n"
        ))
        rewrite = self.write_file("no-questions.md", "## Product\nnew product\n\n## Decisions\nnew decision\n")
        result = self.invoke("post_write", "--work-item", 54,
                             "--evidence", self.evidence_file(), "--body", rewrite)
        self.assertEqual(result.code, 0, result.stderr)
        body = self.body(54)
        self.assertIn("new product", body)
        self.assertIn("kept question", body)

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
        self._assert_refused(64, "Verification", "post_verify", 64, 'text:{"schema": "pdlc.verify/1"}')

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
