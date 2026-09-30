#!/usr/bin/env python3
from __future__ import annotations
import json, os, re, time, urllib.parse, urllib.request, urllib.error
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
HERE=Path(__file__).resolve().parent
CONFIG=HERE/'telecom_node_config.json'; CACHE=HERE/'telecom_cache.json'; AUDIT=HERE/'telecom_audit.jsonl'; CASES=HERE/'case_files.jsonl'
API='https://api.veriphone.io/v2/verify'; COUNTERS={'requests':0,'success':0,'errors':0,'cache_hits':0}
def cfg():
    try:return json.loads(CONFIG.read_text(encoding='utf-8'))
    except Exception:return {}
def api_key():
    v=os.getenv('VERIPHONE_API_KEY','').strip() or str(cfg().get('veriphone_key','')).strip()
    if not v:raise RuntimeError('Missing Veriphone API key')
    return v
def _read(path,default):
    try:return json.loads(path.read_text(encoding='utf-8'))
    except Exception:return default
def _append(path,obj):
    with path.open('a',encoding='utf-8') as f:f.write(json.dumps(obj,ensure_ascii=False)+'\n')
def mask(v):
    d=re.sub(r'\D','',str(v));return '*'*max(0,len(d)-4)+d[-4:]
def hash_number(v):return hashlib.sha256(str(v).encode()).hexdigest()
import hashlib
def risk_assessment(r, expected_country=''):
    score=0; reasons=[]
    if not r.get('phone_valid'):score+=70;reasons.append('invalid_number')
    t=(r.get('phone_type') or '').lower()
    if 'voip' in t:score+=25;reasons.append('voip_line')
    if expected_country and r.get('country_code') and r.get('country_code')!=expected_country.upper():score+=30;reasons.append('country_mismatch')
    level='LOW' if score<25 else 'REVIEW' if score<50 else 'HIGH'
    return {'score':min(score,100),'level':level,'reasons':reasons,'recommended_action':'allow' if level=='LOW' else 'manual_review'}
def verify(phone,default_country='',expected_country='',use_cache=True):
    phone=str(phone).strip(); default_country=default_country.strip().upper(); expected_country=expected_country.strip().upper()
    if not re.search(r'\d',phone):raise ValueError('Phone must contain digits')
    COUNTERS['requests']+=1; cache=_read(CACHE,{}) if use_cache else {}; ck=f'{phone}|{default_country}'; now=int(time.time()); ttl=int(cfg().get('cache_ttl_seconds',86400))
    if ck in cache and now-int(cache[ck]['saved_at'])<=ttl:
        payload=dict(cache[ck]['payload']);cached=True;COUNTERS['cache_hits']+=1
    else:
        params={'key':api_key(),'phone':phone}
        if default_country:params['default_country']=default_country
        req=urllib.request.Request(API+'?'+urllib.parse.urlencode(params),headers={'Accept':'application/json','User-Agent':'Hannibal-Defensive-Telecom/2.0'})
        try:
            with urllib.request.urlopen(req,timeout=15) as resp:payload=json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            COUNTERS['errors']+=1;raise RuntimeError(f'Veriphone HTTP {e.code}: '+e.read().decode('utf-8','replace'))
        cached=False
        if payload.get('status')=='success':cache[ck]={'saved_at':now,'payload':payload};CACHE.write_text(json.dumps(cache,indent=2),encoding='utf-8')
    result={k:payload.get(k) for k in ['status','phone','phone_valid','phone_type','phone_region','country','country_code','country_prefix','international_number','local_number','e164','carrier']}
    result.update(cached=cached,verified_at=now);result['risk']=risk_assessment(result,expected_country)
    COUNTERS['success']+=1
    _append(AUDIT,{'timestamp':now,'event':'verify','phone_masked':mask(phone),'phone_hash':hash_number(phone),'status':result['status'],'country_code':result['country_code'],'carrier':result['carrier'],'risk':result['risk']})
    return result
def batch(items,workers=3):
    if len(items)>100:raise ValueError('Batch maximum is 100')
    out=[None]*len(items)
    with ThreadPoolExecutor(max_workers=max(1,min(int(workers),5))) as ex:
        jobs={ex.submit(verify,*(x if isinstance(x,(list,tuple)) else (x,'',''))):i for i,x in enumerate(items)}
        for f in as_completed(jobs):
            i=jobs[f]
            try:out[i]={'ok':True,**f.result()}
            except Exception as e:out[i]={'ok':False,'error':str(e)}
    return out
def audit_tail(limit=100):
    try:lines=AUDIT.read_text(encoding='utf-8').splitlines()[-limit:]
    except Exception:return []
    return [json.loads(x) for x in lines if x.strip()]
def create_case(result,notes=''):
    stamp=int(time.time()); seed=json.dumps(result,sort_keys=True)+str(stamp); case_id='HTN-'+hashlib.sha256(seed.encode()).hexdigest()[:12].upper()
    case={'case_id':case_id,'created_at':stamp,'classification':'DEFENSIVE REVIEW','indicator':{'phone_masked':mask(result.get('phone','')),'phone_hash':hash_number(result.get('phone',''))},'result':result,'analyst_notes':notes,'integrity_sha256':hashlib.sha256(json.dumps(result,sort_keys=True).encode()).hexdigest()}
    _append(CASES,case);return case
def cases():
    try:return [json.loads(x) for x in CASES.read_text(encoding='utf-8').splitlines() if x.strip()]
    except Exception:return []
def stats():
    records=audit_tail(10000); levels={'LOW':0,'REVIEW':0,'HIGH':0}
    for r in records:
        lv=(r.get('risk') or {}).get('level')
        if lv in levels:levels[lv]+=1
    return {'service':'hannibal-defensive-telecom','status':'online','key_loaded':bool(cfg().get('veriphone_key') or os.getenv('VERIPHONE_API_KEY')),'endpoint':API,**COUNTERS,'audit_records':len(records),'risk_levels':levels,'case_files':len(cases())}

def geolocation_projection(result):
    """Return numbering-plan geography only, never device/live coordinates."""
    region = result.get('phone_region') or ''
    country = result.get('country') or ''
    code = result.get('country_code') or ''
    return {
        'method': 'telephone_numbering_plan',
        'country': country,
        'country_code': code,
        'region': region,
        'precision': 'region' if region and region.lower() != country.lower() else 'country',
        'live_device_location': False,
        'coordinates_available': False,
        'warning': 'This is numbering-plan metadata, not GPS, cell-tower, IP, or handset tracking.'
    }
