"""Process-wide output redaction for Hannibal Python programs."""
import sys
import logging
from secret_masking import redact_text, redact

class _Stream:
    def __init__(self, target):
        self.target = target

    def write(self, s):
        return self.target.write(redact_text(s))

    def flush(self):
        return self.target.flush()

    def __getattr__(self, n):
        return getattr(self.target, n)

class _Filter(logging.Filter):
    def filter(self, record):
        record.msg = redact_text(record.msg)
        if record.args:
            record.args = redact(record.args)
        return True

def install():
    if not isinstance(sys.stdout, _Stream):
        sys.stdout = _Stream(sys.stdout)
    if not isinstance(sys.stderr, _Stream):
        sys.stderr = _Stream(sys.stderr)
        
    old_add_handler = logging.Logger.addHandler
    if not getattr(old_add_handler, '_hannibal_masked', False):
        def add(self, handler):
            handler.addFilter(_Filter())
            return old_add_handler(self, handler)
        add._hannibal_masked = True
        logging.Logger.addHandler = add

    for logger in [logging.getLogger()] + list(logging.Logger.manager.loggerDict.values()):
        if isinstance(logger, logging.Logger):
            for h in logger.handlers:
                if not any(isinstance(f, _Filter) for f in h.filters):
                    h.addFilter(_Filter())

install()