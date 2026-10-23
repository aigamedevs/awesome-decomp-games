#!/usr/bin/env python3
"""Fetch the Recompendium catalogue (https://recompendium.com, data repo Nio03/unricopie) -> raw/recompendium.json.
Recompendium's catalogue data is CC BY-SA 4.0 (since 2026-10-17). We copy facts only (game name, project repo URL,
console, category) and never its descriptions. Kept: recomps, ports and decomps with a GitHub repo, 10+ stars in
Recompendium's own stats.json (build.py re-applies the 10-star bar and fork check on live GitHub data), not marked
forkOf, and game-specific tools listed in TOOLS. Repos in overrides.json "recompendium_exclude" are skipped.
Downloads are retried (SSL EOFs happen) and on failure the previous raw/recompendium.json is kept."""
import io, json, os, re, sys, tarfile, time, requests, yaml
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
URL = "https://codeload.github.com/Nio03/unricopie/tar.gz/refs/heads/main"
UA = {"User-Agent": "awesome-decomp-games-refresh (+https://github.com/aigamedevs/awesome-decomp-games)"}
HINT = {"recomps": "recomp", "decomps": "decomp", "ports": "port", "tools": "tool"}
PORT_HINT = {"fan-remake": "remake", "game-engine": "remake", "decomp-port": "port", "source-port": "port", "native-layer": "port"}
TOOLS = {"Matteo842/CrashBandicoot-Launcher"}  # game-specific tools only; general recompilers/launchers/libraries are skipped
CONS = {"x360": "Xbox 360", "xboxone": "Xbox One", "megadrive": "Genesis", "megacd": "Sega CD", "sms": "Master System", "gamegear": "Game Gear",
        "virtualboy": "Virtual Boy", "neogeo": "Neo Geo", "wiiu": "Wii U", "pc98": "PC-98", "other": ""}
BAD = re.compile(r"\b(iso|roms?|rom ?pack|emulator)\b", re.I)

def download():
    for i in range(6):
        try:
            r = requests.get(URL, headers=UA, timeout=120); r.raise_for_status(); return r.content
        except Exception as ex:
            print(f"WARN recompendium download attempt {i+1}: {ex}", file=sys.stderr); time.sleep(5 * (i + 1))
    raise SystemExit("recompendium download failed; keeping previous raw/recompendium.json")

def main():
    over = json.load(open(os.path.join(ROOT, "data", "overrides.json")))
    skip = {s.lower() for s in over.get("recompendium_exclude", [])}
    tf = tarfile.open(fileobj=io.BytesIO(download()), mode="r:gz")
    files = {m.name.split("/", 1)[1]: m for m in tf.getmembers() if m.isfile() and "/" in m.name}
    stats = json.load(tf.extractfile(files["src/data/stats.json"]))
    out, n = [], 0
    for path, m in sorted(files.items()):
        mm = re.match(r"src/data/(recomps|ports|decomps|tools)/[^/]+\.ya?ml$", path)
        if not mm: continue
        n += 1
        y = yaml.safe_load(tf.extractfile(m)) or {}
        repo = (y.get("repo") or "").strip().strip("/")
        if not re.fullmatch(r"[\w.-]+/[\w.-]+", repo) or repo.lower() in skip or y.get("forkOf"): continue
        kind = mm.group(1)
        if kind == "tools" and repo not in TOOLS: continue
        if (stats.get(repo) or {}).get("stars", 0) < 10: continue
        if BAD.search(y.get("name", "")): continue
        cons = y.get("console") or ((y.get("consoles") or [None])[0])
        hint = PORT_HINT.get(y.get("category"), "port") if kind == "ports" else HINT[kind]
        out.append({"name": y.get("name", "").strip(), "url": f"https://github.com/{repo}", "platform": CONS.get(cons, cons or ""),
                    "hint": hint, "kind": kind, "ai": "ai-assisted" in (y.get("tags") or []) or "ai-generated" in (y.get("tags") or [])})
    if len(out) < 100: raise SystemExit(f"only {len(out)} recompendium entries parsed; keeping previous raw/recompendium.json")
    os.makedirs(os.path.join(ROOT, "raw"), exist_ok=True)
    json.dump(out, open(os.path.join(ROOT, "raw", "recompendium.json"), "w"), indent=1, ensure_ascii=False)
    print(f"recompendium: {n} catalogue files, {len(out)} GitHub entries kept")
if __name__ == "__main__": main()
