# Privacy Policy

Pearipherals does not collect, store, transmit, sell, or share personal data.

The application works locally on the user's Windows PC. It reads local input-device data, battery reports, display controls, configuration files, and Windows settings only to provide the features described in the README.

Pearipherals does not make background network requests or contact its maintainers automatically. The tray includes two **fixed GitHub support links** for documentation and issue reporting; Pearipherals asks Windows to open one in your default browser **only when you click** that menu action. Any resulting browser/GitHub traffic follows those products' privacy practices. Windows, device drivers, GitHub, your browser, and any software-distribution service used to download Pearipherals are outside this application's control.

Crash details are written only to `pearipherals.err.log` next to the executable. They are never uploaded automatically. A user may choose to share that file when requesting support.

## Screenshots

Pearipherals opens the **Windows Snipping Tool** **selection overlay** **only when you press F6** without a modifier while its Mac F-row is enabled. Pearipherals does not capture the screen, read the selected image pixels, write an image file, or place image data on the clipboard. Modifier+F6 passes the original key through and opens nothing.

After you select a region, **Windows handles** the selected image, including the **clipboard** and whether a file is written under the Snipping Tool **auto-save setting**. That Windows-owned behavior and storage remain under your control. The selected image is **never uploaded by Pearipherals**, is **not included in diagnostics**, and is never attached to a support link or report. Pearipherals does not open the selection overlay at startup, in the background, on a schedule, or after a crash.

## Diagnostic reports

Pearipherals can write a diagnostic report, `pearipherals-diagnostics.json`, next to the executable. This happens **only when you ask** for it with the tray menu's *Save a diagnostic report* action. No report is generated in the background, at startup, on a schedule, or on a crash.

The report is a small **plain JSON** file that you can open and **review** in any text editor before deciding whether to share it. Pearipherals will **never transmit** it: there is **no automatic diagnostic upload**, analytics endpoint, or background update check. The fixed GitHub support links described above are separate user-clicked browser actions and never attach or transmit the report.

The report contains a schema version, a **UTC generation timestamp**, a fixed privacy notice, the product name, and a fixed whitelist of product-level state: the product version and build identity, whether the build is frozen or source, the Windows version/build/architecture, and fixed status labels for configuration, battery paths, driver-service registration, Raw Input registration, gesture mode and readiness, touchpad settings, scroll direction, autostart, version-change observation, and removal readiness.

The report deliberately excludes, by construction:

- your Windows **username** or any account name;
- any **full local path**, drive path, UNC path, device path, or the location of the application, its configuration, or its logs;
- any **Bluetooth address**, MAC address, HID instance path, or other device identifier;
- raw configuration contents, registry exports, error-log contents, arbitrary exception text, and raw HID reports.

Sharing the report is entirely your decision, and you can delete it at any time.

Last updated: 2026-08-22.
