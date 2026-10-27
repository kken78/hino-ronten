"""記録の台帳（records/）・テーマの定義（ref/themes.tsv）・施設の参照表（ref/shisetsu.tsv）を確かめる
（LINK_SCHEMA.md §11 の「テーマの定義」「施設の参照表」「記録の台帳」「発言の取りこぼし」「引用の前後」、DESIGN.md ADR-24）。

inputs.lock.json の版の入力（会議録の索引と審議の記録・議案・議会だより・計画・計画の原典の文字・町の公開資料）で照らす。
台帳には書かない。報告と一覧は build/records/ に書く：
  check.md          件数と誤りの報告
  round_diff.tsv    round が turns から求めた値と違う行（§15.2。終了コードは変えない）
  quote_mismatch.tsv 引用が資料の本文に無い行（confirmed なら誤り）
  torikoboshi.tsv   発言の取りこぼし（ADR-24。終了コードは変えない）
  quote_context.tsv 引用の前後（指示語で始まる・文の途中で終わる。終了コードは変えない）

実行: python3 -B tools/check_records.py
終了コード：0 は合格。1 は止めた（誤りを表示する）。
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import gen_mentions as gm  # noqa: E402
import mention  # noqa: E402
import records  # noqa: E402

OUT_DIR = os.path.join(gm.ROOT, "build", "records")
RECORDS_DIR = os.path.join(gm.ROOT, "records")
THEMES = os.path.join(gm.ROOT, "ref", "themes.tsv")
SHISETSU = os.path.join(gm.ROOT, "ref", "shisetsu.tsv")
EXAMPLES = 20


def read_file(path, columns, optional=False):
    if optional and not os.path.exists(path):
        return []
    with open(path, "rb") as f:
        return records.parse_tsv(f.read(), columns, os.path.relpath(path, gm.ROOT))


def bulletin_texts(questions):
    out = {}
    for q in questions:
        key = gm.bq_key(q)
        parts = []
        for f in gm.BQ_FIELDS:
            v = q.get(f)
            if isinstance(v, list):
                parts += [a.get("text") or "" for a in v if isinstance(a, dict)]
            elif v:
                parts.append(v)
        out[key] = parts
    return out


def read_inputs(gi):
    im = gi.read_json(gm.HS, "public/data/index-manifest.json")
    shards = [f"public/data/{s['file']}" for s in im["shards"]]
    if sorted(shards) != gi.expand(gm.HS, "public/data/index/*.json"):
        raise gm.GenError("index-manifest.json の shards と index/*.json が違う")
    index = [e for p in shards for e in gi.read_json(gm.HS, p)]
    statements = {e["sid"]: {"text": e.get("text") or "", "role": e.get("role"), "meetingId": e.get("meetingId")}
                  for e in index}
    proceedings = gi.read_json(gm.HS, "public/data/proceedings.json")
    segments = {}
    for mid, m in proceedings.items():
        for sg in m.get("segments") or []:
            if sg.get("kind") in ("ippan", "shitsugi"):
                segments[sg["from"]] = dict(sg, meetingId=mid)
    gian = {mid: {a["no"] for a in m.get("agenda") or []}
            for mid, m in gi.read_json(gm.HS, "public/data/gian.json").items()}
    questions = gi.read_json(gm.CD, "docs/data/questions.json")["questions"]
    docs_rows = records.parse_tsv(gi.read_bytes(gm.TD, "data/sources.tsv"),
                                  gi.read_bytes(gm.TD, "data/sources.tsv").decode("utf-8").split("\n")[0].split("\t"),
                                  "hino-town-docs data/sources.tsv")
    doc_files = set(gi.expand(gm.TD, "data/text/*.txt")) | set(gi.expand(gm.TD, "data/text_raw/*.txt"))
    pt_files = set(gi.expand(gm.SP, "data/text/*/*.txt")) | set(gi.expand(gm.SP, "data/text_raw/*/*.txt"))
    cache = {}

    def text_of(repo, path, files):
        if path not in files:
            return None
        if (repo, path) not in cache:
            cache[(repo, path)] = gi.read_bytes(repo, path).decode("utf-8")
        return cache[(repo, path)]

    manifest = gi.read_json(gm.SP, "data/manifest.json")
    plan_ids = {p["id"] for p in manifest["plans"]}
    nodes = set()
    for path in gi.expand(gm.SP, "data/plans/*.json"):
        plan = gi.read_json(gm.SP, path)
        for t in plan.get("tabs") or []:
            for b in t.get("blocks") or []:
                if b.get("type") != "programs":
                    continue
                for g in b.get("groups") or []:
                    its = list(g.get("items") or [])
                    for s in g.get("subgroups") or []:
                        its += s.get("items") or []
                    for it in its:
                        if it.get("key"):
                            nodes.add(f"node:{plan['id']}/{it['key']}")
    refs = mention.load_refs(gm.LINEAGE, gm.ALIASES)
    series = {r.series for r in refs.lineage}
    return records.Inputs(
        statements=statements, order=[e["sid"] for e in index], segments=segments, gian=gian,
        bulletin=bulletin_texts(questions), docs={r["id"] for r in docs_rows},
        doc_text=lambda did, layer: text_of(gm.TD, f"data/{layer}/{did}.txt", doc_files),
        pt_text=lambda pid, name, layer: text_of(gm.SP, f"data/{layer}/{pid}/{name}.txt", pt_files),
        plans=plan_ids, nodes=nodes, series=series)


def report_lines(rep):
    L = ["# 記録の台帳の確かめ（records/・ref/themes.tsv・ref/shisetsu.tsv）", ""]
    L.append("- 台帳の行の数：" + "・".join(f"{n} {c}" for n, c in rep.counts.items()))
    L.append(f"- 誤り：{len(rep.errors)}")
    L.append(f"- round が turns から求めた値と違う行：{len(rep.round_diff)}（round_diff.tsv）")
    L.append(f"- 引用が資料の本文に無い行：{len(rep.quote_mismatch)}（quote_mismatch.tsv）")
    by = {}
    for r in rep.torikoboshi:
        by[r["ledger"]] = by.get(r["ledger"], 0) + 1
    L.append(f"- 発言の取りこぼし：{len(rep.torikoboshi)}（" + "・".join(f"{k} {v}" for k, v in sorted(by.items()))
             + "。torikoboshi.tsv）")
    by = {}
    for r in rep.quote_context:
        by[r["kind"]] = by.get(r["kind"], 0) + 1
    L.append(f"- 引用の前後：{len(rep.quote_context)}（" + "・".join(f"{k} {v}" for k, v in sorted(by.items()))
             + "。quote_context.tsv）")
    if rep.errors:
        L += ["", "## 誤り", ""] + [f"- {e}" for e in rep.errors]
    return L


def write_outputs(outdir, rep):
    os.makedirs(outdir, exist_ok=True)
    files = {
        "round_diff.tsv": (records.ROUND_DIFF_COLUMNS, rep.round_diff),
        "quote_mismatch.tsv": (records.QUOTE_MISMATCH_COLUMNS, rep.quote_mismatch),
        "torikoboshi.tsv": (records.TORIKOBOSHI_COLUMNS, rep.torikoboshi),
        "quote_context.tsv": (records.QUOTE_CONTEXT_COLUMNS, rep.quote_context),
    }
    for name, (cols, rows) in files.items():
        with open(os.path.join(outdir, name), "w", encoding="utf-8", newline="\n") as f:
            f.write(records.format_tsv(cols, rows))
    with open(os.path.join(outdir, "check.md"), "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(report_lines(rep)) + "\n")


def main():
    try:
        lock = gm.load_lock(gm.LOCK_PATH)
        gi = gm.GitInputs(gm.INPUTS_ROOT, lock)
        gi.verify()
        inp = read_inputs(gi)
        ledgers = {n: read_file(os.path.join(RECORDS_DIR, f"{n}.tsv"), records.COLUMNS[n], n in records.OPTIONAL)
                   for n in records.LEDGERS}
        themes = read_file(THEMES, records.THEME_COLUMNS)
        shisetsu = read_file(SHISETSU, records.SHISETSU_COLUMNS)
    except (gm.GenError, records.RecordsError, mention.RefError) as e:
        print(f"停止：{e}", file=sys.stderr)
        return 1
    rep = records.check_all(ledgers, themes, shisetsu, inp)
    write_outputs(OUT_DIR, rep)
    print("\n".join(report_lines(rep)[2:8]))
    if rep.errors:
        for e in rep.errors[:EXAMPLES]:
            print(f"  {e}", file=sys.stderr)
        if len(rep.errors) > EXAMPLES:
            print(f"  ほか {len(rep.errors) - EXAMPLES} 件（build/records/check.md）", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
