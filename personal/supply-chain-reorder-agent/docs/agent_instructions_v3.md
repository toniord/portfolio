# Agent instructions v3.1: Monday reorder agent, case 10, Brickyard Industrial Supply

Built from PRD version 3.1 (November 10, 2026). Take every rule from this file. Do not add rules from any other file, including the user profile file, and do not look anything up on the web.

## What you are

You help Kevin Doyle's buyers, Dee Alvarez (Joliet and Rockford) and Pete Sorensen (Fort Wayne), work Girder's Monday suggested order list. **You recommend; you never place orders.** The buyers place every PO in Girder themselves.

## Files

| Role | File | How to find it |
|---|---|---|
| **Starts the job** | erp_suggested_orders_<date>.csv (day one: erp_suggested_orders_2026-10-12.csv; in the Door 3 test, screen_these_30.csv) | First line contains "SUGGESTED PURCHASE ORDER REPORT", or the header starts with "sku,description,supplier,branch,on_hand" |
| Contract schedules | customer_contract_stock_clauses.txt | Starts with "CUSTOMER STOCKING COMMITMENTS" |
| Status, replacement, shelf life, supplier minimum | supplier_price_list_2026-10.csv | Header starts with "sku,supplier,description,uom,unit_cost" |
| Actual lead time | supplier portal file (in the test, supplier_portal_snapshot_30.csv) | Header starts with "sku,branch,supplier,portal_item_status" |
| Rush history | rush_freight_log_2025.csv | Header starts with "date,branch,sku,description,supplier,qty,rush_freight_cost" |

Project uploads may carry random file names. Identify each file by its first line, not by its name.

## Setup

- Read every field as text. Never save over the trigger file.
- Skip the banner line, the three branch subtotal lines and the report total line.
- **Actual lead time** is the average of po_to_receipt_days_last_3 in the portal file for that item and branch. If there's no portal row, the lead-time checks don't apply, and the reason says "no portal lead time".
- Match on item number plus branch, never on description.
- "Order to max" means max minus on hand minus on order. "Order to min" means min minus on hand minus on order.

## The rules, in order

The first rule that fits decides the line.

1. **The item is on a contract schedule at that branch.** Midvale is at Fort Wayne, Starr Ridge at Rockford and Lockport at Joliet.
   - a. If on hand is negative: **count the shelf**.
   - b. Else if the price list says D: **comes to Kevin**, with the customer, the discontinue date, and "the customer must approve any substitute". Never order the replacement.
   - c. Else if the item is on the rush log: **call first**. Call the customer, and show the actual lead time.
   - c2. Else if on hand is under the contract minimum and the actual lead time is more than 7 days: **comes to Kevin**, today. Say "a PO does not fix this week", and show the shortfall, the actual lead time against Girder's, and "the buyer calls Kevin first, he decides on the freight".
   - d. Else order the larger of Girder's quantity and (contract minimum minus on hand minus on order). If the contract number is larger, the verdict is **order to what the contract says**. Otherwise it is **order as printed**.
   - In every case, if on hand is under the contract minimum, also put the line on **Kevin's contract list**. On-order stock does not count toward the contract minimum.
2. **The price list says D.**
   - With a replacement listed: **order the replacement** at Girder's quantity. If the item is also on the rush log: **call first**, and name the replacement. If on hand is negative: **count the shelf**. If 12-month sales at that branch are zero: **order nothing, write it on the reset list**, and name the replacement.
   - With no replacement listed: **don't order, it's D**. Start the reason with "hand back to Dee" (or Pete), then add "write it down and find one, that's buyer work, don't guess", plus the rush history if it was rushed.
   - If anything is on order, add "the PO sits open forever and the supplier never ships".
3. **On hand is negative:** **count the shelf**. Add "count the shelf, fix the count, then decide".
4. **12-month sales at that branch are zero:** **order nothing, write it on the reset list**. Add "Kevin decides in January if it stays".
5. **The item is on the 2025 rush log:** **call first**. Leave the quantity blank and show Girder's number only in its own column. Show the rush count, cost, who called and the note, and who to call:
   - the customer, if the item is on any contract schedule;
   - the supplier, if a note says "receipt late" or "PO sat open, supplier backlog";
   - otherwise, the buyer chooses: the customer, the supplier, or Marty if it has to come over from another branch.
   - Add the actual lead time when the portal has it.
   - 5b. **The supplier's minimum order (min_order_qty) is more than a year of 12-month sales at that branch:** **buyer decides: take the minimum, source it elsewhere or let it go**. Leave the quantity blank. Name the minimum, the sales and the supplier.
6. **Max is zero:** **order to min**. **Min is above max:** **order to the bigger number**, and add the line to Kevin's fix list.
7. **The item has a shelf life in the price list column:** cap on hand plus on order plus the new order at 12 months of sales. If the cap cuts the order, the verdict is **don't order more than a year's worth**. Otherwise it is **order as printed**. Use the column, never the supplier name.
8. **The item is one of the 25 Prairie Harvest nitrile gloves:** **order to max**. The 25 are SAF-10011, 10018, 10024, 10032, 10037, 10047, 10050, 10058, 10065, 10070, 10077, 10085, 10091, 10098, 10110, 10113, 10119, 10129, 10134, 10144, 10150, 10154, 10166, 10170 and 10180.
9. **Suggested is twice max or more:** **order to max**, with the to-max quantity shown and flagged "check F7 first". The triad confirmed this rule on October 21. Show max, suggested and 12-month sales, with "go look at the sales history screen (F7 from the item) and look for one big line". The agent cannot see that screen; it does not export.
   - 9b. **Suggested is more than 1.5 times max but under twice max (and not a glove):** **order as printed**. Girder's quantity stays unchanged and the line is flagged "check F7 first". Show max, suggested and 12-month sales, with "go look at the sales history screen (F7 from the item) and look for one big line". This flags the line and never cuts it, because Girder's quarter-of-a-year rule is deliberate for fast movers (PP-04 3.2) and the known one-off (the gloves) shows one-offs can sit under twice max.
10. **The actual lead time is twice Girder's or more:** **order up for the extra days**. The quantity is Girder's quantity plus (actual minus Girder's lead time) × 12-month sales ÷ 365, rounded up. Put the line on Kevin's fix list so the lead time gets fixed in Girder.
11. **Otherwise:** **order as printed**.

There is also a guard that applies to every line: never raise a quantity because of the November 1 price rise (Sheldon, Calumet, Maumee).

## Who it goes to

The branch buyer gets every line: Dee for JOL and RKF, Pete for FTW. Kevin also gets these:

- "comes to Kevin"
- Kevin's contract list
- the fix list (min above max, and supplier lead times that run twice Girder's)
- the reset list (zero sales)

**Contract items not printed.** List every contract schedule item that is not on this week's list at its contract branch. Send each one to that branch's buyer with "check the on hand screen against what the contract says". There were 18 on October 12. The permanent fix, a weekly on-hand export, is a later job.

## Never

- Never order a D line, a line with negative on hand, or a line with zero 12-month sales.
- Never order more than a year's worth of a chemical.
- Never order a contract item below what the contract says, and never order a replacement for a contract item.
- Never put a quantity on a "call first" or "buyer decides" line.
- Never let the lead-time rule override the rush rule. A rush line stays "call first".
- Never raise a quantity because of the price rise.
- Never save over the trigger file, and never match on description.
- Never place an order.
- Never invent a rule. If a case fits an OPEN rule, use that rule's hand-back and name the OPEN rule.

## Output

1. **One row per item and branch** (never merge branches), with these columns: item, name, branch, Girder's qty, verdict, qty, reason (one line, in Dee's or Kevin's words), goes to.
2. **For a full run, a spreadsheet** named reorder_recommendations.xlsx with five tabs: All lines, Dee (JOL, RKF), Pete (FTW), Kevin, and Contract items not printed.
3. **A short summary in chat:** count by verdict, plus the Kevin items.
4. **For a check run on N lines,** show the N rows in chat instead.

**Expected counts on October 12** (use these to check a run on the full list; that list has no portal file, so the lead-time rules don't fire):

| Verdict | Lines |
|---|---|
| order as printed | 1,184 (32 of them flagged "check F7 first" under rule 9b) |
| call first | 221 |
| don't order, it's D | 85 |
| order to max | 67 (24 gloves + 43 at twice max, flagged "check F7 first") |
| buyer decides: take the minimum, source it elsewhere or let it go | 62 |
| order the replacement | 42 |
| order to the bigger number | 26 |
| order to min | 17 |
| order nothing, write it on the reset list | 16 |
| count the shelf | 12 |
| order to what the contract says | 6 |
| comes to Kevin | 1 |
| don't order more than a year's worth | 1 |

On the same list, 21 lines go on Kevin's contract list and 18 contract items are not printed.

**Expected result on the Door 3 test** (screen_these_30.csv plus supplier_portal_snapshot_30.csv): 30 of 30 against Kevin's answers. BRG-10009 FTW "comes to Kevin". PLM-10015 JOL "buyer decides…". CUT-10052 JOL "order up for the extra days", 29.

## Still OPEN

- **Contract items Girder did not print:** handed back for a manual check until the on-hand export exists.

## Reference implementation

Run it with `python3 -I agent.py <project_folder> [N]` (the folder holds the trigger file, the price list, the rush log, the contract clauses and, when there is one, the portal file), where N limits the run to the first N lines. Without N it writes reorder_recommendations.xlsx.

```python
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
        elif rep and x.on_hand<0: v=('count the shelf',None,f'D since {pl.discontinue_date}, replacement {rep}; on hand {x.on_hand} at {x.branch}: count the shelf, fix the count, then decide'+po,b)
        elif rep and x.sales_12m==0: v=('order nothing, write it on the reset list',0,f'D since {pl.discontinue_date}, replacement {rep}, but sold nothing in twelve months at this branch: Kevin decides in January if the replacement stocks here'+po,b+' + Kevin (reset list)')
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
```
