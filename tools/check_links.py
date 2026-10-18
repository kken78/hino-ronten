"""台帳 links/mention.tsv と links/relink.tsv を確かめる（LINK_SCHEMA.md §5・§6・§11、DESIGN.md §5 工程4-4）。
ビルドのたびに動かす。

inputs.lock.json の版の入力で、台帳の形（§11）・§5 の照合・根拠の消失・台帳と lock の版・sentinel を確かめる。
links/relink.tsv（人が付け替えた行。無ければ0行）には、台帳の形・§5 の照合・sentinel・付け替えの元・
付け替えの重なりをかける（台帳と lock の版・根拠の消失はかけない。機械が作らないため）。
台帳には書かない。一覧と報告は build/links/mention/ に、relink の一覧は build/links/relink/ に書く。

実行: python3 -B tools/check_links.py
終了コード：0 は合格（移動・移動先が見つからない rejected は一覧に出すだけ）。1 は止めた（件数と該当を表示する）。
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import gen_mentions as gm  # noqa: E402
import ledger  # noqa: E402
import mention  # noqa: E402

METHOD = "mention"
LEDGER_PATH = os.path.join(gm.ROOT, "links", f"{METHOD}.tsv")
OUT_DIR = os.path.join(gm.ROOT, "build", "links", METHOD)
RELINK = "relink"
RELINK_PATH = os.path.join(gm.ROOT, "links", f"{RELINK}.tsv")
RELINK_OUT_DIR = os.path.join(gm.ROOT, "build", "links", RELINK)
EXAMPLES = 10


def relink_path_of(ledger_path):
    """mention の台帳と同じ場所の relink の台帳（links/relink.tsv）。"""
    return os.path.join(os.path.dirname(ledger_path), f"{RELINK}.tsv")


def relink_outdir_of(outdir):
    """mention の一覧（build/links/mention/）に並ぶ relink の一覧の場所（build/links/relink/）。"""
    return os.path.join(os.path.dirname(outdir), RELINK)


def report_lines(rows, rep):
    c = rep.checked.counts
    L = ["# 台帳の確かめ（links/mention.tsv）", "",
         f"- 台帳：{len(rows)} 行（{'・'.join(f'{s} {sum(1 for r in rows if r['status'] == s)}' for s in ledger.STATUSES)}）",
         f"- §5 の照合（confirmed・candidate）：一致 {c[ledger.MATCH]}・移動 {c[ledger.MOVED]}・停止 {c[ledger.STOPPED]}",
         f"- rejected の移動 {sum(1 for r in rep.checked.moved if r['status'] == ledger.REJECTED)}・"
         f"移動先が見つからない rejected {len(rep.checked.rejected_unmatched)}",
         f"- 根拠の消失（再生成で出なくなった confirmed）：{len(rep.merged.vanished_confirmed)}",
         f"- 台帳と lock の版：作り直した台帳と違う行 {len(rep.stale)}",
         f"- sentinel：{len(rows) - sum(1 for r in rows if r['status'] == ledger.REJECTED)} 行で確かめ、"
         f"一致になった行 {len(rep.sentinel_failures)}"]
    rr = rep.relink
    rc = rr.checked.counts
    L += [f"- 付け替え（links/relink.tsv）：{len(rr.rows)} 行（"
          f"{'・'.join(f'{s} {sum(1 for r in rr.rows if r['status'] == s)}' for s in (ledger.CONFIRMED, ledger.REJECTED))}）",
          f"- 付け替えの §5 の照合（confirmed）：一致 {rc[ledger.MATCH]}・移動 {rc[ledger.MOVED]}・停止 {rc[ledger.STOPPED]}"
          f"、sentinel で一致になった行 {len(rr.sentinel_failures)}",
          f"- 付け替えの元の誤り {len(rr.origin_errors)}・付け替えの重なり {len(rr.conflicts)}",
          f"- 判定：{'合格' if rep.exit_code == 0 else '停止'}"]
    if rep.stale:
        L += ["", f"台帳が lock の版で更新されていない。tools/update_links.py を先に動かす。違う行（先頭{EXAMPLES}件）：", ""]
        L += [f"- {' '.join(k)}" for k in rep.stale[:EXAMPLES]]
    if rep.sentinel_failures:
        L += ["", f"sentinel で一致になった行（先頭{EXAMPLES}件）：", ""]
        L += [f"- {r['from']} {r['to']}：{r['context']}" for r in rep.sentinel_failures[:EXAMPLES]]
    if rr.origin_errors:
        L += ["", "付け替えの元の誤り（全件）：", ""]
        L += [f"- {e}" for e in rr.origin_errors]
    if rr.conflicts:
        L += ["", f"付け替えの重なり（build/links/relink/relink_conflict.tsv。先頭{EXAMPLES}件）：", ""]
        L += [f"- {r['from']} {r['to']}：relink {r['relink_status']}・mention {r['mention_status']}"
              for r in rr.conflicts[:EXAMPLES]]
    if rr.checked.stopped:
        L += ["", f"付け替えの §5 の照合で停止した行（build/links/relink/stopped.tsv。先頭{EXAMPLES}件）：", ""]
        L += [f"- {r['from']} {r['to']}：{r['reason']}" for r in rr.checked.stopped[:EXAMPLES]]
    if rr.sentinel_failures:
        L += ["", f"付け替えの sentinel で一致になった行（先頭{EXAMPLES}件）：", ""]
        L += [f"- {r['from']} {r['to']}：{r['context']}" for r in rr.sentinel_failures[:EXAMPLES]]
    return L


def run(built, ledger_path, outdir, relink_path=None, relink_outdir=None):
    """台帳を確かめる。返り値は（終了コード、台帳の行、Report）。台帳には書かない。
    relink の台帳と一覧の場所は、省くと mention の台帳と一覧の場所に並べる。"""
    rows = ledger.read_ledger(ledger_path, METHOD)
    relink_rows = ledger.read_ledger(relink_path or relink_path_of(ledger_path), RELINK, missing_ok=True)
    corpus = ledger.make_corpus(built.inputs, built.refs)
    rep = ledger.check_ledger(rows, ledger.generated_rows(built), corpus, relink_rows)
    ledger.write_lists(outdir, rep.checked, rep.merged, update=False)
    ledger.write_relink_lists(relink_outdir or relink_outdir_of(outdir), rep.relink)
    with open(os.path.join(outdir, "check.md"), "wb") as f:
        f.write(("\n".join(report_lines(rows, rep)) + "\n").encode("utf-8"))
    return rep.exit_code, rows, rep


def main():
    try:
        refs = mention.load_refs(gm.LINEAGE, gm.ALIASES)
        lock = gm.load_lock(gm.LOCK_PATH)
        gi = gm.GitInputs(gm.INPUTS_ROOT, lock)
        gi.verify()
        built = gm.build(gm.read_inputs(gi, lock), refs)
        code, rows, rep = run(built, LEDGER_PATH, OUT_DIR, RELINK_PATH, RELINK_OUT_DIR)
    except (gm.GenError, mention.RefError) as e:
        print(f"停止：{e}", file=sys.stderr)
        return 1
    lines = report_lines(rows, rep)[2:]
    print("\n".join(lines), file=sys.stderr if code else sys.stdout)
    return code


if __name__ == "__main__":
    sys.exit(main())
