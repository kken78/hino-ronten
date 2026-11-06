"""台帳 links/mention.tsv・links/fuhyo.tsv・links/fuhyo-years.tsv を更新する（LINK_SCHEMA.md §6・§11、
DESIGN.md §5 工程4-3・工程5・ADR-33）。

inputs.lock.json の版から tools/gen_mentions.py の build で候補を作り（build/mention/ のファイルは読まない）、
tools/ledger.py の merge で台帳に合わせて書く。台帳と同じ場所の links/relink.tsv（無ければ0行）を読み、
付け替え済みの組は candidate にしない（§6）。一覧と報告は build/links/mention/ に書く。
--ledger fuhyo のときは、tools/gen_fuhyo.py の build で附表の候補を作り（build/fuhyo/ のファイルは読まない）、
links/fuhyo.tsv に合わせて書く。付け替えは使わない（§6）。一覧と報告は build/links/fuhyo/ に書く。
--ledger fuhyo-years のときは、tools/gen_fuhyo_years.py の build で名前の一致の候補を作り、links/fuhyo-years.tsv に
合わせて書く。manual の行（人が足した行）は変えない（§6）。一覧と報告は build/links/fuhyo-years/ に書く。
機械が作るのは candidate だけ（DESIGN.md ADR-2）。

実行: python3 -B tools/update_links.py              （links/mention.tsv）
      python3 -B tools/update_links.py --ledger fuhyo （links/fuhyo.tsv）
      python3 -B tools/update_links.py --ledger fuhyo-years （links/fuhyo-years.tsv）
終了コード：0 は台帳を書いた。1 は止めた（台帳は書かない。件数と該当を表示し、一覧を build/links/<method>/ に書く）。
止めるのは、使い方の誤り・台帳の形の誤り・入力の誤り・§5 の停止・再生成で出なくなった confirmed があるとき。
--ledger fuhyo のときは、附表の分類（§11）の誤りがあるときも止める（誤りの事業を表示する）。
--ledger fuhyo-years のときは、年度の対応（§11）の誤りがあるときも止める（誤りの行を表示する）。
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import check_links  # noqa: E402
import gen_fuhyo  # noqa: E402
import gen_fuhyo_years  # noqa: E402
import gen_mentions as gm  # noqa: E402
import ledger  # noqa: E402
import mention  # noqa: E402

METHOD = "mention"
LEDGER_PATH = os.path.join(gm.ROOT, "links", f"{METHOD}.tsv")
OUT_DIR = os.path.join(gm.ROOT, "build", "links", METHOD)
FUHYO = check_links.FUHYO
YEARS = check_links.YEARS
USAGE = "使い方：python3 -B tools/update_links.py [--ledger fuhyo | --ledger fuhyo-years]"


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


def fuhyo_report_lines(merged, checked, wrote, classification):
    c = checked.counts
    rows = merged.rows
    return ["# 台帳の更新（links/fuhyo.tsv）", "",
            f"- 台帳：{'書いた' if wrote else '書いていない（止めた）'}。{len(rows)} 行"
            f"（{'・'.join(f'{s} {sum(1 for r in rows if r['status'] == s)}' for s in ledger.STATUSES)}。"
            f"node {sum(1 for r in rows if r['to'].startswith('node:'))}・"
            f"none {sum(1 for r in rows if r['to'].startswith('none:'))}）",
            f"- 足した candidate {len(merged.added)}・値が変わった candidate {len(merged.updated)}"
            f"（うち note {len(merged.note_changed)}）・削除した candidate {len(merged.removed)}",
            f"- 再生成で出なくなった confirmed {len(merged.vanished_confirmed)}・rejected "
            f"{len(merged.vanished) - len(merged.vanished_confirmed)}",
            f"- §5 の照合（confirmed・candidate）：一致 {c[ledger.MATCH]}・移動 {c[ledger.MOVED]}・停止 {c[ledger.STOPPED]}",
            f"- 附表の分類：附表の事業 {classification.total}・分類済み {len(classification.classified)}・"
            f"候補のある事業 {len(classification.pending)}・分類の誤り {len(classification.errors)}"]


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


def run_fuhyo(fbuilt, ledger_path, outdir):
    """附表の台帳を更新する（§6）。返り値は（終了コード、Merged、Checked、Classification）。止めるときは台帳を書かない。"""
    current = ledger.read_ledger(ledger_path, FUHYO, missing_ok=True)
    corpus = gen_fuhyo.corpus(fbuilt)
    merged = ledger.merge(current, gen_fuhyo.generated_rows(fbuilt), corpus)
    checked = ledger.check_rows(merged.rows, corpus)
    ledger.parse_ledger(ledger.format_ledger(merged.rows), FUHYO)  # 書く前に §11 の形を確かめる
    classification = ledger.classify_fuhyo(merged.rows, gen_fuhyo.fuhyo_keys(fbuilt))
    code = 1 if (checked.stopped or merged.vanished_confirmed or classification.errors) else 0
    if code == 0:
        ledger.write_ledger(ledger_path, merged.rows)
    ledger.write_lists(outdir, checked, merged, update=True)
    with open(os.path.join(outdir, "update.md"), "wb") as f:
        f.write(("\n".join(fuhyo_report_lines(merged, checked, code == 0, classification)) + "\n").encode("utf-8"))
    return code, merged, checked, classification


def years_report_lines(merged, checked, wrote, errors, ybuilt):
    c = checked.counts
    rows = merged.rows
    return ["# 台帳の更新（links/fuhyo-years.tsv）", "",
            f"- 台帳：{'書いた' if wrote else '書いていない（止めた）'}。{len(rows)} 行"
            f"（{'・'.join(f'{s} {sum(1 for r in rows if r['status'] == s)}' for s in ledger.STATUSES)}。"
            f"name {sum(1 for r in rows if r['method'] == gen_fuhyo_years.NAME)}・"
            f"manual {sum(1 for r in rows if r['method'] == gen_fuhyo_years.MANUAL)}）",
            f"- 足した candidate {len(merged.added)}・値が変わった candidate {len(merged.updated)}"
            f"（うち note {len(merged.note_changed)}）・削除した candidate {len(merged.removed)}",
            f"- 再生成で出なくなった confirmed {len(merged.vanished_confirmed)}・rejected "
            f"{len(merged.vanished) - len(merged.vanished_confirmed)}",
            f"- §5 の照合（confirmed・candidate）：一致 {c[ledger.MATCH]}・移動 {c[ledger.MOVED]}・停止 {c[ledger.STOPPED]}",
            f"- 年度の対応の誤り：{len(errors)}"] + gen_fuhyo_years.count_lines(rows, ybuilt)


def run_years(ybuilt, ledger_path, outdir):
    """年度の台帳を更新する（§6）。返り値は（終了コード、Merged、Checked、年度の対応の誤り）。止めるときは台帳を書かない。"""
    current = ledger.read_ledger(ledger_path, YEARS, missing_ok=True)
    corpus = gen_fuhyo_years.corpus(ybuilt)
    merged = ledger.merge(current, gen_fuhyo_years.generated_rows(ybuilt), corpus)
    checked = ledger.check_rows(merged.rows, corpus)
    ledger.parse_ledger(ledger.format_ledger(merged.rows), YEARS)  # 書く前に §11 の形を確かめる
    errors = gen_fuhyo_years.years_errors(merged.rows, ybuilt)
    code = 1 if (checked.stopped or merged.vanished_confirmed or errors) else 0
    if code == 0:
        ledger.write_ledger(ledger_path, merged.rows)
    ledger.write_lists(outdir, checked, merged, update=True)
    gen_fuhyo_years.write_rename_lists(outdir, ybuilt)
    with open(os.path.join(outdir, "update.md"), "wb") as f:
        f.write(("\n".join(years_report_lines(merged, checked, code == 0, errors, ybuilt)) + "\n").encode("utf-8"))
    return code, merged, checked, errors


def _stop_messages(merged, checked, outdir):
    if checked.stopped:
        print(f"停止：§5 の照合で停止した行 {len(checked.stopped)} 件（{outdir}/stopped.tsv）", file=sys.stderr)
    if merged.vanished_confirmed:
        print(f"停止：再生成で出なくなった confirmed {len(merged.vanished_confirmed)} 件（{outdir}/vanished.tsv）",
              file=sys.stderr)


def main_fuhyo():
    try:
        code, merged, checked, classification = run_fuhyo(gen_fuhyo.load_built(), check_links.FUHYO_PATH,
                                                          check_links.FUHYO_OUT_DIR)
    except gm.GenError as e:
        print(f"停止：{e}", file=sys.stderr)
        return 1
    print("\n".join(fuhyo_report_lines(merged, checked, code == 0, classification)[2:]))
    _stop_messages(merged, checked, check_links.FUHYO_OUT_DIR)
    if classification.errors:
        print(f"停止：附表の分類の誤り {len(classification.errors)} 件", file=sys.stderr)
        for e in classification.errors:
            print(f"  {e}", file=sys.stderr)
    return code


def main_years():
    try:
        ybuilt = gen_fuhyo_years.load_built()
        code, merged, checked, errors = run_years(ybuilt, check_links.YEARS_PATH, check_links.YEARS_OUT_DIR)
    except gm.GenError as e:
        print(f"停止：{e}", file=sys.stderr)
        return 1
    print("\n".join(years_report_lines(merged, checked, code == 0, errors, ybuilt)[2:]))
    _stop_messages(merged, checked, check_links.YEARS_OUT_DIR)
    if errors:
        print(f"停止：年度の対応の誤り {len(errors)} 件", file=sys.stderr)
        for e in errors:
            print(f"  {e}", file=sys.stderr)
    return code


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv[1:]
    if args == ["--ledger", FUHYO]:
        return main_fuhyo()
    if args == ["--ledger", YEARS]:
        return main_years()
    if args:
        print(USAGE, file=sys.stderr)
        return 1
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
    _stop_messages(merged, checked, OUT_DIR)
    return code


if __name__ == "__main__":
    sys.exit(main())
