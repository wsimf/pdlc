"""Attaching pull requests to a record or delivery task, through the file
backend: the `pdlc post attach-pr` command, the automatic attachment
`pdlc post implement-task` performs, and the guarantee that bodies stay
human-authored content. The GitHub backend's own storage format is covered in
test_github_hosts.py."""

import json
import unittest

from pathlib import Path
from _support import FileBackendTest
from pdlc.domain.lifecycle import PdlcError
from pdlc.domain.records import PullRef, parse_pull_refs

BODY = "## Scope\nDo the thing.\n\n## Acceptance criteria\n- ok\n"


class PullRefTests(unittest.TestCase):
    def test_parses_bare_hash_and_qualified_forms(self):
        self.assertEqual(PullRef.parse("12", "acme/api"), PullRef(12, "acme/api"))
        self.assertEqual(PullRef.parse("#12", "acme/api"), PullRef(12, "acme/api"))
        self.assertEqual(PullRef.parse("Acme/Web#12", "acme/api"), PullRef(12, "acme/web"))
        for text in ("", "#", "web#12", "acme/web#", "acme/web12", "0", "12a"):
            with self.subTest(text=text), self.assertRaises(PdlcError):
                PullRef.parse(text, "acme/api")

    def test_labels_and_json_stay_bare_in_the_code_repository(self):
        here, there, plain = PullRef(12, "acme/api"), PullRef(12, "acme/web"), PullRef(12)
        self.assertEqual([ref.label("acme/api") for ref in (here, there, plain)], ["#12", "acme/web#12", "#12"])
        self.assertEqual([ref.json("acme/api") for ref in (here, there, plain)], [12, "acme/web#12", 12])
        self.assertEqual([ref.token() for ref in (here, plain)], ["acme/api#12", "12"])

    def test_stored_tokens_are_tolerant_and_deduplicated(self):
        refs = parse_pull_refs([12, "12", "acme/api#12", "acme/web#3", "junk", 0, -1], "acme/api")
        self.assertEqual(refs, [PullRef(3, "acme/web"), PullRef(12, "acme/api")])


class AttachPrCommandTests(FileBackendTest):
    def setUp(self):
        super().setUp()
        self.seed_record(70, "Implementation", "Pending")
        self.seed_task(70, 701, "TASK-001", "OPEN", "WORK-70-TASK-001 [CORE] Core", body=BODY)

    def _body(self):
        return (self.records_dir() / "70" / "tasks" / "701" / "body.md").read_text()

    def test_attaches_and_is_idempotent(self):
        first = self.invoke("post_attach_pr", 701, 148)
        self.assertEqual(first.json, {"task": 701, "prs": [148]})

        again = self.invoke("post_attach_pr", 701, "#148")
        self.assertEqual(again.json, {"task": 701, "prs": [148]})

        second = self.invoke("post_attach_pr", 701, 160)
        self.assertEqual(second.json, {"task": 701, "prs": [148, 160]})
        # The body is never a storage surface on this backend.
        self.assertEqual(self._body(), BODY)

    def test_a_pull_request_in_another_repository_stays_qualified(self):
        self.invoke("post_attach_pr", 701, 148)
        result = self.invoke("post_attach_pr", 701, "acme/web#148")
        # The same number in another repository is a different pull request.
        self.assertEqual(result.json, {"task": 701, "prs": [148, "acme/web#148"]})
        meta = json.loads((self.records_dir() / "70" / "tasks" / "701" / "meta.json").read_text())
        self.assertEqual(meta["prs"], [148, "acme/web#148"])

    def test_rejects_a_repository_without_a_number_separator(self):
        self.assertEqual(self.invoke("post_attach_pr", 701, "acme/web148").code, 1)

    def test_rejects_a_non_delivery_work_item(self):
        result = self.invoke("post_attach_pr", 70, 148)
        self.assertEqual(result.code, 1)

    def test_rejects_a_non_numeric_pr(self):
        result = self.invoke("post_attach_pr", 701, "feature")
        self.assertEqual(result.code, 1)

    def test_stores_the_numbers_in_the_task_meta_json(self):
        self.invoke("post_attach_pr", 701, 148)
        meta = json.loads((self.records_dir() / "70" / "tasks" / "701" / "meta.json").read_text())
        self.assertEqual(meta["prs"], [148])

    def test_inspect_task_reports_prs_and_leaves_the_body_clean(self):
        self.invoke("post_attach_pr", 701, 148)
        rendered = self.invoke("inspect_task", 701).stdout
        self.assertIn("prs:", rendered)
        self.assertIn("- 148", rendered)
        self.assertNotIn("pdlc:meta", rendered)


class AttachmentSurvivesRePlanTests(FileBackendTest):
    def setUp(self):
        super().setUp()
        self.seed_record(70, "Implementation", "Pending", slug="record-70")
        self.seed_task(70, 701, "TASK-001", "OPEN", "WORK-70-TASK-001 [CORE] Core", body=BODY)

    def test_upsert_keeps_registered_prs_and_reports_unchanged(self):
        from pdlc.hosts.workitem_host import get_backend
        from pdlc.internal.workitem import task_tree

        self.invoke("post_attach_pr", 701, 148)

        backend = get_backend()
        existing = task_tree("70")
        body_file = self.write_file("task.md", BODY)
        results = backend.upsert_tasks("70", [{"id": "TASK-001", "title": "[CORE] Core", "bodyText": Path(body_file).read_text()}], existing)

        self.assertEqual(results[0]["action"], "unchanged")
        self.assertEqual(task_tree("70")[0]["prs"], [PullRef(148)])
        self.assertEqual(
            (self.records_dir() / "70" / "tasks" / "701" / "body.md").read_text(),
            BODY,
        )


class RecordAttachmentTests(FileBackendTest):
    """A record carries its own attachments, separately from its tasks'."""

    def setUp(self):
        super().setUp()
        self.seed_record(80, "Implementation", "Pending")

    def test_attaches_to_a_record_and_reports_it_back(self):
        from pdlc.internal.workitem import attach_pr, attached_prs, resolve_item

        self.assertEqual(attach_pr("80", PullRef(300)), [PullRef(300)])
        self.assertEqual(attach_pr("80", PullRef(300)), [PullRef(300)])
        self.assertEqual(attach_pr("80", PullRef(210)), [PullRef(210), PullRef(300)])
        self.assertEqual(attached_prs("80"), [PullRef(210), PullRef(300)])
        self.assertEqual(resolve_item("80")["prs"], [PullRef(210), PullRef(300)])

    def test_record_body_is_untouched(self):
        from pdlc.internal.workitem import attach_pr

        before = (self.records_dir() / "80" / "body.md").read_text()
        attach_pr("80", PullRef(300))
        self.assertEqual((self.records_dir() / "80" / "body.md").read_text(), before)


class RecordPullRequestsTests(FileBackendTest):
    def setUp(self):
        super().setUp()
        self.seed_record(70, "Verification", "Pending")
        self.seed_task(70, 701, "TASK-001", "CLOSED", "WORK-70-TASK-001 [CORE] Core", body=BODY)
        self.seed_prs(70, [
            {"number": 148, "title": "task pr", "url": "u", "state": "MERGED",
             "isDraft": False, "branch": "pdlc/record-70/task-001", "mergedAt": "x", "checks": "SUCCESS"},
            {"number": 900, "title": "stray", "url": "u", "state": "OPEN",
             "isDraft": False, "branch": "other", "mergedAt": None, "checks": "FAILURE"},
        ], register=False)

    def test_only_registered_prs_are_returned(self):
        from pdlc.internal.pull_requests import record_pull_requests

        self.invoke("post_attach_pr", 701, 148)
        prs = record_pull_requests("70")
        self.assertEqual([pr["number"] for pr in prs], [148])

    def test_the_same_number_in_two_repositories_resolves_to_two_pull_requests(self):
        from pdlc.internal.pull_requests import pr_label, record_pull_requests

        web = {"number": 148, "repository": "Acme/Web", "title": "web pr", "url": "u", "state": "OPEN",
               "isDraft": False, "branch": "pdlc/record-70/task-001", "mergedAt": None, "checks": "FAILURE"}
        path = self.records_dir() / "70" / "pull_requests.json"
        path.write_text(json.dumps([*json.loads(path.read_text()), web]))
        self.invoke("post_attach_pr", 701, 148)
        self.invoke("post_attach_pr", 701, "acme/web#148")

        prs = record_pull_requests("70")
        self.assertEqual([(pr["repository"], pr["state"]) for pr in prs], [("", "MERGED"), ("acme/web", "OPEN")])
        self.assertEqual([pr_label(pr) for pr in prs], ["#148", "acme/web#148"])

    def test_open_review_comments_are_stamped_with_their_pr_and_unregistered_prs_are_never_queried(self):
        from unittest import mock
        from pdlc.internal.pull_requests import record_open_review_comments

        self.invoke("post_attach_pr", 701, 148)

        def fake(pr):
            self.assertEqual(pr, PullRef(148))  # #900 is registered on no task/record
            return [{"author": "reviewer", "body": "fix this", "url": "u", "path": "a.py", "line": 1}]

        with mock.patch("pdlc.internal.pull_requests.get_code_host") as get_host:
            get_host.return_value.unresolved_review_comments = fake
            comments = record_open_review_comments("70")

        self.assertEqual(comments, [{"pr": PullRef(148), "author": "reviewer", "body": "fix this", "url": "u", "path": "a.py", "line": 1}])


if __name__ == "__main__":
    unittest.main()
