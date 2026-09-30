#!/usr/bin/env python3
"""Client helpers for Hannibal to reach the combined telecom explorer."""
import json, urllib.request
BASE='http://127.0.0.1:1884'
def _call(path,payload=None):
    data=None;headers={'Accept':'application/json'}
    if payload is not None:data=json.dumps(payload).encode();headers['Content-Type']='application/json'
    req=urllib.request.Request(BASE+path,data=data,headers=headers)
    with urllib.request.urlopen(req,timeout=15) as r:return json.loads(r.read().decode())
def ping():return _call('/ping')
def verify(phone,default_country='',expected_country=''):return _call('/verify',{'phone':phone,'default_country':default_country,'expected_country':expected_country})
def batch(items):return _call('/verify-batch',{'items':items})
