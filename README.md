# PlasmaDDC

PlasmaDDC is a Linux desktop application for controlling external monitors through DDC/CI.

It provides a graphical interface built with PySide6 and a command-line tool for reading and changing common monitor settings using `ddcutil`.

The project is designed especially for KDE Plasma users, but it should also work on other Linux desktop environments as long as DDC/CI, `ddcutil`, Python and the required permissions are available.

## Features

- Detect external monitors
- Read monitor DDC/CI capabilities
- Control brightness
- Control contrast
- Control RGB gain
- Control monitor audio volume
- Change color preset / color temperature
- Change input source, such as HDMI or DisplayPort
- Show raw `ddcutil capabilities`
- Show raw `ddcutil getvcp all`
- Provide a CLI for testing and scripting
- Provide a safe interactive installer
- Provide a conservative uninstaller
- Avoid running the graphical application as root
- Select English, Spanish, or your system language in Preferences
- Read Picture, Color, Audio, and Input controls by section, on demand
- Use simulated monitors in `--demo` mode, without DDC/CI access
- Run advanced diagnostics only after explicit confirmation

## Current status

**PlasmaDDC 1.1.0** adds opt-in, serialized DDC/CI operations, section reads,
a self-contained demo mode, bilingual preferences, and improved diagnostics.
See [CHANGELOG.md](CHANGELOG.md) for release details and credits.

It uses `ddcutil` as its primary backend, `monitorcontrol` as an auxiliary
backend, and PySide6 for its graphical interface. Development and initial
hardware validation took place on Kubuntu / KDE Plasma / Wayland. Monitor and
GPU-driver behavior varies, so success on one system does not establish general
hardware compatibility.

## Hardware access and driver safety

The GUI uses conservative defaults because a severe `amdgpu` GPU/desktop hang
was observed on an AMD/DisplayPort configuration with the original startup
behavior. The underlying driver issue has **not** been proven fixed.

- Starting in real mode **does not automatically detect or query** monitors.
- Before the first real DDC/CI operation in a session, the GUI asks for consent.
- The **Detect monitors** action identifies a monitor but does not bulk-read its
  settings; use individual **Read** buttons or **Read this section** to load values.
- Real operations run on a Qt background worker, **one at a time**. Section reads
  are sequential and require confirmation for multiple requests.
- `capabilities` and `getvcp all` are available under **Diagnostics**, but only
  on demand with explicit confirmation. They can issue many DDC/CI requests.
- Language changes reuse cached values and never trigger hardware reads.

**Warning:** A background thread keeps a slow operation from directly blocking
Qt's GUI thread; it **cannot prevent** a kernel graphics-driver hang. A single
DDC/CI command might still freeze a susceptible system. Use `--demo` instead
if you cannot safely test real DDC/CI operations. These GUI safeguards do not
change the independent CLI's behavior.

## Demo mode (safe simulated monitors)

To test the GUI without querying actual DDC/CI hardware, use the new **demo mode**:

```bash
./run_plasmaddc.sh --demo
```

Demo mode creates two entirely simulated monitors and immediately fills in
brightness, contrast, RGB gains, volume, color preset, and input selection.
All **Read**, **Apply**, and **Change input** actions operate exclusively on
in-memory demo values. A visible DEMO banner distinguishes the simulated window
from real hardware mode. The demo backend **never calls ddcutil, monitorcontrol,
or `/dev/i2c-*`**, and no real monitor is detected or changed. Simulation resets
when the app exits; demo-language preferences use separate Qt settings from the
real application's preferences.

The main window still uses Qt and the computer's graphics stack to draw itself;
`--demo` only guarantees that PlasmaDDC will not perform real DDC/CI access.

For automated offline checks (with PySide6 installed):

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m unittest discover -s tests -p 'test_*.py' -v
```

**Do not use normal hardware mode on a system with an unresolved GPU/DDC/CI
freeze.** Demo mode can validate GUI behavior, not real driver stability.

## Screenshots

Screenshots will be added later.

## Requirements

General requirements:

- Linux
- External monitor with DDC/CI support
- DDC/CI enabled in the monitor OSD menu
- `ddcutil`
- Python 3
- PySide6
- monitorcontrol
- Access to `/dev/i2c-*`

On Ubuntu, Kubuntu, Debian and related distributions, the installer can help install and configure most requirements automatically.

## Installation

Clone or download this repository, then run:

```bash
chmod +x install_plasmaddc.sh
./install_plasmaddc.sh
```

Do not run the graphical application as root.

The installer may ask for `sudo` only when it needs to install system packages or configure I2C permissions.

If the installer adds your user to the `i2c` group, you may need to log out and log back in before DDC/CI access works correctly.

More detailed instructions are available in:

```text
docs/INSTALL.md
```

## Run the graphical application

After installation:

```bash
./run_plasmaddc.sh
```

If the desktop launcher was created, you can also search for:

```text
PlasmaDDC
```

in the application launcher.

## Language preferences

Choose **Preferences → Language…** to select **System default**, **English**, or
**Español**. Changes take effect immediately and are remembered between launches.
**System default** follows the desktop locale: Spanish locales use Spanish;
English, unsupported, or unavailable locales use English.

The preference is stored in Qt's per-user settings (`PlasmaDDC/PlasmaDDC`, key
`language`). On Linux this is normally `~/.config/PlasmaDDC/PlasmaDDC.conf`.
Language changes refresh the interface using previously cached values, without
accessing the monitor. Diagnostic output originates from `ddcutil`; invalid
UTF-8 bytes are escaped so that the result can be displayed instead of crashing.

English messages are the fallback source text. The Spanish catalog lives in
`translations/es.json`; translated messages must preserve their format placeholders.
The standalone CLI keeps its existing commands and output format.

To run the language and GUI checks without a connected monitor:

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m unittest discover -s tests -v
```

## CLI usage

Activate the virtual environment first:

```bash
source .venv/bin/activate
```

Useful examples:

```bash
python plasmaddc_cli.py list
python plasmaddc_cli.py profile
python plasmaddc_cli.py get brightness
python plasmaddc_cli.py get contrast
python plasmaddc_cli.py get volume
python plasmaddc_cli.py get rgb
python plasmaddc_cli.py get input
python plasmaddc_cli.py get color
python plasmaddc_cli.py capabilities
python plasmaddc_cli.py getvcp-all
```

Examples that change monitor settings:

```bash
python plasmaddc_cli.py set brightness 80
python plasmaddc_cli.py set contrast 60
python plasmaddc_cli.py set volume 80
python plasmaddc_cli.py set red 50
python plasmaddc_cli.py set green 50
python plasmaddc_cli.py set blue 50
```

Changing the monitor input source is supported, but should be used carefully:

```bash
python plasmaddc_cli.py inputs
python plasmaddc_cli.py set input HDMI1
```

If you switch to an input without signal, you may need to use the monitor's physical buttons to switch back.

## Uninstall

Run:

```bash
chmod +x uninstall_plasmaddc.sh
./uninstall_plasmaddc.sh
```

The uninstaller is conservative and asks before removing files or changing system configuration.

More details are available in:

```text
docs/UNINSTALL.md
```

## Safety notes

PlasmaDDC should not be run as root.

The installer may configure this udev rule:

```text
/etc/udev/rules.d/60-plasmaddc-i2c.rules
```

This rule allows users in the `i2c` group to access `/dev/i2c-*`.

This is safer than launching the graphical application with administrator privileges.

## Backend design

PlasmaDDC uses a hybrid backend:

- `ddcutil` is the main backend
- `monitorcontrol` is auxiliary

This design was chosen because some monitors respond correctly to `ddcutil` but not to `monitorcontrol`.

The graphical interface does not need to know which low-level backend is being used. It talks to `backend.py`, which handles the details.

## Safe, on-demand section reads and diagnostics

After detecting a monitor, click **Read picture controls** (2 sequential reads),
**Read color controls** (4 sequential reads), or **Read audio controls** (1 read)
to load values for that section. **Read this section** in the toolbar/menu works
on Picture, Color, Audio, or Input. No values are queried automatically by
switching pages, changing language, or opening the app. A confirmation is
required for multi-read operations on real hardware. A single background job
runs the reads one at a time, with a short delay between real reads.

The color preset menu shows *generic MCCS choices*, not a verified list for
any particular monitor. Applying a real preset requires confirmation; the
monitor may reject or apply it without verifying. The RGB controls may require
User/Custom color mode in the physical monitor OSD.

Advanced **capabilities** and **getvcp all** diagnostics are available only
after monitor detection and explicit confirmation. They may perform many
DDC/CI requests and **can still trigger a kernel graphics-driver hang** even
though the GUI uses a background thread. They are disabled in `--demo`.
Diagnostics show useful partial output even when `ddcutil` returns a nonzero
exit code, while clearly marking that the result could be incomplete. Parsing
warnings in a capabilities response are produced by `ddcutil` and do not, by
themselves, indicate a PlasmaDDC failure.

## Known limitations

Not all monitors support the same VCP codes.

Some monitors may support brightness and contrast but not volume, RGB gain,
input switching, or color presets. Generic preset names are **not** a supported
values list for the connected monitor. A failed write verification does not
prove that the monitor rejected the setting; review its OSD/readback before
repeating a command. Some monitor capabilities strings are incomplete or
malformed, and the reported MCCS version may not match VCP `0xDF`.

Some gaming features such as game mode, overdrive, FreeSync / Adaptive-Sync, HDR modes, dynamic contrast or crosshair overlays may be proprietary and may not be exposed through standard DDC/CI.

The input source control should be used with care because switching to an inactive input may temporarily remove the image.

## Useful diagnostic commands

```bash
ddcutil detect
ddcutil capabilities
ddcutil getvcp all
ddcutil getvcp known
ddcutil getvcp scan
```

For permissions:

```bash
groups
ls -l /dev/i2c-*
```

## Project structure

```text
PlasmaDDC/
├── app.py
├── backend.py
├── demo_backend.py
├── i18n.py
├── plasmaddc_cli.py
├── install_plasmaddc.sh
├── uninstall_plasmaddc.sh
├── run_plasmaddc.sh
├── requirements.txt
├── pyproject.toml
├── LICENSE
├── README.md
├── CHANGELOG.md
├── translations/
├── tests/
└── docs/
```

## Contributors

PlasmaDDC is maintained by [SirArthurLM](https://github.com/SirArthurLM).
Thanks to [Marcel Vojtkovszky](https://github.com/mvojtkovszky) for the
English/Spanish language preferences and persistent language selection
contributed through pull request #1.

## License

PlasmaDDC is released under the MIT License.
