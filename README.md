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

## Current status

PlasmaDDC 1.0 is a working first version.

It currently uses:

- `ddcutil` as the main backend
- `monitorcontrol` as an auxiliary backend
- PySide6 for the graphical interface

The application has been developed and tested mainly on Kubuntu / KDE Plasma / Wayland.

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
Language changes only refresh the interface and read monitor values; they do not
change monitor settings. Raw diagnostic output comes from `ddcutil` unchanged.

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

## Known limitations

Not all monitors support the same VCP codes.

Some monitors may support brightness and contrast but not volume, RGB gain, input switching, or color presets.

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
├── plasmaddc_cli.py
├── install_plasmaddc.sh
├── uninstall_plasmaddc.sh
├── run_plasmaddc.sh
├── requirements.txt
├── pyproject.toml
├── LICENSE
├── README.md
├── assets/
└── docs/
```

## License

PlasmaDDC is released under the MIT License.
