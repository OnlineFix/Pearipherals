"""Real battery start/stop definitions and threads, with deterministic gates."""
import ast
from pathlib import Path
import threading
import time
import types
import unittest
from unittest import mock

import pearipherals_core as core


APP_PATH = Path(__file__).resolve().parents[1] / "pearipherals.py"


def lifecycle_harness(thread_type=threading.Thread):
    tree = ast.parse(APP_PATH.read_text(encoding="utf-8"), str(APP_PATH))
    names = {"start_battery_worker", "stop_battery_worker", "publish_battery_snapshot"}
    nodes = [node for node in tree.body if (
        isinstance(node, ast.FunctionDef) and node.name in names
    ) or (
        isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id.startswith("battery_")
            for target in node.targets
        )
    )]
    polled = threading.Event()
    hid = types.SimpleNamespace(enumerate=lambda: polled.set() or [])
    app = {**vars(core), "time": time, "append_error": mock.Mock(),
           "threading": types.SimpleNamespace(Event=threading.Event,
                                               Lock=threading.Lock, Thread=thread_type)}
    exec(compile(ast.Module(nodes, type_ignores=[]), str(APP_PATH), "exec"), app)
    return app, hid, polled


class BatteryLifecycleTests(unittest.TestCase):
    def test_terminal_stop_before_start_prevents_late_polling(self):
        app, hid, polled = lifecycle_harness()
        stop = app["battery_stop"]
        self.assertTrue(app["stop_battery_worker"]())
        with mock.patch.dict("sys.modules", {"hid": hid}):
            try:
                app["start_battery_worker"]()
                self.assertIs(stop, app["battery_stop"])
                self.assertTrue(stop.is_set())
                self.assertIsNone(app["battery_thread"])
                self.assertFalse(polled.is_set())
            finally:
                app["stop_battery_worker"]()

    def test_thread_start_failure_leaves_shutdown_safe(self):
        class FailedThread(threading.Thread):
            def start(self):
                raise RuntimeError("thread creation failed")

        app, hid, polled = lifecycle_harness(FailedThread)
        with mock.patch.dict("sys.modules", {"hid": hid}):
            app["start_battery_worker"]()
        self.assertTrue(app["battery_stop"].is_set())
        self.assertIsNone(app["battery_thread"])
        self.assertIsNone(app["battery_poller"])
        self.assertFalse(polled.is_set())
        app["append_error"].assert_called_once()
        self.assertTrue(app["stop_battery_worker"]())
        self.assertTrue(app["stop_battery_worker"]())

    def test_duplicate_start_and_repeated_stop_keep_one_worker(self):
        app, hid, polled = lifecycle_harness()
        with mock.patch.dict("sys.modules", {"hid": hid}):
            try:
                app["start_battery_worker"]()
                self.assertTrue(polled.wait(3))
                worker, stop = app["battery_thread"], app["battery_stop"]
                app["start_battery_worker"]()
                self.assertIs(worker, app["battery_thread"])
                self.assertIs(stop, app["battery_stop"])
                self.assertTrue(app["stop_battery_worker"]())
                self.assertTrue(app["stop_battery_worker"]())
                app["start_battery_worker"]()
                self.assertIsNone(app["battery_thread"])
                self.assertFalse(worker.is_alive())
            finally:
                app["stop_battery_worker"]()

    def test_late_worker_entry_observes_stop_and_join_releases_lock(self):
        run_entered = threading.Event()
        release_run = threading.Event()
        acquired = threading.Event()

        class LateThread(threading.Thread):
            def join(self, timeout=None):
                if timeout != 0:
                    # Release target only once stop is at its join boundary.
                    release_run.set()
                super().join(timeout)

            def run(self):
                run_entered.set()
                if not release_run.wait(3):
                    return
                with app["battery_lifecycle_lock"]:
                    acquired.set()
                super().run()

        app, hid, polled = lifecycle_harness(LateThread)
        with mock.patch.dict("sys.modules", {"hid": hid}):
            try:
                app["start_battery_worker"]()
                worker = app["battery_thread"]
                self.assertTrue(run_entered.wait(3))
                # A timed-out stop must retain the handle for a repeated stop.
                self.assertFalse(app["stop_battery_worker"](timeout=0))
                self.assertIs(worker, app["battery_thread"])
                self.assertTrue(app["stop_battery_worker"]())
                self.assertTrue(acquired.is_set())
                self.assertFalse(polled.is_set())
                self.assertFalse(worker.is_alive())
            finally:
                release_run.set()
                app["stop_battery_worker"]()

    def test_stop_cannot_join_worker_before_real_thread_start(self):
        start_entered = threading.Event()
        release_start = threading.Event()
        stop_boundary = threading.Event()
        errors = []

        class GatedThread(threading.Thread):
            def start(self):
                start_entered.set()
                if not release_start.wait(3):
                    raise AssertionError("start gate timed out")
                super().start()

        app, hid, _ = lifecycle_harness(GatedThread)

        class ObservedLock:
            def __init__(self):
                self.lock = threading.Lock()

            def __enter__(self):
                if threading.current_thread().name == "stopper":
                    stop_boundary.set()
                self.lock.acquire()

            def __exit__(self, *args):
                self.lock.release()

        app["battery_lifecycle_lock"] = ObservedLock()

        def call(name):
            try:
                app[name]()
            except Exception as exc:
                errors.append(exc)
            finally:
                if name == "stop_battery_worker":
                    stop_boundary.set()

        starter = threading.Thread(target=call, args=("start_battery_worker",))
        stopper = threading.Thread(target=call, args=("stop_battery_worker",), name="stopper")
        with mock.patch.dict("sys.modules", {"hid": hid}):
            try:
                starter.start()
                self.assertTrue(start_entered.wait(3))
                stopper.start()
                self.assertTrue(stop_boundary.wait(3))
            finally:
                release_start.set()
                starter.join(3)
                if stopper.ident is not None:
                    stopper.join(3)
                app["stop_battery_worker"]()
        self.assertFalse(starter.is_alive())
        self.assertFalse(stopper.is_alive())
        self.assertEqual([], errors)


if __name__ == "__main__":
    unittest.main()
