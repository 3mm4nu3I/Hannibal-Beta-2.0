# hannibal_terminal.spec
# ----------------------------------------------------------------------------
# PyInstaller build spec for PROJECT HANNIBAL.
#
# Build on Windows (PyInstaller builds for whatever OS it runs on -- this spec
# must be run on your Windows machine, not on Linux/Mac, to produce a .exe):
#
#   pip install pyinstaller
#   pyinstaller hannibal_terminal.spec
#
# Output lands in dist\HANNIBAL_TERMINAL\HANNIBAL_TERMINAL.exe
# (one-folder build, not one-file -- see note below on why)
# ----------------------------------------------------------------------------

# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

# yfinance and pandas both do dynamic/lazy imports that PyInstaller's static
# analysis misses on its own -- without these, the exe builds fine but throws
# ModuleNotFoundError at runtime the first time yfinance actually tries to
# pull data. Listing them explicitly avoids that class of failure.
hidden_imports = (
    collect_submodules('yfinance')
    + collect_submodules('pandas')
    + collect_submodules('cryptography')
    + collect_submodules('defusedxml')
    + [
        # orbital / satellite / masking modules -- imported inside try/except in the
        # terminal, so list them explicitly to be sure they are bundled
        'hannibal_orbital',
        'hannibal_net',
        'hannibal_spacetrack',
        'hannibal_nasa',
        'hannibal_n2yo',
        'hannibal_login',
        'hannibal_creds',
        'hannibal_vault',
        'hannibal_art',
        'hannibal_feeder',
        'run_telemetry',
        'hannibal_blueglobe',
        'hannibal_geoint',
        'hannibal_security_bootstrap',
        'secret_masking',
        'requests',
        'http.server',
        'zoneinfo',
        'sqlite3',
        'multiprocessing',  # pandas pulls this in on some versions
        'phonenumbers',
    ]
    + collect_submodules('phonenumbers')
)

# zoneinfo needs the IANA tz database. Windows has no system copy of it the
# way Linux/Mac do, so the 'tzdata' PyPI package (in requirements.txt) must
# be installed in THIS environment before running PyInstaller -- it's only
# added to hidden_imports if it's actually present, so a missing tzdata
# fails as a clear pip step (see requirements.txt) rather than a cryptic
# PyInstaller Analysis error.
try:
    import tzdata  # noqa: F401
    hidden_imports.append('tzdata')
except ImportError:
    print("WARNING: tzdata not installed in this environment -- run "
          "'pip install -r requirements.txt' before building, or zoneinfo "
          "lookups (used for the WEST timestamp) will fail at runtime.")

# pandas/yfinance also ship non-Python data files (e.g. pandas' timezone
# data, yfinance's cached ticker lookups) that need to be bundled alongside
# the code, not just the .py/.pyc files.
datas = collect_data_files('pandas') + collect_data_files('yfinance')

# Satellite dashboard + default target list. The engine looks for
# norad_targets.json / telemetry_report.json NEXT TO THE .EXE first (so you can
# edit them), then falls back to these bundled copies. build.bat also copies
# norad_targets.json beside the exe.
datas += [
    ('blueglobe_dashboard.html', '.'),
    ('norad_targets.json', '.'),
]

# Market brain page (hannibal_brain.py, menu [R]) -- added 2026-10-11.
datas += [('hannibal_brain.html', '.')]
# Modules imported inside try-blocks are invisible to PyInstaller's scan; name them.
hidden_imports += ['hannibal_fred', 'hannibal_brain', 'hannibal_geoint']
# Grand Unified Happiness Theorem (menu [T]) -- added 2026-10-11.
hidden_imports += ['hannibal_theorem']
# Zombie check (menu [Z]) and its default target list -- added 2026-10-22.
hidden_imports += ['hannibal_zombie']
datas += [('zombie_targets_2026-10-17.json', '.')]

a = Analysis(
    ['hannibal_terminal.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='HANNIBAL_TERMINAL',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,          # REQUIRED: this is a terminal UI app, not a
                            # windowed app -- console=False would hide the
                            # window it needs to draw into and the program
                            # would appear to do nothing.
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

# One-folder build (COLLECT), not one-file (--onefile).
# --onefile unpacks the whole interpreter + pandas/numpy/yfinance to a temp
# directory on EVERY launch before the program can start -- with this
# dependency set that adds several seconds of extra startup lag on top of
# the responsiveness work already done in the script itself. One-folder
# starts instantly since nothing needs unpacking; the tradeoff is a folder
# instead of a single file to distribute, which is fine for a tool that
# lives in one place on your own machine.
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='HANNIBAL_TERMINAL',
)
