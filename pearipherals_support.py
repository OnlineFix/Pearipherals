"""Pure support, diagnostics, and lifecycle models for Pearipherals."""

from copy import deepcopy
from dataclasses import dataclass
from datetime import timezone
import re

from pearipherals_version import BuildIdentity


DIAGNOSTICS_SCHEMA_VERSION = 1
PRIVACY_NOTICE = (
    "Whitelisted product state only; excludes local paths, device identifiers, "
    "raw configuration, registry data, logs, and network destinations. "
    "Pearipherals does not upload this report."
)
SUPPORT_ENUMS = {
    "mode": frozenset(("source", "frozen")),
    "config_state": frozenset(("loaded", "missing", "recovery required", "unavailable")),
    "keyboard_battery": frozenset(
        ("available", "not detected", "unavailable", "unsupported", "stale")
    ),
    "trackpad_battery": frozenset(
        ("available", "not detected", "unavailable", "unsupported", "stale")
    ),
    # Conservative registration wording only: Pearipherals can observe that it
    # registered a Raw Input listener, never that a device is present or bound.
    "raw_input_state": frozenset(
        ("not started", "starting", "listener registered", "unavailable")
    ),
    # A service registry key says a service is registered. It does not say the
    # driver is installed, running, healthy, or bound to any device.
    "driver_state": frozenset(
        ("service registration detected", "not detected", "unavailable")
    ),
    "gesture_mode": frozenset(("swipes", "drag", "off")),
    "gesture_readiness": frozenset(
        ("ready", "off", "not started", "starting", "unavailable", "action required")
    ),
    "touchpad_settings": frozenset(
        (
            "applied",
            "needs apply",
            "original settings",
            "restore incomplete",
            "unavailable",
        )
    ),
    "scroll_direction": frozenset(("natural", "classic", "unavailable")),
    "autostart": frozenset(("off", "current", "stale", "unavailable")),
    "lifecycle": frozenset(
        ("first observed", "unchanged", "version changed", "not recorded")
    ),
    "removal_readiness": frozenset(("ready", "action required")),
}


@dataclass(frozen=True)
class SupportSnapshot:
    identity: BuildIdentity
    mode: str
    windows_version: str
    windows_build: str
    architecture: str
    config_state: str
    keyboard_battery: str
    trackpad_battery: str
    raw_input_state: str
    driver_state: str
    gesture_mode: str
    gesture_readiness: str
    touchpad_settings: str
    scroll_direction: str
    autostart: str
    lifecycle: str
    removal_readiness: str

    def __post_init__(self):
        for field, allowed in SUPPORT_ENUMS.items():
            if getattr(self, field) not in allowed:
                raise ValueError(f"unsupported support state for {field}")


def format_about(snapshot):
    """Format a deterministic About/status view without performing I/O."""
    return "\n".join((
        "Pearipherals",
        f"Version: {redact_support_text(snapshot.identity.version)}",
        f"Build: {snapshot.identity.build_id}",
        f"Mode: {snapshot.mode}",
        f"Windows: {redact_support_text(snapshot.windows_version)} "
        f"(build {redact_support_text(snapshot.windows_build)}; "
        f"{redact_support_text(snapshot.architecture)})",
        f"Config: {snapshot.config_state}",
        f"Magic Keyboard battery path: {snapshot.keyboard_battery}",
        f"Magic Trackpad battery path: {snapshot.trackpad_battery}",
        f"AmtPtpHidFilter service: {snapshot.driver_state}",
        f"Raw Input: {snapshot.raw_input_state}",
        f"Gesture mode: {snapshot.gesture_mode}",
        f"Gesture readiness: {snapshot.gesture_readiness}",
        f"Touchpad settings: {snapshot.touchpad_settings}",
        f"Scrolling: {snapshot.scroll_direction}",
        f"Autostart: {snapshot.autostart}",
        f"Lifecycle: {snapshot.lifecycle}",
        f"Prepare for removal: {snapshot.removal_readiness}",
        "",
        "Help: use Open documentation or Report a problem from the tray menu.",
    ))


_REDACTED_PATH = "[redacted path]"
# Any UNC share, extended-length (\\?\), or device (\\.\) path.
_UNC_OR_DEVICE_PATH = re.compile(r"\\\\[^\s,;]+")
# Any absolute drive path, not just C:\Users. A trailing space is consumed only
# while the next token still looks like a path segment, so ordinary prose after
# the path survives.
_WINDOWS_DRIVE_PATH = re.compile(
    r"(?i)(?<![a-z0-9])[a-z]:[\\/]+[^\s,;]*(?:[ ][^\s,;]*[\\/][^\s,;]*)*"
)
_POSIX_USER_PATH = re.compile(r"(?i)(?<!\w)/(?:users|home)/[^\s,;]+")
# Device instance identifiers use \, / or # as separators, in any case.
_DEVICE_IDENTIFIER = re.compile(r"(?i)(?<![a-z0-9])(?:hid|bthenum)[\\/#][^\s,;]+")
_MAC_ADDRESS = re.compile(
    r"(?i)(?<![0-9a-f])(?:[0-9a-f]{2}[:-]){5}[0-9a-f]{2}(?![0-9a-f])"
)
_COMPACT_BLUETOOTH_ADDRESS = re.compile(
    r"(?i)(?<![0-9a-f])[0-9a-f]{12}(?![0-9a-f])"
)


def redact_support_text(value, max_length=160):
    """Redact likely local identifiers and bound diagnostic free text."""
    text = str(value)
    text = re.sub(r"[\x00-\x1f\x7f]+", " ", text)
    # Bound the input before pattern matching so pathological free text cannot
    # dominate redaction cost. The cut is deliberately generous and redaction
    # runs over the WHOLE remaining text before the final max_length bound is
    # applied: truncating first could sever a pattern mid-match and leak the
    # surviving fragment (e.g. 5 of 6 MAC octets).
    text = text[: max(max_length * 8, 4096)]
    text = _UNC_OR_DEVICE_PATH.sub(_REDACTED_PATH, text)
    text = _WINDOWS_DRIVE_PATH.sub(_REDACTED_PATH, text)
    text = _POSIX_USER_PATH.sub(_REDACTED_PATH, text)
    text = _DEVICE_IDENTIFIER.sub("[redacted device id]", text)
    text = _MAC_ADDRESS.sub("[redacted address]", text)
    text = _COMPACT_BLUETOOTH_ADDRESS.sub("[redacted address]", text)
    if len(text) > max_length:
        # An ellipsis must never push the result past the caller's bound.
        if max_length <= 3:
            text = text[:max_length]
        else:
            text = text[: max_length - 3] + "..."
    return text


def diagnostics_payload(snapshot, generated_at):
    """Build the local diagnostic report from an explicit field whitelist."""
    generated_at_utc = (
        generated_at.astimezone(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )
    return {
        "schema_version": DIAGNOSTICS_SCHEMA_VERSION,
        "generated_at_utc": generated_at_utc,
        "privacy_notice": PRIVACY_NOTICE,
        "product": {
            "name": "Pearipherals",
            "version": redact_support_text(snapshot.identity.version),
            "build_id": snapshot.identity.build_id,
            "mode": snapshot.mode,
        },
        "windows": {
            "version": redact_support_text(snapshot.windows_version),
            "build": redact_support_text(snapshot.windows_build),
            "architecture": redact_support_text(snapshot.architecture),
        },
        "state": {
            "config": snapshot.config_state,
            "keyboard_battery": snapshot.keyboard_battery,
            "trackpad_battery": snapshot.trackpad_battery,
            "driver": snapshot.driver_state,
            "raw_input": snapshot.raw_input_state,
            "gesture_mode": snapshot.gesture_mode,
            "gesture_readiness": snapshot.gesture_readiness,
            "touchpad_settings": snapshot.touchpad_settings,
            "scroll_direction": snapshot.scroll_direction,
            "autostart": snapshot.autostart,
            "lifecycle": snapshot.lifecycle,
            "removal_readiness": snapshot.removal_readiness,
        },
    }


def observe_version(config, current, save):
    """Persist an observed version change transactionally, without ordering it."""
    observed = config.get("current_version")
    if observed == current:
        return "unchanged"

    before = deepcopy(config)
    if observed is None:
        config["current_version"] = current
        config["previous_version"] = None
        transition = "first observed"
    else:
        config["previous_version"] = observed
        config["current_version"] = current
        transition = "version changed"

    try:
        save()
    except Exception:
        config.clear()
        config.update(before)
        raise
    return transition


def battery_state(result):
    """Map an immutable battery result to a conservative fixed state."""
    if result.stale:
        return "stale"
    return {
        "available": "available",
        "not_detected": "not detected",
        "unavailable": "unavailable",
        "unsupported": "unsupported",
    }.get(result.status, "unavailable")


def classify_removal_readiness(
    autostart, legacy_autostart, mac_fkeys, gesture_mode, settings_applied,
    backup_entries
):
    """Return ready only after every persistent/custom state is clear.

    Both the current and every legacy start-with-Windows entry must be
    *confirmed* absent, and both custom input behaviours (Mac F-row handling
    and three-finger gestures) must be off. Anything unreadable stays
    "action required" so uncertainty is never reported as ready.
    """
    if (
        autostart == "off"
        and legacy_autostart == "absent"
        and not mac_fkeys
        and gesture_mode == "off"
        and not settings_applied
        and not backup_entries
    ):
        return "ready"
    return "action required"


DIAGNOSTICS_FILENAME = "pearipherals-diagnostics.json"

# Removal preparation order. Durable preferences are persisted BEFORE runtime
# input is released, so a crash between steps can never leave the app owning
# input it no longer has a stored mandate for. Every step is independent and
# each one is attempted even after an earlier failure.
REMOVAL_STEP_ORDER = ("settings", "input_release", "autostart", "touchpad")
_REMOVAL_STEP_LABELS = {
    "settings": "Mac F-row handling and three-finger gestures were turned off",
    "input_release": "custom input handling was released",
    "autostart": "start-with-Windows entries were removed and verified",
    "touchpad": "original Windows touchpad settings were restored",
}


@dataclass(frozen=True)
class RemovalOutcome:
    completed: tuple
    failed: tuple

    @property
    def succeeded(self):
        return not self.failed


def perform_removal(steps):
    """Run every removal step independently; never report a partial success.

    Failures are counted, never described: an exception message can carry a
    local path or registry detail, so only the fixed step name survives.
    """
    completed = []
    failed = []
    for name in REMOVAL_STEP_ORDER:
        try:
            steps[name]()
        except Exception:
            failed.append(name)
        else:
            completed.append(name)
    return RemovalOutcome(tuple(completed), tuple(failed))


def format_removal_summary(outcome):
    """Describe only what actually happened, without leaking failure text."""
    lines = []
    for name in outcome.completed:
        lines.append(f"- {_REMOVAL_STEP_LABELS[name]}.")
    if outcome.succeeded:
        head = (
            "Pearipherals is ready to be removed. It changed back:"
            if lines else "Pearipherals is ready to be removed."
        )
        tail = (
            "Nothing was erased. Close Pearipherals with Quit, then delete its "
            "folder whenever you like."
        )
    else:
        head = "Some removal preparation could not be completed."
        pending = ", ".join(_REMOVAL_STEP_LABELS[n] for n in outcome.failed)
        tail = (
            f"Still outstanding: {pending}. Nothing was erased. Try Prepare for "
            "removal again, or open About / status for the current state."
        )
    body = [head]
    body.extend(lines)
    body.append("")
    body.append(tail)
    return "\n".join(body)


def _normalize_windows_command(command):
    return command.strip().replace("/", "\\").casefold()


def classify_autostart(command, expected_command):
    """Classify the registered command without exposing either command.

    A Run value can hold any registry type: winreg returns int for REG_DWORD,
    list for REG_MULTI_SZ and bytes for REG_BINARY. Anything that is not a
    string was not written by this app in a form it can compare, so it is
    uncertainty ("unavailable") - never a claim that autostart is off, and
    never an exception that could take the tray down.
    """
    if command is None:
        return "off"
    if not isinstance(command, str) or not isinstance(expected_command, str):
        return "unavailable"
    if _normalize_windows_command(command) == _normalize_windows_command(
        expected_command
    ):
        return "current"
    return "stale"
