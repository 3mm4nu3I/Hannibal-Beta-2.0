#!/usr/bin/env python3
from __future__ import annotations
import hashlib,json,time
WEIGHTS={'server_auth_log':100,'cryptographic_signature':100,'transaction_record':95,'provider_security_alert':90,'carrier_metadata':80,'verified_user_statement':75,'ip_geolocation':60,'historical_behavior':55,'anonymous_report':25,'unverified_claim':10}
def _clip(v):return max(0,min(100,int(round(v))))
def assess_evidence(items):
    out=[]
    for item in items:
        kind=str(item.get('source_type','unverified_claim'));base=WEIGHTS.get(kind,10);integrity=1 if item.get('integrity_verified') else .8;fresh=max(.25,min(float(item.get('freshness',1)),1));cor=min(int(item.get('corroborating_sources',0))*3,9);con=min(int(item.get('contradictions',0))*12,36);score=_clip(base*integrity*fresh+cor-con);out.append({'evidence_id':item.get('evidence_id','unknown'),'source_type':kind,'score':score})
    if out:
        mean=sum(x['score'] for x in out)/len(out);weak=min(x['score'] for x in out);score=_clip(.75*mean+.25*weak)
    else:score=0
    quality='HIGH' if score>=80 else 'MEDIUM' if score>=50 else 'LOW'
    result={'module':'hannibal_evidence_confidence','timestamp':int(time.time()),'evidence_items':len(out),'weighted_confidence':score,'quality':quality,'requires_manual_review':score<80,'breakdown':out}
    result['integrity_sha256']=hashlib.sha256(json.dumps(result,sort_keys=True).encode()).hexdigest();return result
def apply_confidence_gate(result,confidence):
    result=dict(result);result['evidence_confidence']=confidence;summary=dict(result.get('arbitration',{}));summary['confidence_gate']='passed' if confidence.get('weighted_confidence',0)>=80 else 'blocked'
    if summary['confidence_gate']=='blocked':summary['final_action']='manual_review';summary['human_approval_required']=True
    result['arbitration']=summary;return result
