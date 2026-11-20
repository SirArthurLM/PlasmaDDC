# Troubleshooting

This document lists common PlasmaDDC and DDC/CI problems.

## 1. Check the basics

Before debugging the application, check that the monitor itself is ready:

- The monitor is external.
- DDC/CI is enabled in the monitor OSD menu.
- The monitor is connected through HDMI, DisplayPort, DVI or VGA.
- The cable or adapter supports DDC/CI.
- The system exposes `/dev/i2c-*`.

Run:

```bash
ls -l /dev/i2c-*
```

If no `/dev/i2c-*` devices exist, try:

```bash
sudo modprobe i2c-dev
ls -l /dev/i2c-*
```

## 2. `ddcutil detect` does not detect the monitor

Try:

```bash
sudo ddcutil detect --verbose
```

Possible causes:

- DDC/CI is disabled in the monitor OSD.
- The cable does not pass DDC/CI correctly.
- A dock, KVM, adapter or hub is interfering.
- The graphics driver does not expose the I2C bus.
- The monitor has limited or broken DDC/CI support.

Try another cable or direct connection if possible.

## 3. `ddcutil detect` works with sudo but not without sudo

This is usually a permissions problem.

Check:

```bash
groups
ls -l /dev/i2c-*
getfacl /dev/i2c-* 2>/dev/null | head -n 80
```

Your user should either:

- belong to the `i2c` group, or
- have an ACL entry granting access to the relevant `/dev/i2c-*` devices

A typical group-based setup looks like:

```text
crw-rw---- 1 root i2c ... /dev/i2c-1
```

and:

```bash
groups
```

should include:

```text
i2c
```

If your user was just added to the `i2c` group, log out and log back in.

## 4. Fix I2C permissions manually

Create the group if needed:

```bash
sudo groupadd -f i2c
```

Add your user to it:

```bash
sudo usermod -aG i2c "$USER"
```

Create the udev rule:

```bash
echo 'KERNEL=="i2c-[0-9]*", GROUP="i2c", MODE="0660"' | sudo tee /etc/udev/rules.d/60-plasmaddc-i2c.rules
```

Reload udev:

```bash
sudo udevadm control --reload-rules
sudo udevadm trigger
```

Log out and log back in.

Then test:

```bash
groups
ddcutil detect
```

## 5. PlasmaDDC opens but controls are missing

Not all monitors support all VCP codes.

Run:

```bash
ddcutil capabilities
ddcutil getvcp all
```

If a control does not appear there or returns an error, the monitor may not expose that setting through DDC/CI.

Examples:

```bash
ddcutil getvcp 10   # brightness
ddcutil getvcp 12   # contrast
ddcutil getvcp 62   # volume
ddcutil getvcp 60   # input source
```

## 6. `monitorcontrol` fails but `ddcutil` works

This can happen.

PlasmaDDC uses `ddcutil` as the main backend. `monitorcontrol` is only auxiliary.

Some monitors return DDC/CI responses that `monitorcontrol` does not interpret correctly, while `ddcutil` still works.

If this happens, it is usually not fatal.

Test:

```bash
source .venv/bin/activate
python backend.py
python plasmaddc_cli.py profile
```

If the `ddcutil` values are correct, PlasmaDDC should work.

## 7. Python says PySide6 is missing

Activate the virtual environment:

```bash
source .venv/bin/activate
```

Then install dependencies:

```bash
pip install -r requirements.txt
```

Test:

```bash
python -c "from PySide6.QtWidgets import QApplication; print('PySide6 OK')"
```

## 8. The terminal prompt shows `(.venv)`

That is normal.

It means the Python virtual environment is active.

To leave it:

```bash
deactivate
```

When developing or testing PlasmaDDC, it is normal to activate it again:

```bash
source .venv/bin/activate
```

## 9. The desktop launcher does not appear

Try:

```bash
ls -l ~/.local/share/applications/plasmaddc.desktop
```

If the file exists, refresh KDE's application cache:

```bash
kbuildsycoca6
```

If using another desktop environment, log out and log back in.

You can always run PlasmaDDC manually:

```bash
./run_plasmaddc.sh
```

## 10. Changing input source removed the image

This can happen if you switch to an input without signal.

Use the monitor's physical buttons and OSD menu to switch back.

The graphical application asks for confirmation before changing the input source for this reason.

## 11. RGB controls do not work

Some monitors only allow RGB gain changes when the color mode is set to a custom/user mode.

Try setting the monitor's color mode in the OSD to something like:

```text
User
Custom
Personalizado
Usuario
```

Then test:

```bash
ddcutil getvcp 16
ddcutil getvcp 18
ddcutil getvcp 1A
```

## 12. Brightness or contrast values seem ignored

Some monitors expose a VCP code but ignore changes depending on the current picture mode.

Try changing the monitor mode in the OSD:

- Standard
- User
- Custom
- Eco off
- HDR off
- Dynamic contrast off

Then retry:

```bash
ddcutil setvcp 10 50
ddcutil setvcp 12 50
```

## 13. Wayland warnings in terminal

You may see warnings such as:

```text
qt.qpa.wayland: Wayland does not support QWindow::requestActivate()
```

These are usually Qt/Wayland warnings and do not necessarily mean DDC/CI is broken.

If the application opens and controls the monitor, they can normally be ignored.

## 14. Useful diagnostic bundle

When reporting a problem, collect:

```bash
groups
ls -l /dev/i2c-*
getfacl /dev/i2c-* 2>/dev/null | head -n 120
ddcutil detect
ddcutil capabilities
ddcutil getvcp all
source .venv/bin/activate
python backend.py
python plasmaddc_cli.py profile
```

## DDC/CI diagnostics show parsing errors or a partial result

The **Diagnostics** page can run `capabilities` and `getvcp all` only after
monitor detection and an additional confirmation. They are intentionally
unavailable in `--demo`. A capability string is supplied by monitor firmware;
`ddcutil` may report invalid VCP values, an unparseable response, or even
inconsistent MCCS versions. Such warnings do not necessarily indicate an
application defect.

For `getvcp all`, an unsupported or nonresponding individual VCP can cause a
nonzero exit code despite many successful readings. PlasmaDDC retains that
partial result and labels it as potentially incomplete. An invalid UTF-8 byte
is escaped in the displayed output rather than crashing the GUI.

**GPU-driver safety:** Real DDC/CI access has previously coincided with an
`amdgpu` hang on an AMD/DisplayPort configuration. Even one request might
trigger a faulty driver; moving commands off the GUI thread is not a hardware
safety guarantee. If your system has a history of DDC/CI-related GPU freezes,
avoid real diagnostics and use `./run_plasmaddc.sh --demo` for GUI tests.
Do not run repeated/bulk scans solely to investigate a GUI presentation issue.
