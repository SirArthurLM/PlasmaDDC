# Installation

This document explains how to prepare a Linux system and install PlasmaDDC.

PlasmaDDC controls external monitors through DDC/CI. It uses `ddcutil` as the main backend and Python/PySide6 for the graphical interface.

## 1. Physical requirements

Before installing anything, check:

- The monitor is external.
- The monitor supports DDC/CI.
- DDC/CI is enabled in the monitor OSD menu.
- The monitor is connected through HDMI, DisplayPort, DVI or VGA.
- The system exposes I2C devices as `/dev/i2c-*`.

Internal laptop panels usually do not use DDC/CI in the same way as external monitors.

## 2. Quick installation (virtual environment)

The interactive installer sets up a private `.venv` and a desktop launcher.
For the smaller APT-based installation, use section 4A instead.

From the project directory:

```bash
chmod +x install_plasmaddc.sh
./install_plasmaddc.sh
```

Do not run the installer with `sudo`.

The installer will ask for `sudo` only when it needs to install system packages or configure system permissions.

## 3. What the installer does

The installer is interactive and conservative.

It can:

- detect the Linux package manager
- install required system packages
- check `/dev/i2c-*`
- test `ddcutil detect`
- configure the `i2c` group
- create a udev rule for `/dev/i2c-*`
- create a Python virtual environment
- install Python dependencies
- create a desktop launcher
- create an installation state file for safer uninstall

It asks before making important changes.

## 4. Manual installation on Ubuntu / Kubuntu / Debian

Install system packages:

```bash
sudo apt update
sudo apt install ddcutil ddcui i2c-tools python3-pip python3-venv
```

`ddcui` is optional, but useful for testing DDC/CI with an existing graphical interface.

### 4A. Lightweight APT installation (Ubuntu / Kubuntu 26.04)

This alternative was tested on **Kubuntu 26.04**. It uses the system Python
and distro-provided PySide6/Qt packages instead of creating a private
`.venv`. It was substantially smaller on the tested system, but space savings
vary and package names/versions differ on other releases.

1. Clone or download PlasmaDDC and enter the project directory.
2. Install the system packages:

   ```bash
   sudo apt update
   sudo apt install ddcutil i2c-tools python3-pyside6.qtwidgets
   ```

   The Widgets package also installs its required QtCore/QtGui bindings.
   `monitorcontrol` is **optional**, and is needed only to use that auxiliary
   Python backend; the default `ddcutil` backend needs no `monitorcontrol`
   package. Check APT package availability on other Ubuntu/Debian versions.

3. Configure I2C permissions as described in section 5 below (unless already
   configured). **Never run PlasmaDDC as root.**
4. Verify PySide6 and start the hardware-isolated demonstration:

   ```bash
   /usr/bin/python3 -c 'from PySide6.QtWidgets import QApplication; print("PySide6 OK")'
   /usr/bin/python3 app.py --demo
   ```

5. When ready to access hardware, close the demo and run:

   ```bash
   /usr/bin/python3 app.py
   ```

   The GUI does not contact a real monitor at startup. Use **Detect monitors**
   and explicitly consent before accessing hardware. If a GPU/driver hang has
   occurred on this machine, avoid testing real DDC/CI until you understand
   the risk; `--demo` does not access monitor hardware.

**Important:** the current `install_plasmaddc.sh` installer creates `.venv`,
and the repository's `run_plasmaddc.sh` requires `.venv/bin/python`. **Do not
run those scripts for this APT-only method**; use `/usr/bin/python3 app.py`
instead.

#### Optional KDE Plasma application-menu shortcut

If you want an entry in the application launcher, from the project directory:

```bash
APP_DIR="$(pwd -P)"
mkdir -p "$HOME/.local/share/applications"
cat > "$HOME/.local/share/applications/plasmaddc-system.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=PlasmaDDC (system Python)
Comment=Control external monitors using DDC/CI
Exec=/usr/bin/python3 "$APP_DIR/app.py"
Path=$APP_DIR
Terminal=false
Categories=Settings;Utility;
EOF
```

The shortcut uses the directory in which you ran the command. If you move
or rename that directory, update the desktop entry. The distinct filename
avoids overwriting the launcher created by the virtual-environment installer.
For an existing KDE launcher, edit its command to point to the system Python
and your actual `app.py` path instead of creating a duplicate. Do not launch
PlasmaDDC as root.

To run the automated tests with system PySide6 (no monitor access):

```bash
QT_QPA_PLATFORM=offscreen /usr/bin/python3 -m unittest discover -s tests -p 'test_*.py' -v
```

## 5. Configure I2C permissions

PlasmaDDC should not be run as root.

Create the `i2c` group if needed:

```bash
sudo groupadd -f i2c
```

Add your user to the group:

```bash
sudo usermod -aG i2c "$USER"
```

Create a udev rule:

```bash
echo 'KERNEL=="i2c-[0-9]*", GROUP="i2c", MODE="0660"' | sudo tee /etc/udev/rules.d/60-plasmaddc-i2c.rules
```

Reload udev:

```bash
sudo udevadm control --reload-rules
sudo udevadm trigger
```

Log out and log back in.

Then verify:

```bash
groups
ls -l /dev/i2c-*
ddcutil detect
```

Your user should belong to the `i2c` group, and `/dev/i2c-*` should usually belong to `root:i2c`.

## 6. Create the Python environment manually (non-APT method)

**Skip this section if you chose the lightweight APT method.**

From the project directory:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 7. Run PlasmaDDC

Graphical interface with the virtual-environment installation:

```bash
./run_plasmaddc.sh
```

With the lightweight APT installation, use `/usr/bin/python3 app.py` instead.

CLI with a virtual environment:

```bash
source .venv/bin/activate
python plasmaddc_cli.py list
python plasmaddc_cli.py profile
```

With the lightweight APT installation, use the system interpreter, e.g.
`/usr/bin/python3 plasmaddc_cli.py list`.

## 8. Test DDC/CI manually

These commands access actual monitor hardware and may be slow or unsafe
on systems affected by driver hangs. Run them only when necessary:

```bash
ddcutil detect
ddcutil capabilities
ddcutil getvcp all
```

Common VCP tests:

```bash
ddcutil getvcp 10   # brightness
ddcutil getvcp 12   # contrast
ddcutil getvcp 14   # color preset
ddcutil getvcp 16   # red gain
ddcutil getvcp 18   # green gain
ddcutil getvcp 1A   # blue gain
ddcutil getvcp 60   # input source
ddcutil getvcp 62   # audio volume
```

## 9. Fedora, Arch and openSUSE

The installer has basic support for `dnf`, `pacman` and `zypper`, but the project is currently developed and tested mainly on Kubuntu/Ubuntu/Debian.

Approximate package names:

### Fedora

```bash
sudo dnf install ddcutil ddcui i2c-tools python3 python3-pip
```

### Arch / Manjaro

```bash
sudo pacman -S ddcutil i2c-tools python python-pip
```

`ddcui` may require AUR.

### openSUSE

```bash
sudo zypper install ddcutil i2c-tools python3 python3-pip
```

After installing packages, configure I2C permissions as described above.

## 10. Installation success criteria

The system is ready when these work without `sudo`:

```bash
ddcutil detect
ddcutil capabilities
ddcutil getvcp 10
```

For the virtual-environment method, these work inside `.venv`:

```bash
source .venv/bin/activate
python plasmaddc_cli.py profile
python app.py --demo
```

For the lightweight APT method, the following works without `.venv`:

```bash
/usr/bin/python3 -c 'from PySide6.QtWidgets import QApplication; print("PySide6 OK")'
/usr/bin/python3 app.py --demo
```

Hardware-specific CLI commands and real-mode operations still require
working DDC/CI permissions and a compatible monitor.
