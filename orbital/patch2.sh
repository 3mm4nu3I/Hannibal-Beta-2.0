#!/bin/bash
# Hannibal Orbital Directorate integration (Linux / macOS / Git-Bash)
# Run from the folder that holds the module files. Pass the Hannibal folder as the first argument
# if it is somewhere else:   ./patch2.sh /path/to/hannibal
set -e
HANNIBAL_DIR="${1:-./}"
HANNIBAL_DIR="${HANNIBAL_DIR%/}/"

FILES="hannibal_orbital.py hannibal_net.py hannibal_spacetrack.py hannibal_nasa.py hannibal_n2yo.py hannibal_login.py hannibal_creds.py hannibal_vault.py hannibal_art.py \
hannibal_feeder.py run_telemetry.py hannibal_telemetry_node.py hannibal_blueglobe.py hannibal_geoint.py \
blueglobe_dashboard.html secret_masking.py hannibal_security_bootstrap.py sitecustomize.py \
patch_hannibal.py requirements.txt"

echo "[*] Installing the orbital module files into ${HANNIBAL_DIR}"
if [ "$(cd "$HANNIBAL_DIR" && pwd)" != "$(pwd)" ]; then
    for f in $FILES; do cp "$f" "${HANNIBAL_DIR}${f}"; done
    # never overwrite the user's own target list / credentials
    if [ ! -f "${HANNIBAL_DIR}norad_targets.json" ]; then
        cp norad_targets.json "${HANNIBAL_DIR}norad_targets.json"
    else
        echo "[=] Kept your existing norad_targets.json"
    fi
fi

echo "[*] Verifying Python dependencies..."
python3 -m pip install requests defusedxml --quiet

if [ -f "${HANNIBAL_DIR}hannibal_terminal.py" ]; then
    echo "[*] Patching hannibal_terminal.py (backup: hannibal_terminal.py.pre-orbital.bak)"
    python3 "${HANNIBAL_DIR}patch_hannibal.py" "${HANNIBAL_DIR}hannibal_terminal.py"
else
    echo "[!] No hannibal_terminal.py found there -- skipped. Standalone use still works."
fi

echo "[*] Done."
echo "    Standalone menu : python3 hannibal_orbital.py"
echo "    Terminal        : python3 hannibal_terminal.py   (L fleet, B globe, V Orbital Ops)"
echo "    Undo the patch  : python3 patch_hannibal.py --revert"
echo "    Optional env    : SPACETRACK_USER / SPACETRACK_PASS, BLUEGLOBE_API_KEY, HANNIBAL_HOME_LAT/LON/NAME"
