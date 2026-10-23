#!/usr/bin/env python3
"""Mirror every browser-playable entry in data/games.json that has no local backup in /workspace/downloads.
Usage: backup_browser.py [--dry] [--jobs N] [--only id,id]"""
import json, os, re, subprocess, sys, urllib.parse, time, concurrent.futures as cf
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITES = '/workspace/downloads'; T = SITES + '/tools'; CAP = 6 * 1024**3
args = sys.argv[1:]; dry = '--dry' in args
jobs = int(args[args.index('--jobs')+1]) if '--jobs' in args else 3
only = set(args[args.index('--only')+1].split(',')) if '--only' in args else None
SKIP_HOSTS = ('github.com',)
TRACK = re.compile(r'google|doubleclick|analytics|gtag|facebook|cloudflareinsights|clarity|hotjar|adservice|fonts\.g|sentry|posthog|plausible|umami', re.I)

def norm(u):
    s = urllib.parse.urlsplit(u.strip()); return (s.netloc.lower().removeprefix('www.') + s.path.rstrip('/')).lower()

def known():
    m = {}
    for l in open(f'{SITES}/urls.tsv'):
        if '\t' in l: n, u = l.rstrip('\n').split('\t', 1); m[norm(u)] = n
    return m

def du(p): return sum(os.path.getsize(os.path.join(d, f)) for d, _, fs in os.walk(p) for f in fs if not os.path.islink(os.path.join(d, f)))

def assets(p):
    big = {}
    for d, _, fs in os.walk(p):
        for f in fs:
            e = f.lower().split('?')[0].rsplit('.', 1)[-1]
            if e in ('wasm','data','pak','pk3','js','mjs','bin','zip','wad','unityweb','pck','mpq','iso','img','7z','bsp','br','gz'):
                try: s = os.path.getsize(os.path.join(d, f))
                except OSError: continue
                big[e] = big.get(e, 0) + s
    return big

def slug_for(g, used):
    s = re.sub(r'[^a-z0-9]+', '-', g['id'].lower()).strip('-')[:40]
    b, i = s, 2
    while s in used: s = f'{b}-{i}'; i += 1
    return s

def done_ids():
    try: return {json.loads(l)['id'] for l in open(f'{SITES}/logs/backup_status.jsonl')}
    except FileNotFoundError: return set()

def next_idx():
    nums = [int(l.split()[1]) for l in open(f'{SITES}/sites.txt') if len(l.split()) == 2]
    return max(nums + [0]) + 1

def run(cmd, log, timeout):
    with open(log, 'a') as f:
        f.write(f'\n$ {" ".join(cmd)}\n'); f.flush()
        try: return subprocess.run(cmd, stdout=f, stderr=subprocess.STDOUT, timeout=timeout).returncode
        except subprocess.TimeoutExpired: f.write('TIMEOUT\n'); return 124

MIN_FREE = 10 * 1024**3
def free(): st = os.statvfs(SITES); return st.f_bavail * st.f_frsize

def backup(g, slug, idx):
    if free() < MIN_FREE:
        r = dict(id=g['id'], slug=slug, url=g['play_url'], status='skipped', reason=f'low disk ({free()/1e9:.1f} GB free < 10 GB)', bytes=0, at=time.strftime('%F %T'))
        open(f'{SITES}/logs/backup_status.jsonl', 'a').write(json.dumps(r) + '\n'); print('skipped', slug, r['reason'], flush=True); return r
    url = g['play_url']; root = f'{SITES}/{slug}'; log = f'{SITES}/logs/{slug}.backup.log'
    sp = urllib.parse.urlsplit(url); origin = f'{sp.scheme}://{sp.netloc}'
    path = sp.path or '/'
    if sp.query: path += '?' + sp.query
    if not os.path.isdir(root) or du(root) < 50_000: run(['bash', f'{SITES}/mirror.sh', slug, url], log, 5700)
    if du(root) < CAP: run(['python3', f'{T}/fill.py', slug, url], log, 3600)
    try:
        reqs = json.load(open(f'{SITES}/logs/{slug}.requests.json'))
        hosts = sorted({urllib.parse.urlsplit(u).netloc for u in reqs if u.startswith('https://')
                        and urllib.parse.urlsplit(u).netloc != sp.netloc and not TRACK.search(u)
                        and re.search(r'\.(js|mjs|wasm|data|pak|pk3|bin|json|zip|css|glb|ogg|mp3|png|jpe?g|webp)(\?|$)', urllib.parse.urlsplit(u).path, re.I)})
    except Exception: hosts = []
    if hosts: run(['python3', f'{T}/localize.py', slug] + hosts, log, 600)
    if du(root) < CAP:
        env = dict(os.environ, ROUNDS='3')
        with open(log, 'a') as f:
            try: subprocess.run(['python3', f'{T}/repair.py', slug, origin, str(18400 + idx), path], stdout=f, stderr=subprocess.STDOUT, timeout=3600, env=env)
            except subprocess.TimeoutExpired: f.write('repair TIMEOUT\n')
    try: rep = json.load(open(f'{SITES}/logs/{slug}.repair.json'))
    except Exception: rep = {}
    size = du(root); a = assets(root); errs = len(rep.get('local_errors', []))
    heavy = sum(v for k, v in a.items() if k != 'js'); js = a.get('js', 0) + a.get('mjs', 0)
    if size < 50_000: st, why = 'failed', 'nothing usable downloaded'
    elif size >= CAP: st, why = 'partial', 'hit 6 GB cap'
    elif errs == 0 and (heavy > 1_000_000 or js > 500_000): st, why = 'ok', ''
    elif heavy > 1_000_000 or js > 500_000: st, why = 'partial', f'{errs} local 404s on replay'
    else: st, why = 'partial', 'page only, no game data found (likely streamed/server-side)'
    r = dict(id=g['id'], slug=slug, url=url, status=st, reason=why, bytes=size, assets=a, local_errors=errs, ext_hosts=rep.get('external'), at=time.strftime('%F %T'))
    with open(f'{SITES}/logs/backup_status.jsonl', 'a') as f: f.write(json.dumps(r) + '\n')
    print(st, slug, f'{size/1e6:.0f}MB', why, flush=True); return r

def main():
    games = json.load(open(f'{REPO}/data/games.json'))['games']
    k = known(); used = set(k.values()) | set(os.listdir(SITES)); todo = []
    try: drive = {l.split('\t')[0] for l in open(f'{SITES}/drive-index.tsv') if '\t' in l}  # already uploaded to Drive
    except OSError: drive = set()
    have = lambda s: s in drive or os.path.isdir(f'{SITES}/{s}')
    for g in games:
        u = g.get('play_url')
        if not u or not g.get('browser_playable', True) or urllib.parse.urlsplit(u).netloc in SKIP_HOSTS: continue
        if only and g['id'] not in only: continue
        n = norm(u); host = n.split('/')[0]
        hit = next((v for kk, v in k.items() if n == kk or n.startswith(kk + '/')), None)
        if hit and (hit in drive or (os.path.isdir(f'{SITES}/{hit}') and du(f'{SITES}/{hit}') > 50_000)): continue
        same = next((v for kk, v in k.items() if kk.split('/')[0] == host), None)
        if same and have(same) and n == host: continue  # host root already mirrored
        if same and have(same):
            if g['id'] in done_ids(): continue   # extra page on an already-mirrored host
            todo.append((g, same)); continue
        slug = k.get(n) or slug_for(g, used); used.add(slug); todo.append((g, slug))
    print(len(todo), 'to back up:', [s for _, s in todo], flush=True)
    if dry: return
    idx = next_idx(); plan = []
    for g, slug in todo:
        if slug not in set(k.values()) and norm(g['play_url']) not in k:
            open(f'{SITES}/urls.tsv', 'a').write(f'{slug}\t{g["play_url"]}\n')
        if slug not in {l.split()[0] for l in open(f'{SITES}/sites.txt') if l.strip()}:
            open(f'{SITES}/sites.txt', 'a').write(f'{slug} {idx}\n')
        plan.append((g, slug, idx)); idx += 1
    groups = {}
    for t in plan: groups.setdefault(t[1], []).append(t)
    with cf.ThreadPoolExecutor(jobs) as ex: list(ex.map(lambda grp: [backup(*t) for t in grp], groups.values()))

if __name__ == '__main__': main()
