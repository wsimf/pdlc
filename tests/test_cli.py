import unittest

from pdlc.cli import _resolve


class CliTests(unittest.TestCase):
    def test_resolves_post_complete(self):
        module, arguments = _resolve(["post", "complete", "236", "completion.md"])
        self.assertEqual(module, "pdlc.commands.post_complete")
        self.assertEqual(arguments, ["236", "completion.md"])

    def test_supports_exec_alias(self):
        module, _ = _resolve(["exec", "post", "complete"])
        self.assertEqual(module, "pdlc.commands.post_complete")
