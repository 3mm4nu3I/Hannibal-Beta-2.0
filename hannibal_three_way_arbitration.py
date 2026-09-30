#!/usr/bin/env python3
"""Hannibal two-stream arbitration engine. Keys are read from environment only."""
from __future__ import annotations
import concurrent.futures, datetime, hashlib, json, os, urllib.request

API_ROOT='https://generativelanguage.googleapis.com/v1beta/models'
MODEL=os.getenv('HANNIBAL_GEMINI_MODEL','gemini-2.5-flash')

def _rules(record):
    evidence=record.get('evidence',[])
    risk=sum(1 for e in evidence if abs(float(e.get('z_score',0) or 0))>=4)
    classification='high_risk' if risk else 'normal'
    return {'status':'success','engine':'deterministic','analysis':{'summary':'Deterministic policy evaluation.','classification':classification,'confidence':100,'recommended_action':'manual_review' if risk else 'allow','evidence':[e.get('evidence_id') for e in evidence if abs(float(e.get('z_score',0) or 0))>=4]}}

def _stream(label,key,record):
    if not key:return {'status':'error','model':label,'error':'missing API key'}
    schema={'type':'OBJECT','properties':{'summary':{'type':'STRING'},'classification':{'type':'STRING','enum':['normal','review','high_risk','insufficient_evidence']},'confidence':{'type':'INTEGER'},'recommended_action':{'type':'STRING','enum':['allow','monitor','manual_review']}},'required':['summary','classification','confidence','recommended_action']}
    prompt='Analyze this defensive telemetry record. Do not infer identity or live location. Return only schema JSON.\n'+json.dumps(record,separators=(',',':'))
    body={'contents':[{'parts':[{'text':prompt}]}],'generationConfig':{'temperature':0,'responseMimeType':'application/json','responseSchema':schema}}
    req=urllib.request.Request(f'{API_ROOT}/{MODEL}:generateContent',data=json.dumps(body).encode(),headers={'Content-Type':'application/json','x-goog-api-key':key})
    try:
        with urllib.request.urlopen(req,timeout=45) as response: raw=json.loads(response.read().decode())
        text=raw['candidates'][0]['content']['parts'][0]['text']
        return {'status':'success','model':label,'analysis':json.loads(text)}
    except Exception as exc:return {'status':'error','model':label,'error':f'{type(exc).__name__}: {exc}'}

def arbitrate(record):
    a=os.getenv('GEMINI_API_KEY_A','');b=os.getenv('GEMINI_API_KEY_B','')
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        fa=pool.submit(_stream,'gemini_a',a,record);fb=pool.submit(_stream,'gemini_b',b,record)
        ra,rb=fa.result(),fb.result()
    rr=_rules(record); engines=[ra,rb,rr]
    analyses=[e['analysis'] for e in engines if e.get('status')=='success']
    classes=[x.get('classification') for x in analyses];actions=[x.get('recommended_action') for x in analyses]
    unanimous=len(analyses)==3 and len(set(classes))==1 and len(set(actions))==1
    disagreement=len(set(classes))>1 or len(set(actions))>1
    action=actions[0] if unanimous else 'manual_review'
    stamp=datetime.datetime.now(datetime.timezone.utc).isoformat()
    digest=hashlib.sha256(json.dumps(record,sort_keys=True,default=str).encode()).hexdigest()
    return {'run_id':'HAR-'+digest[:12].upper(),'timestamp':stamp,'input_sha256':digest,'gemini_a':ra,'gemini_b':rb,'deterministic':rr,'arbitration':{'successful_engines':len(analyses),'unanimous':unanimous,'disagreement':disagreement,'final_action':action,'human_approval_required':action!='allow'}}
