"""台帳 links/mention.tsv を確かめる（LINK_SCHEMA.md §5・§6・§11、DESIGN.md §5 工程4-4）。ビルドのたびに動かす。

inputs.lock.json の版の入力で、台帳の形（§11）・§5 の照合・根拠の消失・台帳と lock の版・sentinel を確かめる。
台帳には書かない。一覧と報告は build/links/mention/ に書く。

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
EXAMPLES = 10


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
         f"一致になった行 {len(rep.sentinel_failures)}",
         f"- 判定：{'合格' if rep.exit_code == 0 else '停止'}"]
    if rep.stale:
        L += ["", f"台帳が lock の版で更新されていない。tools/update_links.py を先に動かす。違う行（先頭{EXAMPLES}件）：", ""]
        L += [f"- {' '.join(k)}" for k in rep.stale[:EXAMPLES]]
    if rep.sentinel_failures:
        L += ["", f"sentinel で一致になった行（先頭{EXAMPLES}件）：", ""]
        L += [f"- {r['from']} {r['to']}：{r['context']}" for r in rep.sentinel_failures[:EXAMPLES]]
    return L


def run(built, ledger_path, outdir):
    """台帳を確かめる。返り値は（終了コード、台帳の行、Report）。台帳には書かない。"""
    rows = ledger.read_ledger(ledger_path, METHOD)
    corpus = ledger.make_corpus(built.inputs, built.refs)
    rep = ledger.check_ledger(rows, ledger.generated_rows(built), corpus)
    ledger.write_lists(outdir, rep.checked, rep.merged, update=False)
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
        code, rows, rep = run(built, LEDGER_PATH, OUT_DIR)
    except (gm.GenError, mention.RefError) as e:
        print(f"停止：{e}", file=sys.stderr)
        return 1
    lines = report_lines(rows, rep)[2:]
    print("\n".join(lines), file=sys.stderr if code else sys.stdout)
    return code


if __name__ == "__main__":
    sys.exit(main())
