import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pdlc.config import Config, ConfigurationError, get_config, load_config
from pdlc.commands.setup import _write_config


class ConfigTests(unittest.TestCase):
    def make_repo(self, config: str | None = None) -> Path:
        root = Path(tempfile.mkdtemp())
        (root / ".git").mkdir()
        if config is not None:
            config_dir = root / ".pdlc"
            config_dir.mkdir()
            (config_dir / "config.toml").write_text(config)
        return root / "nested"

    def test_config_file_overrides_environment(self):
        nested = self.make_repo(
            '[backend.github]\n'
            'repository = "file/repository"\n'
            'project_owner = "file-owner"\n'
        )
        with patch.dict(
            os.environ,
            {
                "PDLC_REPOSITORY": "environment/repository",
                "PDLC_PROJECT_NUMBER": "7",
                "PDLC_PROJECT_OWNER": "environment-owner",
            },
            clear=False,
        ):
            config = load_config(nested)
        self.assertEqual(config.repository, "file/repository")
        self.assertEqual(config.project_owner, "file-owner")
        self.assertEqual(config.project_number, "7")

    def test_config_file_supports_toml_types(self):
        nested = self.make_repo(
            '[backend]\nname = "file"\n'
            '[workflow]\nno_sleep = true\nmax_attempts = 4\n'
        )
        config = load_config(nested)
        self.assertEqual(config.backend, "file")
        self.assertEqual(config.no_sleep, "true")
        self.assertEqual(config.max_attempts, "4")

    def test_later_cli_environment_changes_are_visible(self):
        nested = self.make_repo('[backend.github]\nrepository = "file/repository"\n')
        with patch.dict(os.environ, {}, clear=False):
            load_config(nested)
            os.environ["PDLC_REPOSITORY"] = "cli/repository"
            self.assertEqual(get_config().repository, "cli/repository")

    def test_environment_is_used_when_config_is_missing(self):
        nested = self.make_repo()
        with patch.dict(
            os.environ,
            {"PDLC_REPOSITORY": "environment/repository"},
            clear=False,
        ):
            config = load_config(nested)
        self.assertEqual(config.repository, "environment/repository")

    def test_github_validation_explains_configuration(self):
        with self.assertRaisesRegex(ConfigurationError, "Create .pdlc/config.toml"):
            Config().validate_for_backend()

    def test_file_backend_does_not_need_github_values(self):
        Config(backend="file").validate_for_backend()

    def test_config_rejects_unknown_settings(self):
        nested = self.make_repo('[backend]\nunknown = "value"\n')
        with self.assertRaisesRegex(ConfigurationError, "Unknown setting"):
            load_config(nested)

    def test_setup_writes_grouped_toml(self):
        root = Path(tempfile.mkdtemp())
        (root / ".git").mkdir()
        path = root / ".pdlc" / "config.toml"
        _write_config(
            path,
            backend="github",
            code_host="github",
            repository="owner/repository",
            project_number="12",
            project_owner="owner",
        )
        config = load_config(root)
        self.assertEqual(config.repository, "owner/repository")
        self.assertEqual(config.project_number, "12")
