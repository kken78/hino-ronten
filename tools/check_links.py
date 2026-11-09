"""台帳 links/mention.tsv・links/relink.tsv・links/fuhyo.tsv・links/fuhyo-years.tsv を確かめる（LINK_SCHEMA.md §5・§6・§11、
DESIGN.md §5 工程4-4・工程5・ADR-33）。ビルドのたびに動かす。

inputs.lock.json の版の入力で、台帳の形（§11）・§5 の照合・根拠の消失・台帳と lock の版・sentinel を確かめる。
links/relink.tsv（人が付け替えた行。無ければ0行）には、台帳の形・§5 の照合・sentinel・付け替えの元・
付け替えの重なりをかける（台帳と lock の版・根拠の消失はかけない。機械が作らないため）。
links/fuhyo.tsv（附表の台帳）には、mention と同じ検査と、附表の分類（§11）をかける。無ければ、
tools/update_links.py --ledger fuhyo を先に動かすよう示して止める。
links/fuhyo-years.tsv（年度の台帳）には、mention と同じ検査と、年度の対応（§11）をかける。manual の行（人が足した行）は、
生成の結果に無くても根拠の消失に数えない（§6）。無ければ、tools/update_links.py --ledger fuhyo-years を先に動かすよう示して止める。
links/gian-yosan.tsv（議案と回の台帳）には、台帳の形・§5 の照合（to の hs。from の gi は §5 に決まりが無いので照合しない）・
根拠の消失・台帳と lock の版をかけ、confirmed の行の to の hs が検収の済んだ行（§2）でなければ止める。sentinel は
かけない（tools/ledger.py の NO_FROM_RULE。§5 gi）。回の表に行のある年度の、資料の無い回の議案を no_kai.tsv に出す。
links/hosei-fuhyo.tsv（○の行と附表の台帳）には、mention と同じ検査と、○の行と附表の対応（§11）をかける。manual の行
（人が足した行。to が fh か none）は、生成の結果に無くても根拠の消失に数えない（§6）。名前の一致しない○の行を
name_unmatched.tsv に出す（confirmed の manual の行がある○の行は出さない）。
どちらも、無ければ tools/update_links.py --ledger gian-yosan・--ledger hosei-fuhyo を先に動かすよう示して止める。
台帳には書かない。一覧と報告は build/links/mention/ に、relink の一覧は build/links/relink/ に、
附表の一覧と報告は build/links/fuhyo/ に、年度の台帳の一覧と報告は build/links/fuhyo-years/ に、
議案と回の台帳は build/links/gian-yosan/ に、○の行と附表の台帳は build/links/hosei-fuhyo/ に書く。

実行: python3 -B tools/check_links.py
終了コード：0 は合格（移動・移動先が見つからない rejected は一覧に出すだけ）。1 は止めた（件数と該当を表示する）。
"""
import os
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import gen_fuhyo  # noqa: E402
import gen_fuhyo_years  # noqa: E402
import gen_gian_yosan  # noqa: E402
import gen_hosei_fuhyo  # noqa: E402
import gen_mentions as gm  # noqa: E402
import hosei  # noqa: E402
import ledger  # noqa: E402
import mention  # noqa: E402

METHOD = "mention"
LEDGER_PATH = os.path.join(gm.ROOT, "links", f"{METHOD}.tsv")
OUT_DIR = os.path.join(gm.ROOT, "build", "links", METHOD)
RELINK = "relink"
RELINK_PATH = os.path.join(gm.ROOT, "links", f"{RELINK}.tsv")
RELINK_OUT_DIR = os.path.join(gm.ROOT, "build", "links", RELINK)
FUHYO = gen_fuhyo.METHOD
FUHYO_PATH = os.path.join(gm.ROOT, "links", f"{FUHYO}.tsv")
FUHYO_OUT_DIR = os.path.join(gm.ROOT, "build", "links", FUHYO)
YEARS = gen_fuhyo_years.METHOD
YEARS_PATH = os.path.join(gm.ROOT, "links", f"{YEARS}.tsv")
YEARS_OUT_DIR = os.path.join(gm.ROOT, "build", "links", YEARS)
GIAN = gen_gian_yosan.METHOD
GIAN_PATH = os.path.join(gm.ROOT, "links", f"{GIAN}.tsv")
GIAN_OUT_DIR = os.path.join(gm.ROOT, "build", "links", GIAN)
HOSEI = gen_hosei_fuhyo.METHOD
HOSEI_PATH = os.path.join(gm.ROOT, "links", f"{HOSEI}.tsv")
HOSEI_OUT_DIR = os.path.join(gm.ROOT, "build", "links", HOSEI)
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


def fuhyo_report_lines(rows, rep):
    c = rep.checked.counts
    cl = rep.classification
    L = ["# 台帳の確かめ（links/fuhyo.tsv）", "",
         f"- 附表の台帳：{len(rows)} 行（{'・'.join(f'{s} {sum(1 for r in rows if r['status'] == s)}' for s in ledger.STATUSES)}。"
         f"node {sum(1 for r in rows if r['to'].startswith('node:'))}・none {sum(1 for r in rows if r['to'].startswith('none:'))}）",
         f"- 附表の §5 の照合（confirmed・candidate）：一致 {c[ledger.MATCH]}・移動 {c[ledger.MOVED]}・停止 {c[ledger.STOPPED]}",
         f"- 附表の根拠の消失（再生成で出なくなった confirmed）：{len(rep.merged.vanished_confirmed)}",
         f"- 附表の台帳と lock の版：作り直した台帳と違う行 {len(rep.stale)}",
         f"- 附表の sentinel：{len(rows) - sum(1 for r in rows if r['status'] == ledger.REJECTED)} 行で確かめ、"
         f"一致になった行 {len(rep.sentinel_failures)}",
         f"- 附表の分類：附表の事業 {cl.total}・分類済み {len(cl.classified)}・候補のある事業 {len(cl.pending)}・"
         f"行の無い事業 {len(cl.missing)}・none と node の両方が確定 {len(cl.both)}・候補をすべて却下 {len(cl.all_rejected)}・"
         f"区分の誤り {len(cl.bad_kubun)}",
         f"- 附表の台帳の判定：{'合格' if rep.exit_code == 0 else '停止'}"]
    if rep.checked.stopped:
        L += ["", f"附表の §5 の照合で停止した行（build/links/fuhyo/stopped.tsv。先頭{EXAMPLES}件）：", ""]
        L += [f"- {r['from']} {r['to']}：{r['reason']}" for r in rep.checked.stopped[:EXAMPLES]]
    if rep.stale:
        L += ["", f"附表の台帳が lock の版で更新されていない。tools/update_links.py --ledger fuhyo を先に動かす。"
                  f"違う行（先頭{EXAMPLES}件）：", ""]
        L += [f"- {' '.join(k)}" for k in rep.stale[:EXAMPLES]]
    if rep.sentinel_failures:
        L += ["", f"附表の sentinel で一致になった行（先頭{EXAMPLES}件）：", ""]
        L += [f"- {r['from']} {r['to']}：{r['context']}" for r in rep.sentinel_failures[:EXAMPLES]]
    if cl.errors:
        L += ["", "附表の分類の誤り（全件）：", ""]
        L += [f"- {e}" for e in cl.errors]
    return L


def run_fuhyo(fbuilt, ledger_path, outdir):
    """附表の台帳を確かめる。返り値は（終了コード、台帳の行、Report）。台帳には書かない。
    台帳が無ければ、tools/update_links.py --ledger fuhyo を先に動かすよう示して止める。"""
    if not os.path.exists(ledger_path):
        raise ledger.LedgerError(f"附表の台帳が無い（{ledger_path}）。tools/update_links.py --ledger fuhyo を先に動かす")
    rows = ledger.read_ledger(ledger_path, FUHYO)
    rep = ledger.check_ledger(rows, gen_fuhyo.generated_rows(fbuilt), gen_fuhyo.corpus(fbuilt), relink_rows=None,
                              fuhyo_keys=gen_fuhyo.fuhyo_keys(fbuilt))
    ledger.write_lists(outdir, rep.checked, rep.merged, update=False)
    with open(os.path.join(outdir, "check.md"), "wb") as f:
        f.write(("\n".join(fuhyo_report_lines(rows, rep)) + "\n").encode("utf-8"))
    return rep.exit_code, rows, rep


def years_report_lines(rows, rep, errors, ybuilt):
    c = rep.checked.counts
    by = Counter((r["method"], r["status"]) for r in rows)
    L = ["# 台帳の確かめ（links/fuhyo-years.tsv）", "",
         f"- 年度の台帳：{len(rows)} 行（"
         + "・".join(f"{m} " + "・".join(f"{s} {by[(m, s)]}" for s in ledger.STATUSES)
                     for m in (gen_fuhyo_years.NAME, gen_fuhyo_years.MANUAL)) + "）",
         f"- 年度の台帳の §5 の照合（confirmed・candidate）：一致 {c[ledger.MATCH]}・移動 {c[ledger.MOVED]}・停止 {c[ledger.STOPPED]}",
         f"- 年度の台帳の根拠の消失（再生成で出なくなった confirmed）：{len(rep.merged.vanished_confirmed)}",
         f"- 年度の台帳と lock の版：作り直した台帳と違う行 {len(rep.stale)}",
         f"- 年度の台帳の sentinel：{len(rows) - sum(1 for r in rows if r['status'] == ledger.REJECTED)} 行で確かめ、"
         f"一致になった行 {len(rep.sentinel_failures)}",
         f"- 年度の対応の誤り：{len(errors)}"]
    L += gen_fuhyo_years.count_lines(rows, ybuilt)
    L += [f"- 年度の台帳の判定：{'合格' if rep.exit_code == 0 and not errors else '停止'}"]
    if rep.checked.stopped:
        L += ["", f"年度の台帳の §5 の照合で停止した行（build/links/fuhyo-years/stopped.tsv。先頭{EXAMPLES}件）：", ""]
        L += [f"- {r['from']} {r['to']}：{r['reason']}" for r in rep.checked.stopped[:EXAMPLES]]
    if rep.stale:
        L += ["", f"年度の台帳が lock の版で更新されていない。tools/update_links.py --ledger fuhyo-years を先に動かす。"
                  f"違う行（先頭{EXAMPLES}件）：", ""]
        L += [f"- {' '.join(k)}" for k in rep.stale[:EXAMPLES]]
    if rep.sentinel_failures:
        L += ["", f"年度の台帳の sentinel で一致になった行（先頭{EXAMPLES}件）：", ""]
        L += [f"- {r['from']} {r['to']}：{r['context']}" for r in rep.sentinel_failures[:EXAMPLES]]
    if errors:
        L += ["", "年度の対応の誤り（全件）：", ""]
        L += [f"- {e}" for e in errors]
    return L


def run_years(ybuilt, ledger_path, outdir):
    """年度の台帳を確かめる。返り値は（終了コード、台帳の行、Report、年度の対応の誤り）。台帳には書かない。
    台帳が無ければ、tools/update_links.py --ledger fuhyo-years を先に動かすよう示して止める。"""
    if not os.path.exists(ledger_path):
        raise ledger.LedgerError(f"年度の台帳が無い（{ledger_path}）。tools/update_links.py --ledger fuhyo-years を先に動かす")
    rows = ledger.read_ledger(ledger_path, YEARS)
    rep = ledger.check_ledger(rows, gen_fuhyo_years.generated_rows(ybuilt), gen_fuhyo_years.corpus(ybuilt),
                              relink_rows=None)
    errors = gen_fuhyo_years.years_errors(rows, ybuilt)
    ledger.write_lists(outdir, rep.checked, rep.merged, update=False)
    gen_fuhyo_years.write_rename_lists(outdir, ybuilt)
    with open(os.path.join(outdir, "check.md"), "wb") as f:
        f.write(("\n".join(years_report_lines(rows, rep, errors, ybuilt)) + "\n").encode("utf-8"))
    return (1 if rep.exit_code or errors else 0), rows, rep, errors


def struct_lines(struct):
    """構造化の層の行の数と、検収の台帳の key の作り直し（§2 の (1)）・検収の状態の件数。"""
    counts, states = struct.counts()
    same, diff, orphan, other = struct.rekey_counts()
    return [f"- 構造化の層：回 {counts['回']}・資料のページ {counts['資料のページ']}・款の行 {counts[hosei.KAN]}・"
            f"主な内容の行 {counts[hosei.MARU]}・事項 {counts[hosei.JIKO]}",
            f"- 検収の台帳の key の作り直し：同じ {same}・違う {diff}・表に行の無い台帳の行 {orphan}・"
            f"読まない表（hosei-kaikei など）の台帳の行 {other}",
            "- 検収の状態（款の行・主な内容の行・事項）：" + "・".join(f"{k} {v}" for k, v in sorted(states.items()))]


def gian_errors(rows, struct):
    """§11 ○の行と附表の対応の後半：議案と回の台帳の confirmed の行の to の hs が、検収の済んだ行（§2）。"""
    return [f"{r['from']} {r['to']} {r['method']}：confirmed の行の to が検収の済んだ行でない（LINK_SCHEMA §2）"
            for r in rows if r["status"] == ledger.CONFIRMED and not struct.is_checked(r["to"])]


def gian_report_lines(rows, rep, errors, gbuilt):
    c = rep.checked.counts
    L = ["# 台帳の確かめ（links/gian-yosan.tsv）", "",
         f"- 議案と回の台帳：{len(rows)} 行（{'・'.join(f'{s} {sum(1 for r in rows if r['status'] == s)}' for s in ledger.STATUSES)}）",
         f"- 議案と回の台帳の §5 の照合（confirmed・candidate。to の hs だけ）：一致 {c[ledger.MATCH]}・"
         f"移動 {c[ledger.MOVED]}・停止 {c[ledger.STOPPED]}",
         f"- 議案と回の台帳の根拠の消失（再生成で出なくなった confirmed）：{len(rep.merged.vanished_confirmed)}",
         f"- 議案と回の台帳と lock の版：作り直した台帳と違う行 {len(rep.stale)}",
         f"- 議案と回の台帳の sentinel：from の gi は §5 に決まりが無いのでかけない（{len(rows)} 行）",
         f"- confirmed の行の to が検収の済んだ行でない：{len(errors)}"]
    L += gen_gian_yosan.count_lines(rows, gbuilt) + struct_lines(gbuilt.inputs.struct)
    L += [f"- 議案と回の台帳の判定：{'合格' if rep.exit_code == 0 and not errors else '停止'}"]
    if rep.checked.stopped:
        L += ["", f"§5 の照合で停止した行（build/links/gian-yosan/stopped.tsv。先頭{EXAMPLES}件）：", ""]
        L += [f"- {r['from']} {r['to']}：{r['reason']}" for r in rep.checked.stopped[:EXAMPLES]]
    if rep.stale:
        L += ["", f"議案と回の台帳が lock の版で更新されていない。tools/update_links.py --ledger gian-yosan を先に動かす。"
                  f"違う行（先頭{EXAMPLES}件）：", ""]
        L += [f"- {' '.join(k)}" for k in rep.stale[:EXAMPLES]]
    if errors:
        L += ["", "検収の済んだ行でない confirmed の行（全件）：", ""] + [f"- {e}" for e in errors]
    return L


def run_gian(gbuilt, ledger_path, outdir):
    """議案と回の台帳を確かめる。返り値は（終了コード、台帳の行、Report、誤り）。台帳には書かない。"""
    if not os.path.exists(ledger_path):
        raise ledger.LedgerError(f"議案と回の台帳が無い（{ledger_path}）。tools/update_links.py --ledger gian-yosan を先に動かす")
    rows = ledger.read_ledger(ledger_path, GIAN)
    rep = ledger.check_ledger(rows, gen_gian_yosan.generated_rows(gbuilt), gen_gian_yosan.corpus(gbuilt),
                              relink_rows=None)
    errors = gian_errors(rows, gbuilt.inputs.struct)
    ledger.write_lists(outdir, rep.checked, rep.merged, update=False)
    gen_gian_yosan.write_lists(outdir, gbuilt)
    with open(os.path.join(outdir, "check.md"), "wb") as f:
        f.write(("\n".join(gian_report_lines(rows, rep, errors, gbuilt)) + "\n").encode("utf-8"))
    return (1 if rep.exit_code or errors else 0), rows, rep, errors


def hosei_report_lines(rows, rep, errors, hbuilt):
    c = rep.checked.counts
    by = Counter((r["method"], r["status"]) for r in rows)
    L = ["# 台帳の確かめ（links/hosei-fuhyo.tsv）", "",
         f"- ○の行と附表の台帳：{len(rows)} 行（"
         + "・".join(f"{m} " + "・".join(f"{s} {by[(m, s)]}" for s in ledger.STATUSES)
                     for m in (gen_hosei_fuhyo.NAME, gen_hosei_fuhyo.MANUAL)) + "）",
         f"- ○の行と附表の台帳の §5 の照合（confirmed・candidate）：一致 {c[ledger.MATCH]}・移動 {c[ledger.MOVED]}・"
         f"停止 {c[ledger.STOPPED]}",
         f"- ○の行と附表の台帳の根拠の消失（再生成で出なくなった confirmed）：{len(rep.merged.vanished_confirmed)}",
         f"- ○の行と附表の台帳と lock の版：作り直した台帳と違う行 {len(rep.stale)}",
         f"- ○の行と附表の台帳の sentinel：{ledger.sentinel_rows(rows)} 行で確かめ、一致になった行 {len(rep.sentinel_failures)}",
         f"- ○の行と附表の対応の誤り：{len(errors)}"]
    L += gen_hosei_fuhyo.count_lines(rows, hbuilt)
    L += [f"- ○の行と附表の台帳の判定：{'合格' if rep.exit_code == 0 and not errors else '停止'}"]
    if rep.checked.stopped:
        L += ["", f"§5 の照合で停止した行（build/links/hosei-fuhyo/stopped.tsv。先頭{EXAMPLES}件）：", ""]
        L += [f"- {r['from']} {r['to']}：{r['reason']}" for r in rep.checked.stopped[:EXAMPLES]]
    if rep.stale:
        L += ["", f"○の行と附表の台帳が lock の版で更新されていない。tools/update_links.py --ledger hosei-fuhyo を先に動かす。"
                  f"違う行（先頭{EXAMPLES}件）：", ""]
        L += [f"- {' '.join(k)}" for k in rep.stale[:EXAMPLES]]
    if rep.sentinel_failures:
        L += ["", f"sentinel で一致になった行（先頭{EXAMPLES}件）：", ""]
        L += [f"- {r['from']} {r['to']}：{r['context']}" for r in rep.sentinel_failures[:EXAMPLES]]
    if errors:
        L += ["", "○の行と附表の対応の誤り（全件）：", ""] + [f"- {e}" for e in errors]
    return L


def run_hosei(hbuilt, ledger_path, outdir):
    """○の行と附表の台帳を確かめる。返り値は（終了コード、台帳の行、Report、誤り）。台帳には書かない。"""
    if not os.path.exists(ledger_path):
        raise ledger.LedgerError(f"○の行と附表の台帳が無い（{ledger_path}）。tools/update_links.py --ledger hosei-fuhyo を先に動かす")
    rows = ledger.read_ledger(ledger_path, HOSEI)
    rep = ledger.check_ledger(rows, gen_hosei_fuhyo.generated_rows(hbuilt), gen_hosei_fuhyo.corpus(hbuilt),
                              relink_rows=None)
    errors = gen_hosei_fuhyo.hosei_errors(rows, hbuilt)
    ledger.write_lists(outdir, rep.checked, rep.merged, update=False)
    gen_hosei_fuhyo.write_lists(outdir, hbuilt, rows)
    with open(os.path.join(outdir, "check.md"), "wb") as f:
        f.write(("\n".join(hosei_report_lines(rows, rep, errors, hbuilt)) + "\n").encode("utf-8"))
    return (1 if rep.exit_code or errors else 0), rows, rep, errors


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
    # 附表の台帳（mention・relink の報告のあとに出す）
    try:
        fcode, frows, frep = run_fuhyo(gen_fuhyo.build(gen_fuhyo.read_fuhyo_inputs(gi, lock)), FUHYO_PATH, FUHYO_OUT_DIR)
    except gm.GenError as e:
        print(f"停止：{e}", file=sys.stderr)
        return 1
    print("\n".join(fuhyo_report_lines(frows, frep)[2:]), file=sys.stderr if fcode else sys.stdout)
    # 年度の台帳（附表の台帳の報告のあとに出す）
    try:
        ybuilt = gen_fuhyo_years.build(gen_fuhyo_years.read_years_inputs(gi, lock))
        ycode, yrows, yrep, yerrors = run_years(ybuilt, YEARS_PATH, YEARS_OUT_DIR)
    except gm.GenError as e:
        print(f"停止：{e}", file=sys.stderr)
        return 1
    print("\n".join(years_report_lines(yrows, yrep, yerrors, ybuilt)[2:]), file=sys.stderr if ycode else sys.stdout)
    # 議案と回の台帳・○の行と附表の台帳（年度の台帳の報告のあとに出す）
    try:
        gbuilt = gen_gian_yosan.build(gen_gian_yosan.read_gian_inputs(gi, lock))
        gcode, grows, grep_, gerrors = run_gian(gbuilt, GIAN_PATH, GIAN_OUT_DIR)
    except gm.GenError as e:
        print(f"停止：{e}", file=sys.stderr)
        return 1
    print("\n".join(gian_report_lines(grows, grep_, gerrors, gbuilt)[2:]), file=sys.stderr if gcode else sys.stdout)
    try:
        hbuilt = gen_hosei_fuhyo.build(gen_hosei_fuhyo.read_hosei_inputs(gi, lock))
        hcode, hrows, hrep, herrors = run_hosei(hbuilt, HOSEI_PATH, HOSEI_OUT_DIR)
    except gm.GenError as e:
        print(f"停止：{e}", file=sys.stderr)
        return 1
    print("\n".join(hosei_report_lines(hrows, hrep, herrors, hbuilt)[2:]), file=sys.stderr if hcode else sys.stdout)
    total = 1 if (code or fcode or ycode or gcode or hcode) else 0
    print(f"- 全体の判定：{'合格' if total == 0 else '停止'}", file=sys.stderr if total else sys.stdout)
    return total


if __name__ == "__main__":
    sys.exit(main())
