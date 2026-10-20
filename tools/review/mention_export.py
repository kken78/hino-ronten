"""言及の確認ページの判定を、tools/apply_decisions.py に渡す2つの TSV に書き出す（CLAUDE.md 不変の制約11）。

ページの decisions の集まりを1判定1ファイルの JSON（<id>.json）でフォルダに書き出したもの（今回）と、前の回に書き出したもの
（前回。無ければ空のフォルダ）、ページに入れた束（tools/review/mention_seed.py の出力）から、判定の一覧と判定した範囲を書く。
範囲には、束の全行を入れる（判定の無い行があれば止める）。付け替え先（relink_to）は、系譜表にある計画（plan・lin）で、
却下の行にだけ付けられる。次のどれかがあれば何も書かずに止める：判定の無い行、台帳の candidate と合わない行、
理由の無い却下、付け替え先の誤り。前回から変わった判定と、束にも前回にも無い判定は、表示だけする。

実行: python3 -B tools/review/mention_export.py <束.json> <今回の decisions のフォルダ> <前回の decisions のフォルダ> <判定の一覧.tsv> <範囲.tsv> --reviewer <判定した人> [--ledger <links/mention.tsv>]
判定に reviewer が無いときは --reviewer の値を使う。判定の一覧と範囲の TSV はリポジトリに入れない。
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


def load(d):
    out = {}
    for f in glob.glob(os.path.join(d, "*.json")):
        x = json.load(open(f, encoding="utf-8"))
        out[os.path.basename(f)[:-5]] = x.get("data", x) if isinstance(x, dict) and "data" in x and "decision" not in x else x
    return out


def lineage_keys():
    keys = set()
    for r in csv.DictReader(open(gm.LINEAGE, encoding="utf-8"), delimiter="\t"):
        keys.add(f"plan:{r['plan']}" if r["plan"] else f"lin:{r['series']}/{r['edition']}")
    return keys


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("batch")
    ap.add_argument("new")
    ap.add_argument("old")
    ap.add_argument("out")
    ap.add_argument("keys")
    ap.add_argument("--reviewer", required=True)
    ap.add_argument("--ledger", default=os.path.join(gm.ROOT, "links", "mention.tsv"))
    a = ap.parse_args(argv)
    rows = json.load(open(a.batch, encoding="utf-8"))
    ids = {r["id"] for r in rows}
    dec, old = load(a.new), load(a.old)
    changed = [i for i in old if json.dumps(old[i], sort_keys=True) != json.dumps(dec.get(i), sort_keys=True)]
    orphans = [i for i in dec if i not in ids and i not in old]
    if changed:
        print(f"前回から変わった判定 {len(changed)}：{'、'.join(changed)}")
    if orphans:
        print(f"束にも前回にも無い判定 {len(orphans)}：{'、'.join(orphans)}")
    L = {(r["from"], r["to"], r["method"]): r for r in csv.DictReader(open(a.ledger, encoding="utf-8"), delimiter="\t")}
    T = lineage_keys()
    out, prob = [], []
    for r in rows:
        i, d = r["id"], dec.get(r["id"])
        if not d:
            prob.append(("判定が無い", i))
            continue
        k = (r["key_from"], r["key_to"], r["method"])
        if (d["from"], d["to"], d["method"]) != k or d["context"] != r["context"]:
            prob.append(("束と判定が合わない", i))
        l = L.get(k)
        if not l or l["status"] != "candidate" or l["context"] != r["context"]:
            prob.append(("台帳の candidate と合わない", i))
        note = (d.get("note") or "").strip()
        rel = d.get("relinkTo") or ""
        if d["decision"] == "rejected" and not note:
            prob.append(("理由の無い却下", i))
        if rel and (d["decision"] != "rejected" or rel not in T or rel == k[1]):
            prob.append(("付け替え先の誤り", i))
        note = note[:-1] if note.endswith("。") else note
        if "\t" in note or "\n" in note:
            prob.append(("メモにタブか改行", i))
        out.append([*k, r["context"], d["decision"], d.get("reviewer") or a.reviewer, d["decidedAt"], note, rel])
    c = Counter((o[1], o[4], bool(o[8])) for o in out)
    print("・".join(f"{to} {st}{'（付け替え）' if rel else ''} {n}" for (to, st, rel), n in sorted(c.items())))
    if prob:
        print(f"停止：{len(prob)} 件", file=sys.stderr)
        for p in prob:
            print(f"  {p[0]}：{p[1]}", file=sys.stderr)
        return 1
    hasrel = any(o[8] for o in out)
    with open(a.out, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, delimiter="\t", lineterminator="\n")
        w.writerow(["from", "to", "method", "context", "status", "reviewer", "date", "note"] + (["relink_to"] if hasrel else []))
        w.writerows([o if hasrel else o[:8] for o in out])
    with open(a.keys, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, delimiter="\t", lineterminator="\n")
        w.writerow(["from", "to", "method"])
        w.writerows(sorted({(r["key_from"], r["key_to"], r["method"]) for r in rows}))
    print(f"束 {len(rows)} 行を書いた")
    return 0


if __name__ == "__main__":
    sys.exit(main())
