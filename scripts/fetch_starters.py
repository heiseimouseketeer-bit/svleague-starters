#!/usr/bin/env python3
"""SVリーグ公式サイトから試合のセット別スタメンを取得して starters.json 形式で返す。

使い方:
  python3 scripts/fetch_starters.py --match 37495            # 1試合をJSONで標準出力
  python3 scripts/fetch_starters.py --scan 37400 37520       # ID範囲を走査して女子レギュラーシーズンの試合一覧
  python3 scripts/fetch_starters.py --build 37426 37495 --out data/starters.json
  python3 scripts/fetch_starters.py --check data/starters.json   # 既存データを公式から再取得して全件照合
  python3 scripts/fetch_starters.py --update data/starters.json  # 未取り込み/延期試合を追記(週次更新用)

標準ライブラリのみ。Python 3.8+。
"""
import argparse
import html as htmllib
import json
import re
import sys
import time
import urllib.request

BASE = "https://www.svleague.jp"
UA = "svleague-starters-fetcher/1.0 (personal, low-frequency)"
WEEKDAYS = "月火水木金土日"
TEAM_FULL = {}  # 略称(詳細ページ表記) -> 正式名(帳票B表記)。実施済み試合から学習する


# ---------------------------------------------------------------- HTTP
def http_get(url, retries=3, pause=0.4):
    last = None
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=30) as r:
                body = r.read().decode("utf-8", errors="replace")
            time.sleep(pause)
            return body
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(1.5 * (i + 1))
    raise RuntimeError("GET failed: %s (%s)" % (url, last))


def detail_url(mid):
    return "%s/match/detail/%s/" % (BASE, mid)


def form_url(mid, sheet):
    return "%s/match/form/?id=%s&sheet=%s" % (BASE, mid, sheet)


# ---------------------------------------------------------------- parsing helpers
def strip_tags(s):
    s = re.sub(r"<[^>]+>", " ", s)
    return re.sub(r"\s+", " ", htmllib.unescape(s)).strip()


def parse_detail(h):
    """試合詳細ページ -> dict。女子レギュラーシーズン以外は None。"""
    m = re.search(r"<p><em>([^<]*)</em>\s*第(\d+)節\s*/\s*GAME(\d+)</p>", h)
    if not m:
        return None
    league = m.group(1).strip()
    if "WOMEN" not in league or "Regular" not in league:
        return None
    venue = re.search(r'<div class="venue">(.*?)</div>', h, re.S)
    home = re.search(r'<div class="col home">.*?<b>(.*?)</b>', h, re.S)
    away = re.search(r'<div class="col away">.*?<b>(.*?)</b>', h, re.S)
    slug_h = re.search(r'<div class="col home">.*?href="/team/([a-z0-9_]+)/', h, re.S)
    slug_a = re.search(r'<div class="col away">.*?href="/team/([a-z0-9_]+)/', h, re.S)
    date = re.search(r"<em>(\d{4})\.(\d{2})\.(\d{2})</em>\s*\(([月火水木金土日])\)", h)
    out = {
        "round": int(m.group(2)),
        "game": int(m.group(3)),
        "venue": strip_tags(venue.group(1)) if venue else "",
        "home_short": strip_tags(home.group(1)) if home else "",
        "away_short": strip_tags(away.group(1)) if away else "",
        "home_slug": slug_h.group(1) if slug_h else "",
        "away_slug": slug_a.group(1) if slug_a else "",
        "date": "%s-%s-%s" % date.groups()[:3] if date else "",
        "weekday": date.group(4) if date else "",
    }
    # 結果(スコア)があれば実施済み
    sc = re.search(r'<div class="score">\s*<strong>(\d+)</strong>(.*?)<strong>(\d+)</strong>', h, re.S)
    sets = re.findall(r"<li>(\d+-\d+)</li>", sc.group(2)) if sc else []
    if sc and sets:
        out["status"] = "played"
        out["home_sets"], out["away_sets"] = int(sc.group(1)), int(sc.group(3))
        out["set_scores"] = sets
    else:
        out["status"] = "postponed"  # 後段で未実施(予定)を判定
        out["home_sets"] = out["away_sets"] = None
        out["set_scores"] = []
    # 選手(背番号, 氏名, セット別出場印)。個人記録の最初のtable(アタック)が全選手を持つ
    rosters = []
    for dd in re.findall(r"<dt>.*?</dt>\s*<dd>(.*?)</dd>", h, re.S)[:2]:
        t = re.search(r"<table>(.*?)</table>", dd, re.S)
        roster = {}
        if t:
            for tr in re.findall(r"<tr>(.*?)</tr>", t.group(1), re.S):
                num = re.match(r"\s*<td>(\d+)</td>", tr)
                nm = re.search(r"<th>(.*?)</th>", tr, re.S)
                if not (num and nm):
                    continue
                marks = [strip_tags(x) for x in re.findall(r'<td class="set">(.*?)</td>', tr, re.S)]
                roster[int(num.group(1))] = {"name": strip_tags(nm.group(1)), "marks": marks}
        rosters.append(roster)
    out["rosters"] = rosters
    return out


def parse_form_b(h):
    """帳票B -> (home_team, away_team, home_grids[5], away_grids[5])。
    各gridは読み順(上段4,3,2 / 下段5,6,1)の背番号6個。実施されなかったセットは None。"""
    names = re.findall(r'<span class="vs_team_name">(.*?)</span>', h, re.S)
    names = [strip_tags(n) for n in names]
    area = re.search(r'<div class="member_area">(.*?)</table>\s*</div>', h, re.S)
    body = area.group(1) if area else h
    uls = re.findall(r"<ul>(.*?)</ul>", body, re.S)
    grids = []
    for ul in uls:
        lis = re.findall(r"<li>(.*?)</li>", ul, re.S)
        if len(lis) != 6:
            continue
        nums = []
        for li in lis:
            first = re.split(r"<br\s*/?>", li)[0]
            first = strip_tags(first)
            nums.append(int(first) if first.isdigit() else None)
        grids.append(None if any(n is None for n in nums) else nums)
    if len(grids) != 10 or len(names) < 2:
        raise RuntimeError("帳票Bの構造が想定外: ul=%d, team=%d" % (len(grids), len(names)))
    return names[0], names[1], grids[:5], grids[5:]


def grid_to_positions(g):
    """読み順 g1..g6 -> ポジション1..6の背番号。P1=g6,P2=g3,P3=g2,P4=g1,P5=g4,P6=g5"""
    return [g[5], g[2], g[1], g[0], g[3], g[4]]


# ---------------------------------------------------------------- 1試合
def fetch_match(mid):
    d = parse_detail(http_get(detail_url(mid)))
    if d is None:
        return None
    match = {
        "id": int(mid),
        "round": d["round"],
        "game": d["game"],
        "date": d["date"],
        "weekday": d["weekday"],
        "home": d["home_short"],
        "away": d["away_short"],
        "venue": d["venue"],
        "venue_note": "",
        "status": d["status"],
        "home_sets": d["home_sets"],
        "away_sets": d["away_sets"],
        "set_scores": d["set_scores"],
        "note": "",
        "detail_url": detail_url(mid),
        "form_b_url": form_url(mid, "b"),
        "lineups": [],
    }
    if d["status"] != "played":
        match["note"] = "未実施(予定)"
        match["home"] = TEAM_FULL.get(match["home"], match["home"])
        match["away"] = TEAM_FULL.get(match["away"], match["away"])
        return match

    home_full, away_full, hg, ag = parse_form_b(http_get(form_url(mid, "b")))
    TEAM_FULL[d["home_short"]], TEAM_FULL[d["away_short"]] = home_full, away_full
    match["home"], match["away"] = home_full, away_full
    for side, team, grids, roster in (("home", home_full, hg, d["rosters"][0]), ("away", away_full, ag, d["rosters"][1])):
        for s, g in enumerate(grids, start=1):
            if g is None:
                continue
            pos = grid_to_positions(g)
            starters = []
            for p, num in enumerate(pos, start=1):
                starters.append({"position": p, "number": num, "name": roster.get(num, {}).get("name", "")})
            liberos = []
            for num, info in sorted(roster.items()):
                marks = info["marks"]
                if len(marks) >= s and marks[s - 1] == "▲":
                    liberos.append({"number": num, "name": info["name"], "flag": "▲"})
            match["lineups"].append({
                "team": team,
                "set": s,
                "starters": starters,
                "grid": {"top_row_numbers": [g[0], g[1], g[2]], "bottom_row_numbers": [g[3], g[4], g[5]]},
                "liberos": liberos,
                "note": "",
            })
    return match


# ---------------------------------------------------------------- 検証
def validate_match(m):
    errs = []
    if m["status"] != "played":
        return errs
    nsets = len(m["set_scores"])
    teams = {}
    for lu in m["lineups"]:
        teams.setdefault(lu["team"], []).append(lu["set"])
        nums = [s["number"] for s in lu["starters"]]
        if len(nums) != 6 or len(set(nums)) != 6:
            errs.append("%s %s set%s: 先発が6人ちょうど/重複なしでない %s" % (m["id"], lu["team"], lu["set"], nums))
        for s in lu["starters"]:
            if not s["name"]:
                errs.append("%s %s set%s: 背番号%s の氏名が引けない" % (m["id"], lu["team"], lu["set"], s["number"]))
    for t, sets in teams.items():
        if sorted(sets) != list(range(1, nsets + 1)):
            errs.append("%s %s: セット数が不一致 lineups=%s / 試合=%d" % (m["id"], t, sorted(sets), nsets))
    if len(teams) != 2:
        errs.append("%s: チーム数が2でない" % m["id"])
    return errs


# ---------------------------------------------------------------- 走査
def scan(a, b):
    found = []
    for mid in range(a, b + 1):
        try:
            d = parse_detail(http_get(detail_url(mid), pause=0.25))
        except RuntimeError:
            continue
        if d:
            found.append((mid, d))
            sys.stderr.write("%d 第%d節 G%d %s %s vs %s [%s]\n" % (mid, d["round"], d["game"], d["date"], d["home_short"], d["away_short"], d["status"]))
    return found


def apply_names(matches):
    """未実施試合の略称を正式名に直す(TEAM_FULL 学習後)。"""
    for m in matches:
        m["home"] = TEAM_FULL.get(m["home"], m["home"])
        m["away"] = TEAM_FULL.get(m["away"], m["away"])


def wrap(matches):
    apply_names(matches)
    return {
        "teams": dict(sorted(TEAM_FULL.items())),
        "description": "大同生命SV.LEAGUE WOMEN 2026-27 レギュラーシーズン セット別スタメン(公式帳票Bより自動取得)",
        "starters_order": "starters はポジション1〜6の順。P1=サーブ位置(コート右下)、前衛は4,3,2、後衛は5,6,1。",
        "libero_flag": "liberos.flag は公式詳細ページの出場セット欄の印(▲=リベロ)。",
        "matches": sorted(matches, key=lambda x: (x["round"], x["game"], x["date"], x["id"])),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--match", type=int)
    ap.add_argument("--scan", nargs=2, type=int, metavar=("FROM", "TO"))
    ap.add_argument("--build", nargs=2, type=int, metavar=("FROM", "TO"))
    ap.add_argument("--out")
    ap.add_argument("--keep", nargs="*", type=int, help="延期試合などで保持する未実施ID")
    ap.add_argument("--check")
    ap.add_argument("--update")
    a = ap.parse_args()

    if a.match:
        m = fetch_match(a.match)
        print(json.dumps(m, ensure_ascii=False, indent=1))
        return
    if a.scan:
        scan(*a.scan)
        return
    if a.build:
        found = scan(*a.build)
        top = max(mid for mid, d in found if d["status"] == "played")
        keep = set(a.keep or [])
        # 実施済み + 明示指定した延期試合(--keep) + 実施済み最大IDより前の未実施
        matches = [fetch_match(mid) for mid, d in found if d["status"] == "played" or mid in keep or mid < top]
        errs = [e for m in matches for e in validate_match(m)]
        for e in errs:
            sys.stderr.write("NG " + e + "\n")
        with open(a.out, "w", encoding="utf-8") as f:
            json.dump(wrap(matches), f, ensure_ascii=False, indent=1)
        print("wrote %s: %d試合 エラー%d件" % (a.out, len(matches), len(errs)))
        sys.exit(1 if errs else 0)
    if a.check:
        data = json.load(open(a.check, encoding="utf-8"))
        bad = 0
        for old in data["matches"]:
            if old["status"] != "played":
                continue
            new = fetch_match(old["id"])
            o = {(l["team"], l["set"]): [(s["number"], s["name"]) for s in l["starters"]] for l in old["lineups"]}
            n = {(l["team"], l["set"]): [(s["number"], s["name"]) for s in l["starters"]] for l in new["lineups"]}
            if o != n:
                bad += 1
                sys.stderr.write("不一致 %s\n" % old["id"])
        print("check: 不一致 %d 試合" % bad)
        sys.exit(1 if bad else 0)
    if a.update:
        data = json.load(open(a.update, encoding="utf-8"))
        TEAM_FULL.update(data.get("teams", {}))
        have = {m["id"]: m for m in data["matches"]}
        changed = []
        # 1) 保持している未実施(延期)試合が実施されたか/日程変更されたか
        for mid, m in list(have.items()):
            if m["status"] != "played":
                new = fetch_match(mid)
                if new and (new["status"] == "played" or (new["date"], new["venue"]) != (m["date"], m["venue"])):
                    have[mid] = new
                    changed.append(mid)
        # 2) 未取得のID。保持IDの欠番も含めて先頭から走査し、保持最大IDを越えてから
        #    未実施が30件連続したら打ち切る(1節=14試合)
        mid, unplayed_run, new_unplayed = min(have), 0, []
        while not (mid > max(have) and unplayed_run >= 30):
            if mid in have:
                mid += 1
                continue
            try:
                new = fetch_match(mid)
            except RuntimeError:
                new = None
            if new and new["status"] == "played":
                have[mid] = new
                changed.append(mid)
                unplayed_run = 0
            else:
                if new:
                    new_unplayed.append(new)
                unplayed_run += 1
            mid += 1
        # 3) 実施済み最大IDより前に取り残された未実施は延期として保持(追跡対象)
        top = max(i for i, m in have.items() if m["status"] == "played")
        for new in new_unplayed:
            if new["id"] < top and new["id"] not in have:
                have[new["id"]] = new
                changed.append(new["id"])
        errs = [e for i in changed for e in validate_match(have[i])]
        for e in errs:
            sys.stderr.write("NG " + e + "\n")
        if errs:
            sys.exit(1)
        if changed:
            with open(a.update, "w", encoding="utf-8") as f:
                json.dump(wrap(list(have.values())), f, ensure_ascii=False, indent=1)
        print("updated: %s" % (sorted(changed) or "変更なし"))
        return
    ap.print_help()


if __name__ == "__main__":
    main()
