import copy
import json
import os
import tempfile
import unittest
from datetime import datetime, timezone


class BuildIdentityTests(unittest.TestCase):
    def test_rejects_build_ids_without_an_exact_validated_prefix(self):
        from pearipherals_version import BuildIdentity

        rejected = (
            "not-a-build-id",
            "a" * 64,                       # unprefixed entry digest
            "b" * 40,                       # unprefixed revision
            "git:" + "c" * 39,              # short revision
            "git:" + "d" * 41,              # long revision
            "git:" + "z" * 40,              # non-hexadecimal revision
            "entry-sha256:" + "e" * 63,     # short digest
            "entry-sha256:" + "f" * 65,     # long digest
            "entry-sha256:" + "g" * 64,     # non-hexadecimal digest
            "sha256:" + "a" * 64,           # unknown prefix
            "git:",
            "",
            None,
            b"git:" + b"a" * 40,
        )
        for build_id in rejected:
            with self.subTest(build_id=build_id):
                with self.assertRaises(ValueError):
                    BuildIdentity(version="1.2.0", build_id=build_id)

    def test_rejects_versions_outside_the_release_manifest_grammar(self):
        from pearipherals_version import BuildIdentity

        for version in (
            "", "1.2", "latest", "1.2.3-beta", "1.2.3.65536", None,
            "01.2.3", "1.02.3", "1.2.03", "٠.١.٢",
            "65536.2.3", "1.65536.3", "1.2.65536",
        ):
            with self.subTest(version=version):
                with self.assertRaises(ValueError):
                    BuildIdentity(version=version, build_id="git:" + "a" * 40)

    def test_accepts_exact_frozen_revision_and_entry_script_digest(self):
        from pearipherals_version import BuildIdentity

        frozen = BuildIdentity(version="1.2.0", build_id="git:" + "a" * 40)
        source = BuildIdentity(
            version="1.2.0", build_id="entry-sha256:" + "b" * 64
        )

        self.assertEqual("git:" + "a" * 40, frozen.build_id)
        self.assertEqual("entry-sha256:" + "b" * 64, source.build_id)

    def test_build_identity_is_immutable(self):
        from dataclasses import FrozenInstanceError

        from pearipherals_version import BuildIdentity

        identity = BuildIdentity("1.2.0", "git:" + "a" * 40)
        with self.assertRaises(FrozenInstanceError):
            identity.build_id = "git:" + "b" * 40

    def test_hash_file_returns_complete_sha256(self):
        from pearipherals_version import hash_file

        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "fixture.bin")
            with open(path, "wb") as stream:
                stream.write(b"Pearipherals build fixture\x00\xff")

            self.assertEqual(
                "32d128aa57aa5a59b84214bc8a1245a11040db559f3aa4f4d9fbded725a00e8e",
                hash_file(path),
            )

    def test_entry_source_build_id_prefixes_the_exact_entry_digest(self):
        from pearipherals_version import BuildIdentity, entry_source_build_id

        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "fixture.bin")
            with open(path, "wb") as stream:
                stream.write(b"Pearipherals build fixture\x00\xff")

            build_id = entry_source_build_id(path)

            self.assertEqual(
                "entry-sha256:"
                "32d128aa57aa5a59b84214bc8a1245a11040db559f3aa4f4d9fbded725a00e8e",
                build_id,
            )
            self.assertEqual(build_id, BuildIdentity("1.2.0", build_id).build_id)

    def test_source_mode_is_labelled_an_entry_script_identity_only(self):
        import pearipherals_version
        from pearipherals_version import entry_source_build_id

        documentation = " ".join(
            text.casefold()
            for text in (
                pearipherals_version.__doc__ or "",
                entry_source_build_id.__doc__ or "",
                pearipherals_version.ENTRY_BUILD_ID_PREFIX,
            )
        )

        self.assertIn("entry script", documentation)
        self.assertIn("not a complete", documentation)
        self.assertNotIn("complete source-build identity.", documentation)


class BatterySupportTests(unittest.TestCase):
    def test_battery_states_use_conservative_fixed_labels(self):
        from pearipherals_core import BatteryResult
        from pearipherals_support import battery_state

        cases = (
            (BatteryResult("available", 72), "available"),
            (BatteryResult("not_detected"), "not detected"),
            (BatteryResult("unavailable"), "unavailable"),
            (BatteryResult("unsupported"), "unsupported"),
            (BatteryResult("unavailable", stale=True, last_percentage=72), "stale"),
        )
        labels = [battery_state(result) for result, _ in cases]

        self.assertEqual([expected for _, expected in cases], labels)
        self.assertNotIn("driver missing", " ".join(labels).casefold())


class AboutFormattingTests(unittest.TestCase):
    def test_about_format_includes_complete_support_snapshot(self):
        from pearipherals_support import SupportSnapshot, format_about
        from pearipherals_version import BuildIdentity

        snapshot = SupportSnapshot(
            identity=BuildIdentity("1.2.0", "entry-sha256:" + "a" * 64),
            mode="source",
            windows_version="Windows 11",
            windows_build="26100",
            architecture="AMD64",
            config_state="loaded",
            keyboard_battery="available",
            trackpad_battery="not detected",
            raw_input_state="listener registered",
            driver_state="service registration detected",
            gesture_mode="swipes",
            gesture_readiness="ready",
            touchpad_settings="applied",
            scroll_direction="classic",
            autostart="current",
            lifecycle="version changed",
            removal_readiness="action required",
        )

        self.assertEqual(
            "\n".join((
                "Pearipherals",
                "Version: 1.2.0",
                f"Build: entry-sha256:{'a' * 64}",
                "Mode: source",
                "Windows: Windows 11 (build 26100; AMD64)",
                "Config: loaded",
                "Magic Keyboard battery path: available",
                "Magic Trackpad battery path: not detected",
                "AmtPtpHidFilter service: service registration detected",
                "Raw Input: listener registered",
                "Gesture mode: swipes",
                "Gesture readiness: ready",
                "Touchpad settings: applied",
                "Scrolling: classic",
                "Autostart: current",
                "Lifecycle: version changed",
                "Prepare for removal: action required",
                "",
                "Help: use Open documentation or Report a problem from the tray menu.",
            )),
            format_about(snapshot),
        )
        self.assertNotIn("driver missing", format_about(snapshot).casefold())

    def test_about_redacts_free_text_without_mutating_snapshot(self):
        from pearipherals_support import format_about
        from pearipherals_version import BuildIdentity

        snapshot = DiagnosticsPayloadTests._snapshot(
            identity=BuildIdentity("1.2.0", "git:" + "d" * 40),
            windows_version=r"Windows C:\Users\name\build /Users/name/private",
            windows_build=r"BTHENUM\DEV_AABBCCDDEEFF\SECRET",
            architecture="AA:BB:CC:DD:EE:FF",
        )

        about = format_about(snapshot)

        for secret in (
            "C:\\Users\\name",
            "/Users/name",
            "DEV_AABBCCDDEEFF",
            "AA:BB:CC:DD:EE:FF",
        ):
            with self.subTest(secret=secret):
                self.assertNotIn(secret, about)
        self.assertEqual(
            r"Windows C:\Users\name\build /Users/name/private",
            snapshot.windows_version,
        )


class DiagnosticsPayloadTests(unittest.TestCase):
    @staticmethod
    def _snapshot(**overrides):
        from dataclasses import replace

        from pearipherals_support import SupportSnapshot
        from pearipherals_version import BuildIdentity

        snapshot = SupportSnapshot(
            identity=BuildIdentity("1.2.0", "git:" + "b" * 40),
            mode="frozen",
            windows_version="Windows 11 Pro",
            windows_build="26100.4946",
            architecture="AMD64",
            config_state="loaded",
            keyboard_battery="available",
            trackpad_battery="unavailable",
            raw_input_state="listener registered",
            driver_state="service registration detected",
            gesture_mode="swipes",
            gesture_readiness="ready",
            touchpad_settings="applied",
            scroll_direction="classic",
            autostart="current",
            lifecycle="version changed",
            removal_readiness="action required",
        )
        return replace(snapshot, **overrides)

    def test_support_text_redacts_identifiers_and_truncates(self):
        from pearipherals_support import redact_support_text

        sensitive = (
            r"C:\Users\name\Desktop\pearipherals "
            r"/Users/name/Library/pearipherals "
            r"AA:BB:CC:DD:EE:FF "
            r"HID\VID_004C&PID_0265\7&SECRET "
            r"BTHENUM\DEV_AABBCCDDEEFF\8&SECRET "
            + "x" * 300
        )

        redacted = redact_support_text(sensitive)

        for secret in (
            "C:\\Users\\name",
            "/Users/name",
            "AA:BB:CC:DD:EE:FF",
            "VID_004C",
            "DEV_AABBCCDDEEFF",
        ):
            with self.subTest(secret=secret):
                self.assertNotIn(secret, redacted)
        self.assertIn("[redacted path]", redacted)
        self.assertIn("[redacted address]", redacted)
        self.assertIn("[redacted device id]", redacted)
        self.assertLessEqual(len(redacted), 160)
        self.assertTrue(redacted.endswith("..."))

    def test_support_text_redacts_every_absolute_path_shape(self):
        from pearipherals_support import redact_support_text

        cases = (
            (r"C:\Users\name\Desktop", "name"),
            (r"D:\Portable\Pearipherals\app.exe", "Portable"),
            (r"d:/portable/pearipherals/app.exe", "portable"),
            (r"Z:\Secret Folder\thing", "Secret Folder"),
            (r"\\server\share\Pearipherals", "server"),
            (r"\\?\C:\Users\name\app.exe", "name"),
            (r"\\?\Volume{9f8a}\data", "Volume"),
            (r"\\.\PhysicalDrive0", "PhysicalDrive0"),
            (r"\\.\HID#VID_004C", "VID_004C"),
            ("/Users/name/Library", "name"),
            ("/home/name/.config/pearipherals", "name"),
            ("/HOME/Name/private", "Name"),
        )

        for value, secret in cases:
            with self.subTest(value=value):
                redacted = redact_support_text(f"failed on {value} while starting")

                self.assertNotIn(secret, redacted)
                self.assertIn("[redacted path]", redacted)

    def test_support_text_redacts_device_identifiers_in_any_case(self):
        from pearipherals_support import redact_support_text

        cases = (
            (r"HID\VID_004C&PID_0265\7&SECRET", "VID_004C"),
            (r"hid\vid_004c&pid_0265\7&secret", "vid_004c"),
            (r"Hid#Vid_004C&Pid_0265#7&secret", "Vid_004C"),
            (r"BTHENUM\DEV_AABBCCDDEEFF\8&SECRET", "DEV_AABBCCDDEEFF"),
            (r"bthenum\dev_aabbccddeeff\8&secret", "dev_aabbccddeeff"),
            (r"BthEnum#Dev_AABBCCDDEEFF#8&secret", "Dev_AABBCCDDEEFF"),
        )

        for value, secret in cases:
            with self.subTest(value=value):
                redacted = redact_support_text(f"device {value} disappeared")

                self.assertNotIn(secret, redacted)
                self.assertIn("[redacted device id]", redacted)

    def test_snapshot_rejects_non_whitelisted_enum_values(self):
        enum_fields = (
            "mode",
            "config_state",
            "keyboard_battery",
            "trackpad_battery",
            "raw_input_state",
            "driver_state",
            "gesture_mode",
            "gesture_readiness",
            "touchpad_settings",
            "scroll_direction",
            "autostart",
            "lifecycle",
            "removal_readiness",
        )

        for field in enum_fields:
            with self.subTest(field=field):
                with self.assertRaises(ValueError):
                    self._snapshot(**{field: r"C:\Users\name\private"})

    def test_payload_redacts_every_free_text_field(self):
        from pearipherals_support import diagnostics_payload
        from pearipherals_version import BuildIdentity

        snapshot = self._snapshot(
            identity=BuildIdentity("1.2.0", "git:" + "c" * 40),
            windows_version=r"Windows C:\Users\name\build /Users/name/private",
            windows_build=r"HID\VID_004C&PID_0265\SECRET",
            architecture="adapter AA:BB:CC:DD:EE:FF " + "z" * 300,
        )

        payload = diagnostics_payload(
            snapshot,
            datetime(2026, 8, 21, 22, 15, 30, tzinfo=timezone.utc),
        )
        serialized = json.dumps(payload)

        for secret in (
            "C:\\\\Users\\\\name",
            "/Users/name",
            "VID_004C",
            "AA:BB:CC:DD:EE:FF",
        ):
            with self.subTest(secret=secret):
                self.assertNotIn(secret, serialized)
        for value in payload["windows"].values():
            self.assertLessEqual(len(value), 160)

    def test_payload_uses_fixed_whitelisted_schema(self):
        from pearipherals_support import diagnostics_payload

        payload = diagnostics_payload(
            self._snapshot(),
            datetime(2026, 8, 21, 22, 15, 30, tzinfo=timezone.utc),
        )

        self.assertEqual(
            {
                "schema_version": 1,
                "generated_at_utc": "2026-08-21T22:15:30Z",
                "privacy_notice": (
                    "Whitelisted product state only; excludes local paths, device "
                    "identifiers, raw configuration, registry data, logs, and network "
                    "destinations. Pearipherals does not upload this report."
                ),
                "product": {
                    "name": "Pearipherals",
                    "version": "1.2.0",
                    "build_id": "git:" + "b" * 40,
                    "mode": "frozen",
                },
                "windows": {
                    "version": "Windows 11 Pro",
                    "build": "26100.4946",
                    "architecture": "AMD64",
                },
                "state": {
                    "config": "loaded",
                    "keyboard_battery": "available",
                    "trackpad_battery": "unavailable",
                    "driver": "service registration detected",
                    "raw_input": "listener registered",
                    "gesture_mode": "swipes",
                    "gesture_readiness": "ready",
                    "touchpad_settings": "applied",
                    "scroll_direction": "classic",
                    "autostart": "current",
                    "lifecycle": "version changed",
                    "removal_readiness": "action required",
                },
            },
            payload,
        )


class ConservativeWordingTests(unittest.TestCase):
    def test_driver_state_reports_only_service_registration_not_installation(self):
        from pearipherals_support import SUPPORT_ENUMS

        self.assertEqual(
            frozenset(("service registration detected", "not detected", "unavailable")),
            SUPPORT_ENUMS["driver_state"],
        )

    def test_raw_input_state_reports_listener_registration_not_listening(self):
        from pearipherals_support import SUPPORT_ENUMS

        self.assertEqual(
            frozenset(("not started", "starting", "listener registered", "unavailable")),
            SUPPORT_ENUMS["raw_input_state"],
        )

    def test_no_support_wording_implies_presence_health_or_binding(self):
        from pearipherals_support import (
            PRIVACY_NOTICE,
            SUPPORT_ENUMS,
            diagnostics_payload,
            format_about,
        )

        snapshot = DiagnosticsPayloadTests._snapshot(
            driver_state="service registration detected",
            raw_input_state="listener registered",
        )
        wording = " ".join((
            format_about(snapshot),
            json.dumps(diagnostics_payload(
                snapshot, datetime(2026, 8, 21, 22, 15, 30, tzinfo=timezone.utc)
            )),
            PRIVACY_NOTICE,
            " ".join(sorted(
                value for values in SUPPORT_ENUMS.values() for value in values
            )),
        )).casefold()

        overclaims = (
            "installed",
            "driver missing",
            "device present",
            "device connected",
            "device detected",
            "driver healthy",
            "driver is working",
            "listening",
            "bound",
            "attached to",
            "successfully",
        )
        for phrase in overclaims:
            with self.subTest(phrase=phrase):
                self.assertNotIn(phrase, wording)

    def test_touchpad_settings_enum_covers_every_manager_status(self):
        from pearipherals_core import TouchpadSettingsManager
        from pearipherals_support import SUPPORT_ENUMS

        manager_statuses = {
            "applied", "original settings", "restore incomplete", "needs apply"
        }

        self.assertTrue(
            manager_statuses <= SUPPORT_ENUMS["touchpad_settings"],
            "every TouchpadSettingsManager.status_text result must be representable",
        )
        self.assertIn("unavailable", SUPPORT_ENUMS["touchpad_settings"])
        self.assertTrue(hasattr(TouchpadSettingsManager, "status_text"))


class VersionObservationTests(unittest.TestCase):
    def test_first_observation_is_persisted_before_it_is_reported(self):
        from pearipherals_support import observe_version

        config = {"unknown_setting": "kept"}
        saves = []

        transition = observe_version(
            config,
            "1.2.0",
            lambda: saves.append(dict(config)),
        )

        self.assertEqual("first observed", transition)
        self.assertEqual("1.2.0", config["current_version"])
        self.assertIsNone(config["previous_version"])
        self.assertEqual("kept", config["unknown_setting"])
        self.assertEqual([dict(config)], saves)

    def test_version_change_atomically_records_previous_and_current(self):
        from pearipherals_support import observe_version

        config = {
            "current_version": "1.1.0",
            "previous_version": "1.0.0",
            "unknown_setting": 17,
        }
        saves = []

        transition = observe_version(
            config,
            "1.2.0",
            lambda: saves.append(dict(config)),
        )

        self.assertEqual("version changed", transition)
        self.assertEqual("1.1.0", config["previous_version"])
        self.assertEqual("1.2.0", config["current_version"])
        self.assertEqual(17, config["unknown_setting"])
        self.assertEqual([dict(config)], saves)

    def test_unchanged_version_performs_no_save(self):
        from pearipherals_support import observe_version

        config = {
            "current_version": "1.2.0",
            "previous_version": "1.1.0",
        }
        saves = []

        transition = observe_version(config, "1.2.0", lambda: saves.append(True))

        self.assertEqual("unchanged", transition)
        self.assertEqual([], saves)
        self.assertEqual(
            {"current_version": "1.2.0", "previous_version": "1.1.0"},
            config,
        )

    def test_failed_persistence_restores_prior_state_and_emits_no_transition(self):
        from pearipherals_support import observe_version

        config = {
            "current_version": "1.1.0",
            "previous_version": None,
            "unknown_setting": {"nested": [1, 2, 3]},
        }
        before = copy.deepcopy(config)

        with self.assertRaisesRegex(OSError, "disk full"):
            observe_version(
                config,
                "1.2.0",
                lambda: (_ for _ in ()).throw(OSError("disk full")),
            )

        self.assertEqual(before, config)


class RemovalReadinessTests(unittest.TestCase):
    def test_ready_requires_every_persistent_and_custom_state_to_be_clear(self):
        from pearipherals_support import classify_removal_readiness

        self.assertEqual(
            "ready",
            classify_removal_readiness("off", "absent", False, "off", False, {}),
        )
        blocked = (
            ("current", "absent", False, "off", False, {}),
            ("off", "present", False, "off", False, {}),
            ("off", "absent", True, "off", False, {}),
            ("off", "absent", False, "swipes", False, {}),
            ("off", "absent", False, "off", True, {}),
            ("off", "absent", False, "off", False, {"TapAndDrag": 0}),
        )
        for state in blocked:
            with self.subTest(state=state):
                self.assertEqual(
                    "action required", classify_removal_readiness(*state)
                )


class RemovalOrchestrationTests(unittest.TestCase):
    @staticmethod
    def _steps(recorder, failing=()):
        def make(name):
            def step():
                recorder.append(name)
                if name in failing:
                    raise OSError(rf"denied writing D:\Portable\{name}.json")
            return step

        from pearipherals_support import REMOVAL_STEP_ORDER

        return {name: make(name) for name in REMOVAL_STEP_ORDER}

    def test_every_step_runs_in_a_fail_open_order_and_reports_success(self):
        from pearipherals_support import REMOVAL_STEP_ORDER, perform_removal

        ran = []

        outcome = perform_removal(self._steps(ran))

        self.assertEqual(list(REMOVAL_STEP_ORDER), ran)
        self.assertTrue(outcome.succeeded)
        self.assertEqual(REMOVAL_STEP_ORDER, outcome.completed)
        self.assertEqual((), outcome.failed)

    def test_settings_are_persisted_before_runtime_input_is_released(self):
        from pearipherals_support import REMOVAL_STEP_ORDER

        self.assertLess(
            REMOVAL_STEP_ORDER.index("settings"),
            REMOVAL_STEP_ORDER.index("input_release"),
        )

    def test_an_early_failure_never_skips_the_remaining_independent_cleanup(self):
        from pearipherals_support import REMOVAL_STEP_ORDER, perform_removal

        ran = []

        outcome = perform_removal(self._steps(ran, failing=("settings",)))

        self.assertEqual(list(REMOVAL_STEP_ORDER), ran)
        self.assertFalse(outcome.succeeded)
        self.assertEqual(("settings",), outcome.failed)
        self.assertNotIn("settings", outcome.completed)

    def test_no_partial_run_is_ever_reported_as_success(self):
        from pearipherals_support import REMOVAL_STEP_ORDER, perform_removal

        for name in REMOVAL_STEP_ORDER:
            with self.subTest(failing=name):
                outcome = perform_removal(self._steps([], failing=(name,)))

                self.assertFalse(outcome.succeeded)
                self.assertIn(name, outcome.failed)

    def test_summary_names_only_completed_work_and_leaks_no_failure_text(self):
        from pearipherals_support import perform_removal, format_removal_summary

        outcome = perform_removal(self._steps([], failing=("autostart",)))
        summary = format_removal_summary(outcome)

        self.assertIn("could not be completed", summary)
        for leak in ("Portable", "denied", "OSError", "Traceback", ":\\"):
            with self.subTest(leak=leak):
                self.assertNotIn(leak, summary)

    def test_a_complete_summary_states_what_actually_changed(self):
        from pearipherals_support import perform_removal, format_removal_summary

        summary = format_removal_summary(perform_removal(self._steps([])))

        self.assertIn("Pearipherals is ready to be removed", summary)
        self.assertNotIn("could not be completed", summary)
        # It never deletes files and never quits by itself, so it must not
        # claim either. Directing the user to Quit themselves is fine.
        self.assertIn("Nothing was erased", summary)
        for forbidden in (
            "deleted your", "uninstalled", "removed the app",
            "has quit", "closing now", "will now close",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, summary.lower())


class AutostartClassificationTests(unittest.TestCase):
    def test_missing_command_is_off(self):
        from pearipherals_support import classify_autostart

        self.assertEqual("off", classify_autostart(None, '"C:\\Pearipherals.exe"'))

    def test_matching_command_is_current(self):
        from pearipherals_support import classify_autostart

        command = '"C:\\Program Files\\Pearipherals\\Pearipherals.exe"'
        self.assertEqual("current", classify_autostart(command, command))

    def test_windows_command_normalization_is_case_and_separator_insensitive(self):
        from pearipherals_support import classify_autostart

        registered = '  "c:/program files/pearipherals/pearipherals.exe"  '
        expected = '"C:\\Program Files\\Pearipherals\\Pearipherals.exe"'
        self.assertEqual("current", classify_autostart(registered, expected))

    def test_moved_command_is_stale_without_leaking_paths(self):
        from pearipherals_support import classify_autostart

        registered = '"C:\\Old Folder\\Pearipherals.exe"'
        expected = '"D:\\Portable\\Pearipherals.exe"'
        result = classify_autostart(registered, expected)

        self.assertEqual("stale", result)
        self.assertNotIn("Old Folder", result)
        self.assertNotIn("Portable", result)

    def test_non_string_registry_values_are_unavailable_never_a_crash(self):
        """A Run value written by anything else must not raise.

        winreg.QueryValueEx returns int for REG_DWORD, list for REG_MULTI_SZ
        and bytes for REG_BINARY. Treating those as absence would be a lie and
        raising would take the whole tray down, so they are uncertainty.
        """
        from pearipherals_support import classify_autostart

        expected = '"D:\\Portable\\Pearipherals.exe"'
        for value in (0, 1, ["a", "b"], b"\x00\x01", 3.5, object()):
            with self.subTest(value=type(value).__name__):
                self.assertEqual("unavailable", classify_autostart(value, expected))


class RedactionBoundaryTests(unittest.TestCase):
    def test_redaction_runs_before_any_length_bound(self):
        """Pre-bounding could sever a pattern and leak the surviving fragment."""
        from pearipherals_support import redact_support_text

        padding = ("D:\\Portable\\App " * 80)[:1265]
        result = redact_support_text(padding + " AA:BB:CC:DD:EE:FF")

        self.assertNotIn("AA:BB:CC:DD:EE", result)
        self.assertNotRegex(result, r"(?i)(?:[0-9a-f]{2}[:-]){2}[0-9a-f]{2}")

    def test_output_never_exceeds_the_requested_bound(self):
        from pearipherals_support import redact_support_text

        for max_length in range(0, 8):
            with self.subTest(max_length=max_length):
                result = redact_support_text("abcdefghij", max_length=max_length)
                self.assertLessEqual(len(result), max_length)


class RemovalReadinessInputTests(unittest.TestCase):
    @staticmethod
    def _ready_kwargs(**overrides):
        state = {
            "autostart": "off",
            "legacy_autostart": "absent",
            "mac_fkeys": False,
            "gesture_mode": "off",
            "settings_applied": False,
            "backup_entries": {},
        }
        state.update(overrides)
        return state

    def test_ready_requires_mac_fkeys_off_and_no_legacy_autostart(self):
        from pearipherals_support import classify_removal_readiness

        self.assertEqual(
            "ready", classify_removal_readiness(**self._ready_kwargs())
        )
        for blocking in (
            {"mac_fkeys": True},
            {"legacy_autostart": "present"},
            {"legacy_autostart": "unavailable"},
            {"autostart": "unavailable"},
            {"gesture_mode": "swipes"},
            {"settings_applied": True},
            {"backup_entries": {"TapAndDrag": 0}},
        ):
            with self.subTest(blocking=blocking):
                self.assertEqual(
                    "action required",
                    classify_removal_readiness(**self._ready_kwargs(**blocking)),
                )


if __name__ == "__main__":
    unittest.main()
