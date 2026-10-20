"""附表の確認ページ（tools/review/fuhyo_page.html）に入れる事業の一覧を作る（LINK_SCHEMA.md §7 fuhyo、CLAUDE.md 不変の制約11）。

台帳 links/fuhyo.tsv の candidate の行と、inputs.lock.json の版の附表・計画（実施計画）から、附表の事業ごとに
候補を並べた一覧を作る。事業ごとに、突き合わせの区分の案（suggest）と、事業概要の違う箇所（fseg・jseg）を付ける。
区分の案は次の決まりで作り、--suggest で渡した上書き（JSON。{"b049": ["ichibu", null], "b131": ["meisho", "e124"]}）
があればそれを使う。案を作るだけで、確定は人が確認ページで行う（DESIGN.md ADR-2）。
  - 先頭の node の候補が「事業名が同じ。事業概要も同じ」で柱も同じ → 一致（icchi）、柱が違う → 一致（柱違い）（icchi-hashira）
  - それ以外 → 表記の違い（hyoki）
区分の id：icchi・icchi-hashira・hyoki・meisho（名称の変更）・ichibu（一部）・nendo（年度の事業）・nakami（中身の違い）

実行: python3 -B tools/review/fuhyo_seed.py <out.json> [--suggest <上書き.json>] [--docs <フォルダ>] [--ledger <links/fuhyo.tsv>]
--docs を渡すと、ページの items の集まりに入れる1事業1ファイルの JSON（<key>.json。id を除く）も書く。
入力の clone の場所は、環境変数 HINO_RONTEN_INPUTS で変えられる（gen_mentions.py と同じ）。
"""
import argparse
import csv
import difflib
import hashlib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
sys.path.insert(0, TOOLS)

import gen_fuhyo  # noqa: E402
import gen_mentions as gm  # noqa: E402

ROOT = gm.ROOT


def seg(a, b):
    """2つの文の、同じ部分と違う部分の並び（[文字列, 違うか] の列）。"""
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    fa, fb = [], []
    for t, i1, i2, j1, j2 in sm.get_opcodes():
        if a[i1:i2]:
            fa.append([a[i1:i2], t != "equal"])
        if b[j1:j2]:
            fb.append([b[j1:j2], t != "equal"])
    return fa, fb


def plan_items(plan):
    """計画の事業（key → 柱の番号・タブ・分野・名前・概要・概算事業費・年度）。柱は programs を持つタブを1から数える。"""
    out, pn = {}, 0
    for t in plan["tabs"]:
        its = []
        for b in t["blocks"]:
            if b.get("type") == "programs":
                for g, sgrp, it in ((g, None, it) for g in b["groups"] for it in (g.get("items") or [])):
                    its.append((g, it))
                for g in b["groups"]:
                    for s in g.get("subgroups") or []:
                        for it in s.get("items") or []:
                            its.append((g, it))
        if its:
            pn += 1
            for g, it in its:
                out[it["key"]] = dict(pillar=pn, tab=t.get("label"), field=f"{g.get('no', '')} {g.get('name', '')}".strip(),
                                      name=it["name"], desc=it.get("desc", ""), cost=(it.get("cost") or {}).get("amount"),
                                      years=it.get("years", []))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--suggest")
    ap.add_argument("--docs")
    ap.add_argument("--ledger", default=os.path.join(ROOT, "links", "fuhyo.tsv"))
    a = ap.parse_args(argv)
    lock = gm.load_lock(gm.LOCK_PATH)
    gi = gm.GitInputs(gm.INPUTS_ROOT, lock)
    gi.verify()
    over = json.load(open(a.suggest, encoding="utf-8")) if a.suggest else {}
    rows = list(csv.DictReader(open(a.ledger, encoding="utf-8"), delimiter="\t"))
    by = {}
    for r in rows:
        if r["status"] == "candidate":
            by.setdefault(r["from"], []).append(r)
    docs = []
    for fid, pid in sorted(gen_fuhyo.FUHYO_PLANS.items()):
        fh = gi.read_json("shiga-hino-plans", f"data/fuhyo/{fid}.json")
        plan = gi.read_json("shiga-hino-plans", f"data/plans/{pid}.json")
        jit = plan_items(plan)
        jpdf = ((plan.get("sources") or [{}])[0]).get("url")
        src = fh.get("source") or {}
        fpdf = next((r["url"] for r in csv.DictReader(gi.read_bytes("shiga-hino-plans", "data/sources_index.tsv")
                                                         .decode("utf-8").splitlines(), delimiter="\t")
                     if r["id"] == src.get("id") and r["file"] == src.get("file")), "")
        for p in fh["pillars"]:
            for it in p["items"]:
                k = f"fh:{fh['id']}/{it['key']}"
                if k not in by:
                    continue  # candidate の無い事業（判定済み）は入れない
                cs = []
                for r in by[k]:
                    c = dict(id=hashlib.sha1(f"{r['from']}\t{r['to']}\t{r['method']}".encode()).hexdigest()[:16],
                             to=r["to"], method=r["method"], context=r["context"], to_label=r["to_label"], note=r["note"])
                    c["from"] = r["from"]
                    if r["to"].startswith("node:"):
                        j = jit[r["to"].split("/")[-1]]
                        c.update(jkey=r["to"].split("/")[-1], jdesc=j["desc"], jcost=j["cost"], jyears=j["years"],
                                 jpillar=j["pillar"], jtab=j["tab"], jfield=j["field"])
                        c["fseg"], c["jseg"] = seg(it["desc"], j["desc"])
                    cs.append(c)

                def sk(c):  # node を先（Dice の note があれば大きい順）、none を最後
                    if c["to"].startswith("none:"):
                        return (2, 0, "")
                    d = c["note"].split("Dice ")[-1].split("）")[0] if "Dice" in c["note"] else None
                    return (1 if d else 0, -float(d) if d else 0, c["to"])
                cs.sort(key=sk)
                if it["key"] in over:
                    cat, jk = over[it["key"]]
                    to = f"node:{pid}/{jk}" if jk else f"none:{pid}"
                else:
                    nodes = [c for c in cs if c["to"].startswith("node:")]
                    if nodes and nodes[0]["note"].startswith("事業名が同じ。事業概要も同じ"):
                        cat = "icchi-hashira" if "柱が違う" in nodes[0]["note"] else "icchi"
                        to = nodes[0]["to"]
                    elif nodes:
                        cat, to = "hyoki", nodes[0]["to"]
                    else:
                        cat, to = "nendo", f"none:{pid}"
                if not any(c["to"] == to for c in cs):
                    raise SystemExit(f"停止：{it['key']} の区分の案の先（{to}）が候補に無い")
                page = it.get("page")
                docs.append(dict(id=it["key"], order=len(docs), key=it["key"], pillar=p["no"], pillarName=p["name"],
                                 kubun=it["kubun"], kan=it["kan"], name=it["name"], desc=it["desc"], details=it["details"],
                                 amount=it["amount"], dept=it["dept"], page=page,
                                 pdf=f"{fpdf}#page={page}" if fpdf and page else fpdf, jpdf=jpdf, cands=cs,
                                 suggest={"cat": cat, "to": to}, **{"from": k}))
    json.dump(docs, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    if a.docs:
        os.makedirs(a.docs, exist_ok=True)
        for d in docs:
            x = dict(d)
            x.pop("id")
            json.dump(x, open(os.path.join(a.docs, f"{d['key']}.json"), "w", encoding="utf-8"), ensure_ascii=False)
    print(f"事業 {len(docs)}・候補 {sum(len(d['cands']) for d in docs)}（lock {lock['shiga-hino-plans']['sha'][:7]}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
