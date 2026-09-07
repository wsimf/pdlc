import json

from _support import FileBackendTest
from _gh_replay import GitHubHostTest
from pdlc.hosts import github_issues


class CommentsInspectionTests(FileBackendTest):
    def setUp(self):
        super().setUp()
        self.seed_record(90, "Product", "Pending")
        comments = self.records_dir() / "90" / "comments.jsonl"
        with comments.open("w") as handle:
            for index in range(205):
                handle.write(json.dumps({
                    "body": f"comment {index}",
                    "createdAt": "2026-01-01T00:00:00Z",
                    "url": "u",
                    "author": {"login": "alice"},
                }) + "\n")
        self.seed_task(90, 901, "TASK-001", "OPEN", "WORK-90-TASK-001 Task")

    def test_pages_and_next_guidance(self):
        first = self.invoke("inspect_comments", 90)
        self.assertEqual(first.code, 0)
        self.assertIn("Page 1 of 3 (205 total)", first.stdout)
        self.assertIn("105 more comments; use pdlc inspect comments 90 --page 2", first.stdout)
        second = self.invoke("inspect_comments", 90, "--page", 2)
        self.assertIn("comment 100", second.stdout)
        self.assertIn("5 more comments; use pdlc inspect comments 90 --page 3", second.stdout)
        third = self.invoke("inspect_comments", 90, "--page", 3)
        self.assertIn("comment 4", third.stdout)
        self.assertNotIn("use pdlc inspect comments", third.stdout)
        self.assertIn("alice", first.stdout)

    def test_empty_and_bad_pages_are_read_only_errors(self):
        self.assertIn("No comments", self.invoke("inspect_comments", 90, "--page", 4).stdout)
        result = self.invoke("inspect_comments", 90, "--page", 0)
        self.assertEqual(result.code, 1)
        self.assertIn("page must be", result.stderr)

    def test_page_boundaries_have_exact_lengths(self):
        path = self.records_dir() / "90" / "comments.jsonl"
        for total in (0, 100, 101):
            with path.open("w") as handle:
                for index in range(total):
                    handle.write(json.dumps({"body": str(index), "createdAt": "t", "url": "u", "author": {"login": "a"}}) + "\n")
            first = self.invoke("inspect_comments", 90)
            second = self.invoke("inspect_comments", 90, "--page", 2)
            self.assertEqual(first.code, 0)
            self.assertEqual(second.code, 0)
            self.assertEqual(first.stdout.count("### a"), min(total, 100))
            self.assertEqual(second.stdout.count("### a"), max(0, total - 100))
            self.assertEqual("use pdlc inspect comments" in first.stdout, total > 100)

    def test_delivery_task_is_a_valid_comment_target(self):
        result = self.invoke("inspect_comments", 901)
        self.assertEqual(result.code, 0)


class GitHubCommentsPageTests(GitHubHostTest):
    def test_page_uses_get_and_exact_graphql_total(self):
        self.gh.graphql("totalCount", {"data": {"repository": {"issue": {"comments": {"totalCount": 205}}}}})
        self.gh.api("issues/90/comments", lambda args, _input: [{"body": str(i), "created_at": "t", "html_url": "u", "user": {"login": "a"}} for i in (range(100, 200) if "page=2" in args else range(0, 100))])
        page = github_issues.comments_page("90", 2)
        self.assertEqual((page.total, page.has_next, len(page.comments)), (205, True, 100))
        self.assertEqual([page.comments[0]["body"], page.comments[-1]["body"]], ["104", "5"])
        calls = self.gh.calls
        graphql_args = next(args for args, _ in calls if args[:2] == ["api", "graphql"])
        self.assertTrue(any("comments(last:" in arg for arg in graphql_args))
        self.assertFalse(any("comments(first:" in arg for arg in graphql_args))
        rest = [args for args, _ in calls if args[0] == "api" and args[1] != "graphql"][-1]
        self.assertIn("--method", rest)
        self.assertIn("GET", rest)
        self.assertIn("per_page=100", rest)
        self.assertIn("page=2", rest)
        self.assertNotIn("--paginate", rest)
