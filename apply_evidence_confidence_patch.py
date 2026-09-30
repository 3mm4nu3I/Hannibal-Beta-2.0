#!/usr/bin/env python3
from pathlib import Path
import py_compile,shutil,time
p=Path(__file__).resolve().parent;t=p/"hannibal_three_way_arbitration.py";mark="# === HANNIBAL EVIDENCE CONFIDENCE INTEGRATION ==="
if not t.exists():raise FileNotFoundError(t.name)
x=t.read_text()
if mark in x:print("Already installed.");raise SystemExit(0)
b=t.with_name("hannibal_three_way_arbitration.pre_confidence_"+str(int(time.time()))+".py");shutil.copy2(t,b)
anchor="import hashlib, json, os, time, urllib.request"
if anchor not in x:raise RuntimeError("Import anchor not found")
x=x.replace(anchor,anchor+"\n"+mark+"\nfrom hannibal_evidence_confidence import assess_evidence, apply_confidence_gate",1)
old="    _append(result);return result"
new="    confidence=assess_evidence(record.get('evidence', []))\n    result=apply_confidence_gate(result,confidence)\n    _append(result);return result"
if old not in x:shutil.copy2(b,t);raise RuntimeError("Return anchor not found")
x=x.replace(old,new,1);t.write_text(x)
try:py_compile.compile(str(t),doraise=True)
except Exception:shutil.copy2(b,t);raise
print("Patched",t.name);print("Backup",b.name)
