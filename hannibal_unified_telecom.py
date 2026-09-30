#!/usr/bin/env python3
from __future__ import annotations
import json, queue, threading, time, tkinter as tk
from tkinter import ttk,messagebox,filedialog
from pathlib import Path
import hannibal_combined_node as node
BG='#05070b';PANEL='#0b1119';CYAN='#00f5ff';MAGENTA='#ff2bd6';GREEN='#4dff88';YELLOW='#ffe66d';RED='#ff5d73';TEXT='#d9f7ff';DIM='#6f8792'
THREATS=[('TM-001','Account fraud','High','Validate metadata; manual review'),('TM-002','VoIP context','Medium','Flag as context; never auto-block'),('TM-003','Invalid number','High','Require alternate verification'),('TM-004','Enumeration/batch abuse','High','Batch cap, rate limits, audit'),('TM-005','API key theft','Critical','Local private config; rotation'),('TM-006','Audit tampering','High','SHA-256 case integrity'),('TM-007','Insider misuse','High','Purpose limitation and review'),('TM-008','Credit exhaustion','Medium','Cache and bounded workers')]
class App(tk.Tk):
 def __init__(self):
  super().__init__();self.title('HANNIBAL // Unified Telecom Intelligence v3');self.geometry('1320x860');self.minsize(1050,700);self.configure(bg=BG);self.q=queue.Queue();self.last=None;self.batch_results=[];self.phase=0;self._style();self._build();self.after(100,self._poll);self.after(200,self._mesh);self.refresh()
 def _style(self):
  s=ttk.Style(self);s.theme_use('clam');s.configure('TFrame',background=BG);s.configure('Panel.TFrame',background=PANEL);s.configure('TLabel',background=BG,foreground=TEXT,font=('Consolas',10));s.configure('Panel.TLabel',background=PANEL,foreground=TEXT,font=('Consolas',10));s.configure('Title.TLabel',background=BG,foreground=CYAN,font=('Consolas',18,'bold'));s.configure('TButton',background='#112334',foreground=CYAN,font=('Consolas',10,'bold'),padding=8);s.configure('TEntry',fieldbackground='#07101a',foreground=TEXT,insertcolor=CYAN);s.configure('TNotebook',background=BG);s.configure('TNotebook.Tab',background='#101722',foreground=TEXT,padding=(10,8),font=('Consolas',9,'bold'));s.map('TNotebook.Tab',background=[('selected','#123343')],foreground=[('selected',CYAN)]);s.configure('Treeview',background='#07101a',fieldbackground='#07101a',foreground=TEXT,rowheight=25,font=('Consolas',9));s.configure('Treeview.Heading',background='#123343',foreground=CYAN,font=('Consolas',9,'bold'))
 def _build(self):
  top=ttk.Frame(self);top.pack(fill='x',padx=16,pady=8);ttk.Label(top,text='HANNIBAL // UNIFIED TELECOM INTELLIGENCE v3',style='Title.TLabel').pack(side='left');self.status=ttk.Label(top,text='READY',foreground=GREEN);self.status.pack(side='right')
  self.canvas=tk.Canvas(self,height=100,bg=BG,highlightthickness=0);self.canvas.pack(fill='x',padx=16)
  bar=ttk.Frame(self,style='Panel.TFrame');bar.pack(fill='x',padx=16,pady=8)
  for label in ('Phone','Default','Expected'):ttk.Label(bar,text=label,style='Panel.TLabel').pack(side='left',padx=(10,4));e=ttk.Entry(bar,width=24 if label=='Phone' else 5);e.pack(side='left');setattr(self,label.lower(),e)
  self.phone.insert(0,'+351');self.default.insert(0,'PT');self.expected.insert(0,'PT')
  ttk.Button(bar,text='VERIFY + ASSESS',command=self.verify).pack(side='left',padx=10);ttk.Button(bar,text='CREATE CASE',command=self.case).pack(side='left',padx=4);ttk.Button(bar,text='PING NODE',command=self.ping).pack(side='left',padx=4)
  self.tabs=ttk.Notebook(self);self.tabs.pack(fill='both',expand=True,padx=16,pady=(0,16));self.frames={}
  for n in ['LOOKUP','GEOLOCATION','BATCH','SECURITY OPS','THREAT MODEL','CASE FILES','AUDIT','RAW JSON','NODE HEALTH']:
   f=ttk.Frame(self.tabs,style='Panel.TFrame');self.tabs.add(f,text=n);self.frames[n]=f
  self.lookup=self.tree(self.frames['LOOKUP'],['field','value'],[230,930]);self.lookup.pack(fill='both',expand=True,padx=8,pady=8)
  self.geo=self.tree(self.frames['GEOLOCATION'],['field','value'],[260,880]);self.geo.pack(fill='both',expand=True,padx=8,pady=8);ttk.Label(self.frames['GEOLOCATION'],text='Numbering-plan geography only. No GPS, cell-tower, IP, or live handset location.',style='Panel.TLabel',foreground=YELLOW).pack(pady=8)
  btop=ttk.Frame(self.frames['BATCH'],style='Panel.TFrame');btop.pack(fill='x',padx=8,pady=8);ttk.Label(btop,text='One number per line',style='Panel.TLabel').pack(side='left');ttk.Button(btop,text='RUN BATCH',command=self.run_batch).pack(side='right');ttk.Button(btop,text='EXPORT JSON',command=self.export_batch).pack(side='right',padx=6)
  self.batchin=self.text(self.frames['BATCH'],TEXT,7);self.batchin.pack(fill='x',padx=8);self.batchtree=self.tree(self.frames['BATCH'],['number','valid','type','carrier','country','risk','source'],[180,70,100,220,130,90,80]);self.batchtree.pack(fill='both',expand=True,padx=8,pady=8)
  self.soc=self.text(self.frames['SECURITY OPS'],CYAN);self.soc.pack(fill='both',expand=True,padx=8,pady=8)
  self.threat=self.tree(self.frames['THREAT MODEL'],['id','threat','risk','control'],[100,270,100,700]);self.threat.pack(fill='both',expand=True,padx=8,pady=8)
  for r in THREATS:self.threat.insert('','end',values=r)
  self.cases=self.tree(self.frames['CASE FILES'],['case','created','risk','carrier','country','integrity'],[170,130,80,180,100,430]);self.cases.pack(fill='both',expand=True,padx=8,pady=8);ttk.Button(self.frames['CASE FILES'],text='EXPORT SELECTED CASE',command=self.export_case).pack(pady=6)
  self.audit=self.text(self.frames['AUDIT'],YELLOW);self.audit.pack(fill='both',expand=True,padx=8,pady=8)
  self.raw=self.text(self.frames['RAW JSON'],GREEN);self.raw.pack(fill='both',expand=True,padx=8,pady=8)
  self.health=self.text(self.frames['NODE HEALTH'],MAGENTA);self.health.pack(fill='both',expand=True,padx=8,pady=8);ttk.Button(self.frames['NODE HEALTH'],text='REFRESH',command=self.refresh).pack(pady=6)
 def tree(self,p,cols,widths):
  t=ttk.Treeview(p,columns=cols,show='headings');
  for c,w in zip(cols,widths):t.heading(c,text=c.upper());t.column(c,width=w,anchor='w')
  return t
 def text(self,p,color,h=None):return tk.Text(p,height=h,bg='#07101a',fg=color,insertbackground=CYAN,font=('Consolas',10),relief='flat')
 def _mesh(self):
  self.canvas.delete('all');w=max(self.canvas.winfo_width(),900);color=[CYAN,MAGENTA,GREEN][self.phase%3];pts=[(w*i/10,50+(23 if (i+self.phase)%2 else -23)) for i in range(1,10)]
  for a,b in zip(pts,pts[1:]):self.canvas.create_line(*a,*b,fill=color,width=2)
  for x,y in pts:self.canvas.create_oval(x-4,y-4,x+4,y+4,outline=color,width=2)
  self.canvas.create_text(w/2,50,text='LIVE METADATA // DEFENSIVE ANALYSIS // RECEIPTS',fill=TEXT,font=('Consolas',13,'bold'));self.phase+=1;self.after(700,self._mesh)
 def bg(self,fn,done):
  def w():
   try:self.q.put((done,fn(),None))
   except Exception as e:self.q.put((done,None,e))
  threading.Thread(target=w,daemon=True).start()
 def _poll(self):
  try:
   while True:d,r,e=self.q.get_nowait();d(r,e)
  except queue.Empty:pass
  self.after(100,self._poll)
 def verify(self):self.status.config(text='QUERYING',foreground=YELLOW);self.bg(lambda:node.verify(self.phone.get(),self.default.get(),self.expected.get()),self.show)
 def show(self,r,e):
  if e:self.status.config(text='ERROR',foreground=RED);messagebox.showerror('Lookup failed',str(e));return
  self.last=r;self.status.config(text='ONLINE',foreground=GREEN);self.fill(self.lookup,r);self.fill(self.geo,node.geolocation_projection(r));self.raw.delete('1.0','end');self.raw.insert('1.0',json.dumps(r,indent=2,ensure_ascii=False));self.refresh()
 def fill(self,t,d):
  for x in t.get_children():t.delete(x)
  for k,v in d.items():t.insert('','end',values=(k,json.dumps(v) if isinstance(v,(dict,list)) else v))
 def run_batch(self):
  phones=[x.strip() for x in self.batchin.get('1.0','end').splitlines() if x.strip()];items=[(p,self.default.get(),self.expected.get()) for p in phones];self.bg(lambda:node.batch(items),self.show_batch)
 def show_batch(self,r,e):
  if e:messagebox.showerror('Batch failed',str(e));return
  self.batch_results=r
  for x in self.batchtree.get_children():self.batchtree.delete(x)
  for a in r:
   if a.get('ok'):self.batchtree.insert('','end',values=(a.get('e164') or a.get('phone'),a.get('phone_valid'),a.get('phone_type'),a.get('carrier'),a.get('country_code'),a.get('risk',{}).get('level'),'CACHE' if a.get('cached') else 'LIVE'))
   else:self.batchtree.insert('','end',values=('ERROR','','',a.get('error'),'','',''))
  self.refresh()
 def case(self):
  if not self.last:messagebox.showinfo('Case','Verify a number first.');return
  c=node.create_case(self.last,'Created by unified explorer');messagebox.showinfo('Case created',c['case_id']);self.refresh()
 def refresh(self):
  st=node.stats();self.soc.delete('1.0','end');self.soc.insert('1.0',json.dumps(st,indent=2));self.health.delete('1.0','end');self.health.insert('1.0',json.dumps(st,indent=2));self.audit.delete('1.0','end');self.audit.insert('1.0',json.dumps(node.audit_tail(),indent=2,ensure_ascii=False))
  for x in self.cases.get_children():self.cases.delete(x)
  for c in node.cases():
   r=c['result'];self.cases.insert('','end',values=(c['case_id'],c['created_at'],r.get('risk',{}).get('level'),r.get('carrier'),r.get('country_code'),c['integrity_sha256']))
 def ping(self):messagebox.showinfo('Node','Combined engine loaded locally and ready.')
 def export_batch(self):
  if not self.batch_results:return
  p=filedialog.asksaveasfilename(defaultextension='.json')
  if p:Path(p).write_text(json.dumps(self.batch_results,indent=2,ensure_ascii=False),encoding='utf-8')
 def export_case(self):
  s=self.cases.selection()
  if not s:return
  cid=self.cases.item(s[0])['values'][0];c=next((x for x in node.cases() if x['case_id']==cid),None);p=filedialog.asksaveasfilename(defaultextension='.json',initialfile=cid+'.json')
  if c and p:Path(p).write_text(json.dumps(c,indent=2,ensure_ascii=False),encoding='utf-8')
if __name__=='__main__':App().mainloop()
