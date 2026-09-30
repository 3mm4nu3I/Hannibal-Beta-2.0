#!/usr/bin/env python3
import json
from pathlib import Path
from hannibal_evidence_confidence import assess_evidence,apply_confidence_gate
p=Path(__file__).resolve().parent
fs=json.loads((p/"evidence_confidence_fixtures.json").read_text())
for f in fs:
 r=assess_evidence(f["items"]);g=apply_confidence_gate({"arbitration":{"final_action":"allow","human_approval_required":False}},r);ok=r["quality"]==f["quality"] and r["requires_manual_review"]==f["review"] and (not f["review"] or g["arbitration"]["final_action"]=="manual_review");print(("PASS" if ok else "FAIL")+": "+f["id"]+" score="+str(r["weighted_confidence"])+" quality="+r["quality"]);assert ok
print("All evidence-confidence fixtures passed.")
