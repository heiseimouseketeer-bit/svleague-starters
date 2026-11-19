#!/usr/bin/env python3
"""オフライン検証: data/starters.json の整合性と、スキル記載の検証例(試合37495 PFU 第1セット)。
失敗したら終了コード1。週次更新ではコミット前に必ず通す。"""
import json
import sys
from pathlib import Path

d = json.loads((Path(__file__).resolve().parent.parent / "data" / "starters.json").read_text(encoding="utf-8"))
errs = []
for m in d["matches"]:
    if m["status"] != "played":
        continue
    sets = len(m["set_scores"])
    per_team = {}
    for lu in m["lineups"]:
        nums = [s["number"] for s in lu["starters"]]
        if len(nums) != 6 or len(set(nums)) != 6:
            errs.append("%s %s set%s 先発が6人ちょうどでない" % (m["id"], lu["team"], lu["set"]))
        if any(not s["name"] for s in lu["starters"]):
            errs.append("%s %s set%s 氏名欠落" % (m["id"], lu["team"], lu["set"]))
        per_team.setdefault(lu["team"], []).append(lu["set"])
    bad_sets = any(sorted(v) != list(range(1, sets + 1)) for v in per_team.values())
    if bad_sets or len(per_team) != 2:
        errs.append("%s セット数/チーム数が不一致" % m["id"])

# 検証例: 試合37495、PFU 第1セット
want = [(11, "松井 珠己"), (9, "川添 美優"), (15, "タットダオ・ヌクジャン"), (23, "バルデス メリーサ"), (12, "上村 杏菜"), (1, "横田 真未")]
m = next(x for x in d["matches"] if x["id"] == 37495)
lu = next(l for l in m["lineups"] if l["team"].startswith("PFU") and l["set"] == 1)
got = [(s["number"], s["name"]) for s in lu["starters"]]
if got != want:
    errs.append("検証例(37495 PFU set1)が不一致: %s" % got)
if lu["grid"] != {"top_row_numbers": [23, 15, 9], "bottom_row_numbers": [12, 1, 11]}:
    errs.append("検証例のグリッドが不一致")

teams = {l["team"] for m in d["matches"] for l in m["lineups"]}
if len(teams) != 14:
    errs.append("チーム数が14でない: %d" % len(teams))
for e in errs:
    print("NG", e)
print("verify: %s (%d試合)" % ("OK" if not errs else "FAILED", len(d["matches"])))
sys.exit(1 if errs else 0)
