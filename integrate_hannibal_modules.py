#!/usr/bin/env python3
"""Integrate Hannibal arbitration, confidence, NOAA DART, and spatial calculations.
Creates a timestamped backup, patches once, compiles, and restores on failure.
"""
from pathlib import Path
import py_compile, shutil, sys, time

HERE=Path(__file__).resolve().parent
TARGET=HERE/'hannibal_terminal.py'
MARKER='# === HANNIBAL 2+3 + SUBSEA INTEGRATION ==='
REQUIRED=('hannibal_three_way_arbitration.py','hannibal_evidence_confidence.py','hannibal_subsea_nodes.py','hannibal_spatial_calculations.py')

def once(text, old, new, label):
    n=text.count(old)
    if n!=1: raise RuntimeError(f'{label}: expected one anchor, found {n}')
    return text.replace(old,new,1)

def main():
    missing=[name for name in REQUIRED if not (HERE/name).exists()]
    if missing: raise FileNotFoundError('Missing beside terminal: '+', '.join(missing))
    original=TARGET.read_text(encoding='utf-8')
    if MARKER in original:
        print('Integration already installed.');return 0
    backup=TARGET.with_name(f'hannibal_terminal.pre_2plus3_{int(time.time())}.py')
    shutil.copy2(TARGET,backup)
    text=original
    imports='''\n# === HANNIBAL 2+3 + SUBSEA INTEGRATION ===\ntry:\n    from hannibal_three_way_arbitration import arbitrate as _h_arbitrate\n    from hannibal_evidence_confidence import assess_evidence as _h_assess_evidence, apply_confidence_gate as _h_confidence_gate\n    from hannibal_subsea_nodes import fetch_nodes as _h_fetch_subsea_nodes\n    HANNIBAL_2PLUS3_AVAILABLE = True\n    HANNIBAL_2PLUS3_ERROR = ""\nexcept Exception as _h_integration_error:\n    _h_arbitrate = _h_assess_evidence = _h_confidence_gate = _h_fetch_subsea_nodes = None\n    HANNIBAL_2PLUS3_AVAILABLE = False\n    HANNIBAL_2PLUS3_ERROR = str(_h_integration_error)\n'''
    text=once(text,"warnings.filterwarnings('ignore')",imports+"\nwarnings.filterwarnings('ignore')",'imports')

    block=r'''
# 2+3 state: two AI streams, rules, evidence confidence, arbitration.
_h2_lock = threading.Lock()
_h2_latest = None
_h2_busy = False
_h2_error = ""
_h2_subsea = []
_h2_subsea_updated = 0.0

def _h_evidence(war, infra, macro, subsea):
    evidence=[]
    for idx, entry in enumerate((war+infra+macro)[:12]):
        try: text=entry[1].get('text',str(entry[1]))
        except Exception: text=str(entry)
        evidence.append({'evidence_id':f'feed-{idx}','source_type':'provider_security_alert','integrity_verified':False,'freshness':0.9,'corroborating_sources':0,'contradictions':0,'text':text})
    for node in subsea:
        if node.get('status')=='ok':
            evidence.append({'evidence_id':'dart-'+node['station'],'source_type':'provider_security_alert','integrity_verified':True,'freshness':1.0,'corroborating_sources':1,'contradictions':0,'measurement':node.get('latest'),'z_score':node.get('z_score')})
    return evidence

def _h_run_arbitration():
    global _h2_latest, _h2_busy, _h2_error
    try:
        with state_lock:
            war=list(kinetic_headlines); infra=list(infra_atomic_headlines); macro=list(osint_data); subsea=list(_h2_subsea)
        evidence=_h_evidence(war,infra,macro,subsea)
        record={'source':'project_hannibal','timestamp':datetime.datetime.now(datetime.timezone.utc).isoformat(),'metrics':{'composite':global_composite,'C_t':global_C_t,'K':global_K,'E_t':global_E_t,'T_t':global_T_t},'evidence':evidence,'constraints':{'no_live_location_inference':True,'metadata_is_not_attribution':True}}
        result=_h_arbitrate(record)
        confidence=_h_assess_evidence(evidence)
        result=_h_confidence_gate(result,confidence)
        with _h2_lock: _h2_latest=result; _h2_error=''
    except Exception as exc:
        with _h2_lock: _h2_error=str(exc)
        logger.error('Hannibal 2+3 arbitration failed: %s',exc,exc_info=True)
    finally:
        with _h2_lock: _h2_busy=False

def _h_arbitration_daemon():
    global _h2_busy
    while True:
        if HANNIBAL_2PLUS3_AVAILABLE:
            with _h2_lock:
                launch=not _h2_busy
                if launch:_h2_busy=True
            if launch: threading.Thread(target=_h_run_arbitration,name='Hannibal-2plus3-Run',daemon=True).start()
        time.sleep(90.0)

def _h_subsea_daemon():
    global _h2_subsea, _h2_subsea_updated
    while True:
        try:
            nodes=_h_fetch_subsea_nodes() if _h_fetch_subsea_nodes else []
            with state_lock: _h2_subsea=nodes; _h2_subsea_updated=time.time()
            alerts=[n for n in nodes if n.get('alert')]
            if alerts: logger.warning('DART anomaly candidates: %s',[n.get('station') for n in alerts])
        except Exception as exc: logger.warning('DART subsea fetch failed: %s',exc)
        time.sleep(300.0)
'''
    text=once(text,'# ---------------------------------------------------------\n# PRICES & CALCULUS',block+'\n# ---------------------------------------------------------\n# PRICES & CALCULUS','integration block')

    start='''    threading.Thread(target=price_poll_daemon, name="Price-Poller", daemon=True).start()'''
    started=start+'''\n    threading.Thread(target=_h_subsea_daemon, name="DART-Subsea", daemon=True).start()\n    threading.Thread(target=_h_arbitration_daemon, name="Hannibal-2plus3", daemon=True).start()'''
    text=once(text,start,started,'daemon start')

    q_anchor='''                elif view_key == "T":\n                    # LIVE CHAT VIEW  [from HBL5.py]'''
    q_view='''                elif view_key == "Q":\n                    print(f"{PURPLE}  HANNIBAL 2+3 ARBITRATION + EVIDENCE CONFIDENCE + DART SUBSEA{RESET}")\n                    print(f"{BLUE}========================================================================================={RESET}")\n                    with _h2_lock:\n                        arb=dict(_h2_latest) if isinstance(_h2_latest,dict) else None\n                        busy=_h2_busy; err=_h2_error\n                    with state_lock: nodes=list(_h2_subsea)\n                    if not HANNIBAL_2PLUS3_AVAILABLE:\n                        print(f" {RED}Integration unavailable:{RESET} {HANNIBAL_2PLUS3_ERROR}")\n                    elif err and not arb: print(f" {RED}Last error:{RESET} {err}")\n                    elif not arb: print(f" {YELLOW}{'Analysis running' if busy else 'Awaiting first 90-second cycle'}...{RESET}")\n                    else:\n                        summary=arb.get('arbitration',{}); confidence=arb.get('evidence_confidence',{})\n                        print(f" Run ID                : {arb.get('run_id','N/A')}")\n                        print(f" Successful engines    : {summary.get('successful_engines','N/A')} / 3")\n                        print(f" Unanimous             : {summary.get('unanimous',False)}")\n                        print(f" Final action          : {summary.get('final_action','manual_review')}")\n                        print(f" Evidence confidence   : {confidence.get('weighted_confidence',0)} / 100 ({confidence.get('quality','LOW')})")\n                        print(f" Confidence gate       : {summary.get('confidence_gate','unknown')}")\n                    ok=sum(1 for n in nodes if n.get('status')=='ok'); alerts=[n for n in nodes if n.get('alert')]\n                    print(f"\\n DART subsea nodes      : {ok}/{len(nodes)} reporting | anomaly candidates: {len(alerts)}")\n                    for n in nodes[:10]:\n                        print(f"   {n.get('station','?')}: {n.get('status','?')} z={n.get('z_score','N/A')} delta={n.get('delta','N/A')}")\n                elif view_key == "T":\n                    # LIVE CHAT VIEW  [from HBL5.py]'''
    text=once(text,q_anchor,q_view,'Q view')
    text=once(text,'[P] HANNIBAL AI | [T] Chat','[P] HANNIBAL AI | [Q] 2+3/DART | [T] Chat','footer')
    text=once(text,"['w', 'k', 'i', 'c', 'p', 'h', 'g', 'm', 's', 't', 'y']","['w', 'k', 'i', 'c', 'p', 'q', 'h', 'g', 'm', 's', 't', 'y']",'Q key')
    TARGET.write_text(text,encoding='utf-8')
    try:
        for name in REQUIRED: py_compile.compile(str(HERE/name),doraise=True)
        py_compile.compile(str(TARGET),doraise=True)
    except Exception:
        shutil.copy2(backup,TARGET)
        raise
    print('Integrated:',TARGET.name);print('Backup:',backup.name);print('Open [Q] for 2+3/DART status.')
    return 0
if __name__=='__main__':raise SystemExit(main())
