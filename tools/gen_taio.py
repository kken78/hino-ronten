"""いまの記録の台帳（やりとり・質疑・審査報告の記録）の行を、問い×事項の組にまとめ直し、問いと事項の対応
records/taio.tsv に書く（LINK_SCHEMA.md §2 の段落の位置・§15.12「いまの台帳からのまとめ直し」、DESIGN.md ADR-39 の2・§5 の N2）。

inputs.lock.json の版の会議録の索引（発言の本文と段落）で、もとの行の引用（quote）がどの段落にあるかを決め、
(question, point) の組ごとに範囲（hani）・bills・bq・status・reviewer・date・note を作る。決まりは tools/records.py の matome。
もとの台帳（records/yaritori.tsv・shitsugi.tsv・hokoku.tsv・nozoki.tsv）は読むだけで変えない。

台帳にすでにある行のうち、まとめ直しでない行（note の頭が「まとめ直し：」でない行。これから下書きと判定で作る行）は
そのまま残す。判定を書き写した行（note が「まとめ直し：…（もと：…）」で始まり、その後ろに apply_decisions --ledger taio が
判定の出どころを足した行。records.is_written）もそのまま残し、もとの行が変わっていても止めない。その行と同じ組が
まとめ直しで別の中身（hani・bills・bq）になるか無くなるときは、件数と該当の組を表示する。作り直すのは、まとめ直したままの
行（note の頭が「まとめ直し：」で、判定を書き写していない行）だけ。次のときは、台帳に書かずに止める。
  - まとめ直しの決まりで止める行がある（引用が本文に無い、段落が1つに決まらない、reviewer・bq が2つ以上など。§15.12）
  - まとめ直しでない行と同じ (question, point) の組をまとめ直した

まとめ直した日（note の「まとめ直し：<日>」）は --date で渡す。渡さなければ、台帳のまとめ直した行の日（1つだけのとき）を
使う。台帳にまとめ直した行が無く --date も無ければ止める。同じ台帳・同じ入力・同じ日なら、何度動かしても同じ結果になる。

実行: python3 -B tools/gen_taio.py [--date YYYY-MM-DD]
終了コード：0 は書いた（変わらなければ書かない）。1 は止めた（台帳に書かない。件数と該当の行を表示する）。
確かめは python3 -B tools/check_records.py。
"""
import os
import re
import sys
from datetime import date as Date

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import check_records  # noqa: E402
import gen_mentions as gm  # noqa: E402
import records  # noqa: E402

TAIO_PATH = check_records.TAIO_PATH
USAGE = "使い方：python3 -B tools/gen_taio.py [--date YYYY-MM-DD]"


def parse_args(argv):
    """引数 → まとめ直した日（無ければ None）。合わなければ GenError。"""
    if not argv:
        return None
    if len(argv) != 2 or argv[0] != "--date":
        raise gm.GenError(USAGE)
    d = argv[1]
    try:
        if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", d):
            raise ValueError
        Date.fromisoformat(d)
    except ValueError:
        raise gm.GenError(f"--date が YYYY-MM-DD の日付でない（{d!r}）") from None
    return d


def decide_date(arg, current):
    """まとめ直した日：引数があればそれ。無ければ、台帳のまとめ直した行の日（1つだけのとき）。"""
    if arg:
        return arg
    dates = sorted(records.matome_dates(current))
    if len(dates) == 1:
        return dates[0]
    if not dates:
        raise gm.GenError("台帳にまとめ直した行が無い。まとめ直した日を --date で渡す")
    raise gm.GenError(f"台帳のまとめ直した行の日が2つ以上ある（{'・'.join(dates)}）。--date で渡す")


def _fail(title, items):
    if items:
        raise gm.GenError(f"{title}：{len(items)} 件\n" + "\n".join(f"  - {x}" for x in items))


def build(ledgers, current, inp, date):
    """まとめ直した行を作り、いまの台帳の行に入れる。返り値は (行の並び, 数)。止めるときは GenError。"""
    made, errs = records.matome(ledgers, inp, date)
    _fail("まとめ直しで止める行がある（台帳には書いていない）", errs)
    rows, counts, errs, diff = records.merge_taio(current, made, date)
    _fail("まとめ直した行を台帳に入れられない（台帳には書いていない）", errs)
    counts["made"] = sum(1 for r in rows if records.as_matome(r))   # 台帳に入れた、まとめ直したままの行
    counts["diff"] = diff
    return rows, counts


def run(argv, path=TAIO_PATH, out=None):
    out = out or sys.stdout
    arg = parse_args(argv)
    lock = gm.load_lock(gm.LOCK_PATH)
    gi = gm.GitInputs(gm.INPUTS_ROOT, lock)
    gi.verify()
    inp = check_records.read_inputs(gi)
    ledgers = {n: check_records.read_file(os.path.join(check_records.RECORDS_DIR, f"{n}.tsv"), records.COLUMNS[n],
                                          n in records.OPTIONAL) for n in records.TAIO_SOURCES}
    current = check_records.read_file(path, records.TAIO_COLUMNS, optional=True)
    date = decide_date(arg, current)
    rows, c = build(ledgers, current, inp, date)
    text = records.format_tsv(records.TAIO_COLUMNS, rows)
    old = None
    if os.path.exists(path):
        with open(path, "rb") as f:
            old = f.read().decode("utf-8")
    st = {s: sum(1 for r in rows if records.as_matome(r) and r["status"] == s) for s in records.STATUSES}
    print(f"まとめ直した日：{date}", file=out)
    print(f"まとめ直したままの行：{c['made']}（" + "・".join(f"{s} {st[s]}" for s in records.STATUSES) + "）", file=out)
    print(f"いまの台帳との違い：足した {c['added']}・変わった {c['changed']}・無くなった {c['removed']}"
          f"・残したまとめ直しでない行 {c['kept']}・残した判定を書き写した行 {c['written']}", file=out)
    print(f"判定を書き写した行で、まとめ直すと別の中身になるか無くなる組：{len(c['diff'])}", file=out)
    for q, p, d in c["diff"]:
        print(f"  - {q} × {p}：{d}", file=out)
    if old == text:
        print(f"{os.path.relpath(path, gm.ROOT)} は変わらない（書いていない）", file=out)
    else:
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        print(f"書いた：{os.path.relpath(path, gm.ROOT)}（{len(rows)}行）", file=out)
    return 0


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv[1:]
    try:
        return run(args)
    except (gm.GenError, records.RecordsError) as e:
        print(f"停止：{e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
