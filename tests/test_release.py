import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "write_version_info.py"
ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "build-sign-release.yml"
CI_WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"
SECURITY_POLICY = ROOT / "SECURITY.md"
CONTRIBUTING_GUIDE = ROOT / "CONTRIBUTING.md"
PULL_REQUEST_TEMPLATE = ROOT / ".github" / "pull_request_template.md"
ISSUE_TEMPLATE_DIR = ROOT / ".github" / "ISSUE_TEMPLATE"
BUG_REPORT_FORM = ISSUE_TEMPLATE_DIR / "bug_report.yml"
FEATURE_REQUEST_FORM = ISSUE_TEMPLATE_DIR / "feature_request.yml"
ISSUE_CONFIG = ISSUE_TEMPLATE_DIR / "config.yml"
DEPENDABOT_CONFIG = ROOT / ".github" / "dependabot.yml"
BUILD_MANIFEST_SCRIPT = ROOT / "scripts" / "write_build_manifest.py"
BUILD_SCRIPT = ROOT / "build.bat"
GITIGNORE = ROOT / ".gitignore"
PRIVACY_POLICY = ROOT / "PRIVACY.md"
README = ROOT / "README.md"
SPEC = importlib.util.spec_from_file_location("write_version_info", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class ReleaseMetadataTests(unittest.TestCase):
    def test_normalizes_release_tag_to_windows_version(self):
        self.assertEqual((1, 2, 3, 0), MODULE.normalize_version("v1.2.3"))
        self.assertEqual((1, 2, 3, 4), MODULE.normalize_version("1.2.3.4"))

    def test_rejects_invalid_or_out_of_range_versions(self):
        for value in ("1.2", "latest", "1.2.3-beta", "1.2.3.65536"):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    MODULE.normalize_version(value)

    def test_version_resource_has_consistent_product_metadata(self):
        rendered = MODULE.render((1, 2, 3, 0))
        self.assertIn("filevers=(1, 2, 3, 0)", rendered)
        self.assertIn("prodvers=(1, 2, 3, 0)", rendered)
        self.assertIn("StringStruct('ProductName', 'Pearipherals')", rendered)
        self.assertIn("StringStruct('ProductVersion', '1.2.3')", rendered)
        self.assertIn("StringStruct('OriginalFilename', 'Pearipherals.exe')", rendered)

    def test_cli_writes_utf8_version_resource(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "nested" / "version.txt"
            subprocess.run(
                [sys.executable, str(SCRIPT), "1.2.3", str(output)],
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertIn("ProductVersion', '1.2.3'", output.read_text(encoding="utf-8"))

    def test_release_workflow_pins_actions_and_avoids_template_injection(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        uses = re.findall(r"^\s*uses:\s*([^\s#]+)", workflow, flags=re.MULTILINE)
        self.assertTrue(uses)
        for action in uses:
            with self.subTest(action=action):
                self.assertRegex(action, r"@(?:[0-9a-f]{40})$")
        self.assertIn("DISPATCH_VERSION: ${{ inputs.version }}", workflow)
        self.assertNotIn("$version = '${{ inputs.version }}'", workflow)
        self.assertIn("persist-credentials: false", workflow)

    def test_release_workflow_is_hash_locked_and_fails_closed_for_tags(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("--no-cache-dir --require-hashes", workflow)
        self.assertIn("if: github.ref_type == 'tag' || inputs.submit_for_signing", workflow)
        self.assertIn("Official signing is not configured", workflow)
        self.assertIn("path: release/Pearipherals.exe", workflow)
        self.assertNotIn("path: signed/**/Pearipherals.exe", workflow)

    def test_release_workflow_uses_available_windows_python(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        # Python.org's final 3.11 Windows installer is 3.11.9; later 3.11
        # security releases are source-only and absent from setup-python's
        # Windows tool manifest.
        self.assertIn('python-version: "3.11.9"', workflow)

    def test_uninstall_documents_all_runtime_sidecars(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        uninstall = readme.split("## Uninstall", 1)[1].split("## Build", 1)[0]
        for required in (
            "Restore original Windows settings",
            "pearipherals.json",
            "pearipherals.err.log",
        ):
            self.assertIn(required, uninstall)


class RepositoryQualityTests(unittest.TestCase):
    def test_ci_runs_for_pushes_and_pull_requests_targeting_main(self):
        self.assertTrue(CI_WORKFLOW.is_file(), f"missing CI workflow: {CI_WORKFLOW}")
        workflow = CI_WORKFLOW.read_text(encoding="utf-8")

        self.assertRegex(workflow, r"(?m)^\s*push:\s*$")
        self.assertRegex(workflow, r"(?ms)^\s*push:\s*\n\s*branches:\s*\n\s*-\s*[\"']?main[\"']?\s*$")
        self.assertRegex(workflow, r"(?m)^\s*pull_request:\s*$")
        self.assertRegex(
            workflow,
            r"(?ms)^\s*pull_request:\s*\n\s*branches:\s*\n\s*-\s*[\"']?main[\"']?\s*$",
        )

    def test_ci_is_read_only_and_cancels_superseded_runs(self):
        workflow = CI_WORKFLOW.read_text(encoding="utf-8")

        self.assertIn("permissions:", workflow)
        self.assertIn("concurrency:", workflow)
        permissions = workflow.split("permissions:", 1)[1].split("concurrency:", 1)[0]
        permission_lines = [
            line.strip()
            for line in permissions.splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]
        self.assertEqual(["contents: read"], permission_lines)
        self.assertNotRegex(permissions, r"(?m):\s*write\s*$")
        self.assertIn("group: ${{ github.workflow }}-${{ github.ref }}", workflow)
        self.assertRegex(workflow, r"(?m)^\s*cancel-in-progress:\s*true\s*$")

    def test_ci_uses_windows_and_immutable_toolchain_actions(self):
        workflow = CI_WORKFLOW.read_text(encoding="utf-8")

        self.assertIn("runs-on: windows-2022", workflow)
        uses = re.findall(r"^\s*uses:\s*([^\s#]+)", workflow, flags=re.MULTILINE)
        self.assertIn("actions/checkout", {action.split("@", 1)[0] for action in uses})
        self.assertIn("actions/setup-python", {action.split("@", 1)[0] for action in uses})
        for action in uses:
            with self.subTest(action=action):
                self.assertRegex(action, r"@[0-9a-f]{40}$")
        self.assertIn("persist-credentials: false", workflow)
        self.assertIn('python-version: "3.11.9"', workflow)

    def test_ci_installs_locked_dependencies_and_runs_complete_gates(self):
        workflow = CI_WORKFLOW.read_text(encoding="utf-8")

        self.assertIn(
            "python -m pip install --disable-pip-version-check --no-cache-dir --require-hashes -r requirements-build.txt",
            workflow,
        )
        self.assertIn(
            'python -m unittest discover -s tests -p "test_*.py" -v',
            workflow,
        )
        # The exact module list is asserted by PackagingGateTests; here we only
        # require that the byte-compilation gate exists as its own step.
        self.assertIn("python -m py_compile pearipherals.py", workflow)

    def test_workflows_keep_unit_tests_and_compilation_in_fail_closed_steps(self):
        unit_command = 'python -m unittest discover -s tests -p "test_*.py" -v'
        for path in (WORKFLOW, CI_WORKFLOW):
            workflow = path.read_text(encoding="utf-8")
            with self.subTest(path=path, gate="unit tests"):
                self.assertRegex(
                    workflow,
                    rf"(?m)^[ \t]*- name: Run complete unit test gate[ \t]*\n"
                    rf"[ \t]*run: {re.escape(unit_command)}[ \t]*$",
                )
            with self.subTest(path=path, gate="byte compilation"):
                self.assertRegex(
                    workflow,
                    r"(?m)^[ \t]*- name: Run byte-compilation gate[ \t]*\n"
                    r"[ \t]*run: python -m py_compile [^\n]*tests/test_support\.py[ \t]*$",
                )

    def test_security_policy_uses_private_reporting_and_safe_disclosure(self):
        self.assertTrue(SECURITY_POLICY.is_file(), f"missing security policy: {SECURITY_POLICY}")
        policy = SECURITY_POLICY.read_text(encoding="utf-8")
        lowered = policy.lower()

        self.assertIn("supported versions", lowered)
        self.assertIn("github security advisories", lowered)
        self.assertIn(
            "https://github.com/onlinefix/pearipherals/security/advisories/new",
            lowered,
        )
        self.assertIn("do not open a public issue", lowered)
        for sensitive in (
            "pearipherals.err.log",
            "pearipherals.json",
            "registry export",
            "bluetooth address",
            "full local path",
        ):
            with self.subTest(sensitive=sensitive):
                self.assertIn(sensitive, lowered)
        self.assertNotRegex(lowered, r"respond(?:ed)? within\s+\d+")

    def test_contributing_guide_covers_setup_safety_and_release_boundaries(self):
        self.assertTrue(
            CONTRIBUTING_GUIDE.is_file(),
            f"missing contributing guide: {CONTRIBUTING_GUIDE}",
        )
        guide = CONTRIBUTING_GUIDE.read_text(encoding="utf-8")
        lowered = guide.lower()

        for required in (
            "windows 10 or windows 11",
            "python 3.11",
            "red-green-refactor",
            "input hooks",
            "registry",
            "rollback",
            "[verified]",
            ".hermes/",
            ".hermes.md",
            "do not restart",
        ):
            with self.subTest(required=required):
                self.assertIn(required, lowered)
        self.assertIn(
            '.venv\\Scripts\\python.exe -m unittest discover -s tests -p "test_*.py" -v',
            guide,
        )
        self.assertIn(
            ".venv\\Scripts\\python.exe -m py_compile pearipherals.py",
            guide,
        )
        for target in (
            "pearipherals_snipping.py",
            "pearipherals_support.py",
            "tests\\test_snipping.py",
            "tests\\test_support.py",
        ):
            with self.subTest(target=target):
                self.assertIn(target, guide)
        self.assertIn("do not create or publish a release", lowered)
        self.assertIn("trusted signing", lowered)

    def test_pull_request_template_requires_evidence_and_risk_review(self):
        self.assertTrue(
            PULL_REQUEST_TEMPLATE.is_file(),
            f"missing pull-request template: {PULL_REQUEST_TEMPLATE}",
        )
        template = PULL_REQUEST_TEMPLATE.read_text(encoding="utf-8").lower()

        for required in (
            "behavior summary",
            "red evidence",
            "green evidence",
            "complete test gate",
            "manual hardware scope",
            "input and registry risk",
            "rollback",
            "security and privacy",
            "release impact",
            "not tested on hardware",
        ):
            with self.subTest(required=required):
                self.assertIn(required, template)

    def test_bug_form_collects_compatibility_context_without_private_data(self):
        self.assertTrue(BUG_REPORT_FORM.is_file(), f"missing bug form: {BUG_REPORT_FORM}")
        form = BUG_REPORT_FORM.read_text(encoding="utf-8").lower()

        for field_id in (
            "windows-version",
            "device-model-revision",
            "connection",
            "driver-version",
            "pearipherals-version",
            "reproduction-steps",
            "expected-behavior",
            "actual-behavior",
            "sleep-wake",
            "regression-status",
        ):
            with self.subTest(field_id=field_id):
                self.assertIn(f"id: {field_id}", form)
        for warning in (
            "usernames",
            "device identifiers",
            "bluetooth addresses",
            "full local paths",
            "registry exports",
            "do not attach raw hid traces",
            "explicit maintainer coordination",
        ):
            with self.subTest(warning=warning):
                self.assertIn(warning, form)

    def test_feature_form_captures_problem_scope_alternatives_and_safety(self):
        self.assertTrue(
            FEATURE_REQUEST_FORM.is_file(),
            f"missing feature form: {FEATURE_REQUEST_FORM}",
        )
        form = FEATURE_REQUEST_FORM.read_text(encoding="utf-8").lower()

        for field_id in (
            "user-problem",
            "proposed-behavior",
            "alternatives",
            "hardware-scope",
            "safety-impact",
        ):
            with self.subTest(field_id=field_id):
                self.assertIn(f"id: {field_id}", form)
        self.assertIn("input handling", form)
        self.assertIn("registry", form)
        self.assertIn("privacy", form)
        self.assertIn("remove sensitive information", form)

    def test_issue_chooser_disables_blank_issues_and_links_private_security(self):
        self.assertTrue(ISSUE_CONFIG.is_file(), f"missing issue config: {ISSUE_CONFIG}")
        config = ISSUE_CONFIG.read_text(encoding="utf-8").lower()

        self.assertRegex(config, r"(?m)^blank_issues_enabled:\s*false\s*$")
        self.assertIn("report a security vulnerability privately", config)
        self.assertIn(
            "https://github.com/onlinefix/pearipherals/security/advisories/new",
            config,
        )
        self.assertIn("do not disclose security details in a public issue", config)

    def test_dependabot_updates_only_github_actions_on_a_conservative_schedule(self):
        self.assertTrue(
            DEPENDABOT_CONFIG.is_file(),
            f"missing Dependabot config: {DEPENDABOT_CONFIG}",
        )
        config = DEPENDABOT_CONFIG.read_text(encoding="utf-8").lower()

        self.assertRegex(config, r"(?m)^version:\s*2\s*$")
        self.assertEqual(1, len(re.findall(r"(?m)^\s*-\s*package-ecosystem:", config)))
        self.assertRegex(
            config,
            r'(?m)^\s*-\s*package-ecosystem:\s*["\']github-actions["\']\s*$',
        )
        self.assertRegex(config, r'(?m)^\s*directory:\s*["\']/["\']\s*$')
        self.assertRegex(config, r'(?m)^\s*interval:\s*["\']weekly["\']\s*$')
        limit = re.search(r"(?m)^\s*open-pull-requests-limit:\s*(\d+)\s*$", config)
        self.assertIsNotNone(limit)
        self.assertLessEqual(int(limit.group(1)), 5)
        self.assertNotRegex(config, r'package-ecosystem:\s*["\']?(?:pip|uv)["\']?')


class SupportDocumentationTests(unittest.TestCase):
    def test_readme_documents_the_complete_support_and_lifecycle_surface(self):
        readme = README.read_text(encoding="utf-8")
        lowered = readme.lower()

        for required in (
            "about / status",
            "save a diagnostic report",
            "pearipherals-diagnostics.json",
            "prepare for removal",
            "open documentation",
            "report a problem",
        ):
            with self.subTest(required=required):
                self.assertIn(required, lowered)
        # Privacy limits and the local-only guarantee must be stated, not implied.
        self.assertIn("never uploads", lowered)
        self.assertIn("no local paths", lowered)
        # Confirmation-based, reversible, non-destructive removal.
        self.assertIn("asks for confirmation", lowered)
        self.assertIn("does not delete", lowered)
        # Upgrade observation.
        self.assertIn("previous version", lowered)

    def test_uninstall_section_lists_every_runtime_sidecar(self):
        readme = README.read_text(encoding="utf-8")
        uninstall = readme.split("## Uninstall", 1)[1].split("## Build", 1)[0]

        for sidecar in (
            "pearipherals.json",
            "pearipherals.err.log",
            "pearipherals-diagnostics.json",
        ):
            with self.subTest(sidecar=sidecar):
                self.assertIn(sidecar, uninstall)
        self.assertIn("Prepare for removal", uninstall)

    def test_privacy_policy_describes_explicit_local_reviewable_diagnostics(self):
        policy = PRIVACY_POLICY.read_text(encoding="utf-8").lower()

        for required in (
            "pearipherals-diagnostics.json",
            "only when you ask",
            "plain json",
            "never transmit",
            "review",
        ):
            with self.subTest(required=required):
                self.assertIn(required, policy)
        for excluded in ("username", "bluetooth address", "full local path"):
            with self.subTest(excluded=excluded):
                self.assertIn(excluded, policy)

    def test_privacy_policy_discloses_timestamp_and_user_clicked_support_links(self):
        policy = PRIVACY_POLICY.read_text(encoding="utf-8").lower()

        self.assertIn("utc generation timestamp", policy)
        self.assertIn("fixed github support links", policy)
        self.assertIn("only when you click", policy)
        self.assertIn("no automatic diagnostic upload", policy)
        self.assertNotIn("no network destination anywhere", policy)

    def test_snipping_overlay_behavior_and_privacy_are_explicit(self):
        readme = README.read_text(encoding="utf-8").lower()
        policy = PRIVACY_POLICY.read_text(encoding="utf-8").lower()

        for required in (
            "f6",
            "windows snipping tool",
            "selection overlay",
            "select a region",
            "clipboard",
            "auto-save setting",
            "modifier+f6",
        ):
            with self.subTest(document="README", required=required):
                self.assertIn(required, readme)
        for required in (
            "only when you press f6",
            "windows snipping tool",
            "selection overlay",
            "pearipherals does not capture",
            "windows handles",
            "clipboard",
            "auto-save setting",
            "never uploaded by pearipherals",
            "not included in diagnostics",
        ):
            with self.subTest(document="PRIVACY", required=required):
                self.assertIn(required, policy)
        self.assertNotIn("full desktop", readme)
        self.assertNotIn("full desktop", policy)

    def test_generated_diagnostic_report_is_ignored_by_git(self):
        ignore = GITIGNORE.read_text(encoding="utf-8")

        self.assertRegex(ignore, r"(?m)^pearipherals-diagnostics\.json\s*$")


class PackagingGateTests(unittest.TestCase):
    COMPILE_TARGETS = (
        "pearipherals.py",
        "pearipherals_core.py",
        "pearipherals_snipping.py",
        "pearipherals_support.py",
        "pearipherals_version.py",
        "scripts/write_build_manifest.py",
        "scripts/write_version_info.py",
        "tests/test_core.py",
        "tests/test_release.py",
        "tests/test_snipping.py",
        "tests/test_support.py",
    )

    def test_every_release_relevant_module_is_byte_compiled_in_both_workflows(self):
        for path in (WORKFLOW, CI_WORKFLOW):
            workflow = path.read_text(encoding="utf-8")
            compile_line = next(
                line for line in workflow.splitlines()
                if "py_compile" in line
            )
            for target in self.COMPILE_TARGETS:
                with self.subTest(path=path.name, target=target):
                    self.assertIn(target, compile_line)

    def test_unit_and_compilation_gates_stay_separate_and_fail_closed(self):
        unit_command = 'python -m unittest discover -s tests -p "test_*.py" -v'
        for path in (WORKFLOW, CI_WORKFLOW):
            workflow = path.read_text(encoding="utf-8")
            with self.subTest(path=path.name, gate="unit tests"):
                self.assertRegex(
                    workflow,
                    rf"(?m)^[ \t]*- name: Run complete unit test gate[ \t]*\n"
                    rf"[ \t]*run: {re.escape(unit_command)}[ \t]*$",
                )
            with self.subTest(path=path.name, gate="byte compilation"):
                self.assertRegex(
                    workflow,
                    r"(?m)^[ \t]*- name: Run byte-compilation gate[ \t]*\n"
                    r"[ \t]*run: python -m py_compile ",
                )
            with self.subTest(path=path.name, gate="separate steps"):
                # Chaining them into one step would let a shell swallow a
                # failure; each gate must be its own fail-closed step.
                self.assertNotIn("unittest discover -s tests -p \"test_*.py\" -v && ", workflow)

    def test_release_build_generates_the_manifest_before_pyinstaller_analysis(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")

        manifest_at = workflow.index("scripts/write_build_manifest.py")
        pyinstaller_at = workflow.index("pyinstaller")
        self.assertLess(manifest_at, pyinstaller_at)

    def test_frozen_build_bundles_the_manifest_as_one_file_data(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")

        self.assertIn("--add-data", workflow)
        self.assertIn("pearipherals-build.json", workflow)

    def test_pe_resource_and_manifest_share_one_validated_version_input(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")

        # Both generators must read the same validated env var, never inputs.*
        # or the raw ref directly.
        for generator in (
            "scripts/write_version_info.py $env:PEARIPHERALS_VERSION",
            "scripts/write_build_manifest.py $env:PEARIPHERALS_VERSION",
        ):
            with self.subTest(generator=generator):
                self.assertIn(generator, workflow)
        self.assertNotIn("write_build_manifest.py ${{", workflow)

    def test_local_build_validates_environment_version_before_expansion(self):
        script = BUILD_SCRIPT.read_text(encoding="utf-8")
        validation_at = script.index("validate_build_version")
        version_info_at = script.index("scripts\\write_version_info.py")
        manifest_at = script.index("scripts\\write_build_manifest.py \"%PEARIPHERALS_VERSION%\"")

        self.assertLess(validation_at, version_info_at)
        self.assertLess(validation_at, manifest_at)
        self.assertIn("os.environ.get('PEARIPHERALS_VERSION'", script)
        self.assertIn("re.fullmatch", script)

    def test_local_build_rejects_quote_breakout_before_any_injected_command_runs(self):
        env = dict(os.environ)
        env["PEARIPHERALS_VERSION"] = '1.2.0" & echo BUILD_BAT_QUOTE_BREAKOUT & rem "'
        result = subprocess.run(
            ["cmd.exe", "/c", str(BUILD_SCRIPT)],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )

        combined = result.stdout + result.stderr
        self.assertNotEqual(0, result.returncode)
        self.assertNotIn("BUILD_BAT_QUOTE_BREAKOUT", combined)
        self.assertIn("Build FAILED", combined)

    def test_generated_build_manifest_is_ignored_and_never_committed(self):
        ignore = GITIGNORE.read_text(encoding="utf-8")

        self.assertRegex(ignore, r"(?m)^build/\s*$")

    def test_local_build_resets_inherited_revision_and_uses_clean_worktree_resolver(self):
        script = BUILD_SCRIPT.read_text(encoding="utf-8")

        self.assertRegex(script, r"(?m)^set PEARIPHERALS_REVISION=$")
        self.assertIn("--resolve-local-revision .", script)
        self.assertNotIn("git rev-parse HEAD", script)


class BuildManifestTests(unittest.TestCase):
    @staticmethod
    def _module():
        spec = importlib.util.spec_from_file_location(
            "write_build_manifest", BUILD_MANIFEST_SCRIPT
        )
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        return module

    def test_manifest_records_a_prefixed_frozen_revision_identity(self):
        module = self._module()

        manifest = module.build_manifest("1.2.0", "A" * 40)

        self.assertEqual("git:" + "a" * 40, manifest["build_id"])
        self.assertEqual("1.2.0", manifest["version"])

    def test_manifest_rejects_anything_that_is_not_an_exact_revision(self):
        module = self._module()

        for revision in ("", "abc", "z" * 40, "a" * 39, "a" * 41, None):
            with self.subTest(revision=revision):
                with self.assertRaises(ValueError):
                    module.build_manifest("1.2.0", revision)

    def test_manifest_rejects_a_version_the_pe_resource_would_reject(self):
        module = self._module()

        for version in ("1.2", "latest", "1.2.3-beta", "1.2.3.65536"):
            with self.subTest(version=version):
                with self.assertRaises(ValueError):
                    module.build_manifest(version, "a" * 40)

    def test_manifest_is_deterministic_for_identical_inputs(self):
        module = self._module()

        first = module.render("1.2.0", "a" * 40)
        second = module.render("1.2.0", "a" * 40)

        self.assertEqual(first, second)
        self.assertEqual(
            {"build_id", "version", "channel"}, set(json.loads(first))
        )

    def test_local_revision_cli_returns_unknown_for_a_dirty_repository(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
            subprocess.run(
                ["git", "config", "user.email", "test@example.invalid"],
                cwd=repo, check=True,
            )
            subprocess.run(
                ["git", "config", "user.name", "Pearipherals Tests"],
                cwd=repo, check=True,
            )
            (repo / "tracked.txt").write_text("clean\n", encoding="utf-8")
            subprocess.run(["git", "add", "tracked.txt"], cwd=repo, check=True)
            subprocess.run(
                ["git", "commit", "-q", "-m", "fixture"], cwd=repo, check=True
            )
            (repo / "untracked.txt").write_text("dirty\n", encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable, str(BUILD_MANIFEST_SCRIPT),
                    "--resolve-local-revision", str(repo),
                ],
                capture_output=True, text=True,
            )

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual("0" * 40, result.stdout.strip())

    def test_manifest_carries_no_local_path_or_identifier(self):
        module = self._module()

        rendered = module.render("1.2.0", "a" * 40)

        for leak in ("C:\\", "/home/", "\\\\", "Users", "runner"):
            with self.subTest(leak=leak):
                self.assertNotIn(leak, rendered)

    def test_cli_writes_a_parseable_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "nested" / "pearipherals-build.json"
            subprocess.run(
                [
                    sys.executable, str(BUILD_MANIFEST_SCRIPT),
                    "1.2.0", "b" * 40, str(output),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            manifest = json.loads(output.read_text(encoding="utf-8"))

        self.assertEqual("git:" + "b" * 40, manifest["build_id"])

    def test_cli_fails_closed_on_an_unusable_revision(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "pearipherals-build.json"
            result = subprocess.run(
                [sys.executable, str(BUILD_MANIFEST_SCRIPT), "1.2.0", "nope", str(output)],
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(0, result.returncode)
            self.assertFalse(output.exists())

    def test_runtime_version_and_pe_product_version_agree(self):
        import pearipherals_version

        rendered = MODULE.render(
            MODULE.normalize_version(pearipherals_version.APP_VERSION)
        )

        self.assertIn(
            f"StringStruct('ProductVersion', '{pearipherals_version.APP_VERSION}')",
            rendered,
        )
        self.assertIn(
            f"StringStruct('FileVersion', '{pearipherals_version.APP_VERSION}')",
            rendered,
        )

    def test_manifest_version_matches_the_runtime_product_version(self):
        import pearipherals_version

        module = self._module()
        manifest = module.build_manifest(pearipherals_version.APP_VERSION, "c" * 40)

        self.assertEqual(pearipherals_version.APP_VERSION, manifest["version"])


if __name__ == "__main__":
    unittest.main()
