"""Execute production window-cycle definitions with Win32 replaced, never the app."""
import ast
import ctypes
import ctypes.wintypes as w
from pathlib import Path
import queue
import threading
import unittest


class FakeClock:
    def __init__(self, api):
        self.now = 0.0
        self.api = api

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds
        for at, callback in list(self.api.scheduled):
            if at <= self.now:
                self.api.scheduled.remove((at, callback))
                callback()


SOURCE = Path(__file__).resolve().parents[1] / "pearipherals.py"


class FakeUser32:
    def __init__(self):
        self.windows = {h: dict(iconic=False, visible=True, tool=False,
                                pid=h + 100, tid=h + 200, maximized=h == 2,
                                rect=(10*h, 20, 600, 500)) for h in (1, 2, 3)}
        self.order = [1, 2, 3]
        self.foreground = 1
        self.pending = []
        self.events = []
        self.hung = set()
        self.scheduled = []
        self.clock = FakeClock(self)
        self.delayed_minimize = False
        self.restore_delays = {}
        self.ignore_restore = set()
        self.deny_focus = False
        self.focus_delay = 0
        self.position_delay = 0.03
        # ctypes functions expose argtypes/restype; retain the real declarations.
        for name in dir(type(self)):
            if name[0].isupper():
                fn = getattr(self, name)
                setattr(self, name, lambda *args, _fn=fn: _fn(*args))

    def EnumWindows(self, cb, _):
        for h in list(self.order):
            if not cb(h, 0):
                return 0
        return 1

    def IsWindowVisible(self, h):
        return self.windows.get(h, {}).get("visible", False)

    def IsWindow(self, h):
        return h in self.windows

    def IsIconic(self, h):
        return self.windows.get(h, {}).get("iconic", False)

    def GetWindowLongW(self, h, _):
        window = self.windows.get(h, {})
        return (0x80 if window.get("tool") else 0) | (0x8 if window.get("topmost") else 0)

    def GetForegroundWindow(self):
        return self.foreground

    def GetShellWindow(self):
        return 90

    def GetDesktopWindow(self):
        return 91

    def GetClassNameW(self, h, buf, size):
        buf.value = "Progman" if h == 90 else "App"
        return len(buf.value)

    def GetWindowThreadProcessId(self, h, pid):
        window = self.windows.get(h)
        if not window:
            return 0
        pid._obj.value = window["pid"]
        return window["tid"]

    def activate(self, h):
        self.foreground = h
        self.raise_window(h)

    def raise_window(self, h):
        self.order.remove(h)
        index = 0 if self.windows[h].get("topmost") else sum(
            bool(self.windows[i].get("topmost")) for i in self.order)
        self.order.insert(index, h)

    def ShowWindowAsync(self, h, command):
        # Independent target queues may finish in any order, not call order.
        self.pending.append((h, command))
        return 1

    def finish_async(self):
        for h, command in sorted(self.pending):
            self.windows[h]["iconic"] = False
            if command == 9:
                self.activate(h)
        self.pending.clear()

    def SendMessageTimeoutW(self, h, msg, command, lp, flags, timeout, result):
        assert (msg, command) == (0x112, 0xF120)
        assert flags & 0x2 and not flags & 0x8
        assert 0 < timeout <= 250
        self.events.append(("restore", h))
        assert self.windows[h]["tid"] != threading.get_native_id()
        if h in self.hung:
            self.clock.sleep(timeout / 1000)
            return 0
        def complete():
            self.windows[h]["iconic"] = False
            self.activate(h)
        if h in self.ignore_restore:
            pass
        elif h in self.restore_delays:
            self.scheduled.append((self.clock.now + self.restore_delays[h], complete))
        else:
            complete()
        result._obj.value = 0  # WM_SYSCOMMAND's result is zero on success.
        return 1

    def SetWindowPos(self, h, after, x, y, cx, cy, flags):
        assert after == 0  # HWND_TOP does not change the topmost band.
        assert flags & 0x4013 == 0x4013  # async, noactivate, nomove, nosize
        self.events.append(("position", h))
        def complete():
            self.raise_window(h)
        self.scheduled.append((self.clock.now + self.position_delay, complete))
        return 1

    def SetForegroundWindow(self, h):
        self.events.append(("foreground", h))
        if self.deny_focus:
            return 0
        if self.focus_delay:
            self.scheduled.append((self.clock.now + self.focus_delay, lambda: self.activate(h)))
            return 1
        self.activate(h)
        return 1

    def minimize(self, *_):
        if self.delayed_minimize:
            self.delayed_minimize = False
            self.scheduled.append((self.clock.now + 0.06, self.minimize))
            return
        self.events.append(("minimize", self.foreground))
        for window in self.windows.values():
            window["iconic"] = True
        self.foreground = 90
        self.order = [3, 1, 2]  # Deliberately not pre-down Z order.


def load_cycle(api):
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    # Only this trusted source section plus the real worker; no module startup.
    start = next(n.lineno for n in tree.body if isinstance(n, ast.Assign)
                 and any(isinstance(t, ast.Name) and t.id == "SWIPE_ACTIONS" for t in n.targets))
    end = next(n.lineno for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "PHYSICAL_MONITOR")
    nodes = [n for n in tree.body if start <= n.lineno < end or
             isinstance(n, ast.FunctionDef) and n.name == "worker"]
    namespace = dict(ctypes=ctypes, w=w, user32=api, queue=queue,
                     time=api.clock, threading=threading,
                     VK_LWIN=0x5B, VK_M=0x4D, VK_TAB=9, send_keys=api.minimize,
                     append_error=lambda message: api.events.append(("error", message)))
    exec(compile(ast.Module(nodes, []), str(SOURCE), "exec"), namespace)
    return namespace


def action(ns, direction):
    ns["actions"] = queue.Queue()
    ns["actions"].put(ns["SWIPE_ACTIONS"][direction])
    ns["actions"].put(None)
    ns["worker"]()


class WindowRestoreTests(unittest.TestCase):
    def test_failed_enumeration_preserves_snapshot_for_retry(self):
        for partial in (False, True):
            with self.subTest(partial=partial):
                api = FakeUser32()
                ns = load_cycle(api)
                action(ns, "down")
                snapshot = ns["_window_cycle"]
                enumerate_windows = api.EnumWindows
                if partial:
                    def fail_after_one(callback, _):
                        callback(api.order[0], 0)
                        return 0
                    api.EnumWindows = fail_after_one
                else:
                    api.EnumWindows = lambda *_: 0
                action(ns, "up")
                self.assertIs(snapshot, ns["_window_cycle"])
                self.assertIn(("error", "Window restore failed: EnumWindows failed"),
                              api.events)
                self.assertTrue(all(v["iconic"] for v in api.windows.values()))
                self.assertFalse(any(e[0] in ("restore", "position", "foreground")
                                     for e in api.events))
                api.EnumWindows = enumerate_windows
                action(ns, "up")
                self.assertTrue(all(not v["iconic"] for v in api.windows.values()))
                self.assertEqual(1, api.foreground)
                self.assertEqual([1, 2, 3], api.order)
                self.assertIsNone(ns["_window_cycle"])

    def test_window_worker_exception_is_logged_and_next_action_runs(self):
        for direction, name, label in (
                ("down", "minimize_all_windows", "minimize"),
                ("up", "restore_all_windows", "restore")):
            with self.subTest(direction=direction):
                api = FakeUser32()
                ns = load_cycle(api)
                def fail():
                    raise RuntimeError("injected worker failure")
                ns[name] = fail
                ns["actions"] = queue.Queue()
                ns["actions"].put(ns["SWIPE_ACTIONS"][direction])
                ns["actions"].put(("keys", ([123],)))
                ns["actions"].put(None)
                ns["worker"]()
                self.assertIn(("error", f"Window {label} failed: injected worker failure"),
                              api.events)
                self.assertIn(("minimize", 1), api.events)

    def test_topmost_band_survives_normal_foreground_activation(self):
        api = FakeUser32()
        api.windows[3]["topmost"] = True
        api.order = [3, 1, 2]
        ns = load_cycle(api)
        action(ns, "down")
        action(ns, "up")
        self.assertEqual([3, 1, 2], api.order)
        self.assertEqual(1, api.foreground)
        self.assertTrue(api.windows[3]["topmost"])

    def test_closed_during_restore_is_skipped(self):
        api = FakeUser32()
        ns = load_cycle(api)
        action(ns, "down")
        send = api.SendMessageTimeoutW
        def close_foreground(*args):
            if args[0] == 3:
                del api.windows[1]
                api.order.remove(1)
            return send(*args)
        api.SendMessageTimeoutW = close_foreground
        action(ns, "up")
        self.assertNotIn(("restore", 1), api.events)
        self.assertNotIn(("foreground", 1), api.events)
        self.assertEqual([2, 3], api.order)

    def test_shell_minimize_timeout_is_bounded(self):
        api = FakeUser32()
        ns = load_cycle(api)
        ns["send_keys"] = lambda *_: None
        action(ns, "down")
        self.assertLessEqual(api.clock.now, 1.01)
        self.assertIn(("error", "Window minimize: completion deadline expired"), api.events)

    def test_z_order_timeout_is_bounded_and_nonactivating(self):
        api = FakeUser32()
        api.position_delay = 100
        ns = load_cycle(api)
        action(ns, "down")
        action(ns, "up")
        self.assertLessEqual(api.clock.now, 1.01)
        self.assertEqual(1, api.foreground)
        self.assertIn(("error", "Window restore: Z-order completion deadline expired"), api.events)

    def test_delayed_final_activation_completes_before_next_down_snapshot(self):
        api = FakeUser32()
        ns = load_cycle(api)
        action(ns, "down")
        # A normal non-minimized foreground can be behind another window;
        # this also keeps the test independent of restore auto-activation.
        api.windows[1]["iconic"] = False
        api.focus_delay = 0.06
        action(ns, "up")
        self.assertEqual(1, api.foreground)
        self.assertEqual([], api.scheduled)

    def test_repeated_down_keeps_original_snapshot(self):
        api = FakeUser32()
        ns = load_cycle(api)
        action(ns, "down")
        action(ns, "down")
        action(ns, "up")
        self.assertEqual(1, api.foreground)
        self.assertEqual([1, 2, 3], api.order)
        api.activate(3)
        action(ns, "down")
        action(ns, "up")
        self.assertEqual(3, api.foreground)

    def test_up_without_down_restores_external_minimized_windows_only(self):
        api = FakeUser32()
        api.windows[2]["iconic"] = api.windows[3]["iconic"] = True
        ns = load_cycle(api)
        action(ns, "up")
        self.assertTrue(all(not v["iconic"] for v in api.windows.values()))
        self.assertNotIn(("restore", 1), api.events)
        self.assertFalse(any(e[0] == "foreground" for e in api.events))

    def test_window_added_after_down_is_also_restored(self):
        api = FakeUser32()
        ns = load_cycle(api)
        action(ns, "down")
        api.windows[4] = dict(api.windows[3], pid=104, tid=204)
        api.order.append(4)
        action(ns, "up")
        self.assertFalse(api.windows[4]["iconic"])
        self.assertEqual([1, 2, 3, 4], api.order)

    def test_closed_foreground_is_not_activated(self):
        api = FakeUser32()
        ns = load_cycle(api)
        action(ns, "down")
        del api.windows[1]
        api.order.remove(1)
        action(ns, "up")
        self.assertNotIn(("foreground", 1), api.events)
        self.assertEqual([2, 3], api.order)
        self.assertIsNone(ns["_window_cycle"])

    def test_reused_foreground_handle_is_restored_but_not_saved_focus(self):
        api = FakeUser32()
        ns = load_cycle(api)
        action(ns, "down")
        api.windows[1].update(pid=999, tid=998)
        action(ns, "up")
        self.assertFalse(api.windows[1]["iconic"])
        self.assertNotIn(("foreground", 1), api.events)
        self.assertEqual([2, 3, 1], api.order)

    def test_hidden_tool_and_shell_windows_are_not_restored(self):
        api = FakeUser32()
        api.windows[2]["tool"] = True
        api.windows[3]["visible"] = False
        api.windows[90] = dict(api.windows[1], pid=190, tid=290)
        api.order.append(90)
        ns = load_cycle(api)
        action(ns, "down")
        action(ns, "up")
        self.assertEqual([("restore", 1)], [e for e in api.events if e[0] == "restore"])

    def test_ignored_restore_has_bounded_wait_and_no_focus_on_iconic(self):
        api = FakeUser32()
        ns = load_cycle(api)
        action(ns, "down")
        api.ignore_restore.add(1)
        action(ns, "up")
        self.assertLessEqual(api.clock.now, 1.5)
        self.assertNotIn(("foreground", 1), api.events)
        self.assertTrue(any(e[0] == "error" for e in api.events))

    def test_foreground_denial_is_reported_without_force_focus_hacks(self):
        api = FakeUser32()
        api.deny_focus = True
        ns = load_cycle(api)
        action(ns, "down")
        action(ns, "up")
        self.assertEqual(1, api.events.count(("foreground", 1)))
        self.assertIn(("error", "Window restore: Windows denied foreground activation"), api.events)

    def test_ctypes_signatures_are_pointer_sized(self):
        api = FakeUser32()
        ns = load_cycle(api)
        self.assertEqual([w.HWND, w.UINT, w.WPARAM, w.LPARAM, w.UINT, w.UINT,
                          ctypes.POINTER(ctypes.c_size_t)], api.SendMessageTimeoutW.argtypes)
        self.assertIs(ctypes.c_ssize_t, api.SendMessageTimeoutW.restype)
        self.assertEqual([ns["_WINDOW_ENUM_PROC"], w.LPARAM], api.EnumWindows.argtypes)
        self.assertIs(w.HWND, api.GetForegroundWindow.restype)
        self.assertEqual([w.HWND, ctypes.POINTER(w.DWORD)], api.GetWindowThreadProcessId.argtypes)
        self.assertEqual([w.HWND, w.HWND, ctypes.c_int, ctypes.c_int,
                          ctypes.c_int, ctypes.c_int, w.UINT], api.SetWindowPos.argtypes)

    def test_hung_restore_is_bounded_reported_and_retry_keeps_foreground(self):
        api = FakeUser32()
        ns = load_cycle(api)
        action(ns, "down")
        api.hung.add(1)
        action(ns, "up")
        self.assertLessEqual(api.clock.now, 1.5)
        self.assertTrue(api.windows[1]["iconic"])
        self.assertTrue(all(not api.windows[h]["iconic"] for h in (2, 3)))
        self.assertTrue(any(e[0] == "error" for e in api.events))
        api.hung.clear()
        action(ns, "up")
        self.assertEqual(1, api.foreground)
        self.assertIsNone(ns["_window_cycle"])

    def test_same_thread_window_is_not_sent_an_unbounded_message(self):
        api = FakeUser32()
        api.windows[2]["tid"] = threading.get_native_id()
        ns = load_cycle(api)
        action(ns, "down")
        action(ns, "up")
        self.assertNotIn(("restore", 2), api.events)
        self.assertTrue(api.windows[2]["iconic"])
        self.assertEqual(1, api.foreground)

    def test_saved_stack_includes_windows_already_restored_before_up(self):
        api = FakeUser32()
        ns = load_cycle(api)
        action(ns, "down")
        api.windows[2]["iconic"] = False
        api.activate(2)
        action(ns, "up")
        api.clock.sleep(1)
        self.assertEqual([1, 2, 3], api.order)
        self.assertEqual(1, api.foreground)

    def test_deferred_restore_finishes_before_final_focus(self):
        api = FakeUser32()
        api.restore_delays = {3: 0.06, 2: 0.02}
        ns = load_cycle(api)
        action(ns, "down")
        action(ns, "up")
        api.clock.sleep(1)
        self.assertEqual(1, api.foreground)
        self.assertEqual([1, 2, 3], api.order)

    def test_queued_down_up_waits_for_shell_and_keeps_fifo(self):
        api = FakeUser32()
        api.delayed_minimize = True
        ns = load_cycle(api)
        ns["actions"] = queue.Queue()
        for direction in ("down", "down", "up"):
            ns["actions"].put(ns["SWIPE_ACTIONS"][direction])
        ns["actions"].put(None)
        ns["worker"]()
        api.clock.sleep(1)
        self.assertTrue(all(not v["iconic"] for v in api.windows.values()))
        self.assertEqual(1, api.foreground)
        self.assertEqual(["minimize", "restore", "restore", "restore", "foreground"],
                         [e[0] for e in api.events if e[0] != "position"])

    def test_down_up_restores_all_in_saved_order_with_original_foreground(self):
        api = FakeUser32()
        ns = load_cycle(api)
        placements = {h: (v["rect"], v["maximized"]) for h, v in api.windows.items()}
        action(ns, "down")
        self.assertTrue(all(v["iconic"] for v in api.windows.values()))
        action(ns, "up")
        api.finish_async()
        self.assertTrue(all(not v["iconic"] for v in api.windows.values()))
        self.assertEqual(1, api.foreground)
        self.assertEqual([1, 2, 3], api.order)
        self.assertEqual(placements, {h: (v["rect"], v["maximized"]) for h, v in api.windows.items()})
        self.assertEqual([], api.pending)


if __name__ == "__main__":
    unittest.main()
