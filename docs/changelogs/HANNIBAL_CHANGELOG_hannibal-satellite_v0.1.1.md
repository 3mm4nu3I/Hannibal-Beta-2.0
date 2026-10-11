# Changelog entry v0.1.1 (mirror of hannibal-satellite/CHANGELOG.md; v0.1.0 is in HANNIBAL_CHANGELOG_hannibal-satellite_v0.1.0.md)

## [0.1.1] - 2026-10-11

### Changed
- hannibal_orbital.py: added a 9-line guarded block after MENU that registers the new [E] "Earth export" screen from hannibal_sat. Purely additive: no existing line changed or removed. If hannibal_sat is not installed the module behaves exactly as before. Patch file: hannibal_orbital_earth_export.patch (in this folder).
- Menu label in hannibal_bridge.py now follows the module's own column layout.

### Backup
- Before patching, the original was copied in Google Drive as "hannibal_orbital.py.BACKUP_2026-10-11_pre-earth-export" (46,881 bytes, byte-identical to the original; SHA-256 starts 07efd334f0b0).

### Verified
- 8 of 8 tests pass. Patched file compiles; diff against the original is additions only.

### Not verified
- The patched module has not been run inside Hannibal (hannibal_net, hannibal_art, run_telemetry etc. are not available here), so the [E] screen is untested end to end.
- Other modules (hannibal_terminal.py, hannibal_login.py, hannibal_telemetry_node.py, blueglobe_dashboard.html) were not changed: the Earth export only touches the orbital module.
- The Drive copy of hannibal_orbital.py was NOT overwritten (Drive access here cannot edit file contents). Apply the patch, or replace the file with the patched copy, on your computer.
- Not pushed to GitHub (invalid login) and not mirrored to OneDrive (connector not connected).
