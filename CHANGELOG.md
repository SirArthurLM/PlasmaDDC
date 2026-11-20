# Changelog

## 1.1.0

### Added

- English/Spanish language preferences with persistent Qt settings and system
  language fallback (contributed by Marcel Vojtkovszky in pull request #1).
- Fully simulated `--demo` mode with two monitors and no real DDC/CI access.
- On-demand section reads for Picture, Color, Audio, and Input; individual
  controls retain their own **Read** and **Apply** actions.
- Explicitly confirmed, on-demand `capabilities` and `getvcp all` diagnostics.
- Automated regression coverage for language, asynchronous operations, demo
  isolation, control states, section reads, and partial diagnostic output.

### Changed

- GUI starts without automatic hardware detection or bulk DDC/CI reads.
- DDC/CI commands run in the background and are serialized; multi-control
  section reads are performed sequentially.
- A confirmation is requested before first real DDC/CI access per session.
- Controls distinguish **Not read** from an actual value of zero; controls
  become editable after successful reads.
- The color preset UI warns that MCCS choices are generic and may not all be
  supported by the connected monitor.

### Fixed

- Restored control editability after successful individual reads.
- More informative verification errors for color presets and RGB gain.
- Invalid UTF-8 in diagnostic output no longer causes a decoding exception.
- Partial `ddcutil` diagnostics are displayed in the Diagnostics panel with
  a visible warning when the command exits unsuccessfully.

### Known limitations

- DDC/CI behavior is monitor-specific. Some preset values and RGB gain writes
  can fail verification even when the monitor visibly changes its settings.
- A historical `amdgpu`/DisplayPort desktop hang was observed. These changes
  reduce automatic DDC/CI traffic but **do not guarantee driver stability**.
  Advanced diagnostics remain explicitly opt-in.
- Diagnostic `capabilities` parsing errors can originate in monitor firmware
  or `ddcutil`; a partial `getvcp all` output is not necessarily an app failure.
- Demo mode intentionally disables advanced real-hardware diagnostics.

### Thanks

- [Marcel Vojtkovszky](https://github.com/mvojtkovszky) for the original
  language-preferences contribution (pull request #1).

## 1.0.0

- Initial GUI and CLI for monitor control through `ddcutil`, with
  `monitorcontrol` as an auxiliary backend.
- Support for brightness, contrast, RGB gain, color presets, audio volume,
  and input source, with installation and removal scripts.
