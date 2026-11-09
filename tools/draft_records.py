"""記録の下書きを判定シートにかける補助（LINK_SCHEMA.md §11「記録の台帳」・§15.1、DESIGN.md ADR-31 の3、
CLAUDE.md 不変の制約11 の (4)）。

生成AIの下書き（TSV）を受け、§15.1 の note の形と status を整え、records/ の作業用の写しに合わせて
records.check_all をかけ、判定シート（Markdown）と、見直し役に渡す行の一覧を出す。records/ 本体は書かない。

下書きの TSV の列：その台帳の列（records.COLUMNS）から status・reviewer・date を除いたもの（note は下書きの注記。
空でよい）と、最後に任意の列 mayoi（「迷い」か空）。ヘッダで判定する（mayoi が無ければ全部空）。

整えること：status は candidate、reviewer・date は空、note は
「下書き：<date>・<model>（<prompt か「プロンプトの版なし」>）」＋（注記があれば「。」＋注記）＋（迷いなら「（迷い）」）。

検査：records/ の全台帳と ref/themes.tsv・ref/shisetsu.tsv（と、あれば ref/chiku.tsv・ref/soshiki.tsv）を読み、対象の台帳の写しに下書きの行を足して行のキーの順に
並べる。本体に同じキーの行があれば「本体に同じキーの行がある」として誤りにする（写しでは本体の行を下書きの行に
置き換えて検査する）。records.check_all の報告と一覧は check_records.write_outputs と同じ形で --out に書く。

--out（既定 build/draft/<sheet>/）に書くもの：
  <ledger>.candidate.tsv  整えた下書きの行（§1 の形。行のキーの順）
  hantei-<sheet>.md       判定シート（行ごとの出る先・迷い・検査の印と、見直しの空欄）
  review.md               見直し役に渡す一覧（行のキー・資料のキー・引用の全文・ほかの欄。指示文は書かない）
  check.md ほか            records.check_all の報告と一覧（tools/check_records.py と同じ）

抜き取り（ADR-31 の3）は、この道具では選ばない（見直しの結果が出てから、別の段で選ぶ）。

実行: python3 -B tools/draft_records.py <下書きの TSV> --ledger <台帳> --model "<モデルの名前>" --date YYYY-MM-DD
        [--prompt <プロンプトの版>] --sheet <判定シートの番号> [--out <出力の場所>]
終了コード：0 は検査の誤りが無い。1 は検査の誤りがある（判定シートは出す）か、使い方・入力の読み込みの誤りで止めた。
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import check_records  # noqa: E402
import gen_mentions as gm  # noqa: E402
import mention  # noqa: E402
import records  # noqa: E402

MAYOI = "mayoi"
MAYOI_VALUE = "迷い"
DRAFTED = ("status", "reviewer", "date")   # 下書きの TSV に置かない列
NO_PROMPT = "プロンプトの版なし"
QUOTE_SHOW = 60                            # 判定シートで quote を切る字数
DASH = "—"
WHOLE = "テーマ全体"
# 判定シートで、行のキーと quote のほかに見せる列
SHEET_FIELDS = {
    "kotogara": ("point", "source", "source_date", "kind", "value", "target"),
    "kisai": ("title", "about", "source"),
    "tsunagari": ("link", "upper", "lower", "source"),
    "katei": ("step", "name", "from", "to"),
    "shisetsu": ("facility", "aspect", "value", "source"),
    "yaritori": ("n", "row", "side", "round", "stage", "kind", "point"),
    "shitsugi": ("n", "row", "side", "round", "stage", "kind", "point"),
    "nozoki": ("n", "sid", "reason"),
    "teian": ("bill", "sid"),
}
# 見直しの一覧（review.md）で「資料のキー」とする列
SOURCE_COLUMN = {"yaritori": "sid", "shitsugi": "sid", "nozoki": "sid", "katei": "sources", "teian": "sid"}


class DraftError(ValueError):
    """下書きの TSV や引数が使えない。出力を作らずに止める。"""


def draft_columns(ledger):
    return [c for c in records.COLUMNS[ledger] if c not in DRAFTED]


def parse_draft(data, ledger, name="下書き"):
    """下書きの TSV → (行の並び, 迷いの並び)。ヘッダが台帳の列か、それに mayoi を足したものでなければ止める。"""
    cols = draft_columns(ledger)
    head = data.split(b"\n", 1)[0].decode("utf-8", "replace").split("\t")
    with_mayoi = head == cols + [MAYOI]
    try:
        rows = records.parse_tsv(data, cols + [MAYOI] if with_mayoi else cols, name)
    except records.RecordsError as e:
        raise DraftError(str(e)) from None
    bad = [f"{n}行目（{r[MAYOI]}）" for n, r in enumerate(rows, start=2) if with_mayoi and r[MAYOI] not in ("", MAYOI_VALUE)]
    if bad:
        raise DraftError(f"{name}：mayoi が「{MAYOI_VALUE}」か空でない：" + "、".join(bad))
    if not rows:
        raise DraftError(f"{name}：行が無い")
    mayoi = [bool(with_mayoi and r.pop(MAYOI) == MAYOI_VALUE) for r in rows]
    return rows, mayoi


def draft_note(date, model, prompt, note, mayoi):
    """§15.1 の note の形。"""
    out = f"下書き：{date}・{model}（{prompt or NO_PROMPT}）"
    if note:
        out += "。" + note
    if mayoi:
        out += "（迷い）"
    return out


def prepare(rows, mayoi, ledger, date, model, prompt):
    """下書きの行を §15 の台帳の行に整える（status は candidate、reviewer・date は空）。迷いは行ごとの並びで返す。
    行のキーの順に並べる（同じ順に迷いも並べ替える）。"""
    out = []
    for r, m in zip(rows, mayoi):
        x = {c: "" for c in records.COLUMNS[ledger]}
        x.update(r)
        x.update(status="candidate", reviewer="", date="", note=draft_note(date, model, prompt, r["note"], m))
        out.append((x, m))
    out.sort(key=lambda t: records.sort_key(t[0], records.KEYS[ledger]))
    return [x for x, _ in out], [m for _, m in out]


def row_key(ledger, r):
    return "/".join(r[c] for c in records.KEYS[ledger])


def merge(ledger, body, drafts):
    """本体の写しに下書きの行を足す。本体に同じキーの行があれば、写しではその行を下書きの行に置き換え、
    そのキーを返す（誤りにするのは check で）。"""
    keys = {row_key(ledger, r) for r in drafts}
    dup = sorted({row_key(ledger, r) for r in body} & keys)
    merged = [r for r in body if row_key(ledger, r) not in keys] + list(drafts)
    merged.sort(key=lambda r: records.sort_key(r, records.KEYS[ledger]))
    return merged, dup


def check(ledger, drafts, ledgers, themes_rows, shisetsu_rows, inp, chiku_rows=(), soshiki_rows=()):
    """写しに下書きの行を足して records.check_all をかける。(Report, Theme) を返す。"""
    copy = {n: list(rows) for n, rows in ledgers.items()}
    copy[ledger], dup = merge(ledger, ledgers.get(ledger, []), drafts)
    rep = records.check_all(copy, themes_rows, shisetsu_rows, inp, chiku_rows, soshiki_rows)
    for r in drafts:
        if row_key(ledger, r) in dup:
            rep.err(records.label(ledger, r), f"本体に同じキーの行がある（records/{ledger}.tsv）")
    # 出る先を引くためのテーマの定義（誤りは check_all の報告にあるので、ここでは捨てる）
    theme = records.check_themes(themes_rows, inp, {r["key"] for r in shisetsu_rows}, records.Report(),
                                 {r["key"] for r in chiku_rows}, {r["key"] for r in soshiki_rows})
    return rep, theme


def destinations(ledger, r, theme):
    """行の出る先（その行の点の views。§13.1）。views が空なら「テーマ全体」。やりとり・質疑・過程・記録しない文は「—」。"""
    if ledger == "kotogara":
        vs = theme.views_of("事柄", r["point"])
    elif ledger == "kisai":
        vs = theme.point_views(r["about"]) if r["about"] else set()
    elif ledger == "tsunagari":
        vs = theme.views_of("記載", r["upper"]) | theme.views_of("記載", r["lower"])
    elif ledger == "shisetsu":
        vs = theme.views_of("施設", r["facility"])
    else:
        return DASH
    return "、".join(sorted(vs)) or WHOLE


def row_errors(ledger, r, rep):
    """その行の誤りの文（records.label で始まる誤り）。"""
    head = records.label(ledger, r) + "："
    return [e[len(head):] for e in rep.errors if e.startswith(head)]


def mismatch_keys(ledger, rep):
    return {m["key"] for m in rep.quote_mismatch if m["ledger"] == ledger}


def cell(s):
    return str(s).replace("|", "｜").replace("\n", " ")


def cut(s, n=QUOTE_SHOW):
    return s if len(s) <= n else s[:n] + "…"


def sheet_key(ledger, r):
    """判定シートの行のキー：quote を除いたキーの列（quote は quote の欄に出す）。"""
    return "/".join(r[c] for c in records.KEYS[ledger] if c != "quote")


def sheet_lines(sheet, ledger, date, model, drafts, mayoi, rep, theme):
    fields = SHEET_FIELDS[ledger]
    mis = mismatch_keys(ledger, rep)
    keys = {records.label(ledger, r) + "：" for r in drafts}
    loose = [e for e in rep.errors if not any(e.startswith(k) for k in keys)]
    n_mis = sum(1 for r in drafts if row_key(ledger, r) in mis)
    L = [f"# 判定シート {sheet}（{ledger}。下書き：{date}・{model}）", ""]
    L.append(f"- 行数：{len(drafts)}")
    L.append(f"- 迷い：{sum(mayoi)}")
    L.append(f"- 検査の誤り：{len(rep.errors)}（下書きの行に結び付くもの {len(rep.errors) - len(loose)}）")
    L.append(f"- 引用が本文に無い行：{n_mis}")
    L.append("- 見直しの欄：見直し役が「○」か「×：理由」を書く")
    L.append("")
    head = ["#", "行のキー", *fields, "quote", "出る先", "迷い", "見直し"]
    L.append("| " + " | ".join(head) + " |")
    L.append("|" + "---|" * len(head))
    for i, (r, m) in enumerate(zip(drafts, mayoi), 1):
        marks = [f"検査：{e}" for e in row_errors(ledger, r, rep)]
        if row_key(ledger, r) in mis and not any("引用が資料の本文に無い" in e for e in marks):
            marks.append("検査：引用が資料の本文に無い")
        q = cut(r["quote"]) + ("<br>" + "<br>".join(marks) if marks else "")
        cells = [str(i), sheet_key(ledger, r), *(r[f] for f in fields), q, destinations(ledger, r, theme),
                 MAYOI_VALUE if m else "", ""]
        L.append("| " + " | ".join(cell(c) for c in cells) + " |")
    if loose:
        L += ["", "## 行に結び付かない検査の誤り", ""] + [f"- {e}" for e in loose]
    return L


def review_lines(sheet, ledger, drafts):
    """見直し役に渡す一覧。note と迷いは渡さない（下書きの判断を見ずに見直すため。ADR-31 の3）。"""
    src = SOURCE_COLUMN.get(ledger, "source")
    skip = {"quote", src, *records.COMMON}
    L = [f"# 見直しの一覧 {sheet}（{ledger}。{len(drafts)}行）", ""]
    for i, r in enumerate(drafts, 1):
        L.append(f"## {i}. {row_key(ledger, r)}")
        L.append("")
        L.append(f"- 資料のキー：{r[src]}")
        L.append(f"- 引用：{r['quote']}")
        for c in records.COLUMNS[ledger]:
            if c not in skip and r[c]:
                L.append(f"- {c}：{r[c]}")
        L.append("")
    return L


def write_all(outdir, sheet, ledger, date, model, drafts, mayoi, rep, theme):
    os.makedirs(outdir, exist_ok=True)
    check_records.write_outputs(outdir, rep)
    files = {
        f"{ledger}.candidate.tsv": records.format_tsv(records.COLUMNS[ledger], drafts),
        f"hantei-{sheet}.md": "\n".join(sheet_lines(sheet, ledger, date, model, drafts, mayoi, rep, theme)) + "\n",
        "review.md": "\n".join(review_lines(sheet, ledger, drafts)),
    }
    for name, text in files.items():
        with open(os.path.join(outdir, name), "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
    return sorted(files)


def parse_args(argv):
    ap = argparse.ArgumentParser(description="記録の下書きを判定シートにかける（records/ は書かない）")
    ap.add_argument("draft")
    ap.add_argument("--ledger", required=True, choices=records.LEDGERS)
    ap.add_argument("--model", required=True)
    ap.add_argument("--date", required=True)
    ap.add_argument("--prompt", default="")
    ap.add_argument("--sheet", required=True)
    ap.add_argument("--out", default="")
    a = ap.parse_args(argv)
    if not records.RE_DAY.fullmatch(a.date):
        raise DraftError(f"--date が YYYY-MM-DD でない（{a.date}）")
    if not a.sheet or "/" in a.sheet or a.sheet.startswith("."):
        raise DraftError(f"--sheet が使えない（{a.sheet}）")
    if not a.model.strip():
        raise DraftError("--model が空")
    return a


def main(argv):
    try:
        a = parse_args(argv)
        with open(a.draft, "rb") as f:
            rows, mayoi = parse_draft(f.read(), a.ledger, os.path.basename(a.draft))
        drafts, mayoi = prepare(rows, mayoi, a.ledger, a.date, a.model, a.prompt)
        lock = gm.load_lock(gm.LOCK_PATH)
        gi = gm.GitInputs(gm.INPUTS_ROOT, lock)
        gi.verify()
        inp = check_records.read_inputs(gi)
        ledgers = {n: check_records.read_file(os.path.join(check_records.RECORDS_DIR, f"{n}.tsv"), records.COLUMNS[n],
                                              n in records.OPTIONAL) for n in records.LEDGERS}
        themes_rows = check_records.read_file(check_records.THEMES, records.THEME_COLUMNS)
        shisetsu = check_records.read_file(check_records.SHISETSU, records.SHISETSU_COLUMNS)
        area = check_records.read_area_refs()
    except (OSError, DraftError, gm.GenError, records.RecordsError, mention.RefError) as e:
        print(f"停止：{e}", file=sys.stderr)
        return 1
    outdir = a.out or os.path.join(gm.ROOT, "build", "draft", a.sheet)
    return run(a, drafts, mayoi, ledgers, themes_rows, shisetsu, inp, outdir, area)


def run(a, drafts, mayoi, ledgers, themes_rows, shisetsu, inp, outdir, area=((), ())):
    """検査をかけ、出すものを書き、件数を表示する。終了コード（誤りがあれば1）を返す。area は地区・組織の参照表の行。"""
    rep, theme = check(a.ledger, drafts, ledgers, themes_rows, shisetsu, inp, *area)
    names = write_all(outdir, a.sheet, a.ledger, a.date, a.model, drafts, mayoi, rep, theme)
    mis = mismatch_keys(a.ledger, rep)
    print(f"{outdir}：" + "・".join(names))
    print(f"  行数 {len(drafts)}・迷い {sum(mayoi)}・検査の誤り {len(rep.errors)}・"
          f"引用が本文に無い行 {sum(1 for r in drafts if row_key(a.ledger, r) in mis)}")
    if rep.errors:
        for e in rep.errors[:check_records.EXAMPLES]:
            print(f"  {e}", file=sys.stderr)
        if len(rep.errors) > check_records.EXAMPLES:
            print(f"  ほか {len(rep.errors) - check_records.EXAMPLES} 件（{os.path.join(outdir, 'check.md')}）", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
