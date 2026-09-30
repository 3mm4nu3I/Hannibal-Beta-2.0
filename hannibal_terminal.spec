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
    + [
        'zoneinfo',
        'sqlite3',
        'multiprocessing',  # pandas pulls this in on some versions
    ]
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
