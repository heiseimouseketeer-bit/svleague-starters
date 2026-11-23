#!/usr/bin/env python3
"""data/starters.json を compact 形式に変換し、template.html の `var MATCHES = [...];` を置換して index.html を出力する。"""
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def compact(m):
    out = {
        "id": m["id"], "r": m["round"], "g": m["game"], "d": m["date"], "wd": m["weekday"],
        "h": m["home"], "a": m["away"], "v": m["venue"], "vn": m.get("venue_note", ""),
        "st": m["status"], "hs": m["home_sets"], "as": m["away_sets"], "ss": m["set_scores"],
        "note": m.get("note", ""), "du": m["detail_url"], "fu": m["form_b_url"], "L": [],
    }
    for lu in m["lineups"]:
        out["L"].append({
            "t": lu["team"], "s": lu["set"],
            "p": [[s["number"], s["name"]] for s in sorted(lu["starters"], key=lambda x: x["position"])],
            "lb": [[l["number"], l["name"], l["flag"]] for l in lu["liberos"]],
            "n": lu.get("note", ""),
        })
    return out


def main():
    data = json.loads((ROOT / "data" / "starters.json").read_text(encoding="utf-8"))
    matches = [compact(m) for m in data["matches"]]
    for m in data["matches"]:  # 最低限の整合チェック
        for lu in m["lineups"]:
            if len(lu["starters"]) != 6:
                sys.exit("先発が6人でない: %s %s set%s" % (m["id"], lu["team"], lu["set"]))
    payload = json.dumps(matches, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    tpl = (ROOT / "template.html").read_text(encoding="utf-8")
    new, n = re.subn(r"var MATCHES = \[.*?\];", lambda _: "var MATCHES = " + payload + ";", tpl, count=1, flags=re.S)
    if n != 1:
        sys.exit("template.html に `var MATCHES = [...];` が見つからない")
    build = hashlib.sha1(payload.encode("utf-8")).hexdigest()[:12]
    new = new.replace('var BUILD = "";', 'var BUILD = "%s";' % build, 1)
    (ROOT / "index.html").write_text(new, encoding="utf-8")
    print("index.html を出力: %d試合 / %d bytes" % (len(matches), len(new.encode("utf-8"))))


if __name__ == "__main__":
    main()
