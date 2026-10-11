"""Shared redaction primitives for Project Hannibal. No secret values are stored by this module."""
import re
from collections.abc import Mapping

SENSITIVE = re.compile(
    r'(?i)(api[_-]?key|token|secret|password|passwd|authorization|access[_-]?key|client[_-]?secret|cookie|session|credential)'
)

PATTERNS = [
    (re.compile(r'(?i)(authorization|x-api-key|api-key)\s*[:=]\s*[^\s,;]+(?:\s+[^\s,;]+)?'), lambda m: m.group(1) + ': ************'),
    (re.compile(r'(?i)\b(bearer|apikey|token)\s+[A-Za-z0-9._~+/=-]{6,}'), lambda m: m.group(1) + ' ************'),
    (re.compile(r'(?i)([?&](?:api[_-]?key|token|access[_-]?token|key|secret|password)=)[^&#\s]+'), lambda m: m.group(1) + '************'),
    (re.compile(r'(?i)\b(api[_-]?key|token|secret|password|passwd)\s*=\s*[^\s,;]+'), lambda m: m.group(1) + '=************'),
    # JSON-shaped pairs: {"apiKey": "..."} / {"token": "..."}. redact() handles
    # dicts, but anything already serialised to a string reaches print(), a log
    # line or an exception as text, and redact_text() is what wraps stdout.
    (re.compile(r'(?i)("(?:api[_-]?key|token|secret|password|passwd|access[_-]?token'
                r'|client[_-]?secret|credential|authorization)"\s*:\s*)"[^"]*"'),
     lambda m: m.group(1) + '"************"'),
]

# Literal secrets typed in at runtime (e.g. the Space-Track password). They are scrubbed wherever they
# appear, even without a "password=" label in front of them. Held in memory only, never written anywhere.
_LITERALS = set()


def register_secret(value) -> None:
    value = str(value or "")
    if len(value) >= 4:
        _LITERALS.add(value)


def redact_text(value: str) -> str:
    s = str(value)
    for pattern, repl in PATTERNS:
        s = pattern.sub(repl, s)
    for lit in sorted(_LITERALS, key=len, reverse=True):
        if lit in s:
            s = s.replace(lit, '************')
    return s

def redact(value):
    if isinstance(value, Mapping):
        return {k: ('************' if SENSITIVE.search(str(k)) else redact(v)) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(v) for v in value]
    if isinstance(value, tuple):
        return tuple(redact(v) for v in value)
    if isinstance(value, str):
        return redact_text(value)
    return value