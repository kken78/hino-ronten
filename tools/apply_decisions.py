"""人の判定の一覧を台帳 links/mention.tsv に書き写す（LINK_SCHEMA.md §3・§6、DESIGN.md §5 工程4-5）。

判定の一覧（確認用のページが書き出す TSV。列は from・to・method・context・status・reviewer・date・note）の
各行を、台帳の同じ (from, to, method) の candidate の行に書き写す。確定・却下するのは人で、この道具は
人が決めた status・reviewer・date・note を写すだけ（DESIGN.md ADR-2）。
1行でも合わなければ台帳に1件も書かず、合わない行をすべて示して止める。書いたあとに tools/check_links.py の
確かめを動かす（入力のリポジトリは、確かめのために lock の版だけを読む。§10）。

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
DECISION_COLUMNS = ["from", "to", "method", "context", "status", "reviewer", "date", "note"]
DECIDED = (ledger.CONFIRMED, ledger.REJECTED)


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
    if lines[0].split("\t") != DECISION_COLUMNS:
        raise DecisionError(f"判定の一覧のヘッダが {DECISION_COLUMNS} でない（{lines[0].split(chr(9))}）")
    rows, errs = [], []
    for n, line in enumerate(lines[1:], start=2):
        cells = line.split("\t")
        if len(cells) != len(DECISION_COLUMNS):
            errs.append(f"{n}行目：列の数が {len(cells)}（{len(DECISION_COLUMNS)} のはず。note にタブがあると増える）")
            continue
        rows.append((n, dict(zip(DECISION_COLUMNS, cells))))
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
    return f"却下：{note}。判別の根拠：{current}"


def apply(ledger_rows, decisions):
    """判定を台帳の行に書き写した新しい台帳の行を返す。合わない行が1行でもあれば、すべて示して止める。"""
    by_key = {(r["from"], r["to"], r["method"]): r for r in ledger_rows}
    counts = Counter((d["from"], d["to"], d["method"]) for _, d in decisions)
    errs, changes = [], {}
    for n, d in decisions:
        k = (d["from"], d["to"], d["method"])
        at = f"{n}行目 {d['from']} {d['to']}"
        bad = []
        if counts[k] > 1:
            bad.append(f"同じ (from, to, method) が一覧に {counts[k]} 回ある")
        r = by_key.get(k)
        if r is None:
            bad.append("台帳に同じ (from, to, method) の行が無い")
        else:
            if r["status"] != ledger.CANDIDATE:
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
        if d["status"] == ledger.REJECTED and not d["note"]:
            bad.append("rejected の note（却下の理由）が空")
        if bad:
            errs += [f"{at}：{b}" for b in bad]
            continue
        changes[k] = {"status": d["status"], "reviewer": d["reviewer"], "date": d["date"],
                      "note": decided_note(d["status"], r["note"], d["note"])}
    _fail("判定の一覧に台帳と合わない行がある（台帳には書いていない）", errs)
    return [dict(r, **changes[k]) if (k := (r["from"], r["to"], r["method"])) in changes else r for r in ledger_rows]


def write(decisions_path, ledger_path):
    """判定の一覧を読み、台帳に書き写して書く。返り値は書き写した行の数（confirmed・rejected の Counter）。"""
    with open(decisions_path, "rb") as f:
        decisions = parse_decisions(f.read())
    current = ledger.read_ledger(ledger_path, METHOD)
    rows = apply(current, decisions)
    ledger.parse_ledger(ledger.format_ledger(rows), METHOD)  # 書く前に台帳の形を確かめる（§1・§3・§11）
    ledger.write_ledger(ledger_path, rows)
    return Counter(d["status"] for _, d in decisions)


def run(decisions_path, ledger_path, built, outdir):
    """書き写してから check_links.run で確かめる。返り値は（終了コード、書き写した数、台帳の行、check_links の Report）。"""
    applied = write(decisions_path, ledger_path)
    code, rows, rep = check_links.run(built, ledger_path, outdir)
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
        code, applied, rows, rep = run(argv[1], check_links.LEDGER_PATH, built, check_links.OUT_DIR)
    except (gm.GenError, mention.RefError) as e:
        print(f"停止：{e}", file=sys.stderr)
        return 1
    print(f"書き写した：confirmed {applied[ledger.CONFIRMED]}・rejected {applied[ledger.REJECTED]}")
    print("\n".join(check_links.report_lines(rows, rep)[2:]), file=sys.stderr if code else sys.stdout)
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv))
