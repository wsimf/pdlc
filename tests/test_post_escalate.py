import json

from _support import FileBackendTest

DECISION = (
    "## Decision Required\n\n"
    "### Retry on load\n"
    "Question: keep the retry the reviewer asked to drop?\n"
    "Options: keep; drop\n"
    "Recommendation: keep\n"
    "Blocks: WORK-70-TASK-001\n"
    "Why not mechanical: the plan specifies the retry\n"
)


class PostEscalateTests(FileBackendTest):
    def test_escalates_from_a_work_gate_and_the_driver_resolves_it_back_to_changes_required(self):
        self.seed_record(70, "Implementation", "Changes Required")
        evidence = self.write_file("decision.md", DECISION)

        result = self.invoke("post_escalate", 70, evidence)

        self.assertEqual(result.code, 0, result.stderr)
        self.assertEqual(result.json["gateState"], "Decision Required")
        self.assertEqual(result.json["stage"], "Implementation")
        self.assertEqual(self.state(70), ("Implementation", "Decision Required"))
        self.assertIn("PDLC-DECISION", self.comments_text(70))
        self.assertIn("### Retry on load", self.comments_text(70))

        manifest = self.write_file("manifest.json", json.dumps([
            {"decision": "Retry on load", "answer": "keep", "rationale": "the plan specifies it"},
        ]))
        resolved = self.invoke("post_decision", 70, "--manifest", manifest)
        self.assertEqual(resolved.code, 0, resolved.stderr)
        self.assertEqual(self.state(70), ("Implementation", "Changes Required"))
        self.assertIn("Resolved stage: Implementation", self.comments_text(70))

    def test_refused_outside_a_work_gate_and_posts_nothing(self):
        evidence = self.write_file("decision.md", DECISION)
        for number, gate in ((71, "Review Required"), (72, "Approval Required"), (73, "Decision Required")):
            with self.subTest(gate=gate):
                self.seed_record(number, "Implementation", gate)
                result = self.invoke("post_escalate", number, evidence)
                self.assertEqual(result.code, 1, result.stdout)
                self.assertEqual(self.state(number), ("Implementation", gate))
                self.assertEqual(self.comments_text(number), "")

    def test_requires_a_decision_required_section(self):
        self.seed_record(74, "Implementation", "Pending")
        result = self.invoke("post_escalate", 74, "text:no heading here")
        self.assertEqual(result.code, 1)
        self.assertIn("## Decision Required", result.stderr)
        self.assertEqual(self.state(74), ("Implementation", "Pending"))
        self.assertEqual(self.comments_text(74), "")
