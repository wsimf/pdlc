import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pdlc.config import (
    Config,
    ConfigurationError,
    configuration_guidance,
    get_capabilities,
    get_config,
    load_config,
    reset_config,
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
        # Strip every PDLC_* variable so only what a test sets counts.
        env = patch.dict(
            os.environ,
            {k: v for k, v in os.environ.items() if not k.startswith("PDLC_")},
            clear=True,
        )
        env.start()
        self.addCleanup(env.stop)
        self.addCleanup(reset_config)

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

    def make_git_repo(self, origin_url: str, config: str | None = None) -> Path:
        root = Path(tempfile.mkdtemp())
        subprocess.run(["git", "init", "-q", str(root)], check=True)
        subprocess.run(
            ["git", "-C", str(root), "remote", "add", "origin", origin_url],
            check=True,
        )
        if config is not None:
            config_dir = root / ".pdlc"
            config_dir.mkdir()
            (config_dir / "config.toml").write_text(config)
        return root / "nested"

    def non_repo_dir(self) -> Path:
        # A temp dir with no ``.git`` ancestor stands in for "run outside a repo".
        return Path(tempfile.mkdtemp()) / "nested"

    def test_repository_file_overrides_the_environment_variable(self):
        nested = self.make_repo(
            '[tracker.github]\n'
            'repository = "file/repository"\n'
            'project_number = 7\n'
            'project_owner = "file-owner"\n'
        )
        with patch.dict(os.environ, {"PDLC_TRACKER_REPOSITORY": "environment/repository"}):
            config = load_config(nested)
        self.assertEqual(config.tracker_repository, "file/repository")
        self.assertEqual(config.project_owner, "file-owner")
        self.assertEqual(config.project_number, "7")

    def test_optional_assignee_filters_are_read_from_config(self):
        nested = self.make_repo(
            '[tracker]\nprovider = "azure"\n'
            '[tracker.azure]\n'
            'organization = "https://dev.azure.com/acme"\n'
            'project = "delivery"\n'
            'assigned_to = "@me"\n'
            '[tracker.github]\n'
            'repository = "acme/repo"\n'
            'assigned_to = "ada"\n'
        )
        config = load_config(nested)
        self.assertEqual(config.azure_assigned_to, "@me")
        self.assertEqual(config.github_assigned_to, "ada")

    def test_pr_attachment_is_read_from_the_code_table(self):
        nested = self.make_repo(
            '[tracker]\nprovider = "file"\n'
            '[code]\nprovider = "github"\npr_attachment = "Fixes {work.number}"\n'
        )
        config = load_config(nested)
        self.assertEqual(config.pr_attachment, "Fixes {work.number}")

    def test_pr_title_format_is_read_from_the_code_table(self):
        nested = self.make_repo(
            '[tracker]\nprovider = "file"\n'
            '[code]\nprovider = "github"\npr_title_format = "[{work.number}] {task.title}"\n'
        )
        config = load_config(nested)
        self.assertEqual(config.pr_title_format, "[{work.number}] {task.title}")

    def test_config_file_supports_toml_types(self):
        nested = self.make_repo(
            '[tracker]\nprovider = "file"\n'
            '[workflow]\nno_sleep = true\nmax_attempts = 4\n'
        )
        config = load_config(nested)
        self.assertEqual(config.tracker_provider, "file")
        self.assertIs(config.no_sleep, True)
        self.assertEqual(config.max_attempts, 4)

    def test_debug_flag_is_read_from_the_debug_table(self):
        nested = self.make_repo('[tracker]\nprovider = "file"\n[debug]\nenabled = true\n')
        config = load_config(nested)
        self.assertIs(config.debug, True)

    def test_cache_root_is_read_from_config_and_repository_overrides_home(self):
        self.write_home_config('[cache]\nroot = "global_default"\n')
        nested = self.make_repo('[cache]\nroot = "artifacts"\n')
        self.assertEqual(load_config(nested).cache_root, "artifacts")

    def test_cache_root_defaults_to_repository(self):
        nested = self.make_repo('[tracker]\nprovider = "file"\n')
        self.assertEqual(load_config(nested).cache_root, "repository_default")

    def test_blank_cache_root_is_rejected(self):
        nested = self.make_repo('[cache]\nroot = ""\n')
        with self.assertRaisesRegex(ConfigurationError, r"cache\.root"):
            load_config(nested)

    def test_cli_overrides_beat_the_config_file(self):
        nested = self.make_repo('[tracker.github]\nrepository = "file/repository"\n')
        config = load_config(nested, overrides={"tracker_repository": "cli/repository"})
        self.assertEqual(config.tracker_repository, "cli/repository")
        self.assertEqual(get_config().tracker_repository, "cli/repository")

    def test_environment_is_used_when_config_is_missing(self):
        nested = self.make_repo()
        with patch.dict(
            os.environ,
            {"PDLC_TRACKER_REPOSITORY": "environment/repository"},
            clear=False,
        ):
            config = load_config(nested)
        self.assertEqual(config.tracker_repository, "environment/repository")

    def test_github_validation_explains_configuration(self):
        with self.assertRaisesRegex(ConfigurationError, "Create .pdlc/config.toml"):
            Config().validate_providers()

    def test_missing_repository_names_the_value_and_the_origin_fallback(self):
        guidance = configuration_guidance(["tracker.github.repository"])
        self.assertIn("Missing: tracker.github.repository", guidance)
        self.assertIn("auto-detected", guidance)
        self.assertIn("origin", guidance)

    def test_guidance_omits_the_origin_hint_when_repository_is_not_missing(self):
        self.assertNotIn(
            "auto-detected", configuration_guidance(["tracker.github.project_number"])
        )

    def test_file_tracker_does_not_need_github_values(self):
        Config(tracker_provider="file").validate_providers()

    def test_config_rejects_unknown_settings(self):
        nested = self.make_repo('[tracker]\nunknown = "value"\n')
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
        self.write_home_config('[tracker.github]\nrepository = "home/repository"\n')
        nested = self.make_repo('[tracker.github]\nrepository = "repo/repository"\n')
        self.assertEqual(load_config(nested).tracker_repository, "repo/repository")

    def test_home_repository_sections_are_isolated_and_case_insensitive(self):
        self.write_home_config(
            '[worktree]\nbase_ref = "global"\n'
            '[repository."Acme/A".worktree]\ninit_script = "echo A"\n'
            '[repository."acme/B".worktree]\ninit_script = "echo B"\n'
        )
        for identity, script in (("acme/a", "echo A"), ("acme/B", "echo B"), ("acme/C", None)):
            with self.subTest(identity=identity):
                config = load_config(self.make_git_repo(f"git@github.com:{identity}.git"))
                self.assertEqual(config.worktree_init_script, script)
                self.assertEqual(config.worktree_base_ref, "global")

    def test_repository_layer_precedence_and_capabilities(self):
        self.write_home_config(
            '[worktree]\ninit_script = "global"\n'
            '[agents]\ncore-implementer = "global-core"\nui-implementer = "global-ui"\n'
            '[repository."acme/A".worktree]\ninit_script = "scoped"\nbase_ref = "scoped-base"\n'
            '[repository."acme/A".agents]\ncore-implementer = "scoped-core"\n'
            '[repository."acme/A".skills]\nbuild-run = "scoped-build"\n'
        )
        nested = self.make_git_repo("git@github.com:acme/A.git")
        config = load_config(nested)
        self.assertEqual(config.worktree_init_script, "scoped")
        self.assertEqual(get_capabilities().agent("core-implementer"), "scoped-core")
        self.assertEqual(get_capabilities().agent("ui-implementer"), "global-ui")
        self.assertEqual(get_capabilities().skill("build-run"), "scoped-build")
        path = nested.parent / ".pdlc" / "config.toml"
        path.parent.mkdir()
        path.write_text('[worktree]\ninit_script = ""\n[agents]\ncore-implementer = "repo-core"\n')
        config = load_config(nested)
        self.assertEqual(config.worktree_init_script, "")
        self.assertEqual(config.worktree_base_ref, "scoped-base")
        self.assertEqual(get_capabilities().agent("core-implementer"), "repo-core")
        self.assertEqual(load_config(nested, overrides={"worktree_init_script": "cli"}).worktree_init_script, "cli")

    def test_global_and_cli_repository_values_do_not_select_hooks(self):
        self.write_home_config(
            '[tracker.github]\nrepository = "acme/B"\n'
            '[repository."acme/A".worktree]\ninit_script = "A"\n'
            '[repository."acme/B".worktree]\ninit_script = "B"\n'
        )
        nested = self.make_git_repo("git@github.com:acme/A.git")
        with patch.dict(os.environ, {"PDLC_TRACKER_REPOSITORY": "acme/B"}):
            self.assertEqual(load_config(nested, overrides={"tracker_repository": "acme/B"}).worktree_init_script, "A")
            self.assertIsNone(load_config(self.make_repo()).worktree_init_script)
            self.assertIsNone(load_config(self.non_repo_dir()).worktree_init_script)

    def test_local_repository_identity_is_fallback_only(self):
        self.write_home_config('[repository."acme/A".worktree]\ninit_script = "A"\n')
        config = '[code.github]\nrepository = "acme/A"\n'
        for origin, script in (("https://gitlab.com/acme/A.git", "A"), ("git@github.com:acme/B.git", None)):
            with self.subTest(origin=origin):
                self.assertEqual(load_config(self.make_git_repo(origin, config)).worktree_init_script, script)

    def test_repository_identity_survives_linked_worktrees(self):
        self.write_home_config('[repository."acme/A".worktree]\ninit_script = "A"\n')
        repo = self.make_git_repo("git@github.com:acme/A.git").parent
        subprocess.run(["git", "-C", str(repo), "-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "-qm", "seed", "--allow-empty"], check=True)
        linked = repo.parent / (repo.name + "-linked")
        subprocess.run(["git", "-C", str(repo), "worktree", "add", "-qb", "linked", str(linked)], check=True)
        self.assertEqual(load_config(linked).worktree_init_script, "A")

    def test_invalid_repository_sections_are_rejected_even_when_unmatched(self):
        for body, message in (
            ('[repository.A.worktree]\ninit_script = "A"\n', "owner/name"),
            ('[repository."acme/B".worktree]\nbogus = "B"\n', "Unknown setting"),
            ('[repository."acme/B".workflow]\nmax_attempts = 0\n', "max_attempts"),
            ('[repository."acme/B".skills]\nbuild-run = 1\n', "non-empty string"),
            ('[repository."acme/B".unknown]\n', "Unknown table"),
            ('[repository]\n"acme/B" = "B"\n', "TOML table"),
            ('[repository."acme/B".worktree]\ninit_script = []\n', "TOML scalar"),
            ('[repository."acme/B".worktree]\n[repository."Acme/b".worktree]\n', "Duplicate"),
        ):
            with self.subTest(body=body):
                self.write_home_config(body)
                with self.assertRaisesRegex(ConfigurationError, message):
                    load_config(self.make_git_repo("git@github.com:acme/A.git"))

    def test_repository_sections_are_home_only(self):
        nested = self.make_repo('[repository."acme/A".worktree]\ninit_script = "A"\n')
        with self.assertRaisesRegex(ConfigurationError, "Unknown table"):
            load_config(nested)

    def test_repository_is_derived_from_git_origin_when_unset(self):
        for origin_url in (
            "https://github.com/acme/widgets.git",
            "https://github.com/acme/widgets",
            "git@github.com:acme/widgets.git",
            "ssh://git@github.com/acme/widgets.git",
            "ssh://git@github.com:22/acme/widgets.git",
        ):
            with self.subTest(origin_url=origin_url):
                nested = self.make_git_repo(origin_url)
                with patch.dict(os.environ, {}, clear=False):
                    os.environ.pop("PDLC_TRACKER_REPOSITORY", None)
                    config = load_config(nested)
                self.assertEqual(config.tracker_repository, "acme/widgets")
                self.assertEqual(config.code_repository, "acme/widgets")

    def test_configured_repository_beats_git_origin(self):
        nested = self.make_git_repo(
            "https://github.com/acme/widgets.git",
            '[tracker.github]\nrepository = "acme/configured"\n',
        )
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("PDLC_TRACKER_REPOSITORY", None)
            self.assertEqual(load_config(nested).tracker_repository, "acme/configured")

    def test_environment_repository_beats_git_origin(self):
        nested = self.make_git_repo("https://github.com/acme/widgets.git")
        with patch.dict(
            os.environ, {"PDLC_TRACKER_REPOSITORY": "acme/from-env"}, clear=False
        ):
            self.assertEqual(load_config(nested).tracker_repository, "acme/from-env")

    def test_non_github_git_origin_is_not_derived(self):
        for origin_url in (
            "https://gitlab.com/acme/widgets.git",
            "git@github-work:acme/widgets.git",
        ):
            with self.subTest(origin_url=origin_url):
                nested = self.make_git_repo(origin_url)
                with patch.dict(os.environ, {}, clear=False):
                    os.environ.pop("PDLC_TRACKER_REPOSITORY", None)
                    config = load_config(nested)
                self.assertIsNone(config.tracker_repository)
                self.assertIsNone(config.code_repository)

    def test_home_config_repository_overrides_the_environment_variable(self):
        self.write_home_config('[tracker.github]\nrepository = "home/repository"\n')
        nested = self.make_repo()
        with patch.dict(os.environ, {"PDLC_TRACKER_REPOSITORY": "environment/repository"}):
            config = load_config(nested)
        self.assertEqual(config.tracker_repository, "home/repository")

    def test_tracker_and_code_repositories_are_independent(self):
        # A service checkout pointing at a shared tracker keeps its own pull
        # requests: only the tracker is configured, the code side is origin.
        nested = self.make_git_repo(
            "git@github.com:acme/svc-a.git",
            '[tracker.github]\nrepository = "acme/product"\n',
        )
        config = load_config(nested)
        self.assertEqual(config.tracker_repository, "acme/product")
        self.assertEqual(config.code_repository, "acme/svc-a")
        overridden = load_config(self.make_git_repo(
            "git@github.com:acme/svc-a.git",
            '[tracker.github]\nrepository = "acme/product"\n[code.github]\nrepository = "upstream/svc-a"\n',
        ))
        self.assertEqual(overridden.code_repository, "upstream/svc-a")

    def test_code_repository_falls_back_to_the_tracker_without_origin(self):
        nested = self.make_git_repo(
            "git@github-work:acme/widgets.git",
            '[tracker.github]\nrepository = "acme/widgets"\n',
        )
        self.assertEqual(load_config(nested).code_repository, "acme/widgets")

    def test_code_github_repository_is_required_for_a_github_code_provider(self):
        config = Config(tracker_provider="azure", code_provider="github", azure_org="o", azure_project="p")
        with self.assertRaisesRegex(ConfigurationError, r"code\.github\.repository"):
            config.validate_providers()

    def test_old_backend_tables_are_unknown(self):
        for body in ('[backend]\nname = "file"\n', '[code_host]\nname = "github"\n', '[attachment_host]\nname = "file"\n'):
            with self.subTest(body=body):
                with self.assertRaisesRegex(ConfigurationError, "Unknown table"):
                    load_config(self.make_repo(body))

    def test_home_config_applies_without_repository(self):
        self.write_home_config(
            '[tracker.github]\n'
            'repository = "home/repository"\n'
            'project_number = "9"\n'
            'project_owner = "home-owner"\n'
        )
        config = load_config(self.non_repo_dir())
        self.assertEqual(config.tracker_repository, "home/repository")
        config.validate_providers()

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
            tracker="github",
            code="github",
            tracker_repository="owner/repository",
            code_repository=None,
            project_number="12",
            project_owner="owner",
        )
        config = load_config(root)
        self.assertEqual(config.tracker_repository, "owner/repository")
        self.assertEqual(config.project_number, "12")
