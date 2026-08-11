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

    def test_uninstall_documents_all_runtime_sidecars(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        uninstall = readme.split("## Uninstall", 1)[1].split("## Building", 1)[0]
        for required in ("Restore original Windows settings", "pearipherals.json", "pearipherals.err.log"):
            self.assertIn(required, uninstall)


if __name__ == "__main__":
    unittest.main()
