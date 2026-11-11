"""Evals for the Monday reorder agent.

Usage:
    python3 evals.py                 # 30-line graded test (Door 3)
    python3 evals.py --full PATH     # also the full-list evals; PATH is the full ERP list CSV

Runs agent.py as a subprocess, so the agent is tested exactly as a user runs it.
Exits 1 if any check fails.
"""
import argparse, os, re, shutil, subprocess, sys, tempfile
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, 'data')
RESULTS = []

# Expected counts on the full October 12 list, from docs/agent_instructions_v3.md (v3.1).
EXPECTED_COUNTS = {
    'order as printed': 1184, 'call first': 221, "don't order, it's D": 85, 'order to max': 67,
    'buyer decides: take the minimum, source it elsewhere or let it go': 62,
    'order the replacement': 42, 'order to the bigger number': 26, 'order to min': 17,
    'order nothing, write it on the reset list': 16, 'count the shelf': 12,
    'order to what the contract says': 6, 'comes to Kevin': 1, "don't order more than a year's worth": 1,
}
# Lines with known answers, from docs/prd_v3.md section 3: (item, branch, verdict, qty).
KNOWN_TEST = [
    ('BRG-10009', 'FTW', 'comes to Kevin', ''),
    ('PLM-10015', 'JOL', 'buyer decides: take the minimum, source it elsewhere or let it go', ''),
    ('CUT-10052', 'JOL', 'order up for the extra days', '29'),
]
KNOWN_FULL = [
    ('SAF-10018', 'JOL', 'order to max', '20'),
    ('FAS-10007', 'JOL', "don't order, it's D", '0'),
    ('FAS-10007', 'RKF', "don't order, it's D", '0'),
    ('MHD-10011', 'RKF', 'call first', ''),
    ('CUT-10043', 'JOL', 'comes to Kevin', ''),
    ('ADH-10009', 'JOL', "don't order more than a year's worth", '6'),
]


def check(name, passed, detail):
    RESULTS.append((name, passed, detail))


def run_agent(folder, n=None):
    out = tempfile.mkdtemp()
    cmd = [sys.executable, os.path.join(HERE, 'agent.py'), folder] + ([str(n)] if n else [])
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, env={**os.environ, 'OUT': out})
    read = lambda f: pd.read_csv(os.path.join(out, f), dtype=str, keep_default_na=False)
    return read('out.csv'), read('missing.csv')


def read_erp(path):
    banner = 'SUGGESTED PURCHASE ORDER REPORT' in open(path, errors='ignore').readline()
    e = pd.read_csv(path, skiprows=1 if banner else 0, dtype=str, keep_default_na=False)
    e = e[e.branch.isin(['JOL', 'RKF', 'FTW'])].copy()
    for c in ['on_hand', 'on_order', 'sales_12m']:
        e[c] = e[c].astype(float).astype(int)
    return e


def contract_minimums():
    mins, branch = {}, None
    for line in open(os.path.join(DATA, 'customer_contract_stock_clauses.txt')):
        for prefix, br in [('1. MIDVALE', 'FTW'), ('2. STARR', 'RKF'), ('3. LOCKPORT', 'JOL')]:
            if line.startswith(prefix):
                branch = br
        m = re.match(r'^([A-Z]{3}-\d{5})\s+(.*?)\s+(\d+)\s*$', line.rstrip('\n'))
        if m and branch:
            mins[(m.group(1), branch)] = int(m.group(3))
    return mins


def known_answers(label, out, cases):
    got = {(r['item'], r.branch): (r.verdict, r.qty) for _, r in out.iterrows()}
    wrong = [f'{s} {b}: got {got.get((s, b))}' for s, b, v, q in cases if got.get((s, b)) != (v, q)]
    check(f'{label}: known answers', not wrong, '; '.join(wrong) or f'{len(cases)} of {len(cases)}')


def hard_limits(label, out, erp):
    """Rules from the spec's Never list that must hold on every line."""
    price = pd.read_csv(os.path.join(DATA, 'supplier_price_list_2026-10.csv'), dtype=str,
                        keep_default_na=False).set_index('sku')
    discontinued = set(price.index[price.status == 'D'])
    mins = contract_minimums()
    m = out.merge(erp, left_on=['item', 'branch'], right_on=['sku', 'branch'])
    qty = pd.to_numeric(m.qty, errors='coerce').fillna(0).astype(int)
    rules = {
        'no discontinued item ordered': m['item'].isin(discontinued) & (qty > 0)
                                        & (m.verdict != 'order the replacement'),
        'no order on negative stock': (m.on_hand < 0) & (qty > 0),
        'no order on zero sales': (m.sales_12m == 0) & (qty > 0),
        'no quantity on a call-first or hand-back line': m.verdict.isin(
            ['call first', 'comes to Kevin', 'count the shelf',
             'buyer decides: take the minimum, source it elsewhere or let it go']) & (m.qty != ''),
        'no contract item ordered below its minimum': pd.Series(
            [(r['item'], r.branch) in mins and r.qty != '' and r.on_hand >= 0
             and r.on_hand + r.on_order + int(r.qty) < mins[(r['item'], r.branch)]
             for _, r in m.iterrows()], index=m.index),
    }
    for rule, bad in rules.items():
        check(f'{label}: {rule}', not bad.any(),
              ', '.join(m['item'][bad] + ' ' + m.branch[bad]) or f'0 violations on {len(m)} lines')


def graded_test():
    out, _ = run_agent(DATA, 30)
    scored = pd.read_csv(os.path.join(DATA, 'door3_scored_run.csv'), dtype=str, keep_default_na=False)
    hits = (scored.result == 'Hit').sum()
    check('Test: score against the manager', hits == len(scored), f'{hits} of {len(scored)} scored Hit')
    m = scored.merge(out, left_on=['item_id', 'branch'], right_on=['item', 'branch'], suffixes=('_s', ''))
    norm = lambda s: s.str.replace(r'\.0$', '', regex=True)
    diff = m[(m.verdict_s != m.verdict) | (norm(m.qty_s) != m.qty)]
    check('Test: agent reproduces the scored run', len(m) == len(scored) and diff.empty,
          ', '.join(diff.item_id) or f'{len(m)} of {len(scored)} lines identical')
    check('Test: covers every verdict', out.verdict.nunique() == 14, f'{out.verdict.nunique()} of 14 verdicts')
    known_answers('Test', out, KNOWN_TEST)
    hard_limits('Test', out, read_erp(os.path.join(DATA, 'screen_these_30.csv')))


def full_list(erp_path):
    # The agent finds inputs by their first line, so the folder must hold only one order list.
    folder = tempfile.mkdtemp()
    for f in ['supplier_price_list_2026-10.csv', 'rush_freight_log_2025.csv',
              'customer_contract_stock_clauses.txt']:
        shutil.copy(os.path.join(DATA, f), folder)
    shutil.copy(erp_path, folder)
    out, missing = run_agent(folder)
    counts = out.verdict.value_counts().to_dict()
    off = [f'{v}: {counts.get(v, 0)} vs {n}' for v, n in EXPECTED_COUNTS.items() if counts.get(v, 0) != n]
    check('Full list: verdict counts', not off, '; '.join(off) or f'13 of 13 match on {len(out)} lines')
    extras = [('flagged as printed', ((out.verdict == 'order as printed') & out.reason.str.contains('check F7')).sum(), 32),
              ("on Kevin's contract list", out.reason.str.contains("Kevin's contract list").sum(), 21),
              ('contract items not printed', len(missing), 18)]
    for name, got, want in extras:
        check(f'Full list: {name}', got == want, f'{got} (expected {want})')
    known_answers('Full list', out, KNOWN_FULL)
    hard_limits('Full list', out, read_erp(erp_path))


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--full', metavar='PATH', help='the full October 12 ERP list (not published)')
    args = ap.parse_args()
    graded_test()
    if args.full:
        full_list(args.full)
    width = max(len(n) for n, _, _ in RESULTS)
    for name, passed, detail in RESULTS:
        print(f"{'PASS' if passed else 'FAIL'}  {name.ljust(width)}  {detail}")
    failed = sum(not p for _, p, _ in RESULTS)
    print(f'\n{len(RESULTS) - failed} of {len(RESULTS)} checks passed')
    sys.exit(1 if failed else 0)
