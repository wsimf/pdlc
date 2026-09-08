import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pdlc.config import (
    Config,
    ConfigurationError,
    get_capabilities,
    get_config,
    load_config,
)
from pdlc.commands.setup import _write_config


class ConfigTests(unittest.TestCase):
    def setUp(self) -> None:
        # Redirect the machine-wide config lookup so a real ~/.pdlc/config.toml
        # on the developer's machine cannot leak into these tests.
        self._home = Path(tempfile.mkdtemp())
        patcher = patch(
            "pdlc.config.home_config_path",
            lambda: self._home / ".pdlc" / "config.toml",
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def make_repo(self, config: str | None = None) -> Path:
        root = Path(tempfile.mkdtemp())
        (root / ".git").mkdir()
        if config is not None:
            config_dir = root / ".pdlc"
            config_dir.mkdir()
            (config_dir / "config.toml").write_text(config)
        return root / "nested"

    def write_home_config(self, config: str) -> None:
        path = self._home / ".pdlc" / "config.toml"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(config)

    def non_repo_dir(self) -> Path:
        # A temp dir with no ``.git`` ancestor stands in for "run outside a repo".
        return Path(tempfile.mkdtemp()) / "nested"

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

    def test_optional_assignee_filters_are_read_from_config(self):
        nested = self.make_repo(
            '[backend]\nname = "azure"\n'
            '[backend.azure]\n'
            'organization = "https://dev.azure.com/acme"\n'
            'project = "delivery"\n'
            'assigned_to = "@me"\n'
            '[backend.github]\n'
            'repository = "acme/repo"\n'
            'assigned_to = "ada"\n'
        )
        config = load_config(nested)
        self.assertEqual(config.azure_assigned_to, "@me")
        self.assertEqual(config.github_assigned_to, "ada")

    def test_config_file_supports_toml_types(self):
        nested = self.make_repo(
            '[backend]\nname = "file"\n'
            '[workflow]\nno_sleep = true\nmax_attempts = 4\n'
        )
        config = load_config(nested)
        self.assertEqual(config.backend, "file")
        self.assertIs(config.no_sleep, True)
        self.assertEqual(config.max_attempts, 4)

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

    def test_capability_slots_are_read_from_config(self):
        nested = self.make_repo(
            '[agents]\ncore-implementer = "my-core-implementer"\n'
            '[skills]\nbuild-run = "my-build-run"\n'
        )
        load_config(nested)
        caps = get_capabilities()
        self.assertEqual(caps.agent("core-implementer"), "my-core-implementer")
        self.assertEqual(caps.agent("ui-implementer"), "general-purpose")
        self.assertEqual(caps.skill("build-run"), "my-build-run")
        self.assertIsNone(caps.skill("ux-design"))

    def test_capability_rejects_unknown_slot(self):
        nested = self.make_repo('[skills]\nbogus = "x"\n')
        with self.assertRaisesRegex(ConfigurationError, "Unknown capability slot"):
            load_config(nested)

    def test_capability_rejects_non_string_value(self):
        nested = self.make_repo('[agents]\ncore-implementer = 3\n')
        with self.assertRaisesRegex(ConfigurationError, "must be a non-empty string"):
            load_config(nested)

    def test_capabilities_empty_without_config(self):
        nested = self.make_repo()
        load_config(nested)
        caps = get_capabilities()
        self.assertEqual(caps.agent("core-implementer"), "general-purpose")
        self.assertIsNone(caps.skill("build-run"))

    def test_repository_config_overrides_home(self):
        self.write_home_config('[backend.github]\nrepository = "home/repository"\n')
        nested = self.make_repo('[backend.github]\nrepository = "repo/repository"\n')
        self.assertEqual(load_config(nested).repository, "repo/repository")

    def test_home_config_overrides_environment(self):
        self.write_home_config('[backend.github]\nproject_owner = "home-owner"\n')
        nested = self.make_repo()
        with patch.dict(
            os.environ, {"PDLC_PROJECT_OWNER": "environment-owner"}, clear=False
        ):
            config = load_config(nested)
        self.assertEqual(config.project_owner, "home-owner")

    def test_home_config_applies_without_repository(self):
        self.write_home_config(
            '[backend.github]\n'
            'repository = "home/repository"\n'
            'project_number = "9"\n'
            'project_owner = "home-owner"\n'
        )
        config = load_config(self.non_repo_dir())
        self.assertEqual(config.repository, "home/repository")
        config.validate_for_backend()

    def test_missing_repository_still_errors_without_home(self):
        with self.assertRaisesRegex(ConfigurationError, "not configured for this repository"):
            load_config(self.non_repo_dir())

    def test_capability_slots_merge_per_slot(self):
        self.write_home_config(
            '[agents]\n'
            'core-implementer = "home-core"\n'
            'ui-implementer = "home-ui"\n'
            '[skills]\nbuild-run = "home-build-run"\n'
        )
        nested = self.make_repo('[agents]\ncore-implementer = "repo-core"\n')
        load_config(nested)
        caps = get_capabilities()
        self.assertEqual(caps.agent("core-implementer"), "repo-core")
        self.assertEqual(caps.agent("ui-implementer"), "home-ui")
        self.assertEqual(caps.skill("build-run"), "home-build-run")

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
