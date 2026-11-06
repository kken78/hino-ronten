"""附表の事業の年度をまたぐ対応の候補を作る（LINK_SCHEMA.md §3・§5・§7 fuhyo-years・§10・§11、DESIGN.md ADR-33）。

inputs.lock.json の shiga-hino-plans の files に名指しした附表（data/fuhyo/<附表id>.json）をすべて git show で読み、
§7 fuhyo-years の決まりで名前の一致（method が name）の候補を作って build/fuhyo-years/ に書く。台帳（links/）には書かない。
名前が変わった事業（method が manual）の行は作らず、名前の一致でつながらなかった隣り合う年度の事業の組を、
事業概要の Dice 係数の大きい順に一覧（rename_candidates.tsv）に出すだけ（人が確かめてつなぐ）。
ツールが作るのは candidate まで（DESIGN.md ADR-2）。計画・会議録・議会だよりの入力は読まない。
年度の対応（§11）の検査（years_errors）もここに置き、tools/update_links.py・tools/check_links.py・
tools/apply_decisions.py から使う。

実行: python3 -B tools/gen_fuhyo_years.py
入力の clone の場所は、環境変数 HINO_RONTEN_INPUTS で変えられる（gen_mentions.py と同じ）。
終了コード：0 は build/fuhyo-years/ への書き出しまで終えた。1 は入力の誤りで止めた（件数と該当を表示する）。

§7 fuhyo-years の決まり：
- 附表は fiscal_year.year の順に並べる。year が無いか、2つの附表で同じなら止める
- 前の年度の各事業について、後の年度を近い順に見て、事業名（正規化しない）が同じ事業がある最初の年度で候補にする。
  その年度か前の年度に同じ名前が2つ以上あれば、款と担当課（並びも同じ）も同じ事業だけ。1つに決まらなければつながない
- note は「事業名が同じ」（款と担当課も比べたら「。款と担当課も同じ（同じ年度に同じ名前が複数）」）。間の年度があれば
  「。間の年度（R5〜R6）は附表に無い」、事業概要の Dice 係数が 0.3 未満なら「。概要の内容が大きく変わっている（Dice 0.20）」
"""
import os
import re
import sys
from collections import Counter
from dataclasses import dataclass
from fractions import Fraction

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import gen_fuhyo as gf  # noqa: E402
import gen_mentions as gm  # noqa: E402
import ledger  # noqa: E402

OUT_DIR = os.path.join(gm.ROOT, "build", "fuhyo-years")
METHOD = "fuhyo-years"  # 台帳のファイル名（links/fuhyo-years.tsv）
NAME, MANUAL = "name", "manual"  # 行の method（§3）
CHANGED = Fraction(3, 10)  # 概要の Dice 係数がこれ未満なら、概要の内容が大きく変わったと note に書く
REIWA = re.compile(r"令和([0-9]+)年度")
GAP_RE = re.compile(r"。間の年度（[^）]*）は附表に無い")
COUNT_RE = re.compile(r"名前の一致の規則と一覧（([0-9]+)行）")
JUDGED = "判定："
MANUAL_HEAD = "概要の一致：「"
AMBIGUOUS_COLUMNS = ["from", "to", "name", "kan", "dept"]
RENAME_COLUMNS = ["from", "to", "from_name", "to_name", "dice_desc", "dice_name"]


# ---- 入力（§10） ----

@dataclass
class YearsInputs:
    lock: dict
    fuhyo: dict  # 附表id → 附表の JSON


def read_years_inputs(gi, lock):
    """lock の files に名指しした附表をすべて読む（§7 fuhyo-years・§10）。計画は読まない。"""
    return YearsInputs(lock, {fid: gf.read_fuhyo_json(gi, fid, p) for fid, p in gf.named_fuhyo(lock)})


@dataclass(frozen=True)
class Year:
    fid: str
    year: int
    short: str  # note に書く年度（令和の年。例 R5）


def years_order(fuhyo):
    """附表を fiscal_year.year の順に並べる。year が無いか重なる、label が令和の年度でなければ止める。"""
    errs, out = [], []
    for fid, data in sorted(fuhyo.items()):
        fy = data.get("fiscal_year") or {}
        m = REIWA.fullmatch(fy.get("label") or "")
        if not isinstance(fy.get("year"), int):
            errs.append(f"{fid}：fiscal_year.year が無い（{fy.get('year')!r}）")
        elif m is None:
            errs.append(f"{fid}：fiscal_year.label が「令和N年度」の形でない（{fy.get('label')!r}）")
        else:
            out.append(Year(fid, fy["year"], f"R{int(m.group(1))}"))
    counts = Counter(y.year for y in out)
    errs += [f"{y.fid}：fiscal_year.year {y.year} がほかの附表と同じ" for y in out if counts[y.year] > 1]
    gm._fail("附表の年度の誤り（§7 fuhyo-years）", errs)
    return sorted(out, key=lambda y: y.year)


def year_items(fid, data):
    """附表の事業の一覧（gen_fuhyo.fuhyo_items の検査を通したもの）に、款・担当課を足したもの。"""
    raw = {it["key"]: it for p in data.get("pillars") or [] for it in p.get("items") or [] if isinstance(it.get("key"), str)}
    out = []
    for f in gf.fuhyo_items(fid, data):
        it = raw[f["key"]]
        out.append(dict(f, kan=it.get("kan") or "", dept=tuple(it.get("dept") or ())))
    return out


# ---- 候補（§7 fuhyo-years） ----

def gap_text(between):
    """間の年度の note（無ければ空）。between は間の年度の Year の一覧（年度の順）。"""
    if not between:
        return ""
    span = between[0].short if len(between) == 1 else f"{between[0].short}〜{between[-1].short}"
    return f"。間の年度（{span}）は附表に無い"


def name_note(f, x, compared, between):
    note = "事業名が同じ" + ("。款と担当課も同じ（同じ年度に同じ名前が複数）" if compared else "") + gap_text(between)
    if f["d"] and x["d"]:
        value = gf.dice(f["d"], x["d"])
        if value < CHANGED:
            note += f"。概要の内容が大きく変わっている（Dice {gf.dice_text(value)}）"
    return note


def fh(fid, key):
    return f"fh:{fid}/{key}"


def _row(fid, f, lfid, x, method, note):
    return {"from": fh(fid, f["key"]), "to": fh(lfid, x["key"]), "method": method, "evidence": f["n"], "where": "name",
            "context": f["n"], "to_label": x["name"], "status": ledger.CANDIDATE, "reviewer": "", "date": "",
            "note": note}


def name_rows(order, items):
    """§7 fuhyo-years の名前の一致の候補の行と、候補が2つ以上になった事業（name_ambiguous.tsv の行）。"""
    rows, ambiguous = [], []
    for i, y in enumerate(order):
        here = Counter(f["name"] for f in items[y.fid])
        for f in items[y.fid]:
            for j in range(i + 1, len(order)):
                later = order[j]
                same = [x for x in items[later.fid] if x["name"] == f["name"]]
                if not same:
                    continue
                compared = here[f["name"]] > 1 or len(same) > 1
                if compared:
                    same = [x for x in same if x["kan"] == f["kan"] and x["dept"] == f["dept"]]
                if len(same) == 1:
                    rows.append(_row(y.fid, f, later.fid, same[0], NAME, name_note(f, same[0], compared, order[i + 1:j])))
                elif len(same) > 1:
                    ambiguous += [{"from": fh(y.fid, f["key"]), "to": fh(later.fid, x["key"]), "name": x["name"],
                                   "kan": x["kan"], "dept": "・".join(x["dept"])} for x in same]
                break  # それより後の年度は見ない
    return rows, ambiguous


def rename_candidates(order, items, rows):
    """名前の一致でつながらなかった隣り合う年度の事業の組（rename_candidates.tsv の行）。
    事業名が違い（同じ名前の組は名前の一致か name_ambiguous.tsv に出る）、事業概要か事業名の Dice 係数が 0 より大きい組を、
    概要の大きい順・名前の大きい順・from・to の順に並べる。"""
    linked_from = {r["from"] for r in rows}
    linked_to = {r["to"] for r in rows}
    out = []
    for a, b in zip(order, order[1:]):
        prev = [f for f in items[a.fid] if fh(a.fid, f["key"]) not in linked_from]
        nxt = [x for x in items[b.fid] if fh(b.fid, x["key"]) not in linked_to]
        for f in prev:
            for x in nxt:
                if x["name"] == f["name"]:
                    continue
                dd, dn = gf.dice(f["d"], x["d"]), gf.dice(f["n"], x["n"])
                if dd > 0 or dn > 0:
                    out.append((-dd, -dn, fh(a.fid, f["key"]), fh(b.fid, x["key"]), f, x, dd, dn))
    out.sort(key=lambda t: t[:4])
    return [{"from": t[2], "to": t[3], "from_name": t[4]["name"], "to_name": t[5]["name"],
             "dice_desc": gf.dice_text(t[6]), "dice_name": gf.dice_text(t[7])} for t in out]


@dataclass
class YearsBuilt:
    inputs: YearsInputs
    order: list       # 年度の順の Year
    items: dict       # 附表id → 附表の事業の一覧
    rows: list        # 名前の一致の候補の行（台帳の11列。from → to → method の順）
    ambiguous: list   # 名前の一致の候補が2つ以上になった事業
    renames: list     # 名前が変わった事業の候補の組（台帳には書かない）


def build(inp):
    order = years_order(inp.fuhyo)
    items = {y.fid: year_items(y.fid, inp.fuhyo[y.fid]) for y in order}
    rows, ambiguous = name_rows(order, items)
    keys = [(r["from"], r["to"], r["method"]) for r in rows]
    if len(set(keys)) != len(keys):
        raise gm.GenError("候補で (from, to, method) が重なっている")
    return YearsBuilt(inp, order, items, sorted(rows, key=lambda r: (r["from"], r["to"], r["method"])),
                      ambiguous, rename_candidates(order, items, rows))


def generated_rows(built):
    """台帳の11列の候補の行（ledger.merge に渡す）。"""
    return [{c: r[c] for c in ledger.LEDGER_COLUMNS} for r in built.rows]


def corpus(built):
    """§5 の照合の相手（from も to も附表の事業）。"""
    return ledger.Corpus(texts={}, by_pos={}, fields={}, names={}, refs=None,
                         fuhyo={(fid, f["key"]): f for fid, items in built.items.items() for f in items})


def item_of(built, key):
    """fh のキーの附表の事業と、その年度（Year）。無ければ (None, None)。"""
    fid, _, k = key[3:].partition("/")
    year = next((y for y in built.order if y.fid == fid), None)
    item = next((f for f in built.items.get(fid, []) if f["key"] == k), None)
    return item, year


def manual_row(built, frm, to, d):
    """人が確かめた manual の行（§6・§7 fuhyo-years）。返り値は（行、誤りの文の一覧）。d は判定の一覧の行。"""
    f, fy = item_of(built, frm) if frm.startswith("fh:") else (None, None)
    x, ty = item_of(built, to) if to.startswith("fh:") else (None, None)
    bad = []
    if f is None:
        bad.append(f"from が lock の附表の事業に無い（{frm}）")
    if x is None:
        bad.append(f"to が lock の附表の事業に無い（{to}）")
    if bad:
        return None, bad
    if fy.year >= ty.year:
        bad.append(f"from の年度（{fy.short}）が to の年度（{ty.short}）より前でない")
    if f["name"] == x["name"]:
        bad.append("from と to の事業名が同じ（名前の一致の行にする）")
    if d["context"] != f["n"]:
        bad.append("context が from の事業名（§4 の正規化を通した値）と違う")
    row = dict(_row(fy.fid, f, ty.fid, x, MANUAL, d["note"]), status=d["status"], reviewer=d["reviewer"], date=d["date"])
    return row, bad


# ---- 年度の対応（§11） ----

def years_errors(rows, built):
    """§11 年度の対応の誤り（文の一覧）。空なら合格。rejected の行は見ない。"""
    errs = []
    live = [r for r in rows if r["status"] != ledger.REJECTED]
    for r in live:
        at = f"{r['from']} {r['to']} {r['method']}"
        f, fy = item_of(built, r["from"])
        x, ty = item_of(built, r["to"])
        if f is None or x is None:
            continue  # §5 の照合で停止になる
        if fy.year >= ty.year:
            errs.append(f"{at}：from の年度（{fy.short}）が to の年度（{ty.short}）より前でない")
        if r["method"] == NAME:
            if f["name"] != x["name"]:
                errs.append(f"{at}：name の行で from と to の事業名が違う")
            between = [y for y in built.order if fy.year < y.year < ty.year]
            want = gap_text(between)
            found = GAP_RE.search(r["note"])
            if (found.group(0) if found else "") != want:
                errs.append(f"{at}：note の間の年度が lock の附表の年度と合わない（{want[1:] if want else '間の年度は無い'}）")
            if r["status"] == ledger.CONFIRMED and JUDGED not in r["note"]:
                errs.append(f"{at}：confirmed の name の行の note に「{JUDGED}」が無い")
        elif r["method"] == MANUAL:
            if f["name"] == x["name"]:
                errs.append(f"{at}：manual の行で from と to の事業名が同じ")
            if r["status"] == ledger.CONFIRMED and not (r["note"].startswith(MANUAL_HEAD) and JUDGED in r["note"]):
                errs.append(f"{at}：confirmed の manual の行の note が「{MANUAL_HEAD}」で始まらないか、「{JUDGED}」が無い")
    for col, word in (("from", "後"), ("to", "前")):
        counts = Counter(r[col] for r in live)
        errs += [f"{k}：{word}の年度の事業とのつながりが {n} 行ある（1つまで）" for k, n in sorted(counts.items()) if n > 1]
    groups = Counter()
    for r in live:
        m = COUNT_RE.search(r["note"])
        if r["method"] == NAME and r["status"] == ledger.CONFIRMED and m:
            groups[(r["date"], int(m.group(1)))] += 1
    errs += [f"{d} の判定：note の行数 {n} と、その note の confirmed の name の行の数 {c} が違う"
             for (d, n), c in sorted(groups.items()) if c != n]
    return errs


def pair_counts(rows, built):
    """隣り合う年度の組ごとの（前の年度、後の年度、つないだ数、前の年度だけ、後の年度だけ）と、年度を飛ばしてつないだ数。"""
    live = [r for r in rows if r["status"] != ledger.REJECTED]
    out = []
    for a, b in zip(built.order, built.order[1:]):
        pairs = {(r["from"], r["to"]) for r in live
                 if r["from"].startswith(f"fh:{a.fid}/") and r["to"].startswith(f"fh:{b.fid}/")}
        froms, tos = {p[0] for p in pairs}, {p[1] for p in pairs}
        out.append((a, b, len(pairs), sum(1 for f in built.items[a.fid] if fh(a.fid, f["key"]) not in froms),
                    sum(1 for x in built.items[b.fid] if fh(b.fid, x["key"]) not in tos)))
    index = {y.fid: n for n, y in enumerate(built.order)}
    skipped = sum(1 for r in live
                  if index.get(r["to"][3:].split("/")[0], 0) - index.get(r["from"][3:].split("/")[0], 0) > 1)
    return out, skipped


def count_lines(rows, built):
    pairs, skipped = pair_counts(rows, built)
    lines = [f"- {a.short}→{b.short}：つないだ {n}・前の年度だけ {p}・後の年度だけ {q}" for a, b, n, p, q in pairs]
    return lines + [f"- 年度を飛ばしてつないだ {skipped}"]


# ---- 書き出し（build/fuhyo-years/） ----

def report_lines(built):
    rows = built.rows
    L = ["# 附表の年度をまたぐ対応の候補（build/fuhyo-years/）", "",
         f"- 附表：{'・'.join(f'{y.fid}（{y.short}）{len(built.items[y.fid])} 事業' for y in built.order)}",
         f"- 名前の一致の候補：{len(rows)} 行（款と担当課も比べた {sum(1 for r in rows if '款と担当課' in r['note'])}・"
         f"間の年度がある {sum(1 for r in rows if GAP_RE.search(r['note']))}・"
         f"概要の内容が大きく変わっている {sum(1 for r in rows if '概要の内容が大きく変わっている' in r['note'])}）",
         f"- 名前の一致の候補が2つ以上になった事業：{len({a['from'] for a in built.ambiguous})}",
         f"- 名前が変わった事業の候補の組（台帳には書かない）：{len(built.renames)}"]
    return L + count_lines(rows, built)


def write_rename_lists(outdir, built):
    """name_ambiguous.tsv（from → to の順）と rename_candidates.tsv（Dice 係数の順）を書く。返り値は書いたファイルの名前。"""
    os.makedirs(outdir, exist_ok=True)
    ledger._write_files(outdir, [("name_ambiguous.tsv", AMBIGUOUS_COLUMNS, built.ambiguous)])
    lines = ["\t".join(RENAME_COLUMNS)] + ["\t".join(r[c] for c in RENAME_COLUMNS) for r in built.renames]
    with open(os.path.join(outdir, "rename_candidates.tsv"), "wb") as f:
        f.write(("\n".join(lines) + "\n").encode("utf-8"))
    return ["name_ambiguous.tsv", "rename_candidates.tsv"]


def write_outputs(outdir, built):
    """build/fuhyo-years/ の candidates.tsv・name_ambiguous.tsv・rename_candidates.tsv・report.md を書く。"""
    os.makedirs(outdir, exist_ok=True)
    gm.write_tsv(os.path.join(outdir, "candidates.tsv"), ledger.LEDGER_COLUMNS, generated_rows(built))
    names = write_rename_lists(outdir, built)
    with open(os.path.join(outdir, "report.md"), "wb") as f:
        f.write(("\n".join(report_lines(built)) + "\n").encode("utf-8"))
    return ["candidates.tsv"] + names + ["report.md"]


def load_built():
    """lock の版から候補を作る（update_links.py・check_links.py・apply_decisions.py でも使う）。"""
    lock = gm.load_lock(gm.LOCK_PATH)
    gi = gm.GitInputs(gm.INPUTS_ROOT, lock)
    gi.verify()
    return build(read_years_inputs(gi, lock))


def main():
    try:
        built = load_built()
        names = write_outputs(OUT_DIR, built)
    except gm.GenError as e:
        print(f"停止：{e}", file=sys.stderr)
        return 1
    print("\n".join(report_lines(built)[2:]))
    print(f"書き出し：{OUT_DIR}/ の {'・'.join(names)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
