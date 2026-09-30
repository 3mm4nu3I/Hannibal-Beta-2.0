#!/usr/bin/env python3
from pathlib import Path
import sys,time,os
ROOT=Path(__file__).resolve().parent;sys.path.insert(0,str(ROOT/'core'))
from hannibal_intel_sqlite3 import IntelDB
from market_catalog import TABS,COUNTRIES,seed
MAP='''
 +----------------------------------------------------------+
 |      AMERICAS          ATLANTIC      EUROPE / AFRICA      |
 |        ***                ~~~             *****          |
 |      *******          ~~~~~~~~~          ********         |
 |        ***           ~~~~~~~~~~~            ***           |
 |                       ~~~~~~~~          ASIA ******       |
 |   PACIFIC ~~~~~                         ***********        |
 |                        INDIAN ~~~~~        ***             |
 |                                             AUSTRALIA **   |
 +----------------------------------------------------------+
 ASCII-safe map: live layers appear only when configured.
'''
def bar(): print('\n0 Overview | 1 Stocks | 2 Futures | 3 Gold | 4 Energy | 5 FX | 6 Rates | 7 Crypto | 8 Shipping | 9 Volatility')
def render_market(db,country,tab):
 name,cat=TABS[tab];print(f'\n=== {name} | {country} ===')
 rows=db.latest_quotes(country,cat)
 if not rows:print('No instruments configured for this country/category.')
 for r in rows:
  q=r['quote']; val='NO LIVE QUOTE' if not q else f"{q.get('price')} ({q.get('change_pct')}%)"
  print(f"{r['symbol']:<14} {r['name']:<32} {val}")
def usage(db):
 print('\n=== USAGE / HEALTH ===');print(db.health())
 for x in db.usage_summary():print(x)
def main():
 db=IntelDB(ROOT/'data'/'hannibal_intel.sqlite3');seed(db);country='GLOBAL';tab='0';print('HANNIBAL V10 SAFE / LEGACY MODE');print('h=help, m=map, x=usage, c=country, q=quit')
 try:
  while True:
   bar();render_market(db,country,tab)
   try:cmd=input(f'[{country}:{tab}]> ').strip().lower()
   except EOFError:cmd='q'
   t=time.monotonic()
   if cmd in TABS:tab=cmd;db.log_usage('tab',tab,country)
   elif cmd in COUNTRIES:country=COUNTRIES[cmd][0];db.log_usage('country',tab,country)
   elif cmd=='c':print(' '.join(f'{k}={v[1]}' for k,v in COUNTRIES.items()))
   elif cmd=='m':print(MAP);db.log_usage('map',tab,country)
   elif cmd in ('x','usage'):usage(db)
   elif cmd in ('h','?'):print('0-9 market tabs; country keys: '+', '.join(f'{k}:{v[1]}' for k,v in COUNTRIES.items())+'; m map; x usage; q quit')
   elif cmd=='q':
    try:ok=input('Quit Hannibal safely? [y/N] ').strip().lower()=='y'
    except EOFError:ok=True
    if ok:break
   elif cmd:print('Unknown command. Press h for usage.')
 finally:
  db.log_usage('shutdown',tab,country);db.maintain();db.close();print('Database checkpointed. Safe shutdown complete.')
if __name__=='__main__':main()
