#!/usr/bin/env python3
"""Fetch the public Quiver Launcher catalog (api.quiverlauncher.com/api/v1) -> raw/quiver.json.
Walks /apps (cursor-paginated), then /apps/{slug} for the GitHub repository. Slugs listed in
data/overrides.json "quiver_exclude" are skipped (emulators, general engines, tools, legally questionable ports)."""
import json, os, time, requests
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
API = "https://api.quiverlauncher.com/api/v1"
UA = {"User-Agent": "awesome-decomp-games-refresh (+https://github.com/aigamedevs/awesome-decomp-games)"}
def main():
    over = json.load(open(os.path.join(ROOT, "data", "overrides.json")))
    skip = set(over.get("quiver_exclude", []))
    items, cur = [], None
    for _ in range(100):
        r = requests.get(API + "/apps", params={"cursor": cur} if cur else {}, headers=UA, timeout=30); r.raise_for_status()
        d = r.json(); items += d["items"]
        if d.get("isDone") or not d.get("nextCursor"): break
        cur = d["nextCursor"]; time.sleep(0.3)
    out = []
    for i in items:
        if i["slug"] in skip: continue
        try:
            p = requests.get(f"{API}/apps/{i['slug']}", headers=UA, timeout=30).json().get("project") or {}
        except Exception as ex:
            print("WARN detail", i["slug"], ex); continue
        if p.get("provider") != "github" or not p.get("repository"): continue
        out.append({"slug": i["slug"], "name": i["name"], "project": i.get("projectName") or p.get("name"),
                    "repo": p["repository"], "aiLevel": i.get("aiLevel"), "tags": i.get("tags", []),
                    "consoles": i.get("consoles", []), "description": i.get("description", ""), "supportedOS": i.get("supportedOS")})
        time.sleep(0.15)
    json.dump(out, open(os.path.join(ROOT, "raw", "quiver.json"), "w"), indent=1, ensure_ascii=False)
    print(f"quiver: {len(items)} apps, {len(out)} with github repo")
if __name__ == "__main__": main()
