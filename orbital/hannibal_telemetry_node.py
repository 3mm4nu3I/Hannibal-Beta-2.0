"""Legacy entry point kept so existing scripts (patch2.sh etc.) keep working.

The scanning logic now lives in run_telemetry.py -- one engine, so the
terminal, the dashboard and this command all see the same results and the
same telemetry_report.json.
"""
import sys

from run_telemetry import main

if __name__ == "__main__":
    sys.exit(main())
