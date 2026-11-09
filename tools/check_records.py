"""記録の台帳（records/）・テーマの定義（ref/themes.tsv）・施設の参照表（ref/shisetsu.tsv）・
地区と組織の参照表（ref/chiku.tsv・ref/soshiki.tsv）を確かめる
（LINK_SCHEMA.md §11 の「テーマの定義」「施設の参照表」「地区・組織の参照表」「記録の台帳」「発言の取りこぼし」「引用の前後」
「届き先」、DESIGN.md ADR-24・ADR-31・ADR-32）。地区と組織の参照表は、ファイルが無ければ0行として扱う。

inputs.lock.json の版の入力（会議録の索引と審議の記録・議案・議会だより・計画・計画の原典の文字・町の公開資料）で照らす。
台帳には書かない。報告と一覧は build/records/ に書く：
  check.md          件数と誤りの報告
  round_diff.tsv    round が turns から求めた値と違う行（§15.2。終了コードは変えない）
  quote_mismatch.tsv 引用が資料の本文に無い行（confirmed なら誤り）
  torikoboshi.tsv   発言の取りこぼし（ADR-24。終了コードは変えない）
  quote_context.tsv 引用の前後（指示語で始まる・文の途中で終わる。終了コードは変えない）
  signal_todoku.tsv  届き先の信号：views の無い点の確定行（ADR-31 の4。終了コードは変えない）
  signal_point.tsv   届き先の信号：問いごとの点が空の割合（終了コードは変えない）
  signal_chushin.tsv 届き先の信号：テーマごとの、中心の見方に出る行の割合（終了コードは変えない）
  target_unchecked.tsv 対象の照合の (2) に合わない candidate の行（§11。終了コードは変えない）
  target_bill.tsv    対象と議案・名前の (a)（終了コードは変えない）
  target_name.tsv    対象と議案・名前の (b)（終了コードは変えない）
  target_changed.tsv lock の hino-town-docs を上げるときの比べ方（--prev を渡したときだけ。§10）
  teian_segment.tsv  提案理由の記録で、sid が bill の提案の区切りに入っていない行（§11。終了コードは変えない）
  teian_name.tsv     提案理由の記録の事情の行で、○の行の名前が引用に無い行（終了コードは変えない）
  teian_no_jijo.tsv  提案理由の記録に行のある回の○の行のうち、事情の行の無い行（終了コードは変えない）
  teian_group.tsv    同じ文で説明された行の組（同じ面・sid・引用。終了コードは変えない。DESIGN.md ADR-35）

target のキーは、lock の版の附表（fh）と hino-town-docs の構造化の層（hs・hj・hk・hz。tools/hosei.py）で照らし、
links/gian-yosan.tsv・links/hosei-fuhyo.tsv の confirmed の行（無ければ0行）で議案の回と○の行の附表を引く。

実行: python3 -B tools/check_records.py
      python3 -B tools/check_records.py --prev <前の版の hino-town-docs の40桁の SHA>
        （lock の hino-town-docs を上げるとき。前の版といまの lock の版の検収の台帳の key を比べ、target_changed.tsv を書く）
終了コード：0 は合格。1 は止めた（誤りを表示する）。
"""
import os
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import gen_fuhyo  # noqa: E402
import gen_mentions as gm  # noqa: E402
import hosei  # noqa: E402
import ledger  # noqa: E402
import mention  # noqa: E402
import records  # noqa: E402

OUT_DIR = os.path.join(gm.ROOT, "build", "records")
RECORDS_DIR = os.path.join(gm.ROOT, "records")
THEMES = os.path.join(gm.ROOT, "ref", "themes.tsv")
SHISETSU = os.path.join(gm.ROOT, "ref", "shisetsu.tsv")
CHIKU = os.path.join(gm.ROOT, "ref", "chiku.tsv")       # 地区の参照表（§12.1）。無ければ0行
SOSHIKI = os.path.join(gm.ROOT, "ref", "soshiki.tsv")   # 組織の参照表（§12.1）。無ければ0行
LINKS_DIR = os.path.join(gm.ROOT, "links")
EXAMPLES = 20
USAGE = "使い方：python3 -B tools/check_records.py [--prev <前の版の hino-town-docs の SHA>]"


def read_file(path, columns, optional=False):
    if optional and not os.path.exists(path):
        return []
    with open(path, "rb") as f:
        return records.parse_tsv(f.read(), columns, os.path.relpath(path, gm.ROOT))


def read_area_refs():
    """地区と組織の参照表の行（§12.1）。ファイルが無ければ0行。(chiku, soshiki)。"""
    return (read_file(CHIKU, records.AREA_COLUMNS, optional=True),
            read_file(SOSHIKI, records.AREA_COLUMNS, optional=True))


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
    segments, proposals = {}, []
    for mid, m in proceedings.items():
        for sg in m.get("segments") or []:
            if sg.get("kind") in ("ippan", "shitsugi"):
                segments[sg["from"]] = dict(sg, meetingId=mid)
            elif sg.get("kind") == "proposal":   # 提案理由の記録の (a)（§11。DESIGN.md ADR-35）
                proposals.append((sg["from"], sg["to"], mid, list(sg.get("bills") or [])))
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
    plans_in_lineage = {r.plan for r in refs.lineage if r.plan}   # views の plan キーを照らす（§12）
    fuhyo_keys = {f"fh:{fid}/{it['key']}" for fid, p in gen_fuhyo.named_fuhyo(gi.lock)
                  for it in gen_fuhyo.fuhyo_items(fid, gen_fuhyo.read_fuhyo_json(gi, fid, p))}
    return records.Inputs(
        statements=statements, order=[e["sid"] for e in index], segments=segments, gian=gian,
        bulletin=bulletin_texts(questions), docs={r["id"] for r in docs_rows},
        doc_text=lambda did, layer: text_of(gm.TD, f"data/{layer}/{did}.txt", doc_files),
        pt_text=lambda pid, name, layer: text_of(gm.SP, f"data/{layer}/{pid}/{name}.txt", pt_files),
        plans=plan_ids, nodes=nodes, series=series, plans_in_lineage=plans_in_lineage,
        fuhyo_keys=fuhyo_keys, struct=hosei.read_struct(gi), proposals=proposals, **confirmed_links())


def confirmed_links(links_dir=LINKS_DIR):
    """議案と回の台帳・○の行と附表の台帳の confirmed の行（台帳が無ければ0行）。gian_hs と hj_fh を返す。"""
    out = {"gian_hs": {}, "hj_fh": {}}
    for method, name, frm in (("gian-yosan", "gian_hs", "gi"), ("hosei-fuhyo", "hj_fh", "hj")):
        for r in ledger.read_ledger(os.path.join(links_dir, f"{method}.tsv"), method, missing_ok=True):
            if r["status"] == ledger.CONFIRMED and r["from"].startswith(frm + ":"):
                out[name].setdefault(r["from"], set()).add(r["to"])
    return out


def _breakdown(counts):
    """内訳の文（0件なら空）。例「（shitsugi 3・yaritori 244。」"""
    return "・".join(f"{k} {v}" for k, v in sorted(counts.items()))


def report_lines(rep):
    L = ["# 記録の台帳の確かめ（records/・ref/themes.tsv・ref/shisetsu.tsv・ref/chiku.tsv・ref/soshiki.tsv）", ""]
    L.append("- 台帳の行の数：" + "・".join(f"{n} {c}" for n, c in rep.counts.items()))
    L.append(f"- 誤り：{len(rep.errors)}")
    L.append(f"- round が turns から求めた値と違う行：{len(rep.round_diff)}（round_diff.tsv）")
    L.append(f"- 引用が資料の本文に無い行：{len(rep.quote_mismatch)}（quote_mismatch.tsv）")
    by = {}
    for r in rep.torikoboshi:
        by[r["ledger"]] = by.get(r["ledger"], 0) + 1
    L.append(f"- 発言の取りこぼし：{len(rep.torikoboshi)}（" + (_breakdown(by) + "。" if by else "") + "torikoboshi.tsv）")
    by = {}
    for r in rep.quote_context:
        by[r["kind"]] = by.get(r["kind"], 0) + 1
    L.append(f"- 引用の前後：{len(rep.quote_context)}（" + (_breakdown(by) + "。" if by else "") + "quote_context.tsv）")
    L.append(f"- 届き先の信号：views の無い点の確定行 {len(rep.signal_todoku)}（signal_todoku.tsv）")
    L.append(f"- 届き先の信号：問いごとの点が空の割合（signal_point.tsv。問い {len(rep.signal_point)}）")
    L.append(f"- 届き先の信号：中心の見方に出る行の割合（signal_chushin.tsv。テーマ {len(rep.signal_chushin)}）")
    L.append("- 参照表の行の数：" + "・".join(f"{n} {c}" for n, c in rep.ref_counts.items()))
    L.append("- target のキーの種類ごとの数：" + "・".join(f"{k} {rep.target_counts.get(k, 0)}" for k in records.TARGET_KINDS))
    L.append("- target_text の種類ごとの数：" + "・".join(f"{k} {rep.text_counts.get(k, 0)}" for k in records.TEXT_KINDS))
    L.append(f"- 対象の照合の (2) に合わない candidate の行：{len(rep.target_unchecked)}（target_unchecked.tsv）")
    L.append(f"- 対象と議案・名前：(a) {len(rep.target_bill)}（target_bill.tsv）・(b) {len(rep.target_name)}（target_name.tsv）")
    if rep.counts.get("teian"):
        groups = {}
        for r in rep.teian_group:
            groups[r["group"]] = int(r["size"])
        L.append(f"- 提案理由の記録：sid が提案の区切りに入っていない行 {len(rep.teian_segment)}（teian_segment.tsv）・"
                 f"名前が引用に無い事情の行 {len(rep.teian_name)}（teian_name.tsv）・事情の行の無い○の行 "
                 f"{len(rep.teian_no_jijo)}（teian_no_jijo.tsv）・同じ文で説明された行の組 {len(groups)}"
                 + (f"（大きさ {'・'.join(f'{k}行 {v}組' for k, v in sorted(Counter(groups.values()).items()))}）"
                    if groups else "") + "（teian_group.tsv）")
    L += struct_lines(rep.struct)
    changed = rep.target_changed
    if changed is not None:
        by = {}
        for r in changed:
            by[r["change"]] = by.get(r["change"], 0) + 1
        L.append(f"- lock を上げるときの比べ方（前の版 {rep.prev_sha[:7]}）：" + "・".join(
            f"{c} {by.get(c, 0)}" for c in ("key が変わった", "行が無くなった", "検収が済まなくなった"))
            + "（target_changed.tsv）")
    if rep.errors:
        L += ["", "## 誤り", ""] + [f"- {e}" for e in rep.errors]
    return L


def struct_lines(st):
    if st is None:
        return []
    same, diff, orphan, other = st.rekey_counts()
    return [f"- 検収の台帳の key の作り直し：同じ {same}・違う {diff}・表に行の無い台帳の行 {orphan}・"
            f"読まない表（hosei-kaikei など）の台帳の行 {other}"]


def write_outputs(outdir, rep):
    os.makedirs(outdir, exist_ok=True)
    files = {
        "round_diff.tsv": (records.ROUND_DIFF_COLUMNS, rep.round_diff),
        "quote_mismatch.tsv": (records.QUOTE_MISMATCH_COLUMNS, rep.quote_mismatch),
        "torikoboshi.tsv": (records.TORIKOBOSHI_COLUMNS, rep.torikoboshi),
        "quote_context.tsv": (records.QUOTE_CONTEXT_COLUMNS, rep.quote_context),
        "signal_todoku.tsv": (records.SIGNAL_TODOKU_COLUMNS, rep.signal_todoku),
        "signal_point.tsv": (records.SIGNAL_POINT_COLUMNS, rep.signal_point),
        "signal_chushin.tsv": (records.SIGNAL_CHUSHIN_COLUMNS, rep.signal_chushin),
        "target_unchecked.tsv": (records.TARGET_UNCHECKED_COLUMNS, rep.target_unchecked),
        "target_bill.tsv": (records.TARGET_BILL_COLUMNS, rep.target_bill),
        "target_name.tsv": (records.TARGET_NAME_COLUMNS, rep.target_name),
        "teian_segment.tsv": (records.TEIAN_SEGMENT_COLUMNS, rep.teian_segment),
        "teian_name.tsv": (records.TEIAN_NAME_COLUMNS, rep.teian_name),
        "teian_no_jijo.tsv": (records.TEIAN_NO_JIJO_COLUMNS, rep.teian_no_jijo),
        "teian_group.tsv": (records.TEIAN_GROUP_COLUMNS, rep.teian_group),
    }
    if rep.target_changed is not None:
        files["target_changed.tsv"] = (records.TARGET_CHANGED_COLUMNS, rep.target_changed)
    for name, (cols, rows) in files.items():
        with open(os.path.join(outdir, name), "w", encoding="utf-8", newline="\n") as f:
            f.write(records.format_tsv(cols, rows))
    with open(os.path.join(outdir, "check.md"), "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(report_lines(rep)) + "\n")


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv[1:]
    if args and (len(args) != 2 or args[0] != "--prev"):
        print(USAGE, file=sys.stderr)
        return 1
    try:
        lock = gm.load_lock(gm.LOCK_PATH)
        gi = gm.GitInputs(gm.INPUTS_ROOT, lock)
        gi.verify()
        inp = read_inputs(gi)
        prev = None
        if args:
            pgi = gm.GitInputs(gm.INPUTS_ROOT, hosei.lock_with_sha(lock, args[1]))
            pgi.verify()
            prev = hosei.read_struct(pgi, optional=True)
        ledgers = {n: read_file(os.path.join(RECORDS_DIR, f"{n}.tsv"), records.COLUMNS[n], n in records.OPTIONAL)
                   for n in records.LEDGERS}
        themes = read_file(THEMES, records.THEME_COLUMNS)
        shisetsu = read_file(SHISETSU, records.SHISETSU_COLUMNS)
        chiku, soshiki = read_area_refs()
    except (gm.GenError, records.RecordsError, mention.RefError) as e:
        print(f"停止：{e}", file=sys.stderr)
        return 1
    rep = records.check_all(ledgers, themes, shisetsu, inp, chiku, soshiki)
    rep.struct = inp.struct
    if prev is not None:
        rep.prev_sha = args[1]
        rep.target_changed = records.target_changed(ledgers, prev, inp.struct)
    write_outputs(OUT_DIR, rep)
    lines = report_lines(rep)
    print("\n".join(lines[2:lines.index("## 誤り") - 1] if "## 誤り" in lines else lines[2:]))
    if rep.errors:
        for e in rep.errors[:EXAMPLES]:
            print(f"  {e}", file=sys.stderr)
        if len(rep.errors) > EXAMPLES:
            print(f"  ほか {len(rep.errors) - EXAMPLES} 件（build/records/check.md）", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
