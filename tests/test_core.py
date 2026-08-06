import ast
import ctypes
import ctypes.wintypes as wintypes
import json
import os
import tempfile
import threading
import time
import unittest
from unittest import mock

from pearipherals_core import (
    BatteryResult,
    CONFIG_LOCK,
    ConfigRecoveryRequired,
    TouchpadSettingsManager,
    expire_stale_contacts,
    format_battery_label,
    is_target_trackpad_path,
    load_json_config,
    parse_apple_battery_report,
    query_apple_battery,
    read_optional_value,
    release_custom_input,
    require_single_input,
    run_input_callback,
    save_json_atomic,
    set_managed_mode,
    should_suppress_pointer,
    shutdown_custom_input,
)


class InputLifecycleTests(unittest.TestCase):
    @staticmethod
    def _load_app_definition(name, globals_):
        source_path = os.path.join(os.path.dirname(__file__), "..", "pearipherals.py")
        with open(source_path, "r", encoding="utf-8") as stream:
            tree = ast.parse(stream.read(), source_path)
        node = next(
            item for item in tree.body
            if isinstance(item, (ast.ClassDef, ast.FunctionDef)) and item.name == name
        )
        namespace = dict(globals_)
        namespace.setdefault("time", time)
        exec(compile(ast.Module([node], []), source_path, "exec"), namespace)
        return namespace[name]

    def test_raw_input_window_apis_declare_pointer_sized_results(self):
        source_path = os.path.join(os.path.dirname(__file__), "..", "pearipherals.py")
        with open(source_path, "r", encoding="utf-8") as stream:
            source = stream.read()

        for declaration in (
            "kernel32.GetModuleHandleW.restype = w.HMODULE",
            "user32.CreateWindowExW.restype = w.HWND",
            "kernel32.CreateMutexW.restype = w.HANDLE",
            "user32.RegisterRawInputDevices.restype = w.BOOL",
        ):
            with self.subTest(declaration=declaration):
                self.assertIn(declaration, source)

        self.assertIn("run_input_callback(\n                    lambda: self._handle_raw_input(lp)", source)
        self.assertIn('"Raw Input maintenance callback"', source)
        self.assertIn("return set_managed_mode(", source)
        self.assertIn('set_tf_mode(config_value("three_finger_mode"))', source)
        self.assertIn("return read_optional_value(query)", source)
        self.assertIn("require_single_input(", source)
        self.assertIn("shutdown_errors = shutdown_custom_input(", source)
        self.assertIn('"Input release failed on Quit"', source)
        self.assertIn("Swipes (Task View / minimize / restore)", source)
        self.assertNotIn("Task View / desktop / switch apps", source)

    def test_release_attempts_pointer_fail_open_even_if_gesture_abort_fails(self):
        events = []

        def abort():
            events.append("abort")
            raise OSError("button release failed")

        errors = release_custom_input(
            abort_gesture=abort,
            disable_suppression=lambda: events.append("disable"),
        )

        self.assertEqual(["abort", "disable"], events)
        self.assertEqual(1, len(errors))

    def test_shutdown_releases_input_before_stopping_suppressor(self):
        events = []

        errors = shutdown_custom_input(
            abort_gesture=lambda: events.append("abort"),
            disable_suppression=lambda: events.append("disable"),
            stop_suppressor=lambda: events.append("stop"),
        )

        self.assertEqual(["abort", "disable", "stop"], events)
        self.assertEqual([], errors)

    def test_failed_left_button_release_remains_visible_and_retryable(self):
        state = {"drag": "dragging"}
        results = iter((0, 1))

        def release():
            require_single_input(lambda: next(results))
            state["drag"] = "idle"

        with self.assertRaises(OSError):
            release()
        self.assertEqual("dragging", state["drag"])

        release()
        self.assertEqual("idle", state["drag"])

    def test_failed_release_does_not_prevent_independent_suppression_cleanup(self):
        state = {"drag": "dragging", "suppression": True}

        def abort():
            require_single_input(lambda: 0)
            state["drag"] = "idle"

        errors = release_custom_input(
            abort,
            lambda: state.__setitem__("suppression", False),
        )

        self.assertEqual("dragging", state["drag"])
        self.assertFalse(state["suppression"])
        self.assertEqual(1, len(errors))

    def test_shutdown_retries_failed_leftup_independently_until_success(self):
        events = []
        attempts = iter((OSError("LEFTUP failed"), None))

        def abort():
            events.append("abort")
            raise next(attempts)

        def retry_leftup():
            events.append("leftup")
            failure = next(attempts)
            if failure:
                raise failure

        errors = shutdown_custom_input(
            abort,
            lambda: events.append("disable"),
            lambda: events.append("stop"),
            retry_release=retry_leftup,
            release_retries=2,
        )

        self.assertEqual(["abort", "disable", "stop", "leftup"], events)
        self.assertEqual([], errors)

    def test_shutdown_bounds_persistently_failed_leftup_retries(self):
        events = []

        def fail(kind):
            events.append(kind)
            raise OSError("LEFTUP failed")

        errors = shutdown_custom_input(
            lambda: fail("abort"),
            lambda: events.append("disable"),
            lambda: events.append("stop"),
            retry_release=lambda: fail("leftup"),
            release_retries=2,
        )

        self.assertEqual(
            ["abort", "disable", "stop", "leftup", "leftup"], events
        )
        self.assertEqual(1, len(errors))
        self.assertIn("LEFTUP failed", str(errors[0]))

    def test_post_thread_message_failure_resets_active_and_allows_retry(self):
        class FakeUser32:
            post_result = 0
            suppressor = None

            def PostThreadMessageW(self, *args):
                if self.post_result:
                    self.suppressor._hook = 99
                    self.suppressor._active = True
                    self.suppressor._operation_generation = args[2]
                    self.suppressor._operation_done.set()
                return self.post_result

        fake_user32 = FakeUser32()
        suppressor_type = self._load_app_definition("PointerSuppressor", {
            "ctypes": ctypes,
            "w": wintypes,
            "threading": threading,
            "user32": fake_user32,
            "kernel32": object(),
            "ULONG_PTR": ctypes.c_size_t,
            "MAGIC_EXTRA": 1,
        })
        suppressor = suppressor_type()
        fake_user32.suppressor = suppressor
        suppressor.start = lambda: (
            setattr(suppressor, "_thread_id", 7),
            setattr(suppressor, "_thread", mock.Mock(is_alive=lambda: True)),
        )

        with self.assertRaises(OSError):
            suppressor.set(True)
        self.assertFalse(suppressor._active)

        fake_user32.post_result = 1
        suppressor.set(True)
        self.assertTrue(suppressor._active)

    def test_hook_install_failure_resets_active_and_allows_retry(self):
        class FakeUser32:
            hook_result = 0

            def SetWindowsHookExW(self, *args):
                return self.hook_result

        fake_user32 = FakeUser32()
        suppressor_type = self._load_app_definition("PointerSuppressor", {
            "ctypes": ctypes,
            "w": wintypes,
            "threading": threading,
            "user32": fake_user32,
            "kernel32": object(),
            "ULONG_PTR": ctypes.c_size_t,
            "MAGIC_EXTRA": 1,
        })
        suppressor = suppressor_type()
        suppressor._proc = object()
        suppressor._active = True
        suppressor._requested_active = True

        self.assertFalse(suppressor._install_hook())
        self.assertFalse(suppressor._active)

        fake_user32.hook_result = 99
        suppressor._requested_active = True
        suppressor._active = True
        self.assertTrue(suppressor._install_hook())
        self.assertTrue(suppressor._active)

    def test_late_successful_install_after_activation_timeout_is_unhooked(self):
        install_started = threading.Event()
        allow_install = threading.Event()
        install_threads = []

        class FakeUser32:
            suppressor = None
            block_install = True
            unhooked = []

            def SetWindowsHookExW(self, *args):
                install_started.set()
                if self.block_install:
                    self.assert_install_released()
                return 99

            @staticmethod
            def assert_install_released():
                if not allow_install.wait(1.0):
                    raise AssertionError("test did not release hook installation")

            def UnhookWindowsHookEx(self, hook):
                self.unhooked.append(hook)
                return 1

            def PostThreadMessageW(self, *args):
                def install():
                    self.suppressor._install_hook()
                    self.suppressor._operation_generation = args[2]
                    self.suppressor._operation_done.set()

                thread = threading.Thread(target=install)
                install_threads.append(thread)
                thread.start()
                return 1

        fake_user32 = FakeUser32()
        suppressor_type = self._load_app_definition("PointerSuppressor", {
            "ctypes": ctypes,
            "w": wintypes,
            "threading": threading,
            "time": time,
            "user32": fake_user32,
            "kernel32": object(),
            "ULONG_PTR": ctypes.c_size_t,
            "MAGIC_EXTRA": 1,
        })
        suppressor = suppressor_type()
        fake_user32.suppressor = suppressor
        suppressor._proc = object()
        suppressor.start = lambda: (
            setattr(suppressor, "_thread_id", 7),
            setattr(suppressor, "_thread", mock.Mock(is_alive=lambda: True)),
        )

        with mock.patch.object(
            suppressor._operation_done,
            "wait",
            side_effect=lambda timeout: install_started.wait(1.0) and False,
        ):
            with self.assertRaisesRegex(OSError, "operation timed out"):
                suppressor.set(True)

        allow_install.set()
        install_threads[0].join(1.0)
        self.assertFalse(install_threads[0].is_alive())
        self.assertEqual([99], fake_user32.unhooked)
        self.assertIsNone(suppressor._hook)
        self.assertFalse(suppressor._active)

        fake_user32.block_install = False
        suppressor.set(True)
        install_threads[1].join(1.0)
        self.assertEqual(99, suppressor._hook)
        self.assertTrue(suppressor._active)

    def test_disable_racing_with_install_never_publishes_stale_hook_active(self):
        install_started = threading.Event()
        allow_install = threading.Event()

        class FakeUser32:
            unhook_results = iter((0, 1))
            unhooked = []

            @staticmethod
            def SetWindowsHookExW(*args):
                install_started.set()
                if not allow_install.wait(1.0):
                    raise AssertionError("test did not release hook installation")
                return 99

            def UnhookWindowsHookEx(self, hook):
                self.unhooked.append(hook)
                return next(self.unhook_results)

        fake_user32 = FakeUser32()
        suppressor_type = self._load_app_definition("PointerSuppressor", {
            "ctypes": ctypes,
            "w": wintypes,
            "threading": threading,
            "time": time,
            "user32": fake_user32,
            "kernel32": object(),
            "ULONG_PTR": ctypes.c_size_t,
            "MAGIC_EXTRA": 1,
        })
        suppressor = suppressor_type()
        suppressor._proc = object()
        suppressor._requested_active = True
        suppressor._request_generation = 4

        installer = threading.Thread(target=suppressor._install_hook, args=(4,))
        installer.start()
        self.assertTrue(install_started.wait(1.0))
        suppressor.set(False)
        allow_install.set()
        installer.join(1.0)

        self.assertFalse(installer.is_alive())
        self.assertEqual([99], fake_user32.unhooked)
        self.assertEqual(99, suppressor._hook)
        self.assertFalse(suppressor._active)

        # The failed immediate cleanup retained the real handle, allowing a
        # later bounded disable to retry and finish removal.
        suppressor.set(False)
        self.assertEqual([99, 99], fake_user32.unhooked)
        self.assertIsNone(suppressor._hook)
        self.assertFalse(suppressor._active)

    def test_start_timeout_fails_closed_and_later_start_can_retry(self):
        suppressor_type = self._load_app_definition("PointerSuppressor", {
            "ctypes": ctypes,
            "w": wintypes,
            "threading": threading,
            "user32": object(),
            "kernel32": object(),
            "ULONG_PTR": ctypes.c_size_t,
            "MAGIC_EXTRA": 1,
        })
        suppressor = suppressor_type()

        class FakeThread:
            def __init__(self, alive, on_start=lambda: None):
                self.alive = alive
                self.on_start = on_start

            def start(self):
                self.on_start()

            def is_alive(self):
                return self.alive

        threads = iter((
            FakeThread(False),
            FakeThread(
                True,
                lambda: (
                    setattr(suppressor, "_thread_id", 17),
                    suppressor._ready.set(),
                ),
            ),
        ))
        with mock.patch.object(
            threading, "Thread", side_effect=lambda **kwargs: next(threads)
        ):
            with self.assertRaises(OSError):
                suppressor.start()
            self.assertFalse(suppressor._active)
            self.assertIsNone(suppressor._thread)

            suppressor.start()
            self.assertEqual(17, suppressor._thread_id)

    def test_live_thread_readiness_timeout_does_not_spawn_duplicate_on_retry(self):
        suppressor_type = self._load_app_definition("PointerSuppressor", {
            "ctypes": ctypes,
            "w": wintypes,
            "threading": threading,
            "user32": object(),
            "kernel32": object(),
            "ULONG_PTR": ctypes.c_size_t,
            "MAGIC_EXTRA": 1,
        })
        suppressor = suppressor_type()
        thread = mock.Mock(is_alive=lambda: True)

        with mock.patch.object(threading, "Thread", return_value=thread) as factory:
            with mock.patch.object(suppressor._ready, "wait", return_value=False):
                with self.assertRaises(OSError):
                    suppressor.start()
                with self.assertRaises(OSError):
                    suppressor.start()

        self.assertEqual(1, factory.call_count)
        self.assertIs(thread, suppressor._thread)
        self.assertFalse(suppressor._active)

        suppressor._thread_id = 19
        suppressor._ready.set()
        suppressor.start()
        self.assertEqual(1, factory.call_count)

    def test_set_true_readiness_failure_is_inactive_and_retryable(self):
        suppressor_type = self._load_app_definition("PointerSuppressor", {
            "ctypes": ctypes,
            "w": wintypes,
            "threading": threading,
            "user32": object(),
            "kernel32": object(),
            "ULONG_PTR": ctypes.c_size_t,
            "MAGIC_EXTRA": 1,
        })
        suppressor = suppressor_type()
        attempts = 0

        def start():
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise OSError("hook thread did not become ready")
            suppressor._thread_id = 9
            suppressor._thread = mock.Mock(is_alive=lambda: True)

        suppressor.start = start
        suppressor._request_hook_change = lambda active: (
            setattr(suppressor, "_hook", 55),
            setattr(suppressor, "_active", True),
        )

        with self.assertRaises(OSError):
            suppressor.set(True)
        self.assertFalse(suppressor._active)
        self.assertIsNone(suppressor._hook)

        suppressor.set(True)
        self.assertTrue(suppressor._active)
        self.assertEqual(55, suppressor._hook)

    def test_failed_unhook_retains_hook_and_active_state_for_later_retry(self):
        class FakeUser32:
            results = iter((0, 1))

            def UnhookWindowsHookEx(self, hook):
                return next(self.results)

        suppressor_type = self._load_app_definition("PointerSuppressor", {
            "ctypes": ctypes,
            "w": wintypes,
            "threading": threading,
            "user32": FakeUser32(),
            "kernel32": object(),
            "ULONG_PTR": ctypes.c_size_t,
            "MAGIC_EXTRA": 1,
        })
        suppressor = suppressor_type()
        suppressor._hook = 77
        suppressor._active = True

        self.assertFalse(suppressor._uninstall_hook())
        self.assertEqual(77, suppressor._hook)
        self.assertTrue(suppressor._active)

        self.assertTrue(suppressor._uninstall_hook())
        self.assertIsNone(suppressor._hook)
        self.assertFalse(suppressor._active)

    def test_disable_bounds_unhook_retries_and_a_later_disable_can_succeed(self):
        class FakeUser32:
            results = iter((0, 0, 0, 1))
            calls = 0
            suppressor = None

            def UnhookWindowsHookEx(self, hook):
                self.calls += 1
                return next(self.results)

            def PostThreadMessageW(self, *args):
                ok = self.suppressor._uninstall_hook()
                if not ok:
                    self.suppressor._operation_error = OSError("unhook failed")
                self.suppressor._operation_generation = args[2]
                self.suppressor._operation_done.set()
                return 1

        fake_user32 = FakeUser32()
        suppressor_type = self._load_app_definition("PointerSuppressor", {
            "ctypes": ctypes,
            "w": wintypes,
            "threading": threading,
            "user32": fake_user32,
            "kernel32": object(),
            "ULONG_PTR": ctypes.c_size_t,
            "MAGIC_EXTRA": 1,
        })
        suppressor = suppressor_type()
        fake_user32.suppressor = suppressor
        suppressor._hook = 77
        suppressor._active = True
        suppressor._thread_id = 8
        suppressor._thread = mock.Mock(is_alive=lambda: True)

        with self.assertRaises(OSError):
            suppressor.set(False)
        self.assertEqual(3, fake_user32.calls)
        self.assertEqual(77, suppressor._hook)
        self.assertTrue(suppressor._active)

        suppressor.set(False)
        self.assertEqual(4, fake_user32.calls)
        self.assertIsNone(suppressor._hook)
        self.assertFalse(suppressor._active)

    def test_raw_input_callback_logs_failures_and_still_attempts_cleanup(self):
        events = []

        run_input_callback(
            action=lambda: (_ for _ in ()).throw(ValueError("bad report")),
            cleanup=lambda: events.append("cleanup"),
            log=lambda message: events.append(message),
            context="Raw Input callback",
        )

        self.assertEqual("Raw Input callback failed: bad report", events[0])
        self.assertEqual("cleanup", events[1])

    def test_first_run_apply_failure_does_not_mark_setup_done_or_claim_success(self):
        app_config = {}

        class FailedSettings:
            @staticmethod
            def apply():
                raise OSError("registry denied")

        first_run_setup = self._load_app_definition("first_run_setup", {
            "config": app_config,
            "CONFIG_RECOVERY_ERROR": None,
            "CONFIG_LOCK": threading.RLock(),
            "config_value": lambda key, default=None: app_config.get(key, default),
            "autostart_set": lambda enabled: None,
            "tp_settings": FailedSettings(),
            "save_config": lambda config: None,
        })

        self.assertFalse(first_run_setup())
        self.assertNotIn("setup_done", app_config)

    def test_recovery_required_skips_first_run_registry_apply(self):
        app_config = {"three_finger_mode": "off"}
        calls = []
        first_run_setup = self._load_app_definition("first_run_setup", {
            "config": app_config,
            "CONFIG_RECOVERY_ERROR": OSError("invalid config"),
            "CONFIG_LOCK": threading.RLock(),
            "autostart_set": lambda enabled: calls.append("autostart"),
            "tp_settings": mock.Mock(apply=lambda: calls.append("apply")),
            "save_config": lambda config: calls.append("save"),
        })

        self.assertFalse(first_run_setup())
        self.assertEqual([], calls)
        self.assertEqual({"three_finger_mode": "off"}, app_config)


class ConfigPersistenceTests(unittest.TestCase):
    def test_atomic_save_replaces_json_and_leaves_no_temp_file(self):
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "settings.json")
            save_json_atomic(path, {"mode": "swipes"})

            with open(path, "r", encoding="utf-8") as stream:
                self.assertEqual({"mode": "swipes"}, json.load(stream))
            self.assertFalse(os.path.exists(path + ".tmp"))

    def test_concurrent_saves_produce_valid_json_without_temp_artifacts(self):
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "settings.json")
            payloads = (
                {"writer": 1, "values": list(range(100))},
                {"writer": 2, "values": list(range(100, 200))},
            )
            first_dump_started = threading.Event()
            second_dump_started = threading.Event()
            original_dump = json.dump
            dump_calls = 0
            dump_lock = threading.Lock()
            errors = []

            def coordinated_dump(data, stream, **kwargs):
                nonlocal dump_calls
                with dump_lock:
                    dump_calls += 1
                    call = dump_calls
                if call == 1:
                    first_dump_started.set()
                    second_dump_started.wait(0.2)
                elif call == 2:
                    second_dump_started.set()
                return original_dump(data, stream, **kwargs)

            def save(payload):
                try:
                    save_json_atomic(path, payload)
                except Exception as exc:
                    errors.append(exc)

            with mock.patch("pearipherals_core.json.dump", side_effect=coordinated_dump):
                first = threading.Thread(target=save, args=(payloads[0],))
                second = threading.Thread(target=save, args=(payloads[1],))
                first.start()
                self.assertTrue(first_dump_started.wait(1.0))
                second.start()
                first.join(2.0)
                second.join(2.0)

            self.assertFalse(first.is_alive())
            self.assertFalse(second.is_alive())
            self.assertEqual([], errors)
            with open(path, "r", encoding="utf-8") as stream:
                self.assertIn(json.load(stream), payloads)
            artifacts = [
                name for name in os.listdir(folder)
                if name != os.path.basename(path)
            ]
            self.assertEqual([], artifacts)

    def test_mutation_of_same_dictionary_blocks_during_serialization(self):
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "settings.json")
            data = {"generation": "before", "values": list(range(100))}
            dump_started = threading.Event()
            mutation_attempted = threading.Event()
            mutation_done = threading.Event()
            original_dump = json.dump

            def coordinated_dump(payload, stream, **kwargs):
                dump_started.set()
                self.assertTrue(mutation_attempted.wait(1.0))
                self.assertFalse(mutation_done.wait(0.05))
                return original_dump(payload, stream, **kwargs)

            def mutate():
                self.assertTrue(dump_started.wait(1.0))
                mutation_attempted.set()
                with CONFIG_LOCK:
                    data.clear()
                    data.update({"generation": "after", "values": [999]})
                mutation_done.set()

            with mock.patch(
                "pearipherals_core.json.dump", side_effect=coordinated_dump
            ):
                writer = threading.Thread(
                    target=lambda: save_json_atomic(path, data)
                )
                mutator = threading.Thread(target=mutate)
                writer.start()
                mutator.start()
                writer.join(2.0)
                mutator.join(2.0)

            self.assertFalse(writer.is_alive())
            self.assertFalse(mutator.is_alive())
            with open(path, "r", encoding="utf-8") as stream:
                self.assertEqual(
                    {"generation": "before", "values": list(range(100))},
                    json.load(stream),
                )
            self.assertEqual([os.path.basename(path)], os.listdir(folder))

    def test_malformed_primary_config_is_preserved_and_requires_recovery(self):
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "pearipherals.json")
            malformed = b'{"tp_settings_backup":{"TapAndDrag":0}'
            with open(path, "wb") as stream:
                stream.write(malformed)

            with self.assertRaises(ConfigRecoveryRequired) as raised:
                load_json_config(path, {"three_finger_mode": "swipes"})

            self.assertEqual(path, raised.exception.path)
            with open(path, "rb") as stream:
                self.assertEqual(malformed, stream.read())
            self.assertEqual(["pearipherals.json"], os.listdir(folder))

    def test_unreadable_existing_primary_requires_recovery_not_first_run(self):
        path = os.path.join("protected", "pearipherals.json")
        with mock.patch("builtins.open", side_effect=PermissionError("denied")):
            with self.assertRaises(ConfigRecoveryRequired) as raised:
                load_json_config(path, {"three_finger_mode": "swipes"})

        self.assertEqual(path, raised.exception.path)
        self.assertIsInstance(raised.exception.cause, PermissionError)

    def test_missing_primary_config_is_distinct_from_invalid(self):
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "pearipherals.json")

            config, state = load_json_config(
                path, {"three_finger_mode": "swipes"}
            )

            self.assertEqual({"three_finger_mode": "swipes"}, config)
            self.assertEqual("missing", state)

    def test_failed_replace_preserves_previous_valid_json(self):
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "settings.json")
            save_json_atomic(path, {"mode": "off"})

            with mock.patch("pearipherals_core.os.replace", side_effect=OSError("busy")):
                with self.assertRaises(OSError):
                    save_json_atomic(path, {"mode": "swipes"})

            with open(path, "r", encoding="utf-8") as stream:
                self.assertEqual({"mode": "off"}, json.load(stream))
            self.assertFalse(os.path.exists(path + ".tmp"))


class TouchpadSettingsManagerTests(unittest.TestCase):
    def test_custom_apply_write_failure_fails_closed_without_losing_backup(self):
        values = {
            "ThreeFingerSlideEnabled": 1,
            "ThreeFingerTapEnabled": 1,
        }
        config = {"three_finger_mode": "swipes"}
        saves = []

        def write(name, value):
            if name == "ThreeFingerTapEnabled":
                raise OSError("registry denied")
            values[name] = value

        manager = TouchpadSettingsManager(
            config=config,
            read_value=lambda name: values.get(name),
            write_value=write,
            delete_value=lambda name: values.pop(name, None),
            save=lambda: saves.append(dict(config)),
        )

        with self.assertRaises(OSError):
            manager.apply("swipes", include_recommended=False)

        self.assertEqual("off", config["three_finger_mode"])
        self.assertFalse(config["tp_settings_applied"])
        self.assertEqual(
            {"ThreeFingerSlideEnabled": 1, "ThreeFingerTapEnabled": 1},
            config["tp_settings_backup"],
        )
        self.assertFalse(saves[0]["tp_settings_applied"])
        self.assertFalse(saves[-1]["tp_settings_applied"])

    def test_mode_switch_registry_failure_rolls_persisted_mode_back_to_off(self):
        config = {"three_finger_mode": "off", "tp_settings_applied": False}
        saved_modes = []

        with self.assertRaises(OSError):
            set_managed_mode(
                config,
                "drag",
                enforce=lambda mode: (_ for _ in ()).throw(OSError("denied")),
                save=lambda: saved_modes.append(config["three_finger_mode"]),
            )

        self.assertEqual(["drag", "off"], saved_modes)
        self.assertEqual("off", config["three_finger_mode"])
        self.assertFalse(config["tp_settings_applied"])

    def test_startup_enforcement_failure_rolls_existing_custom_mode_off(self):
        config = {"three_finger_mode": "swipes", "tp_settings_applied": True}

        with self.assertRaises(OSError):
            set_managed_mode(
                config,
                config["three_finger_mode"],
                enforce=lambda mode: (_ for _ in ()).throw(OSError("denied")),
                save=lambda: None,
            )

        self.assertEqual("off", config["three_finger_mode"])
        self.assertFalse(config["tp_settings_applied"])

    def test_registry_missing_value_maps_to_absence(self):
        self.assertIsNone(read_optional_value(
            lambda: (_ for _ in ()).throw(FileNotFoundError("missing"))
        ))

    def test_registry_read_error_aborts_apply_before_save_or_mutation(self):
        config = {"three_finger_mode": "swipes"}
        writes = []
        saves = []
        manager = TouchpadSettingsManager(
            config=config,
            read_value=lambda name: read_optional_value(
                lambda: (_ for _ in ()).throw(OSError("registry unavailable"))
            ),
            write_value=lambda name, value: writes.append((name, value)),
            delete_value=lambda name: None,
            save=lambda: saves.append(dict(config)),
        )

        with self.assertRaises(OSError):
            manager.apply("swipes", include_recommended=False)

        self.assertEqual([], writes)
        self.assertEqual("off", config["three_finger_mode"])
        self.assertFalse(config["tp_settings_applied"])
        self.assertEqual(1, len(saves))
        self.assertNotIn("tp_settings_backup", config)

    def test_apply_persists_recovery_backup_before_registry_mutation(self):
        values = {"ThreeFingerSlideEnabled": 1}
        config = {"three_finger_mode": "swipes"}
        events = []

        manager = TouchpadSettingsManager(
            config=config,
            read_value=lambda name: values.get(name),
            write_value=lambda name, value: (
                events.append(("write", name)), values.__setitem__(name, value)
            )[-1],
            delete_value=lambda name: values.pop(name, None),
            save=lambda: events.append(("save", dict(config))),
        )

        manager.apply("swipes", include_recommended=False)

        self.assertEqual("save", events[0][0])
        self.assertEqual(1, events[0][1]["tp_settings_backup"][
            "ThreeFingerSlideEnabled"
        ])

    def test_restore_keeps_failed_backup_entry_for_retry(self):
        values = {"TapsEnabled": 1, "TapAndDrag": 1}
        config = {
            "three_finger_mode": "swipes",
            "tp_settings_applied": True,
            "tp_settings_backup": {"TapsEnabled": 0, "TapAndDrag": 0},
        }

        def write(name, value):
            if name == "TapAndDrag":
                raise OSError("registry busy")
            values[name] = value

        manager = TouchpadSettingsManager(
            config=config,
            read_value=lambda name: values.get(name),
            write_value=write,
            delete_value=lambda name: values.pop(name, None),
            save=lambda: None,
        )

        with self.assertRaises(OSError):
            manager.restore()

        self.assertEqual(0, values["TapsEnabled"])
        self.assertEqual(1, values["TapAndDrag"])
        self.assertEqual({"TapAndDrag": 0}, config["tp_settings_backup"])
        self.assertEqual("off", config["three_finger_mode"])
        self.assertFalse(config["tp_settings_applied"])
        self.assertEqual("restore incomplete", manager.status_text("off"))

    def test_apply_swipes_backs_up_originals_and_disables_native_gestures(self):
        values = {
            "ThreeFingerSlideEnabled": 1,
            "ThreeFingerTapEnabled": 1,
            "TapsEnabled": 0,
            "TwoFingerTapEnabled": 0,
            "TapAndDrag": 0,
            "ScrollDirection": 0,
        }
        config = {"three_finger_mode": "swipes", "natural_scroll": False}
        saves = []

        manager = TouchpadSettingsManager(
            config=config,
            read_value=lambda name: values.get(name),
            write_value=lambda name, value: values.__setitem__(name, value),
            delete_value=lambda name: values.pop(name, None),
            save=lambda: saves.append(dict(config)),
        )

        changed = manager.apply("swipes")

        self.assertEqual(0, values["ThreeFingerSlideEnabled"])
        self.assertEqual(0, values["ThreeFingerTapEnabled"])
        self.assertEqual(1, values["TapsEnabled"])
        self.assertEqual(1, values["TwoFingerTapEnabled"])
        self.assertEqual(1, values["TapAndDrag"])
        self.assertEqual(1, values["ScrollDirection"])
        self.assertEqual(
            {
                "ThreeFingerSlideEnabled": 1,
                "ThreeFingerTapEnabled": 1,
                "TapsEnabled": 0,
                "TwoFingerTapEnabled": 0,
                "TapAndDrag": 0,
                "ScrollDirection": 0,
            },
            config["tp_settings_backup"],
        )
        self.assertTrue(config["tp_settings_applied"])
        self.assertEqual(6, len(changed))
        self.assertEqual(2, len(saves))
        self.assertFalse(saves[0]["tp_settings_applied"])
        self.assertTrue(saves[1]["tp_settings_applied"])

    def test_restore_reinstates_every_backup_and_turns_custom_gestures_off(self):
        values = {
            "ThreeFingerSlideEnabled": 0,
            "ThreeFingerTapEnabled": 0,
            "TapsEnabled": 1,
            "TwoFingerTapEnabled": 1,
        }
        config = {
            "three_finger_mode": "swipes",
            "tp_settings_applied": True,
            "tp_settings_backup": {
                "ThreeFingerSlideEnabled": 1,
                "ThreeFingerTapEnabled": 1,
                "TapsEnabled": 0,
                "TwoFingerTapEnabled": None,
            },
        }
        saves = []

        manager = TouchpadSettingsManager(
            config=config,
            read_value=lambda name: values.get(name),
            write_value=lambda name, value: values.__setitem__(name, value),
            delete_value=lambda name: values.pop(name, None),
            save=lambda: saves.append(dict(config)),
        )

        restored = manager.restore()

        self.assertEqual(1, values["ThreeFingerSlideEnabled"])
        self.assertEqual(1, values["ThreeFingerTapEnabled"])
        self.assertEqual(0, values["TapsEnabled"])
        self.assertNotIn("TwoFingerTapEnabled", values)
        self.assertEqual("off", config["three_finger_mode"])
        self.assertFalse(config["tp_settings_applied"])
        self.assertEqual({}, config["tp_settings_backup"])
        self.assertEqual(4, len(restored))
        self.assertEqual(2, len(saves))

    def test_enforce_off_leaves_restored_registry_values_alone(self):
        values = {
            "ThreeFingerSlideEnabled": 0,
            "ThreeFingerTapEnabled": 0,
        }
        config = {
            "three_finger_mode": "off",
            "tp_settings_applied": False,
            "tp_settings_backup": {},
        }
        writes = []

        manager = TouchpadSettingsManager(
            config=config,
            read_value=lambda name: values.get(name),
            write_value=lambda name, value: writes.append((name, value)),
            delete_value=lambda name: values.pop(name, None),
            save=lambda: None,
        )

        manager.enforce("off")

        self.assertEqual([], writes)
        self.assertEqual("original settings", manager.status_text("off"))


class BatteryTests(unittest.TestCase):
    def test_parse_valid_battery_report_and_status_bits(self):
        reading = parse_apple_battery_report(bytes((0x90, 0x06, 78)))

        self.assertEqual(78, reading.percentage)
        self.assertTrue(reading.charging)
        self.assertTrue(reading.fully_charged)

    def test_parser_rejects_wrong_shape_id_and_percentage(self):
        for report in (b"", b"\x90\x00", b"\x91\x00\x32",
                       b"\x90\x00\x65", b"\x90\x00\x32\x00"):
            with self.subTest(report=report):
                with self.assertRaises(ValueError):
                    parse_apple_battery_report(report)

    def test_query_filters_exact_vendor_collection_and_reports_states(self):
        devices = [
            {"vendor_id": 0x004C, "product_id": 0x0267,
             "usage_page": 0x01, "usage": 0x06, "path": b"keyboard"},
            {"vendor_id": 0x004C, "product_id": 0x0267,
             "usage_page": 0xFF00, "usage": 0x14, "path": b"battery"},
        ]

        result = query_apple_battery(
            0x0267,
            enumerate_devices=lambda: devices,
            request_report=lambda path: b"\x90\x00\x2a",
        )
        missing = query_apple_battery(
            0x0265,
            enumerate_devices=lambda: devices,
            request_report=lambda path: b"\x90\x00\x2a",
        )

        self.assertEqual(BatteryResult("available", 42, False, False), result)
        self.assertEqual("not_detected", missing.status)

    def test_query_failure_and_malformed_report_have_distinct_labels(self):
        devices = [{"vendor_id": 0x004C, "product_id": 0x0265,
                    "usage_page": 0xFF00, "usage": 0x14,
                    "path": b"battery"}]

        unavailable = query_apple_battery(
            0x0265,
            enumerate_devices=lambda: devices,
            request_report=lambda path: (_ for _ in ()).throw(OSError("asleep")),
        )
        unsupported = query_apple_battery(
            0x0265,
            enumerate_devices=lambda: devices,
            request_report=lambda path: b"\x90\x00\xff",
        )

        self.assertEqual("Magic Trackpad battery: unavailable",
                         format_battery_label("Magic Trackpad", unavailable))
        self.assertEqual("Magic Trackpad battery: unsupported report",
                         format_battery_label("Magic Trackpad", unsupported))


class ContactSuppressionTests(unittest.TestCase):
    def test_only_magic_trackpad_ptp_path_is_accepted(self):
        magic = (
            r"\\?\HID#{00001124-0000-1000-8000-00805f9b34fb}"
            r"_VID&0001004c_PID&0265&Col01&Col01#a&2727b852&0&0000"
        )
        other = r"\\?\HID#VID&1234_PID&5678&Col01#1&2&3"

        self.assertTrue(is_target_trackpad_path(magic))
        self.assertFalse(is_target_trackpad_path(other))

    def test_contact_id_churn_does_not_suppress_one_finger_pointer_motion(self):
        now = 10.0
        contacts = {
            4: [100, 100, 9.91, 90, 90, 9.70],
            7: [102, 101, 9.94, 95, 95, 9.80],
            9: [103, 102, 10.00, 103, 102, 9.99],
        }

        active = should_suppress_pointer(
            contacts, now=now, fresh=0.06, min_age=0.06
        )

        self.assertFalse(active)

    def test_three_stable_contacts_enable_pointer_suppression(self):
        now = 10.0
        contacts = {
            1: [100, 100, 9.98, 90, 90, 9.00],
            2: [200, 100, 9.97, 190, 90, 9.00],
            3: [300, 100, 9.96, 290, 90, 9.00],
        }

        active = should_suppress_pointer(
            contacts, now=now, fresh=0.06, min_age=0.06
        )

        self.assertTrue(active)

    def test_timer_expiry_releases_contacts_when_no_lift_report_arrives(self):
        contacts = {
            1: [100, 100, 4.90, 90, 90, 4.00],
            2: [200, 100, 4.98, 190, 90, 4.00],
            3: [300, 100, 4.99, 290, 90, 4.00],
        }

        expired = expire_stale_contacts(contacts, now=5.0, ttl=0.07)

        self.assertEqual([1], expired)
        self.assertEqual({2, 3}, set(contacts))


if __name__ == "__main__":
    unittest.main()
