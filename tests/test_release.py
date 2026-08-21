import importlib.util
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
        uninstall = readme.split("## Uninstall", 1)[1].split("## Building", 1)[0]
        for required in ("Restore original Windows settings", "pearipherals.json", "pearipherals.err.log"):
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
        self.assertIn(
            "python -m py_compile pearipherals.py pearipherals_core.py "
            "scripts/write_version_info.py tests/test_core.py tests/test_release.py",
            workflow,
        )

    def test_workflows_keep_unit_tests_and_compilation_in_fail_closed_steps(self):
        unit_command = 'python -m unittest discover -s tests -p "test_*.py" -v'
        compile_command = (
            "python -m py_compile pearipherals.py pearipherals_core.py "
            "scripts/write_version_info.py tests/test_core.py tests/test_release.py"
        )
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
                    rf"(?m)^[ \t]*- name: Run byte-compilation gate[ \t]*\n"
                    rf"[ \t]*run: {re.escape(compile_command)}[ \t]*$",
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
            ".venv\\Scripts\\python.exe -m py_compile pearipherals.py pearipherals_core.py "
            "scripts\\write_version_info.py tests\\test_core.py tests\\test_release.py",
            guide,
        )
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


if __name__ == "__main__":
    unittest.main()
