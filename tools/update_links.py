"""台帳 links/mention.tsv を更新する（LINK_SCHEMA.md §6・§11、DESIGN.md §5 工程4-3）。

inputs.lock.json の版から tools/gen_mentions.py の build で候補を作り（build/mention/ のファイルは読まない）、
tools/ledger.py の merge で台帳に合わせて書く。台帳と同じ場所の links/relink.tsv（無ければ0行）を読み、
付け替え済みの組は candidate にしない（§6）。一覧と報告は build/links/mention/ に書く。
機械が作るのは candidate だけ（DESIGN.md ADR-2）。

実行: python3 -B tools/update_links.py
終了コード：0 は台帳を書いた。1 は止めた（台帳は書かない。件数と該当を表示し、一覧を build/links/mention/ に書く）。
止めるのは、台帳の形の誤り・入力の誤り・§5 の停止・再生成で出なくなった confirmed があるとき。
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import check_links  # noqa: E402
import gen_mentions as gm  # noqa: E402
import ledger  # noqa: E402
import mention  # noqa: E402

METHOD = "mention"
LEDGER_PATH = os.path.join(gm.ROOT, "links", f"{METHOD}.tsv")
OUT_DIR = os.path.join(gm.ROOT, "build", "links", METHOD)


def report_lines(merged, checked, wrote):
    c = checked.counts
    L = ["# 台帳の更新（links/mention.tsv）", "",
         f"- 台帳：{'書いた' if wrote else '書いていない（止めた）'}。{len(merged.rows)} 行"
         f"（{'・'.join(f'{s} {sum(1 for r in merged.rows if r['status'] == s)}' for s in ledger.STATUSES)}）",
         f"- 足した candidate {len(merged.added)}・値が変わった candidate {len(merged.updated)}"
         f"（うち note {len(merged.note_changed)}）・削除した candidate {len(merged.removed)}",
         f"- 移動先なので candidate にしなかった組 {len(merged.suppressed)}",
         f"- 付け替え済みなので candidate にしなかった組 {len(merged.relinked)}",
         f"- 再生成で出なくなった confirmed {len(merged.vanished_confirmed)}・rejected "
         f"{len(merged.vanished) - len(merged.vanished_confirmed)}",
         f"- §5 の照合（confirmed・candidate）：一致 {c[ledger.MATCH]}・移動 {c[ledger.MOVED]}・停止 {c[ledger.STOPPED]}",
         f"- rejected の移動 {sum(1 for r in checked.moved if r['status'] == ledger.REJECTED)}・"
         f"移動先が見つからない rejected {len(checked.rejected_unmatched)}"]
    return L


def run(built, ledger_path, outdir, relink_path=None):
    """台帳を更新する。返り値は（終了コード、Merged、Checked）。止めるときは台帳を書かない。
    relink の台帳の場所は、省くと mention の台帳と同じ場所（links/relink.tsv）。"""
    current = ledger.read_ledger(ledger_path, METHOD, missing_ok=True)
    relink_rows = ledger.read_ledger(relink_path or check_links.relink_path_of(ledger_path), check_links.RELINK,
                                     missing_ok=True)
    corpus = ledger.make_corpus(built.inputs, built.refs)
    merged = ledger.merge(current, ledger.generated_rows(built), corpus, relink_rows)
    checked = ledger.check_rows(merged.rows, corpus)
    ledger.parse_ledger(ledger.format_ledger(merged.rows), METHOD)  # 書く前に §11 の形を確かめる
    code = 1 if (checked.stopped or merged.vanished_confirmed) else 0
    if code == 0:
        ledger.write_ledger(ledger_path, merged.rows)
    ledger.write_lists(outdir, checked, merged, update=True)
    with open(os.path.join(outdir, "update.md"), "wb") as f:
        f.write(("\n".join(report_lines(merged, checked, code == 0)) + "\n").encode("utf-8"))
    return code, merged, checked


def main():
    try:
        refs = mention.load_refs(gm.LINEAGE, gm.ALIASES)
        lock = gm.load_lock(gm.LOCK_PATH)
        gi = gm.GitInputs(gm.INPUTS_ROOT, lock)
        gi.verify()
        built = gm.build(gm.read_inputs(gi, lock), refs)
        code, merged, checked = run(built, LEDGER_PATH, OUT_DIR, check_links.RELINK_PATH)
    except (gm.GenError, mention.RefError) as e:
        print(f"停止：{e}", file=sys.stderr)
        return 1
    print("\n".join(report_lines(merged, checked, code == 0)[2:]))
    if checked.stopped:
        print(f"停止：§5 の照合で停止した行 {len(checked.stopped)} 件（{OUT_DIR}/stopped.tsv）", file=sys.stderr)
    if merged.vanished_confirmed:
        print(f"停止：再生成で出なくなった confirmed {len(merged.vanished_confirmed)} 件（{OUT_DIR}/vanished.tsv）",
              file=sys.stderr)
    return code


if __name__ == "__main__":
    sys.exit(main())
