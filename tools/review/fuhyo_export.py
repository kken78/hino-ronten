"""附表の確認ページの判定を、tools/apply_decisions.py --ledger fuhyo に渡す2つの TSV に書き出す（CLAUDE.md 不変の制約11）。

ページの decisions の集まりを1判定1ファイルの JSON（<id>.json。中身は data か判定そのもの）でフォルダに書き出したものと、
ページに入れた一覧（tools/review/fuhyo_seed.py の出力）から、判定の一覧（8列）と判定した範囲（from・to・method）を書く。
範囲に入れるのは、候補をすべて判定した附表の事業だけで、事業ごとにその事業の candidate の行をすべて入れる（§7 fuhyo）。
次のどれかがあれば何も書かずに止める：一覧に無い判定、台帳の candidate と合わない行、理由の無い却下、
区分（「区分：<区分>」）の無い確定、附表の分類の誤り（none と node の両方の確定、すべて却下）。

実行: python3 -B tools/review/fuhyo_export.py <一覧.json> <decisions のフォルダ> <判定の一覧.tsv> <範囲.tsv> [--ledger <links/fuhyo.tsv>]
判定の一覧と範囲の TSV はリポジトリに入れない。
"""
import argparse
import csv
import glob
import json
import os
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

import gen_mentions as gm  # noqa: E402

KUBUN = ("一致", "一致（柱違い）", "表記の違い", "名称の変更", "一部", "年度の事業", "中身の違い")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("seed")
    ap.add_argument("decisions")
    ap.add_argument("out")
    ap.add_argument("keys")
    ap.add_argument("--ledger", default=os.path.join(gm.ROOT, "links", "fuhyo.tsv"))
    a = ap.parse_args(argv)
    items = json.load(open(a.seed, encoding="utf-8"))
    decs = {}
    for f in glob.glob(os.path.join(a.decisions, "*.json")):
        d = json.load(open(f, encoding="utf-8"))
        decs[os.path.basename(f)[:-5]] = d.get("data", d)
    L = {(r["from"], r["to"], r["method"]): r for r in csv.DictReader(open(a.ledger, encoding="utf-8"), delimiter="\t")}
    known = {c["id"] for it in items for c in it["cands"]}
    prob = [("一覧に無い判定", i) for i in decs if i not in known]
    out, keys, pending, kinds = [], [], [], Counter()
    for it in items:
        ds = [decs.get(c["id"]) for c in it["cands"]]
        if any(d is None for d in ds):
            pending.append(it["key"])
            continue
        conf = [(c, d) for c, d in zip(it["cands"], ds) if d["decision"] == "confirmed"]
        if {c["to"].split(":")[0] for c, _ in conf} >= {"node", "none"}:
            prob.append(("none と node の両方を確定", it["key"]))
        if not conf:
            prob.append(("候補をすべて却下", it["key"]))
        for c, d in zip(it["cands"], ds):
            k = (c["from"], c["to"], c["method"])
            if (d["from"], d["to"], d["method"]) != k or d["context"] != c["context"]:
                prob.append(("一覧と判定が合わない", c["id"]))
            l = L.get(k)
            if not l or l["status"] != "candidate" or l["context"] != c["context"]:
                prob.append(("台帳の candidate と合わない", c["id"]))
            if d["decision"] not in ("confirmed", "rejected"):
                prob.append(("判定の値", c["id"]))
            note = (d.get("note") or "").strip()
            if d["decision"] == "rejected" and not note:
                prob.append(("理由の無い却下", c["id"]))
            if d["decision"] == "confirmed" and not any(note.startswith(f"区分：{x}") for x in KUBUN):
                prob.append(("区分の無い確定", c["id"]))
            note = note[:-1] if note.endswith("。") else note
            if "\t" in note or "\n" in note:
                prob.append(("メモにタブか改行", c["id"]))
            out.append([*k, c["context"], d["decision"], d.get("reviewer") or "", d.get("decidedAt") or "", note])
            keys.append(k)
            kinds[(c["to"].split(":")[0], d["decision"])] += 1
    print(f"判定した事業 {len(items) - len(pending)}・まだの事業 {len(pending)}・行 {len(out)}・"
          + "・".join(f"{t} {s} {n}" for (t, s), n in sorted(kinds.items())))
    if prob:
        print(f"停止：{len(prob)} 件", file=sys.stderr)
        for p in prob:
            print(f"  {p[0]}：{p[1]}", file=sys.stderr)
        return 1
    out.sort(key=lambda r: (r[0], r[1], r[2]))
    with open(a.out, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, delimiter="\t", lineterminator="\n")
        w.writerow(["from", "to", "method", "context", "status", "reviewer", "date", "note"])
        w.writerows(out)
    with open(a.keys, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, delimiter="\t", lineterminator="\n")
        w.writerow(["from", "to", "method"])
        w.writerows(sorted(keys))
    return 0


if __name__ == "__main__":
    sys.exit(main())
