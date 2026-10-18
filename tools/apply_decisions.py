"""人の判定の一覧を台帳 links/mention.tsv・links/relink.tsv に書き写す（LINK_SCHEMA.md §3・§6、DESIGN.md §5 工程4-5）。

判定の一覧（確認用のページが書き出す TSV。列は from・to・method・context・status・reviewer・date・note で、
その後ろに relink_to を足してもよい）の各行を、台帳の同じ (from, to, method) の candidate の行に書き写す。
relink_to（付け替え先の plan・lin）がある rejected の行は、links/relink.tsv にも付け替えの行を1行足す（§6 付け替え）。
台帳の行がすでに rejected なら、relink_to があるときだけ受け付け、mention の行は変えずに付け替えの行だけを足す。
確定・却下・付け替えをするのは人で、この道具は人が決めた値を写すだけ（DESIGN.md ADR-2）。
1行でも合わなければどちらの台帳にも1件も書かず、合わない行をすべて示して止める。書いたあとに
tools/check_links.py の確かめを動かす（入力のリポジトリは、lock の版だけを読む。§10）。

実行: python3 -B tools/apply_decisions.py <判定の一覧の TSV>
終了コード：0 は書き写し、確かめも合格。1 は止めた（入力の読み込みか一覧の誤りで止めたときは台帳に書かない。
書いたあとの確かめで合格しなかったときは、台帳は書いたまま、件数と該当を表示する）。
"""
import os
import re
import sys
from collections import Counter
from datetime import date as Date

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import check_links  # noqa: E402
import gen_mentions as gm  # noqa: E402
import ledger  # noqa: E402
import mention  # noqa: E402

METHOD = "mention"
RELINK = check_links.RELINK
DECISION_COLUMNS = ["from", "to", "method", "context", "status", "reviewer", "date", "note"]
RELINK_TO = "relink_to"
HEADERS = (DECISION_COLUMNS, DECISION_COLUMNS + [RELINK_TO])  # いまの8列か、relink_to を足した9列
DECIDED = (ledger.CONFIRMED, ledger.REJECTED)
REJECT_PREFIX, REJECT_BASIS = "却下：", "。判別の根拠："  # decided_note の rejected の形


class DecisionError(gm.GenError):
    """判定の一覧の誤り。合わない行をすべて示して止める（台帳には書かない）。"""


def _fail(title, items):
    """items が1件以上なら、件数と全件を示して止める（gen_mentions._fail と同じ形。DecisionError を出す）。"""
    if items:
        raise DecisionError(f"{title}：{len(items)} 件\n" + "\n".join(f"  - {x}" for x in items))


def parse_decisions(data):
    """判定の一覧のバイト列を読み、§1 の形（UTF-8・BOMなし・LF・ヘッダ・列の数）を確かめる。"""
    if data.startswith(b"\xef\xbb\xbf"):
        raise DecisionError("判定の一覧が BOM で始まっている")
    if b"\r" in data:
        raise DecisionError("判定の一覧に CR がある（改行は LF だけ）")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as e:
        raise DecisionError(f"判定の一覧が UTF-8 でない（{e}）") from None
    if not text.endswith("\n"):
        raise DecisionError("判定の一覧の最後の行が改行で終わっていない")
    lines = text[:-1].split("\n")
    columns = lines[0].split("\t")
    if columns not in HEADERS:
        raise DecisionError(f"判定の一覧のヘッダが {DECISION_COLUMNS} か、その後ろに {RELINK_TO} を足したものでない（{columns}）")
    rows, errs = [], []
    for n, line in enumerate(lines[1:], start=2):
        cells = line.split("\t")
        if len(cells) != len(columns):
            errs.append(f"{n}行目：列の数が {len(cells)}（{len(columns)} のはず。note にタブがあると増える）")
            continue
        rows.append((n, {RELINK_TO: "", **dict(zip(columns, cells))}))
    if not rows and not errs:
        errs.append("判定の行が0件")
    _fail("判定の一覧の形の誤り", errs)
    return rows


def decided_note(status, current, note):
    """台帳に書く note。confirmed は道具の判別の根拠を残してメモを足し、rejected は却下の理由を先に書く。"""
    if status == ledger.CONFIRMED:
        if not note:
            return current
        return f"{current}。メモ：{note}" if current else f"メモ：{note}"
    return f"{REJECT_PREFIX}{note}{REJECT_BASIS}{current}"


def rejected_reason(note):
    """rejected の行の note（decided_note の形）から、却下の理由（「却下：」から「。判別の根拠：」の前まで）を取り出す。"""
    if not note.startswith(REJECT_PREFIX) or REJECT_BASIS not in note:
        return ""
    return note[len(REJECT_PREFIX):note.index(REJECT_BASIS)]


def relink_row(r, d, to_label, reason):
    """§6 付け替え：却下した mention の行 r と判定 d から、relink の台帳の行を作る。"""
    return {"from": r["from"], "to": d[RELINK_TO], "method": RELINK, "evidence": r["evidence"],
            "where": r["where"], "context": r["context"], "to_label": to_label, "status": ledger.CONFIRMED,
            "reviewer": d["reviewer"], "date": d["date"], "note": f"付け替え：{r['to']} の却下から。{reason}"}


def _relink_errors(r, d, label):
    """relink_to の誤り（文の一覧）。label は relink_to の §3 の名称（見つからなければ None）。"""
    rt, bad = d[RELINK_TO], []
    if d["status"] != ledger.REJECTED:
        bad.append(f"relink_to は status が rejected の行にだけ書ける（{d['status']}）")
    kind = rt.partition(":")[0]
    if kind not in ledger.TO_KINDS_OF[RELINK] or not ledger.KEY_FORMS[kind].fullmatch(rt):
        bad.append(f"relink_to が plan・lin のキーでない（{rt!r}）")
    elif label is None:
        bad.append(f"relink_to が manifest にも系譜表にも無い（{rt}。名称が見つからない）")
    if rt == d["to"]:
        bad.append(f"relink_to が元の行の to と同じ（{rt}）")
    if r is not None and r["status"] == ledger.REJECTED and not d["note"] and not rejected_reason(r["note"]):
        bad.append("台帳の行の note から却下の理由を取り出せない（判定の note に理由を書く）")
    return bad


def apply(ledger_rows, decisions, relink_rows=(), names=None, refs=None):
    """判定を台帳の行に書き写した新しい台帳の行を返す。返り値は（mention の行、relink の行）。
    names・refs は relink_to の名称を求めるのに使う（gen_mentions.to_label）。合わない行が1行でもあれば、すべて示して止める。"""
    by_key = {(r["from"], r["to"], r["method"]): r for r in ledger_rows}
    counts = Counter((d["from"], d["to"], d["method"]) for _, d in decisions)
    have_relink = {(r["from"], r["to"], r["method"]) for r in relink_rows}
    relink_counts = Counter((d["from"], d[RELINK_TO]) for _, d in decisions if d[RELINK_TO])
    errs, changes, added = [], {}, []
    for n, d in decisions:
        k = (d["from"], d["to"], d["method"])
        at = f"{n}行目 {d['from']} {d['to']}"
        bad = []
        if counts[k] > 1:
            bad.append(f"同じ (from, to, method) が一覧に {counts[k]} 回ある")
        r = by_key.get(k)
        relink_only = (r is not None and r["status"] == ledger.REJECTED and d["status"] == ledger.REJECTED
                       and bool(d[RELINK_TO]))
        if r is None:
            bad.append("台帳に同じ (from, to, method) の行が無い")
        else:
            if r["status"] != ledger.CANDIDATE and not relink_only:
                bad.append(f"台帳の行が candidate でない（{r['status']}）")
            if d["context"] != r["context"]:
                bad.append("context が台帳の行と違う")
        if d["status"] not in DECIDED:
            bad.append(f"status が confirmed・rejected でない（{d['status']!r}）")
        if not d["reviewer"]:
            bad.append("reviewer が空")
        if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", d["date"]):
            bad.append(f"date が YYYY-MM-DD でない（{d['date']!r}）")
        else:
            try:
                Date.fromisoformat(d["date"])
            except ValueError:
                bad.append(f"date が日付として正しくない（{d['date']}）")
        if d["status"] == ledger.REJECTED and not d["note"] and not relink_only:
            bad.append("rejected の note（却下の理由）が空")
        label = None
        if d[RELINK_TO]:
            try:
                label = gm.to_label(d[RELINK_TO], names or {}, refs)
            except gm.GenError:
                label = None
            bad += _relink_errors(r, d, label)
            rk = (d["from"], d[RELINK_TO], RELINK)
            if rk in have_relink:
                bad.append(f"relink の台帳に同じ (from, to, method) の行がある（{d['from']} {d[RELINK_TO]}）")
            if relink_counts[(d["from"], d[RELINK_TO])] > 1:
                bad.append(f"同じ from と relink_to が一覧に {relink_counts[(d['from'], d[RELINK_TO])]} 回ある")
        if bad:
            errs += [f"{at}：{b}" for b in bad]
            continue
        if not relink_only:
            changes[k] = {"status": d["status"], "reviewer": d["reviewer"], "date": d["date"],
                          "note": decided_note(d["status"], r["note"], d["note"])}
        if d[RELINK_TO]:
            added.append(relink_row(r, d, label, d["note"] or rejected_reason(r["note"])))
    _fail("判定の一覧に台帳と合わない行がある（台帳には書いていない）", errs)
    rows = [dict(r, **changes[k]) if (k := (r["from"], r["to"], r["method"])) in changes else r for r in ledger_rows]
    return rows, sorted(list(relink_rows) + added, key=lambda r: (r["from"], r["to"], r["method"]))


def write(decisions_path, ledger_path, built, relink_path=None):
    """判定の一覧を読み、台帳に書き写して書く。relink の台帳は、省くと mention の台帳と同じ場所（links/relink.tsv）。
    返り値は書き写した行の数（confirmed・rejected は mention の行、relink は足した付け替えの行の Counter）。"""
    relink_path = relink_path or check_links.relink_path_of(ledger_path)
    with open(decisions_path, "rb") as f:
        decisions = parse_decisions(f.read())
    current = ledger.read_ledger(ledger_path, METHOD)
    current_relink = ledger.read_ledger(relink_path, RELINK, missing_ok=True)
    rows, relink_rows = apply(current, decisions, current_relink,
                              gm.plan_names(built.inputs.manifest, built.refs), built.refs)
    # 書く前に台帳の形（§1・§3・§11）と、付け替えの元・重なり（§11）を確かめる
    ledger.parse_ledger(ledger.format_ledger(rows), METHOD)
    ledger.parse_ledger(ledger.format_ledger(relink_rows), RELINK)
    _fail("付け替えの元・付け替えの重なりの誤り（台帳には書いていない）",
          ledger.relink_origin_errors(relink_rows, rows)
          + [f"{c['from']} {c['to']}：mention の行が {c['mention_status']}（付け替えの重なり）"
             for c in ledger.relink_conflicts(relink_rows, rows)])
    ledger.write_ledger(ledger_path, rows)
    if len(relink_rows) != len(current_relink):
        ledger.write_ledger(relink_path, relink_rows)
    old = {(r["from"], r["to"], r["method"]): r for r in current}
    applied = Counter(r["status"] for r in rows if old[(r["from"], r["to"], r["method"])] != r)
    applied[RELINK] = len(relink_rows) - len(current_relink)
    return applied


def run(decisions_path, ledger_path, built, outdir, relink_path=None, relink_outdir=None):
    """書き写してから check_links.run で確かめる。返り値は（終了コード、書き写した数、台帳の行、check_links の Report）。"""
    relink_path = relink_path or check_links.relink_path_of(ledger_path)
    applied = write(decisions_path, ledger_path, built, relink_path)
    code, rows, rep = check_links.run(built, ledger_path, outdir, relink_path, relink_outdir)
    return code, applied, rows, rep


def main(argv):
    if len(argv) != 2:
        print("使い方：python3 -B tools/apply_decisions.py <判定の一覧の TSV>", file=sys.stderr)
        return 1
    try:
        refs = mention.load_refs(gm.LINEAGE, gm.ALIASES)
        lock = gm.load_lock(gm.LOCK_PATH)
        gi = gm.GitInputs(gm.INPUTS_ROOT, lock)
        gi.verify()
        built = gm.build(gm.read_inputs(gi, lock), refs)
        code, applied, rows, rep = run(argv[1], check_links.LEDGER_PATH, built, check_links.OUT_DIR,
                                       check_links.RELINK_PATH, check_links.RELINK_OUT_DIR)
    except (gm.GenError, mention.RefError) as e:
        print(f"停止：{e}", file=sys.stderr)
        return 1
    print(f"書き写した：confirmed {applied[ledger.CONFIRMED]}・rejected {applied[ledger.REJECTED]}・"
          f"付け替え {applied[RELINK]}")
    print("\n".join(check_links.report_lines(rows, rep)[2:]), file=sys.stderr if code else sys.stdout)
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv))
