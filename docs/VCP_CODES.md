# Common VCP codes

PlasmaDDC controls monitors through DDC/CI using VCP codes.

VCP means **Virtual Control Panel**. Each VCP code represents a monitor control such as brightness, contrast, input source or audio volume.

Not every monitor supports every VCP code.

## Currently used by PlasmaDDC 1.1.0

| Code | Name | Used for |
|---|---|---|
| `0x10` | Brightness | Image brightness |
| `0x12` | Contrast | Image contrast |
| `0x14` | Select color preset | Color temperature / preset |
| `0x16` | Video gain: Red | Red RGB gain |
| `0x18` | Video gain: Green | Green RGB gain |
| `0x1A` | Video gain: Blue | Blue RGB gain |
| `0x60` | Input Source | HDMI / DisplayPort / VGA / DVI selection |
| `0x62` | Audio speaker volume | Monitor audio volume |

## Useful read commands

```bash
ddcutil getvcp 10
ddcutil getvcp 12
ddcutil getvcp 14
ddcutil getvcp 16
ddcutil getvcp 18
ddcutil getvcp 1A
ddcutil getvcp 60
ddcutil getvcp 62
```

## Useful write commands

Brightness:

```bash
ddcutil setvcp 10 70
```

Contrast:

```bash
ddcutil setvcp 12 60
```

RGB gain:

```bash
ddcutil setvcp 16 50
ddcutil setvcp 18 50
ddcutil setvcp 1A 50
```

Volume:

```bash
ddcutil setvcp 62 80
```

Input source:

```bash
ddcutil setvcp 60 0x11 --noverify
```

Input source changes should be used carefully. If you switch to an input without signal, you may need to use the monitor's physical buttons to switch back.

## Common input source values

| Value | Input |
|---|---|
| `0x01` | VGA-1 |
| `0x02` | VGA-2 |
| `0x03` | DVI-1 |
| `0x04` | DVI-2 |
| `0x0F` | DisplayPort-1 |
| `0x10` | DisplayPort-2 |
| `0x11` | HDMI-1 |
| `0x12` | HDMI-2 |

PlasmaDDC accepts aliases such as:

```text
HDMI1
HDMI2
DP1
DP2
```

## Common color preset values

| Value | Preset |
|---|---|
| `0x01` | sRGB |
| `0x02` | Display native |
| `0x03` | 4000 K |
| `0x04` | 5000 K |
| `0x05` | 6500 K |
| `0x06` | 7500 K |
| `0x07` | 8200 K |
| `0x08` | 9300 K |
| `0x09` | 10000 K |
| `0x0A` | 11500 K |
| `0x0B` | User 1 |
| `0x0C` | User 2 |
| `0x0D` | User 3 |

Not all monitors support all presets. PlasmaDDC offers these generic MCCS
choices but does not automatically filter them by monitor capabilities.
For example, `0x04` denotes 5000 K; if `0x04` is absent from a monitor's
`0x14(...)` capabilities list, it is not advertised as a supported preset.
Capabilities strings can be malformed or incomplete, so this is a useful
clue rather than a definitive guarantee.

## Extra VCP codes worth exploring

These are not exposed as regular controls in PlasmaDDC 1.1.0, but may be
useful for future versions.

| Code | Possible use |
|---|---|
| `0x20` | Horizontal position |
| `0x22` | Horizontal size |
| `0x30` | Vertical position |
| `0x32` | Vertical size |
| `0x3E` | Clock phase |
| `0x6C` | Video black level: Red |
| `0x6E` | Video black level: Green |
| `0x70` | Video black level: Blue |
| `0x8D` | Audio mute / screen blank |
| `0x90` | Hue |
| `0x92` | TV black level / luminance |

Some of these are more relevant to VGA or older display modes than to modern HDMI/DisplayPort connections.

## Explore monitor capabilities

Read capabilities:

```bash
ddcutil capabilities
```

Read all known supported VCPs:

```bash
ddcutil getvcp all
```

Try all known VCPs:

```bash
ddcutil getvcp known
```

Scan possible VCPs:

```bash
ddcutil getvcp scan
```

Show information about one VCP code:

```bash
ddcutil vcpinfo 10 --verbose
ddcutil vcpinfo 60 --verbose
```

## Notes for developers

PlasmaDDC should not assume that a VCP exists just because it is common.

The safe approach is:

1. Detect monitors.
2. Read `ddcutil capabilities`.
3. Try reading common VCPs.
4. Show controls only when the monitor responds correctly.
5. Handle unsupported VCPs gracefully.

Some manufacturer-specific features, such as game mode, overdrive, FreeSync / Adaptive-Sync, HDR modes, dynamic contrast or crosshair overlays, may not be available through standard DDC/CI.

They may require proprietary VCP codes, manufacturer-specific tools, or may not be controllable from Linux at all.
