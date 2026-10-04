import tempfile
import unittest
from pathlib import Path

from _support import isolate_home_config
from pdlc.commands import inspect_capability
from pdlc.config import load_config


class CapabilityCommandTests(unittest.TestCase):
    def setUp(self) -> None:
        isolate_home_config(self)

    def load(self, config: str | None = None) -> None:
        root = Path(tempfile.mkdtemp())
        (root / ".git").mkdir()
        if config is not None:
            (root / ".pdlc").mkdir()
            (root / ".pdlc" / "config.toml").write_text(config)
        load_config(root)

    def test_agent_slot_prints_configured_name(self):
        self.load('[agents]\ncore-implementer = "my-core-implementer"\n')
        self.assertEqual(inspect_capability._one("core-implementer"), "my-core-implementer")

    def test_agent_slot_falls_back_to_general_purpose(self):
        self.load()
        self.assertEqual(inspect_capability._one("ui-implementer"), "general-purpose")

    def test_configured_skill_slot_emits_invoke_instruction(self):
        self.load('[skills]\nbuild-run = "my-build-run"\n')
        line = inspect_capability._one("build-run")
        self.assertIn("invoke the `my-build-run` skill", line)
        self.assertIn("say so and exit", line)

    def test_unset_skill_slot_emits_fallback(self):
        self.load()
        self.assertIn("No cumulative-review skill is configured",
                      inspect_capability._one("cumulative-review"))

    def test_name_prints_configured_name_alone(self):
        self.load('[skills]\nbuild-run = "my-build-run"\n')
        self.assertEqual(inspect_capability._name("build-run"), "my-build-run")

    def test_name_is_empty_for_an_unset_skill_slot(self):
        self.load()
        self.assertEqual(inspect_capability._name("build-run"), "")

    def test_name_suppresses_the_agent_default(self):
        self.load()
        self.assertEqual(inspect_capability._name("ui-implementer"), "")

    def test_name_of_an_unknown_slot_is_an_error(self):
        self.load()
        with self.assertRaises(ValueError):
            inspect_capability._name("bogus")

    def test_name_requires_a_slot(self):
        self.load()
        self.assertEqual(inspect_capability.main(["--name"]), 1)

    def test_unknown_slot_is_an_error(self):
        self.load()
        with self.assertRaises(ValueError):
            inspect_capability._one("bogus")

    def test_dump_lists_every_slot(self):
        self.load('[skills]\nux-design = "acme-ux"\n')
        dump = inspect_capability._dump()
        self.assertIn("core-implementer: general-purpose", dump)
        self.assertIn("ux-design: acme-ux", dump)
        self.assertIn("test-authoring: (unset", dump)


if __name__ == "__main__":
    unittest.main()
