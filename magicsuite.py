"""MagicKeys — Mac-style function row for Apple Magic Keyboard on Windows.

F1  brightness-  (external monitor via DDC/CI)
F2  brightness+
F3  Task View    (Win+Tab)   — Mission Control equivalent
F4  Search      (Win+S)      — Spotlight equivalent
F5  F5 (passthrough)
F6  F6 (passthrough)
F7  previous track
F8  play/pause
F9  next track
F10 mute
F11 volume down
F12 volume up

Holding ANY modifier (Ctrl/Alt/Shift/Win) passes F-keys through untouched,
so Alt+F4, Ctrl+F5, Shift+F10 keep working.

Tray icon: toggle Mac F-keys, autostart, quit.
Config: magickeys.json next to this script.
"""
import ctypes
import ctypes.wintypes as w
import json
import os
import queue
import sys
import threading

import pystray
from PIL import Image, ImageDraw

IS_FROZEN = getattr(sys, "frozen", False)
if IS_FROZEN:
    APP_DIR = os.path.dirname(os.path.abspath(sys.executable))
else:
    APP_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(APP_DIR, "magicsuite.json")
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_NAME = "MagicSuite"
OLD_RUN_NAMES = ("MagicKeys",)
MAGIC_EXTRA = 0xA99C0DE  # tag for our own injected events

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
dxva2 = ctypes.WinDLL("dxva2", use_last_error=True)

# ---------------------------------------------------------------- config
DEFAULTS = {"mac_fkeys": True, "brightness_step": 10,
            "three_finger_mode": "swipes",   # swipes | drag | off
            "drag_gain": 0.75, "drag_grace_ms": 350, "drag_start_units": 30,
            "swipe_units": 300,
            "natural_scroll": False,   # False = swipe down scrolls down (wheel style)
            "cfg_version": 4}


def load_config():
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg = {**DEFAULTS, **json.load(f)}
    except Exception:
        cfg = dict(DEFAULTS)
    # v3: three_finger_drag bool replaced by three_finger_mode enum, and
    # swipe synthesis introduced (old driver can't feed native swipes).
    if cfg.get("cfg_version", 1) < 3:
        cfg.pop("three_finger_drag", None)
        cfg["three_finger_mode"] = "swipes"
    # v4: scroll direction handled by our own instant inversion layer
    # (Windows only reads ScrollDirection at logon — useless as a toggle).
    if cfg.get("cfg_version", 1) < 4:
        cfg["natural_scroll"] = False
        cfg["cfg_version"] = 4
        save_config(cfg)
    return cfg


def save_config(cfg):
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
    except Exception:
        pass


config = load_config()

# ---------------------------------------------------------------- SendInput
ULONG_PTR = ctypes.c_size_t


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", w.WORD), ("wScan", w.WORD), ("dwFlags", w.DWORD),
                ("time", w.DWORD), ("dwExtraInfo", ULONG_PTR)]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", w.LONG), ("dy", w.LONG), ("mouseData", w.DWORD),
                ("dwFlags", w.DWORD), ("time", w.DWORD), ("dwExtraInfo", ULONG_PTR)]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [("uMsg", w.DWORD), ("wParamL", w.WORD), ("wParamH", w.WORD)]


class _INPUTunion(ctypes.Union):
    _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", w.DWORD), ("u", _INPUTunion)]


INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002

user32.SendInput.argtypes = (w.UINT, ctypes.POINTER(INPUT), ctypes.c_int)
user32.SendInput.restype = w.UINT


def send_keys(vks_down, vks_up=None):
    """Press vks_down in order, then release (reverse order by default)."""
    if vks_up is None:
        vks_up = list(reversed(vks_down))
    seq = [(vk, 0) for vk in vks_down] + [(vk, KEYEVENTF_KEYUP) for vk in vks_up]
    arr = (INPUT * len(seq))()
    for i, (vk, flags) in enumerate(seq):
        arr[i].type = INPUT_KEYBOARD
        arr[i].u.ki = KEYBDINPUT(vk, 0, flags, 0, MAGIC_EXTRA)
    user32.SendInput(len(seq), arr, ctypes.sizeof(INPUT))


VK_MEDIA_NEXT, VK_MEDIA_PREV, VK_MEDIA_PLAY = 0xB0, 0xB1, 0xB3
VK_VOL_MUTE, VK_VOL_DOWN, VK_VOL_UP = 0xAD, 0xAE, 0xAF
VK_LWIN, VK_TAB, VK_S = 0x5B, 0x09, 0x53
VK_ALT, VK_SHIFT, VK_D = 0x12, 0x10, 0x44
VK_M = 0x4D

# 3-finger swipe -> action (mac-like navigation on Windows)
# "keys": hotkey; "restore_all": un-minimize every window (undo swipe-down)
SWIPE_ACTIONS = {
    "up":    ("restore_all", None),
    "down":  ("keys", ([VK_LWIN, VK_M],)),     # minimize all
    "right": ("keys", ([VK_LWIN, VK_TAB],)),   # app choice (Task View)
    "left":  ("keys", ([VK_LWIN, VK_TAB],)),   # app choice (Task View)
}


def restore_all_windows():
    """Restore every minimized visible top-level window (skip tool windows)."""
    EnumProc = ctypes.WINFUNCTYPE(w.BOOL, w.HWND, w.LPARAM)
    SW_RESTORE = 9
    GWL_EXSTYLE = -20
    WS_EX_TOOLWINDOW = 0x00000080
    hwnds = []

    @EnumProc
    def cb(hwnd, lparam):
        if user32.IsWindowVisible(hwnd) and user32.IsIconic(hwnd):
            ex = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            if not (ex & WS_EX_TOOLWINDOW):
                hwnds.append(hwnd)
        return True

    user32.EnumWindows(cb, 0)
    for h in reversed(hwnds):
        user32.ShowWindowAsync(h, SW_RESTORE)

# ---------------------------------------------------------------- DDC/CI brightness
class PHYSICAL_MONITOR(ctypes.Structure):
    _fields_ = [("hPhysicalMonitor", w.HANDLE),
                ("szPhysicalMonitorDescription", w.WCHAR * 128)]


MONITORENUMPROC = ctypes.WINFUNCTYPE(w.BOOL, w.HMONITOR, w.HDC,
                                     ctypes.POINTER(w.RECT), w.LPARAM)


class Brightness:
    """DDC/CI brightness for all physical monitors, with cached handles."""

    def __init__(self):
        self._mons = []          # list[(handle, minb, maxb)]
        self._lock = threading.Lock()

    def _close(self):
        for h, _, _ in self._mons:
            try:
                pm = PHYSICAL_MONITOR(h, "")
                dxva2.DestroyPhysicalMonitors(1, ctypes.byref(pm))
            except Exception:
                pass
        self._mons = []

    def _open(self):
        self._close()
        hmons = []

        def cb(hmon, hdc, rect, lparam):
            hmons.append(hmon)
            return True

        user32.EnumDisplayMonitors(None, None, MONITORENUMPROC(cb), 0)
        for hmon in hmons:
            n = w.DWORD(0)
            if not dxva2.GetNumberOfPhysicalMonitorsFromHMONITOR(hmon, ctypes.byref(n)) or n.value == 0:
                continue
            arr = (PHYSICAL_MONITOR * n.value)()
            if not dxva2.GetPhysicalMonitorsFromHMONITOR(hmon, n.value, arr):
                continue
            for pm in arr:
                mn, cur, mx = w.DWORD(), w.DWORD(), w.DWORD()
                if dxva2.GetMonitorBrightness(pm.hPhysicalMonitor, ctypes.byref(mn),
                                              ctypes.byref(cur), ctypes.byref(mx)):
                    self._mons.append((pm.hPhysicalMonitor, mn.value, mx.value))
                else:  # monitor without DDC support
                    one = PHYSICAL_MONITOR(pm.hPhysicalMonitor, "")
                    dxva2.DestroyPhysicalMonitors(1, ctypes.byref(one))

    def step(self, delta):
        """Returns new brightness % of first monitor, or None."""
        with self._lock:
            if not self._mons:
                self._open()
            result = None
            ok_any = False
            for h, mn, mx in self._mons:
                a, cur, b = w.DWORD(), w.DWORD(), w.DWORD()
                if not dxva2.GetMonitorBrightness(h, ctypes.byref(a), ctypes.byref(cur), ctypes.byref(b)):
                    continue
                span = max(1, mx - mn)
                pct = round((cur.value - mn) * 100 / span)
                pct = max(0, min(100, pct + delta))
                raw = mn + round(pct * span / 100)
                if dxva2.SetMonitorBrightness(h, raw):
                    ok_any = True
                    if result is None:
                        result = pct
            if not ok_any:      # stale handles (monitor sleep etc.) — reopen once
                self._open()
                for h, mn, mx in self._mons:
                    a, cur, b = w.DWORD(), w.DWORD(), w.DWORD()
                    if dxva2.GetMonitorBrightness(h, ctypes.byref(a), ctypes.byref(cur), ctypes.byref(b)):
                        span = max(1, mx - mn)
                        pct = round((cur.value - mn) * 100 / span)
                        pct = max(0, min(100, pct + delta))
                        if dxva2.SetMonitorBrightness(h, mn + round(pct * span / 100)):
                            if result is None:
                                result = pct
            return result


class StudioDisplayBrightness:
    """Apple Studio Display via USB HID feature report (needs USB link to display).

    Protocol from juliuszint/asdbctl: report id 1, u32 LE brightness 400..60000.
    """

    PIDS = (0x1114, 0x1116, 0x1118)
    MIN, MAX = 400, 60000

    def __init__(self):
        self._h = None
        self._lock = threading.Lock()

    def _open(self):
        import hid as hidapi
        self._h = None
        for pid in self.PIDS:
            for d in hidapi.enumerate(0x05AC, pid):
                try:
                    h = hidapi.device()
                    h.open_path(d["path"])
                    data = h.get_feature_report(1, 7)
                    if len(data) >= 5:
                        self._h = h
                        return True
                    h.close()
                except Exception:
                    pass
        return False

    def _pct(self, raw):
        return round((raw - self.MIN) * 100 / (self.MAX - self.MIN))

    def step(self, delta):
        with self._lock:
            for attempt in (0, 1):
                if self._h is None and not self._open():
                    return None
                try:
                    data = self._h.get_feature_report(1, 7)
                    raw = int.from_bytes(bytes(data[1:5]), "little")
                    pct = max(0, min(100, self._pct(raw) + delta))
                    nraw = self.MIN + round(pct * (self.MAX - self.MIN) / 100)
                    payload = bytes([1]) + nraw.to_bytes(4, "little") + b"\x00\x00"
                    if self._h.send_feature_report(payload) > 0:
                        return pct
                    raise OSError("send_feature_report failed")
                except Exception:
                    try:
                        self._h.close()
                    except Exception:
                        pass
                    self._h = None   # stale handle (unplug) — retry once
            return None


class GammaBrightness:
    """Fallback software dimming via SetDeviceGammaRamp (video-only links).

    Scales the GPU output curve on every attached display. Floor 20% so the
    screen can never go black.
    """

    def __init__(self):
        self.gdi32 = ctypes.WinDLL("gdi32")
        self.level = self._read_current_level()

    def _read_current_level(self):
        """Infer current dim level from the actual GPU gamma ramp (survives restarts)."""
        try:
            hdc = user32.GetDC(None)
            ramp = (w.WORD * (256 * 3))()
            if self.gdi32.GetDeviceGammaRamp(hdc, ctypes.byref(ramp)):
                lvl = round(ramp[255] * 100 / 65535)
                user32.ReleaseDC(None, hdc)
                return max(20, min(100, lvl))
            user32.ReleaseDC(None, hdc)
        except Exception:
            pass
        return 100

    def _dcs(self):
        class DISPLAY_DEVICE(ctypes.Structure):
            _fields_ = [("cb", w.DWORD), ("DeviceName", w.WCHAR * 32),
                        ("DeviceString", w.WCHAR * 128), ("StateFlags", w.DWORD),
                        ("DeviceID", w.WCHAR * 128), ("DeviceKey", w.WCHAR * 128)]
        i = 0
        dd = DISPLAY_DEVICE()
        dd.cb = ctypes.sizeof(dd)
        DISPLAY_DEVICE_ATTACHED = 0x01
        while user32.EnumDisplayDevicesW(None, i, ctypes.byref(dd), 0):
            if dd.StateFlags & DISPLAY_DEVICE_ATTACHED:
                hdc = self.gdi32.CreateDCW(None, dd.DeviceName, None, None)
                if hdc:
                    yield hdc
            i += 1
            dd = DISPLAY_DEVICE()
            dd.cb = ctypes.sizeof(dd)

    def apply(self, level):
        level = max(20, min(100, level))
        ramp = (w.WORD * (256 * 3))()
        for i in range(256):
            v = min(65535, round(i * 257 * level / 100))
            ramp[i] = ramp[256 + i] = ramp[512 + i] = v
        ok = False
        for hdc in self._dcs():
            if self.gdi32.SetDeviceGammaRamp(hdc, ctypes.byref(ramp)):
                ok = True
            self.gdi32.DeleteDC(hdc)
        if ok:
            self.level = level
            config["gamma_level"] = level
            save_config(config)
        return ok

    def step(self, delta):
        target = max(20, min(100, self.level + delta))
        return target if self.apply(target) else None

    def restore(self):
        self.apply(100)


class BrightnessChain:
    """Studio Display USB -> DDC/CI -> gamma dimming, first one that works."""

    def __init__(self):
        self.sd = StudioDisplayBrightness()
        self.ddc = Brightness()
        self.gamma = GammaBrightness()
        self.last_backend = None

    def step(self, delta):
        pct = self.sd.step(delta)
        if pct is not None:
            self.last_backend = "Studio Display"
            return pct
        pct = self.ddc.step(delta)
        if pct is not None:
            self.last_backend = "DDC"
            return pct
        pct = self.gamma.step(delta)
        self.last_backend = "software dim" if pct is not None else None
        return pct


brightness = BrightnessChain()

# ---------------------------------------------------------------- brightness OSD
class OSD:
    """Windows-11-style bottom-center brightness flyout (tkinter, own thread)."""

    def __init__(self):
        self._q = queue.Queue()
        threading.Thread(target=self._run, daemon=True).start()

    def show(self, pct, backend):
        self._q.put((pct, backend))

    def _run(self):
        import tkinter as tk

        root = tk.Tk()
        root.withdraw()
        root.overrideredirect(True)
        root.attributes("-topmost", True)
        root.attributes("-alpha", 0.94)
        root.configure(bg="#202020")

        W, H = 280, 64
        cv = tk.Canvas(root, width=W, height=H, bg="#202020",
                       highlightthickness=0, bd=0)
        cv.pack()

        sun = cv.create_text(30, H // 2, text="\u2600", font=("Segoe UI Emoji", 18),
                             fill="#ffffff")
        BAR_X, BAR_W, BAR_H = 58, 160, 6
        bar_y = H // 2
        cv.create_rectangle(BAR_X, bar_y - BAR_H // 2, BAR_X + BAR_W,
                            bar_y + BAR_H // 2, fill="#5a5a5a", width=0)
        fill = cv.create_rectangle(BAR_X, bar_y - BAR_H // 2, BAR_X,
                                   bar_y + BAR_H // 2, fill="#ffffff", width=0)
        label = cv.create_text(W - 30, H // 2, text="", font=("Segoe UI", 11),
                               fill="#ffffff")
        hide_job = [None]

        def place():
            sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
            root.geometry(f"{W}x{H}+{(sw - W) // 2}+{sh - H - 76}")

        def tick():
            try:
                while True:
                    pct, backend = self._q.get_nowait()
                    cv.coords(fill, BAR_X, bar_y - BAR_H // 2,
                              BAR_X + round(BAR_W * pct / 100), bar_y + BAR_H // 2)
                    cv.itemconfigure(label, text=f"{pct}%")
                    cv.itemconfigure(sun, text="\u263c" if backend == "software dim" else "\u2600")
                    place()
                    root.deiconify()
                    root.lift()
                    if hide_job[0]:
                        root.after_cancel(hide_job[0])
                    hide_job[0] = root.after(1400, root.withdraw)
            except queue.Empty:
                pass
            root.after(30, tick)

        tick()
        root.mainloop()


osd = OSD()

# ---------------------------------------------------------------- action worker
actions = queue.Queue()
tray_icon = None  # set later


def worker():
    while True:
        item = actions.get()
        if item is None:
            return
        kind, arg = item
        try:
            if kind == "keys":
                send_keys(*arg)
            elif kind == "restore_all":
                restore_all_windows()
            elif kind == "bright":
                pct = brightness.step(arg)
                if pct is not None:
                    osd.show(pct, brightness.last_backend)
                    if tray_icon is not None:
                        tray_icon.title = (f"MagicKeys — brightness {pct}% "
                                           f"({brightness.last_backend})")
        except Exception:
            pass
        # coalesce queued repeats of the same action (key held down)
        try:
            while True:
                nxt = actions.get_nowait()
                if nxt != item:
                    actions.put(nxt)
                    break
        except queue.Empty:
            pass


# ---------------------------------------------------------------- LL keyboard hook
WH_KEYBOARD_LL = 13
WM_KEYDOWN, WM_SYSKEYDOWN = 0x0100, 0x0104
WM_KEYUP, WM_SYSKEYUP = 0x0101, 0x0105
LLKHF_INJECTED = 0x10
VK_F1, VK_F12 = 0x70, 0x7B
MOD_VKS = (0x10, 0x11, 0x12, 0x5B, 0x5C)  # shift, ctrl, alt, lwin, rwin


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [("vkCode", w.DWORD), ("scanCode", w.DWORD), ("flags", w.DWORD),
                ("time", w.DWORD), ("dwExtraInfo", ULONG_PTR)]


HOOKPROC = ctypes.WINFUNCTYPE(ctypes.c_longlong, ctypes.c_int, w.WPARAM, ctypes.c_longlong)

user32.SetWindowsHookExW.argtypes = (ctypes.c_int, HOOKPROC, w.HINSTANCE, w.DWORD)
user32.SetWindowsHookExW.restype = w.HHOOK
user32.CallNextHookEx.argtypes = (w.HHOOK, ctypes.c_int, w.WPARAM, ctypes.c_longlong)
user32.CallNextHookEx.restype = ctypes.c_longlong

# F-key -> action table
ACTIONS = {
    0x70: ("bright", None),            # F1 (delta filled at dispatch)
    0x71: ("bright", None),            # F2
    0x72: ("keys", ([VK_LWIN, VK_TAB],)),   # F3  Task View
    0x73: ("keys", ([VK_LWIN, VK_S],)),     # F4  Search
    0x76: ("keys", ([VK_MEDIA_PREV],)),     # F7
    0x77: ("keys", ([VK_MEDIA_PLAY],)),     # F8
    0x78: ("keys", ([VK_MEDIA_NEXT],)),     # F9
    0x79: ("keys", ([VK_VOL_MUTE],)),       # F10
    0x7A: ("keys", ([VK_VOL_DOWN],)),       # F11
    0x7B: ("keys", ([VK_VOL_UP],)),         # F12
}


@HOOKPROC
def ll_hook(nCode, wParam, lParam):
    if nCode == 0 and config["mac_fkeys"]:
        kb = ctypes.cast(ctypes.c_void_p(lParam), ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
        vk = kb.vkCode
        if VK_F1 <= vk <= VK_F12 and vk in ACTIONS \
           and not (kb.flags & LLKHF_INJECTED) and kb.dwExtraInfo != MAGIC_EXTRA:
            if any(user32.GetAsyncKeyState(m) & 0x8000 for m in MOD_VKS):
                return user32.CallNextHookEx(None, nCode, wParam, lParam)
            if wParam in (WM_KEYDOWN, WM_SYSKEYDOWN):
                kind, arg = ACTIONS[vk]
                if kind == "bright":
                    delta = -config["brightness_step"] if vk == 0x70 else config["brightness_step"]
                    actions.put(("bright", delta))
                else:
                    actions.put((kind, arg))
            return 1  # swallow both keydown and keyup
    return user32.CallNextHookEx(None, nCode, wParam, lParam)


def hook_thread():
    hk = user32.SetWindowsHookExW(WH_KEYBOARD_LL, ll_hook, None, 0)
    if not hk:
        sys.exit(f"SetWindowsHookExW failed: {ctypes.get_last_error()}")
    msg = w.MSG()
    while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
        user32.TranslateMessage(ctypes.byref(msg))
        user32.DispatchMessageW(ctypes.byref(msg))


# ---------------------------------------------------------------- pointer suppressor
class PointerSuppressor:
    """Low-level mouse hook that swallows MOVE/WHEEL while 3 fingers are on
    the pad. The 2021 AmtPtp driver leaks 3-finger motion into the pointer
    stream; without this the cursor wanders during swipes. Our own SendInput
    events carry MAGIC_EXTRA and always pass."""

    WH_MOUSE_LL = 14
    WM_MOUSEMOVE = 0x0200
    WM_MOUSEWHEEL = 0x020A
    WM_MOUSEHWHEEL = 0x020E
    LLMHF_INJECTED = 0x01
    MOUSEEVENTF_WHEEL = 0x0800
    MOUSEEVENTF_HWHEEL = 0x1000

    class MSLLHOOKSTRUCT(ctypes.Structure):
        _fields_ = [("pt", w.POINT), ("mouseData", w.DWORD), ("flags", w.DWORD),
                    ("time", w.DWORD), ("dwExtraInfo", ULONG_PTR)]

    def __init__(self):
        self._active = False
        self._proc = None
        self._ncontacts = 0      # fingers currently on the trackpad
        self._train_until = 0.0  # momentum-scroll train window

    def set(self, active):
        self._active = active

    def set_contacts(self, n):
        self._ncontacts = n

    def _reinject_wheel(self, horizontal, delta):
        inp = INPUT()
        inp.type = 0  # INPUT_MOUSE
        flags = self.MOUSEEVENTF_HWHEEL if horizontal else self.MOUSEEVENTF_WHEEL
        inp.u.mi = MOUSEINPUT(0, 0, ctypes.c_ulong(delta & 0xFFFFFFFF).value,
                              flags, 0, MAGIC_EXTRA)
        user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))

    def start(self):
        HOOKPROC_M = ctypes.WINFUNCTYPE(ctypes.c_longlong, ctypes.c_int,
                                        w.WPARAM, ctypes.c_longlong)

        def proc(nCode, wParam, lParam):
            if nCode == 0 and self._active:
                ms = ctypes.cast(ctypes.c_void_p(lParam),
                                 ctypes.POINTER(self.MSLLHOOKSTRUCT)).contents
                if wParam in (self.WM_MOUSEMOVE, self.WM_MOUSEWHEEL,
                              self.WM_MOUSEHWHEEL) \
                        and not (ms.flags & self.LLMHF_INJECTED) \
                        and ms.dwExtraInfo != MAGIC_EXTRA:
                    return 1  # swallow
            return user32.CallNextHookEx(None, nCode, wParam, lParam)

        self._proc = HOOKPROC_M(proc)

        def run():
            hk = user32.SetWindowsHookExW(self.WH_MOUSE_LL, self._proc, None, 0)
            if not hk:
                return
            msg = w.MSG()
            while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))

        threading.Thread(target=run, daemon=True).start()


suppress_pointer = PointerSuppressor()

# ---------------------------------------------------------------- 3-finger drag
class ThreeFingerDrag:
    """macOS-style three-finger drag via Raw Input PTP frames.

    Reads Precision Touchpad contact frames (usage 0x0D/0x05) in parallel with
    the OS, and when exactly 3 confident contacts move, holds the left mouse
    button and moves the cursor itself. Grace period lets you lift/reposition
    fingers mid-drag like on a Mac.
    """

    WM_INPUT = 0x00FF
    RIDEV_INPUTSINK = 0x00000100
    RIM_TYPEHID = 2
    RID_INPUT = 0x10000003
    RIDI_PREPARSEDDATA = 0x20000005
    RIDI_DEVICENAME = 0x20000007
    HIDP_SUCCESS = 0x00110000
    UP_DIG, U_TOUCHPAD = 0x0D, 0x05
    U_X, U_Y, U_CID, U_COUNT, U_TIP, U_CONF = 0x30, 0x31, 0x51, 0x54, 0x42, 0x47

    MOUSEEVENTF_MOVE = 0x0001
    MOUSEEVENTF_LEFTDOWN = 0x0002
    MOUSEEVENTF_LEFTUP = 0x0004

    class VALUE_CAPS(ctypes.Structure):
        _fields_ = [("UsagePage", w.WORD), ("ReportID", ctypes.c_ubyte),
                    ("IsAlias", ctypes.c_ubyte), ("BitField", w.WORD),
                    ("LinkCollection", w.WORD), ("LinkUsage", w.WORD),
                    ("LinkUsagePage", w.WORD), ("IsRange", ctypes.c_ubyte),
                    ("IsStringRange", ctypes.c_ubyte), ("IsDesignatorRange", ctypes.c_ubyte),
                    ("IsAbsolute", ctypes.c_ubyte), ("HasNull", ctypes.c_ubyte),
                    ("Reserved", ctypes.c_ubyte), ("BitSize", w.WORD),
                    ("ReportCount", w.WORD), ("Reserved2", w.WORD * 5),
                    ("UnitsExp", w.DWORD), ("Units", w.DWORD),
                    ("LogicalMin", ctypes.c_long), ("LogicalMax", ctypes.c_long),
                    ("PhysicalMin", ctypes.c_long), ("PhysicalMax", ctypes.c_long),
                    ("UsageMin", w.WORD), ("UsageMax", w.WORD),
                    ("StringMin", w.WORD), ("StringMax", w.WORD),
                    ("DesignatorMin", w.WORD), ("DesignatorMax", w.WORD),
                    ("DataIndexMin", w.WORD), ("DataIndexMax", w.WORD)]

    class RAWINPUTDEVICE(ctypes.Structure):
        _fields_ = [("usUsagePage", w.WORD), ("usUsage", w.WORD),
                    ("dwFlags", w.DWORD), ("hwndTarget", w.HWND)]

    class RAWINPUTHEADER(ctypes.Structure):
        _fields_ = [("dwType", w.DWORD), ("dwSize", w.DWORD),
                    ("hDevice", w.HANDLE), ("wParam", w.WPARAM)]

    def __init__(self):
        self.hid = ctypes.WinDLL("hid")
        self.hid.HidP_GetUsageValue.argtypes = [
            ctypes.c_int, w.WORD, w.WORD, w.WORD, ctypes.POINTER(ctypes.c_ulong),
            ctypes.c_void_p, ctypes.c_char_p, ctypes.c_ulong]
        self.hid.HidP_GetUsages.argtypes = [
            ctypes.c_int, w.WORD, w.WORD, ctypes.POINTER(w.WORD),
            ctypes.POINTER(ctypes.c_ulong), ctypes.c_void_p,
            ctypes.c_char_p, ctypes.c_ulong]
        self.hid.HidP_GetValueCaps.argtypes = [
            ctypes.c_int, ctypes.c_void_p, ctypes.POINTER(w.WORD), ctypes.c_void_p]
        user32.GetRawInputData.argtypes = [
            ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_uint), ctypes.c_uint]
        user32.GetRawInputDeviceInfoW.argtypes = [
            w.HANDLE, ctypes.c_uint, ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint)]

        self._pp = {}            # hDevice -> preparsed buffer
        self._links = {}         # hDevice -> [contact link collections]
        self._is_tp = {}         # hDevice -> bool (trackpad device filter)
        # Hybrid-report assembly: the AmtPtp driver sends ONE contact per HID
        # report; a "frame" only exists as a rolling window. Track contacts by
        # ID and expire the ones that stop reporting.
        self._touch = {}         # cid -> [x, y, last_ts, x0, y0, t0]
        self.TOUCH_TTL = 0.07    # s without an update -> contact considered gone
        self.FRESH = 0.06        # every contact must be this fresh to fire
        self.MIN_AGE = 0.06      # and this old — filters ghost IDs from churn
        # drag state machine: idle -> armed -> dragging (-> grace -> dragging)
        self._state = "idle"
        self._anchor = None      # (x, y) three-finger centroid at arm time
        self._last = None        # last centroid
        self._grace_deadline = 0.0
        self._residual = [0.0, 0.0]
        self._wndproc_ref = None
        self._thread = None

    # ---------------- device/report helpers ----------------
    def _device_ok(self, hdev):
        ok = self._is_tp.get(hdev)
        if ok is None:
            size = ctypes.c_uint(0)
            user32.GetRawInputDeviceInfoW(hdev, self.RIDI_DEVICENAME, None,
                                          ctypes.byref(size))
            buf = ctypes.create_unicode_buffer(size.value + 2)
            user32.GetRawInputDeviceInfoW(hdev, self.RIDI_DEVICENAME, buf,
                                          ctypes.byref(size))
            ok = True  # any PTP touchpad; all report through usage 0x0D/0x05
            self._is_tp[hdev] = ok
        return ok

    def _preparsed(self, hdev):
        if hdev in self._pp:
            return self._pp[hdev]
        size = ctypes.c_uint(0)
        user32.GetRawInputDeviceInfoW(hdev, self.RIDI_PREPARSEDDATA, None,
                                      ctypes.byref(size))
        buf = ctypes.create_string_buffer(size.value) if size.value else None
        if buf:
            user32.GetRawInputDeviceInfoW(hdev, self.RIDI_PREPARSEDDATA, buf,
                                          ctypes.byref(size))
        self._pp[hdev] = buf
        links = []
        if buf:
            n = w.WORD(128)
            vcaps = (self.VALUE_CAPS * 128)()
            if self.hid.HidP_GetValueCaps(0, vcaps, ctypes.byref(n),
                                          buf) == self.HIDP_SUCCESS:
                for i in range(n.value):
                    c = vcaps[i]
                    if c.UsagePage == 0x01 and c.UsageMin == self.U_X:
                        links.append(c.LinkCollection)
        self._links[hdev] = sorted(set(links))
        return buf

    def _contacts(self, hdev, rep):
        """Yield (contact_id, x, y, tip) for every contact in this report."""
        pp = self._preparsed(hdev)
        if not pp:
            return []
        val = ctypes.c_ulong(0)
        out = []
        for lc in self._links[hdev]:
            if self.hid.HidP_GetUsageValue(0, 0x01, lc, self.U_X, ctypes.byref(val),
                                           pp, rep, len(rep)) != self.HIDP_SUCCESS:
                continue
            x = val.value
            if self.hid.HidP_GetUsageValue(0, 0x01, lc, self.U_Y, ctypes.byref(val),
                                           pp, rep, len(rep)) != self.HIDP_SUCCESS:
                continue
            y = val.value
            cid = lc  # fallback: link collection index
            if self.hid.HidP_GetUsageValue(0, self.UP_DIG, lc, self.U_CID,
                                           ctypes.byref(val), pp, rep,
                                           len(rep)) == self.HIDP_SUCCESS:
                cid = val.value
            n = ctypes.c_ulong(8)
            ub = (w.WORD * 8)()
            tip = conf = False
            if self.hid.HidP_GetUsages(0, self.UP_DIG, lc, ub, ctypes.byref(n),
                                       pp, rep, len(rep)) == self.HIDP_SUCCESS:
                got = {ub[i] for i in range(n.value)}
                tip, conf = self.U_TIP in got, self.U_CONF in got
            if conf or tip:
                out.append((cid, x, y, tip))
        return out

    # ---------------- mouse synthesis ----------------
    def _mouse(self, flags, dx=0, dy=0):
        inp = INPUT()
        inp.type = 0  # INPUT_MOUSE
        inp.u.mi = MOUSEINPUT(dx, dy, 0, flags, 0, MAGIC_EXTRA)
        user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))

    def _button(self, down):
        self._mouse(self.MOUSEEVENTF_LEFTDOWN if down else self.MOUSEEVENTF_LEFTUP)

    def _move(self, fdx, fdy):
        self._residual[0] += fdx
        self._residual[1] += fdy
        dx, dy = int(self._residual[0]), int(self._residual[1])
        if dx or dy:
            self._residual[0] -= dx
            self._residual[1] -= dy
            self._mouse(self.MOUSEEVENTF_MOVE, dx, dy)

    # ---------------- state machine ----------------
    def _end_drag(self):
        self._button(False)
        self._state = "idle"
        self._anchor = self._last = None

    def _frame(self, hdev, rep):
        import time as _t
        mode = config["three_finger_mode"]
        now = _t.monotonic()

        # 1. merge this report's contacts into the rolling touch table,
        #    collecting per-contact motion deltas as we go
        #    (always — scroll inversion needs the live contact count)
        moved = []
        for cid, x, y, tip in self._contacts(hdev, rep):
            if x > 30000 or y > 30000:
                continue          # garbage/padding contact (e.g. id 65535)
            if tip:
                e = self._touch.get(cid)
                if e is not None:
                    moved.append((x - e[0], y - e[1]))
                    e[0], e[1], e[2] = x, y, now
                else:
                    self._touch[cid] = [x, y, now, x, y, now]
            else:
                self._touch.pop(cid, None)   # explicit lift
        # 2. expire contacts that silently stopped reporting
        dead = [cid for cid, e in self._touch.items()
                if now - e[2] > self.TOUCH_TTL]
        for cid in dead:
            del self._touch[cid]

        n = len(self._touch)
        suppress_pointer.set_contacts(n)

        if mode == "off":
            if self._state in ("dragging", "grace"):
                self._end_drag()
            self._state = "idle"
            suppress_pointer.set(False)
            return

        # freeze leaked pointer motion during 3-finger gestures
        suppress_pointer.set(n >= 3)

        if mode == "drag":
            self._frame_drag(n, now, moved)
        else:
            self._frame_swipes(n, now)

    def _quality(self, entries, now):
        """All 3 contacts fresh (still updating) and aged (not churn ghosts)."""
        return (all(now - e[2] <= self.FRESH for e in entries)
                and all(now - e[5] >= self.MIN_AGE for e in entries))

    def _frame_drag(self, n, now, moved):
        if n == 3:
            entries = list(self._touch.values())
            if self._state == "idle":
                for e in entries:            # snapshot per-contact anchors
                    e[3], e[4] = e[0], e[1]
                self._state = "armed"
            elif self._state == "armed":
                mdx = sum(e[0] - e[3] for e in entries) / 3.0
                mdy = sum(e[1] - e[4] for e in entries) / 3.0
                if (mdx * mdx + mdy * mdy) ** 0.5 >= config["drag_start_units"] \
                        and self._quality(entries, now):
                    self._button(True)
                    self._state = "dragging"
                    self._residual = [0.0, 0.0]
            elif self._state == "grace":
                self._state = "dragging"     # fingers back — same drag
            elif self._state == "dragging" and moved:
                gain = config["drag_gain"]
                dx = sum(m[0] for m in moved)
                dy = sum(m[1] for m in moved)
                self._move(dx * gain, dy * gain)
        else:
            if self._state == "dragging":
                self._state = "grace"
                self._grace_deadline = now + config["drag_grace_ms"] / 1000.0
            elif self._state == "grace":
                if now > self._grace_deadline:
                    self._end_drag()
            elif self._state == "armed":
                self._state = "idle"

    def _frame_swipes(self, n, now):
        """One swipe per 3-finger touchdown. Per-contact displacement, all
        fingers must agree on direction — immune to ID churn and ghosts."""
        if n == 3:
            entries = list(self._touch.values())
            if self._state == "idle":
                for e in entries:            # snapshot per-contact anchors
                    e[3], e[4] = e[0], e[1]
                self._state = "armed"
            elif self._state == "armed" and self._quality(entries, now):
                dxs = [e[0] - e[3] for e in entries]
                dys = [e[1] - e[4] for e in entries]
                mdx = sum(dxs) / 3.0
                mdy = sum(dys) / 3.0
                units = config["swipe_units"]
                if abs(mdx) >= abs(mdy):
                    mag, other, ds = abs(mdx), abs(mdy), dxs
                    units *= 1.5           # horizontal swipes must be deliberate
                    margin = 2.0           # and clearly horizontal
                else:
                    mag, other, ds = abs(mdy), abs(mdx), dys
                    margin = 1.4
                same_dir = all(d > 0 for d in ds) or all(d < 0 for d in ds)
                if mag >= units and mag >= margin * other and same_dir:
                    if abs(mdx) >= abs(mdy):
                        direction = "right" if mdx > 0 else "left"
                    else:
                        direction = "down" if mdy > 0 else "up"  # PTP Y grows down
                    actions.put(SWIPE_ACTIONS[direction])
                    self._state = "fired"    # one gesture per touchdown
            # state "fired": ignore all further motion until fingers lift
        else:
            if self._state in ("armed", "fired"):
                self._state = "idle"
                self._anchor = self._last = None

    def _tick_grace(self):
        """Called from message loop timer — releases the button if the grace
        window expires with no frames arriving (fingers fully lifted)."""
        import time as _t
        if self._state == "grace" and _t.monotonic() > self._grace_deadline:
            self._end_drag()

    # ---------------- raw input plumbing ----------------
    def _run(self):
        WNDPROCTYPE = ctypes.WINFUNCTYPE(ctypes.c_longlong, w.HWND, ctypes.c_uint,
                                         w.WPARAM, w.LPARAM)

        def wndproc(hwnd, msg, wp, lp):
            if msg == self.WM_INPUT:
                size = ctypes.c_uint(0)
                user32.GetRawInputData(ctypes.c_void_p(lp), self.RID_INPUT, None,
                                       ctypes.byref(size),
                                       ctypes.sizeof(self.RAWINPUTHEADER))
                buf = ctypes.create_string_buffer(size.value)
                user32.GetRawInputData(ctypes.c_void_p(lp), self.RID_INPUT, buf,
                                       ctypes.byref(size),
                                       ctypes.sizeof(self.RAWINPUTHEADER))
                hdr = ctypes.cast(buf, ctypes.POINTER(self.RAWINPUTHEADER)).contents
                if hdr.dwType == self.RIM_TYPEHID and self._device_ok(hdr.hDevice):
                    off = ctypes.sizeof(self.RAWINPUTHEADER)
                    two = ctypes.cast(ctypes.byref(buf, off),
                                      ctypes.POINTER(w.DWORD * 2)).contents
                    sz, cnt = two[0], two[1]
                    data_off = off + 8
                    for i in range(cnt):
                        rep = buf.raw[data_off + i * sz: data_off + (i + 1) * sz]
                        try:
                            self._frame(hdr.hDevice, rep)
                        except Exception:
                            if self._state in ("dragging", "grace"):
                                self._end_drag()
                return 0
            return user32.DefWindowProcW(hwnd, msg, wp, lp)

        self._wndproc_ref = WNDPROCTYPE(wndproc)

        class WNDCLASSW(ctypes.Structure):
            _fields_ = [("style", ctypes.c_uint), ("lpfnWndProc", WNDPROCTYPE),
                        ("cbClsExtra", ctypes.c_int), ("cbWndExtra", ctypes.c_int),
                        ("hInstance", w.HINSTANCE), ("hIcon", ctypes.c_void_p),
                        ("hCursor", ctypes.c_void_p), ("hbrBackground", ctypes.c_void_p),
                        ("lpszMenuName", w.LPCWSTR), ("lpszClassName", w.LPCWSTR)]

        user32.DefWindowProcW.argtypes = [w.HWND, ctypes.c_uint, w.WPARAM, w.LPARAM]
        user32.DefWindowProcW.restype = ctypes.c_longlong
        hinst = kernel32.GetModuleHandleW(None)
        wc = WNDCLASSW()
        wc.lpfnWndProc = self._wndproc_ref
        wc.hInstance = hinst
        wc.lpszClassName = "MagicSuiteTFD"
        user32.RegisterClassW(ctypes.byref(wc))
        hwnd = user32.CreateWindowExW(0, wc.lpszClassName, "tfd", 0, 0, 0, 0, 0,
                                      None, None, hinst, None)
        rid = self.RAWINPUTDEVICE(self.UP_DIG, self.U_TOUCHPAD,
                                  self.RIDEV_INPUTSINK, hwnd)
        if not user32.RegisterRawInputDevices(ctypes.byref(rid), 1,
                                              ctypes.sizeof(self.RAWINPUTDEVICE)):
            return  # no PTP device / registration failed — feature disabled
        msg = w.MSG()
        import time as _t
        while True:
            while user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
            self._tick_grace()
            _t.sleep(0.004)

    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()


three_finger_drag = ThreeFingerDrag()

# ---------------------------------------------------------------- touchpad settings
class TouchpadSettings:
    """Windows Precision Touchpad registry settings needed for MagicSuite.

    Backs up original values into the config JSON on first apply, so
    everything is reversible. Values take effect on next device
    reconnect/logon for some builds; most apply live.
    """

    KEY = r"Software\Microsoft\Windows\CurrentVersion\PrecisionTouchPad"
    # Mac-like navigation: native Windows 3-finger swipes ON
    # (up=Task View, down=show desktop, left/right=switch apps)
    REQUIRED = {"ThreeFingerSlideEnabled": 1, "ThreeFingerTapEnabled": 1}
    # mac-feel niceties (not strictly required)
    RECOMMENDED = {"TapsEnabled": 1, "TwoFingerTapEnabled": 1, "TapAndDrag": 1}
    # needed ONLY while our three-finger drag daemon is enabled (it must own
    # the 3-finger gesture, so native swipes get turned off)
    DRAG_MODE = {"ThreeFingerSlideEnabled": 0, "ThreeFingerTapEnabled": 0}

    def _read(self, name):
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, self.KEY) as k:
                return winreg.QueryValueEx(k, name)[0]
        except OSError:
            return None

    def _write(self, name, value):
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, self.KEY) as k:
            winreg.SetValueEx(k, name, 0, winreg.REG_DWORD, int(value))

    def status(self):
        """True if all REQUIRED settings already correct."""
        return all(self._read(n) == v for n, v in self.REQUIRED.items())

    def apply(self, include_recommended=True):
        backup = config.get("tp_settings_backup") or {}
        wanted = dict(self.REQUIRED)
        if include_recommended:
            wanted.update(self.RECOMMENDED)
        for name, value in wanted.items():
            cur = self._read(name)
            if cur != value:
                if name not in backup:
                    backup[name] = cur          # None = value didn't exist
                self._write(name, value)
        config["tp_settings_backup"] = backup
        save_config(config)

    def restore(self):
        backup = config.get("tp_settings_backup") or {}
        for name, old in backup.items():
            try:
                if old is None:
                    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, self.KEY, 0,
                                        winreg.KEY_SET_VALUE) as k:
                        winreg.DeleteValue(k, name)
                else:
                    self._write(name, old)
            except OSError:
                pass
        config["tp_settings_backup"] = {}
        save_config(config)

    # natural scrolling: ScrollDirection 0 = mac-style (content follows
    # fingers), 1 = classic wheel (swipe down -> page scrolls down).
    # The gesture engine re-reads this when the device (re)initializes:
    # trackpad power switch off/on, or reboot. NEVER restart the device
    # from this process — doing so with our Raw Input handles open wedges
    # the process in an unkillable kernel wait (learned the hard way).
    def natural_scroll_get(self):
        return self._read("ScrollDirection") == 0

    def natural_scroll_set(self, natural):
        self._write("ScrollDirection", 0 if natural else 1)
        # nudge listeners; harmless if nothing picks it up
        try:
            HWND_BROADCAST, WM_SETTINGCHANGE = 0xFFFF, 0x001A
            user32.SendMessageTimeoutW(
                HWND_BROADCAST, WM_SETTINGCHANGE, 0,
                r"Software\Microsoft\Windows\CurrentVersion\PrecisionTouchPad",
                0x0002, 1000, ctypes.byref(ctypes.c_ulong()))
        except Exception:
            pass


tp_settings = TouchpadSettings()

# ---------------------------------------------------------------- autostart
import winreg


def autostart_get():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            winreg.QueryValueEx(k, RUN_NAME)
        return True
    except OSError:
        return False


def autostart_set(enable):
    if IS_FROZEN:
        cmd = f'"{os.path.abspath(sys.executable)}"'
    else:
        pyw = os.path.join(APP_DIR, ".venv", "Scripts", "pythonw.exe")
        cmd = f'"{pyw}" "{os.path.abspath(__file__)}"'
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
        if enable:
            winreg.SetValueEx(k, RUN_NAME, 0, winreg.REG_SZ, cmd)
        else:
            try:
                winreg.DeleteValue(k, RUN_NAME)
            except OSError:
                pass


# ---------------------------------------------------------------- tray
def make_icon():
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([4, 16, 60, 48], radius=8, fill=(240, 240, 245, 255))
    for x in (14, 26, 38):
        d.rectangle([x, 24, x + 8, 32], fill=(60, 60, 70, 255))
    d.rectangle([14, 36, 50, 42], fill=(60, 60, 70, 255))
    d.ellipse([44, 6, 62, 24], fill=(255, 176, 32, 255))
    d.text((49, 8), "F", fill=(40, 40, 40, 255))
    return img


def on_toggle(icon, item):
    config["mac_fkeys"] = not config["mac_fkeys"]
    save_config(config)


def on_autostart(icon, item):
    autostart_set(not autostart_get())


def set_tf_mode(mode):
    config["three_finger_mode"] = mode
    save_config(config)
    # While MagicSuite owns the 3-finger gesture (swipes or drag), native
    # Windows swipes must be off — on healthy PTP drivers both would fire.
    # mode 'off' hands the gesture back to Windows.
    try:
        if mode == "off":
            for k_, v_ in tp_settings.REQUIRED.items():
                tp_settings._write(k_, v_)
        else:
            for k_, v_ in tp_settings.DRAG_MODE.items():
                tp_settings._write(k_, v_)
    except Exception:
        pass


def on_mode_swipes(icon, item):
    set_tf_mode("swipes")


def on_mode_drag(icon, item):
    set_tf_mode("drag")


def on_mode_off(icon, item):
    set_tf_mode("off")


def on_natural_scroll(icon, item):
    tp_settings.natural_scroll_set(not tp_settings.natural_scroll_get())
    try:
        icon.notify("Flip the trackpad's power switch off/on (2 s) to apply "
                    "— or it applies at next reboot.", "Scroll direction saved")
    except Exception:
        pass


def on_apply_tp(icon, item):
    tp_settings.apply()


def on_restore_tp(icon, item):
    tp_settings.restore()


def first_run_setup():
    """One-click onboarding: called when no config file exists yet.

    - enable autostart from the current location
    - apply required touchpad settings (originals backed up in config)
    """
    if config.get("setup_done"):
        return
    try:
        autostart_set(True)
    except Exception:
        pass
    try:
        tp_settings.apply()
    except Exception:
        pass
    config["setup_done"] = True
    save_config(config)


def on_quit(icon, item):
    actions.put(None)
    try:
        if brightness.last_backend == "software dim":
            brightness.gamma.restore()
    except Exception:
        pass
    icon.stop()
    os._exit(0)


def main():
    global tray_icon
    # migrate: remove old MagicKeys autostart entry if present
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0,
                            winreg.KEY_SET_VALUE) as k:
            for old in OLD_RUN_NAMES:
                try:
                    winreg.DeleteValue(k, old)
                except OSError:
                    pass
    except OSError:
        pass
    first_run_setup()
    # enforce gesture-ownership invariant every launch:
    # swipes/drag mode -> native 3-finger swipes off; off -> native on
    try:
        wanted = (tp_settings.REQUIRED if config["three_finger_mode"] == "off"
                  else tp_settings.DRAG_MODE)
        for k_, v_ in wanted.items():
            if tp_settings._read(k_) != v_:
                tp_settings._write(k_, v_)
    except Exception:
        pass
    # portable self-heal: if autostart is on but we've been moved, re-point it
    if autostart_get():
        try:
            autostart_set(True)
        except Exception:
            pass
    threading.Thread(target=worker, daemon=True).start()
    threading.Thread(target=hook_thread, daemon=True).start()
    suppress_pointer.start()
    three_finger_drag.start()
    tray_icon = pystray.Icon(
        "MagicSuite", make_icon(), "MagicSuite — Magic Keyboard + Trackpad",
        menu=pystray.Menu(
            pystray.MenuItem("Mac F-keys (F1-F12 → media/brightness)", on_toggle,
                             checked=lambda i: config["mac_fkeys"]),
            pystray.MenuItem("Three-finger gesture", pystray.Menu(
                pystray.MenuItem("Swipes (Task View / desktop / switch apps)",
                                 on_mode_swipes, radio=True,
                                 checked=lambda i: config["three_finger_mode"] == "swipes"),
                pystray.MenuItem("Drag (move windows / select like a Mac)",
                                 on_mode_drag, radio=True,
                                 checked=lambda i: config["three_finger_mode"] == "drag"),
                pystray.MenuItem("Off (let Windows handle it)",
                                 on_mode_off, radio=True,
                                 checked=lambda i: config["three_finger_mode"] == "off"),
            )),
            pystray.MenuItem("Natural scrolling", on_natural_scroll,
                             checked=lambda i: tp_settings.natural_scroll_get()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Touchpad settings", pystray.Menu(
                pystray.MenuItem("Status: OK" if tp_settings.status()
                                 else "Status: needs apply",
                                 None, enabled=False),
                pystray.MenuItem("Apply Mac-style settings", on_apply_tp),
                pystray.MenuItem("Restore Windows defaults", on_restore_tp),
            )),
            pystray.MenuItem("Start with Windows", on_autostart,
                             checked=lambda i: autostart_get()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit", on_quit),
        ))
    tray_icon.run()


def _single_instance_or_exit():
    """Named mutex so double-starts (Run key + manual) can't stack hooks."""
    kernel32.CreateMutexW(None, False, "MagicSuite_single_instance_v2")
    ERROR_ALREADY_EXISTS = 183
    if ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
        os._exit(0)


if __name__ == "__main__":
    _single_instance_or_exit()
    log_path = os.path.join(APP_DIR, "magicsuite.err.log")
    # Early-logon resilience: explorer/tray may not exist yet, displays may
    # still be initializing. Retry the whole app a few times before giving up.
    import datetime
    import time as _time
    import traceback
    for attempt in range(5):
        try:
            main()
            break                      # clean exit via Quit
        except SystemExit:
            raise
        except Exception:
            try:
                with open(log_path, "a", encoding="utf-8") as f:
                    f.write(f"\n[{datetime.datetime.now():%Y-%m-%d %H:%M:%S}] "
                            f"attempt {attempt + 1} crashed:\n")
                    f.write(traceback.format_exc())
            except Exception:
                pass
            _time.sleep(10)
