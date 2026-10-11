# Auto-loaded by Python ONLY when this folder is on PYTHONPATH (Python imports
# sitecustomize before a script's own folder is added to sys.path, so merely
# running `python hannibal_terminal.py` does not trigger it -- hannibal_terminal.py
# and run_telemetry.py import the bootstrap explicitly for that reason).
# Set HANNIBAL_NO_MASK=1 to disable output redaction.
import os
if os.environ.get("HANNIBAL_NO_MASK") != "1":
    try:
        import hannibal_security_bootstrap
        hannibal_security_bootstrap.install()
    except Exception:
        pass
