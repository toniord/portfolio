# Monday reorder agent: reference implementation from docs/agent_instructions_v3.md.
# Only change from the spec: OUT defaults to ./output (was /tmp/agent) and is created if missing.
# Usage: python3 agent.py DATA_DIR [N]
"""Reorder agent, case 10, built from PRD v3. Usage: python agent.py PROJECT_DIR [N]"""
import sys, re, glob, os, csv, pandas as pd
D=sys.argv[1]; N=int(sys.argv[2]) if len(sys.argv)>2 else None
def find(pat):
    for f in glob.glob(D+'/**/*',recursive=True):
        if f.endswith(('.csv','.txt')):
            with open(f,errors='ignore') as fh: head=fh.read(400)
            if re.search(pat,head): return f
    raise SystemExit('missing file for '+pat)
F_ERP=find(r'SUGGESTED PURCHASE ORDER REPORT|^sku,description,supplier,branch,on_hand,on_order,min,max,suggested_qty'); F_PL=find(r'^sku,supplier,description,uom,unit_cost'); F_RL=find(r'^date,branch,sku,description,supplier,qty,rush_freight_cost'); F_CC=find(r'CUSTOMER STOCKING COMMITMENTS')
# PRD 2: read as text, skip banner/subtotals/total, never write back
banner='SUGGESTED PURCHASE ORDER REPORT' in open(F_ERP,errors='ignore').readline()
e=pd.read_csv(F_ERP,skiprows=1 if banner else 0,dtype=str,keep_default_na=False)
e=e[e.branch.isin(['JOL','RKF','FTW'])].copy()
for c in ['on_hand','on_order','min','max','suggested_qty','sales_12m']: e[c]=e[c].astype(float).astype(int)
p=pd.read_csv(F_PL,dtype=str,keep_default_na=False).set_index('sku')
rl=pd.read_csv(F_RL,dtype=str,keep_default_na=False)
# PRD v3: actual lead time = average of the last three receipts in the supplier portal file, by item and branch
ACT={}
try:
    F_PO=find(r'^sku,branch,supplier,portal_item_status')
    for _,r in pd.read_csv(F_PO,dtype=str,keep_default_na=False).iterrows():
        d=[int(v) for v in r.po_to_receipt_days_last_3.split(',') if v.strip()]
        if d: ACT[(r.sku,r.branch)]=sum(d)/len(d)
except SystemExit: pass
import math
rows=[];cust=None
for line in open(F_CC):
    if line.startswith('1. MIDVALE'): cust,br='Midvale Castings','FTW'
    if line.startswith('2. STARR'): cust,br='Starr Ridge Packaging','RKF'
    if line.startswith('3. LOCKPORT'): cust,br='Lockport Precision Components','JOL'
    mm=re.match(r'^([A-Z]{3}-\d{5})\s+(.*?)\s+(\d+)\s*$',line.rstrip('\n'))
    if mm and cust: rows.append((mm.group(1),br,cust,mm.group(2).strip(),int(mm.group(3))))
C=pd.DataFrame(rows,columns=['sku','branch','cust','desc','coh'])
CK={(a,b):(c,d) for a,b,c,_,d in rows}; CSKU=set(C.sku)
GLOVES=set('SAF-10011 SAF-10018 SAF-10024 SAF-10032 SAF-10037 SAF-10047 SAF-10050 SAF-10058 SAF-10065 SAF-10070 SAF-10077 SAF-10085 SAF-10091 SAF-10098 SAF-10110 SAF-10113 SAF-10119 SAF-10129 SAF-10134 SAF-10144 SAF-10150 SAF-10154 SAF-10166 SAF-10170 SAF-10180'.split())
BUYER={'JOL':'Dee','RKF':'Dee','FTW':'Pete'}
def rush_ev(sku):
    g=rl[rl.sku==sku]; cost=g.rush_freight_cost.astype(float).sum()
    notes='; '.join(sorted(set(g.note)-{''})); callers='; '.join(sorted(set(g.customer_called)-{''}))
    if sku in CSKU: who='call the customer (contract item)'
    elif g.note.str.contains('receipt late|PO sat open, supplier backlog').any(): who='call the supplier'
    else: who='buyer chooses: the customer, the supplier, or Marty if it has to come over from another branch'
    parts=[f"{len(g)} rush{'es' if len(g)!=1 else ''} in 2025, ${cost:,.0f}"]
    if callers: parts.append('called: '+callers)
    if notes: parts.append('note: '+notes)
    return '; '.join(parts+[who])
def decide(x):
    s=x.sku; pl=p.loc[s] if s in p.index else None
    st=pl.status if pl is not None else ''; rep=pl.replacement_sku if pl is not None else ''
    shelf=pl.shelf_life_months if pl is not None else ''
    pos=x.on_hand+x.on_order; rush=(rl.sku==s).any(); b=BUYER[x.branch]; g=x.suggested_qty
    moq=int(float(pl.min_order_qty)) if pl is not None and pl.min_order_qty else 1
    lt=int(float(x.lead_time_days)) if str(x.lead_time_days).strip() else 0
    act=ACT.get((s,x.branch)); ltxt=(f"; {x.supplier} takes {act:.0f} days now against Girder's {lt}" if act is not None else '; no portal lead time')
    flags=[]
    # Rule 1 contract
    if (s,x.branch) in CK:
        cu,coh=CK[(s,x.branch)]
        if x.on_hand<coh: flags.append(f"Kevin's contract list: {cu}, contract minimum {coh}, on hand {x.on_hand}")
        if x.on_hand<0: v=('count the shelf',None,f'contract item ({cu}); on hand {x.on_hand}: count the shelf, fix the count, then decide',b+' + Kevin')
        elif st=='D': v=('comes to Kevin',None,f"contract item ({cu}), D since {pl.discontinue_date}: the customer must approve any substitute",'Kevin')
        elif rush: v=('call first',None,f'contract item ({cu}), contract minimum {coh}, on hand {x.on_hand}; '+rush_ev(s)+ltxt,b)
        elif x.on_hand<coh and act is not None and act>7: v=('comes to Kevin',None,f"{cu} short today ({x.on_hand} against {coh}); {x.supplier} is {act:.0f} days now (Girder says {lt}), so a PO does not fix this week; {b} calls Kevin first, he decides on the freight",'Kevin + '+b)
        else:
            q=max(g,coh-pos)
            v=('order to what the contract says',q,f'{cu} contract says {coh} on hand; Girder\'s {g} falls short',b) if q>g else ('order as printed',g,f'{cu} contract item; Girder\'s {g} covers the contract minimum {coh}',b)
    # Rule 2 D
    elif st=='D':
        po=f'; {x.on_order} on order: the PO sits open forever and the supplier never ships' if x.on_order>0 else ''
        if rep and rush: v=('call first',None,f'D, replacement {rep}; '+rush_ev(s)+po,b)
        elif rep: v=('order the replacement',g,f'D since {pl.discontinue_date}; order {rep} at the quantity the system wanted'+po,b)
        else: v=("don't order, it's D",0,f"hand back to {b}: {x.supplier}, D since {pl.discontinue_date}: write it down and find one, that's buyer work, don't guess"+(('; '+rush_ev(s)) if rush else '')+po,b)
    elif x.on_hand<0: v=('count the shelf',None,f'on hand {x.on_hand} at {x.branch}: count the shelf, fix the count, then decide',b)
    elif x.sales_12m==0: v=('order nothing, write it on the reset list',0,'sold nothing in twelve months at this branch: Kevin decides in January if it stays',b+' + Kevin (reset list)')
    elif rush: v=('call first',None,'the number comes after the call, never before; '+rush_ev(s)+ltxt,b)
    elif moq>x.sales_12m: v=('buyer decides: take the minimum, source it elsewhere or let it go',None,f"{x.supplier} minimum is {moq}, more than a year of sales ({x.sales_12m} in 12 months): {b} decides whether to take the minimum, source it elsewhere or let it go",b)
    elif x['max']==0: v=('order to min',max(0,x['min']-pos),'min and no max, set up and never finished: order to the min',b)
    elif x['min']>x['max']: v=('order to the bigger number',max(0,x['min']-pos),f"min {x['min']} above max {x['max']}, keyed backwards: tell Kevin so it gets fixed",b+" + Kevin (fix list)")
    elif shelf:
        cap=max(0,x.sales_12m-pos); q=min(g,cap)
        v=("don't order more than a year's worth",q,f'shelf life {shelf} months; 12-month sales {x.sales_12m}, stock {pos}',b) if q<g else ('order as printed',g,f'shelf life {shelf} months; stays within a year\'s worth',b)
    elif s in GLOVES: v=('order to max',max(0,x['max']-pos),'Prairie Harvest glove: I order to the max on every glove line that was on that order',b)
    elif x['max']>0 and g>=2*x['max']: v=('order to max',max(0,x['max']-pos),f"check F7 first: max {x['max']}, suggested {g}, 12-month sales {x.sales_12m}; go look at the sales history screen (F7 from the item) and look for one big line",b)
    elif x['max']>0 and g>1.5*x['max']: v=('order as printed',g,f"check F7 first: max {x['max']}, suggested {g}, 12-month sales {x.sales_12m}; go look at the sales history screen (F7 from the item) and look for one big line",b)
    elif act is not None and lt>0 and act>=2*lt:
        add=math.ceil((act-lt)*x.sales_12m/365)
        v=('order up for the extra days',g+add,f"{x.supplier} takes {act:.0f} days now against Girder's {lt}: Girder's {g} covers the old lead time, add {add} for the extra {act-lt:.0f} days; fix the lead time in Girder",b+' + Kevin (fix list)')
    else: v=('order as printed',g,f"suggested {g} against max {x['max']}: if it's close, fine, order it",b)
    verdict,q,reason,who=v
    if flags: reason+=' | '+'; '.join(flags); who=who if 'Kevin' in who else who+' + Kevin (contract list)'
    return dict(item=s,name=x.description,branch=x.branch,girder_qty=g,verdict=verdict,qty='' if q is None else int(q),reason=reason,goes_to=who)
src=e if N is None else e.head(N)
out=pd.DataFrame([decide(x) for _,x in src.iterrows()])
printed=set(zip(e.sku,e.branch))
missing=C[[ (a,b) not in printed for a,b in zip(C.sku,C.branch)]].assign(goes_to=lambda d:d.branch.map(BUYER),check="check the on hand screen against what the contract says")
OUT=os.environ.get('OUT','output'); os.makedirs(OUT,exist_ok=True)
out.to_csv(OUT+'/out.csv',index=False); missing.to_csv(OUT+'/missing.csv',index=False)
if N is None:
    with pd.ExcelWriter(OUT+'/reorder_recommendations.xlsx') as w:
        out.to_excel(w,sheet_name='All lines',index=False)
        out[out.goes_to.str.startswith('Dee')].to_excel(w,sheet_name='Dee (JOL, RKF)',index=False)
        out[out.goes_to.str.startswith('Pete')].to_excel(w,sheet_name='Pete (FTW)',index=False)
        out[out.goes_to.str.contains('Kevin')].to_excel(w,sheet_name='Kevin',index=False)
        missing.to_excel(w,sheet_name='Contract items not printed',index=False)
pd.set_option('display.width',300,'display.max_colwidth',200)
print(out.to_string(index=False)); print(); print(missing.to_string(index=False))
