import ast
import importlib
import os
import queue
import unittest
from pathlib import Path


class SnippingOverlayTests(unittest.TestCase):
    def test_opens_windows_builtin_selection_overlay(self):
        snipping = importlib.import_module("pearipherals_snipping")
        opened = []

        result = snipping.open_snipping_overlay(startfile=opened.append)

        self.assertIsNone(result)
        self.assertEqual(["ms-screenclip:"], opened)

    def test_custom_capture_and_clipboard_backend_are_retired(self):
        root = Path(__file__).resolve().parents[1]
        source = (root / "pearipherals.py").read_text(encoding="utf-8")

        self.assertFalse((root / "pearipherals_screenshot.py").exists())
        self.assertFalse((root / "tests" / "test_screenshot.py").exists())
        self.assertNotIn("pearipherals_screenshot", source)
        self.assertNotIn("capture_full_desktop", source)
        self.assertNotIn('kind == "screenshot"', source)


class SnippingWorkerTests(unittest.TestCase):
    @staticmethod
    def _load_worker(**overrides):
        source_path = os.path.join(os.path.dirname(__file__), "..", "pearipherals.py")
        with open(source_path, "r", encoding="utf-8") as stream:
            tree = ast.parse(stream.read(), source_path)
        worker = next(
            node for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "worker"
        )

        action_queue = queue.Queue()
        action_queue.put(("snip", None))
        action_queue.put(None)
        events = []
        namespace = {
            "actions": action_queue,
            "send_keys": lambda *_args: events.append(("keys",)),
            "restore_all_windows": lambda: events.append(("restore",)),
            "brightness": object(),
            "osd": object(),
            "tray_icon": object(),
            "open_snipping_overlay": lambda: events.append(("open",)),
            "_notify": lambda _icon, message, title: events.append(
                ("notify", message, title)
            ),
            "append_error": lambda message: events.append(("error", message)),
            "queue": queue,
        }
        namespace.update(overrides)
        exec(compile(ast.Module([worker], []), source_path, "exec"), namespace)
        return namespace["worker"], events

    def test_snip_action_opens_overlay_without_claiming_capture_success(self):
        worker, events = self._load_worker()

        worker()

        self.assertEqual([("open",)], events)

    def test_snip_launch_failure_is_logged_and_notified(self):
        failure = OSError("protocol unavailable")

        def fail_open():
            events.append(("open",))
            raise failure

        worker, events = self._load_worker(open_snipping_overlay=fail_open)

        worker()

        self.assertEqual(
            [
                ("open",),
                ("error", "Snipping overlay launch failed: protocol unavailable"),
                (
                    "notify",
                    "Windows' snipping overlay could not be opened.",
                    "Snipping Tool failed",
                ),
            ],
            events,
        )


if __name__ == "__main__":
    unittest.main()
