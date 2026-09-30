#!/usr/bin/env python3
"""Read-only NOAA/NDBC DART subsea node adapter for Hannibal."""
from __future__ import annotations
import datetime as dt
import math
import urllib.request
from hannibal_spatial_calculations import zscore_latest

BASE='https://www.ndbc.noaa.gov/data/realtime2/{station}.dart'
DEFAULT_STATIONS=('21415','21418','21419','21420','23218','23220','23401','32401','32402','32403','32404','32413','41420','41421','42407','43412','44401','46403','46410','51425')

def parse_dart(text, limit=96):
    rows=[]
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith('#'):continue
        parts=line.split()
        if len(parts)<7:continue
        try:
            year,month,day,hour,minute=map(int,parts[:5])
            t=dt.datetime(year,month,day,hour,minute,tzinfo=dt.timezone.utc)
            measurement=None
            for token in reversed(parts[5:]):
                if token.upper()!='MM':
                    try:measurement=float(token);break
                    except ValueError:pass
            if measurement is not None and math.isfinite(measurement): rows.append({'timestamp':t.isoformat(),'value':measurement})
        except Exception:continue
        if len(rows)>=limit:break
    return rows

def fetch_station(station, timeout=12):
    station=str(station).strip()
    req=urllib.request.Request(BASE.format(station=station),headers={'User-Agent':'ProjectHannibal/11 defensive-monitor'})
    with urllib.request.urlopen(req,timeout=timeout) as response:
        text=response.read().decode('utf-8','replace')
    rows=parse_dart(text)
    values=[r['value'] for r in rows]
    z=zscore_latest(values)
    delta=(values[0]-values[1]) if len(values)>1 else 0.0
    return {'station':station,'status':'ok' if rows else 'no_data','latest':rows[0] if rows else None,'samples':len(rows),'z_score':round(z,3),'delta':round(delta,4),'alert':abs(z)>=4.0}

def fetch_nodes(stations=DEFAULT_STATIONS, max_nodes=20):
    result=[]
    for station in tuple(stations)[:max_nodes]:
        try: result.append(fetch_station(station))
        except Exception as exc: result.append({'station':str(station),'status':'error','error':str(exc),'alert':False})
    return result
