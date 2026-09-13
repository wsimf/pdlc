import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pdlc.commands.doctor import run


class DoctorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = Path(tempfile.mkdtemp())
        self.home_path = self.directory / "home" / ".pdlc" / "config.toml"
        self.repo_root = self.directory / "repo"
        (self.repo_root / ".pdlc").mkdir(parents=True)
        self.repo_config = self.repo_root / ".pdlc" / "config.toml"

    def test_reports_all_missing_github_values(self) -> None:
        self.repo_config.write_text('[backend]\nname = "github"\n')
        with patch("pdlc.commands.doctor.home_config_path", return_value=self.home_path), \
             patch("pdlc.commands.doctor.repository_root", return_value=self.repo_root):
            output, code = run()
        self.assertEqual(code, 1)
        self.assertIn("missing required setting: backend.github.repository", output)
        self.assertIn("missing required setting: backend.github.project_number", output)
        self.assertIn("missing required setting: backend.github.project_owner", output)
        self.assertEqual(output.count("- FAIL:"), 3)

    def test_prints_sources_derivations_and_home_repository_warning(self) -> None:
        self.home_path.parent.mkdir(parents=True)
        self.home_path.write_text('[backend.github]\nrepository = "acme/widgets"\n')
        self.repo_config.write_text('[backend]\nname = "file"\n')
        with patch("pdlc.commands.doctor.home_config_path", return_value=self.home_path), \
             patch("pdlc.commands.doctor.repository_root", return_value=self.repo_root):
            output, code = run()
        self.assertEqual(code, 0)
        self.assertIn("repository = 'acme/widgets'", output)
        self.assertIn(str(self.home_path), output)
        self.assertIn("repository is set in ~/.pdlc/config.toml", output)
        self.assertIn("backend = 'file'", output)

    def test_reports_derived_repository_as_a_warning(self) -> None:
        self.repo_config.write_text('[backend]\nname = "github"\n')
        with patch("pdlc.commands.doctor.home_config_path", return_value=self.home_path), \
             patch("pdlc.commands.doctor.repository_root", return_value=self.repo_root), \
             patch("pdlc.commands.doctor.git_remote_repository", return_value="acme/widgets"):
            output, code = run()
        self.assertEqual(code, 1)
        self.assertIn("repository = 'acme/widgets' [derived from git origin]", output)
        self.assertIn("repository is auto-derived from git origin", output)


if __name__ == "__main__":
    unittest.main()
