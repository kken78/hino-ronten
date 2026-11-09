"""補正予算の概要の○の行と附表の事業の対応の候補を作る（LINK_SCHEMA.md §2・§3・§5・§6・§7 hosei-fuhyo・§10・§11、
DESIGN.md ADR-34 の5）。

inputs.lock.json の版の hino-town-docs の構造化の層（主な内容の行 data/struct/hosei-maru.tsv と回の表。
tools/hosei.py で読む）と、shiga-hino-plans の files に名指しした附表（data/fuhyo/<附表id>.json）を git show で読み、
§7 hosei-fuhyo の名前の一致（method が name）の候補を作って build/hosei-fuhyo/ に書く。台帳（links/）には書かない。
ツールが作るのは candidate まで（DESIGN.md ADR-2）。台帳の更新は tools/update_links.py --ledger hosei-fuhyo。
○の行と附表の対応（§11）の検査（hosei_errors）と、人が確かめた manual の行の組み立て（manual_row。
tools/apply_decisions.py --ledger hosei-fuhyo から使う）もここに置く。

実行: python3 -B tools/gen_hosei_fuhyo.py
入力の clone の場所は、環境変数 HINO_RONTEN_INPUTS で変えられる（gen_mentions.py と同じ）。
終了コード：0 は build/hosei-fuhyo/ への書き出しまで終えた。1 は入力の誤りで止めた（件数と該当を表示する）。

§7 hosei-fuhyo の決まり：
- 対象は、○の行（hj のうち key の頭が m の行）と、同じ年度（回の fiscal_year と附表の fiscal_year.year が同じ）の
  附表の事業（fh）。特別会計・企業会計の主な内容の行（key の頭が t の行）は対象にしない（PR #19 の問い2）
- 名前の一致：○の行の名前と、同じ年度の附表の事業名が §4 の正規化のあとで完全に一致する事業を候補にする。
  同じ年度の附表に同じ名前の事業が2つ以上あるときは name ではつながず、一覧（name_ambiguous.tsv）に出す
- kind（§3）：金額が正なら増額、負なら減額、0 で説明に「財源」の字があれば財源更正。どれにも当たらなければ止める
- 名前が一致しない○の行：台帳に行を作らず、一覧（name_unmatched.tsv）に出す。kind は説明に「新規計上」か「新たに」の字が
  あれば新規、無ければ附表に無い（候補。PR #19 の問い1）。人が確かめた組だけを manual の confirmed の行として足す（§6）
"""
import os
import re
import sys
from collections import Counter
from dataclasses import dataclass

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import gen_fuhyo as gf  # noqa: E402
import gen_fuhyo_years as gy  # noqa: E402
import gen_mentions as gm  # noqa: E402
import hosei  # noqa: E402
import ledger  # noqa: E402
import mention  # noqa: E402

OUT_DIR = os.path.join(gm.ROOT, "build", "hosei-fuhyo")
METHOD = "hosei-fuhyo"   # 台帳のファイル名（links/hosei-fuhyo.tsv）
NAME, MANUAL = "name", "manual"   # 行の method（§3）
COLUMNS = ledger.columns_of(METHOD)
# §3 の kind の5つ。増額・減額・財源更正は to が fh の行に、新規・附表に無いは to が none の行に付ける
ZOUGAKU, GENGAKU, ZAIGEN, SHINKI, NASHI = "増額", "減額", "財源更正", "新規", "附表に無い"
KINDS = (ZOUGAKU, GENGAKU, ZAIGEN, SHINKI, NASHI)
FH_KINDS, NONE_KINDS = (ZOUGAKU, GENGAKU, ZAIGEN), (SHINKI, NASHI)
SHINKI_WORDS = ("新規計上", "新たに")
ZAIGEN_WORD = "財源"
RE_AMOUNT = re.compile(r"-?[0-9]+")
AMBIGUOUS_COLUMNS = ["from", "to", "name", "kan", "dept"]
UNMATCHED_COLUMNS = ["from", "name", "amount", "kind", "desc_head"]   # §11 name_unmatched.tsv
DESC_HEAD = 40   # desc_head の字数（§11）
MARU_HEAD = "m"  # ○の行の key の頭（§2）。t（特別会計・企業会計の主な内容の行）は対象にしない
JUDGED = "判定："
MANUAL_HEAD = "説明と概要の一致：「"
COUNT_RE = re.compile(r"名前の一致の規則と一覧（([0-9]+)行）")


def fh_kind(row):
    """名前の一致の行の kind（§7 hosei-fuhyo）。決まらなければ None。"""
    a = row["amount"]
    if not RE_AMOUNT.fullmatch(a or ""):
        return None
    v = int(a)
    if v > 0:
        return ZOUGAKU
    if v < 0:
        return GENGAKU
    return ZAIGEN if ZAIGEN_WORD in (row["desc"] or "") else None


def none_kind(row):
    """附表に当たらない○の行の kind の候補（§3・§7）：説明に「新規計上」か「新たに」の字があれば新規、無ければ附表に無い。
    台帳には付けず、一覧（name_unmatched.tsv）にだけ出す。"""
    return SHINKI if any(w in (row["desc"] or "") for w in SHINKI_WORDS) else NASHI


def is_maru_key(t):
    """構造化の層の行（(表, 回の id, 行の key)）が○の行か（§2：key の頭が m）。"""
    return t[0] == hosei.MARU and t[2].startswith(MARU_HEAD)


@dataclass
class HoseiInputs:
    lock: dict
    struct: object   # hosei.Struct
    fuhyo: dict      # 附表id → 附表の JSON


@dataclass
class HoseiBuilt:
    inputs: HoseiInputs
    order: list       # 附表の年度（gen_fuhyo_years.Year）
    items: dict       # 附表id → 附表の事業の一覧（款・担当課つき）
    year_fid: dict    # 西暦 → 附表id
    rows: list        # 名前の一致の候補の行（台帳の12列）
    ambiguous: list   # 同じ年度の附表に同じ名前の事業が2つ以上（name_ambiguous.tsv の行）
    unmatched: list   # 附表に名前の一致する事業が無い○の行（name_unmatched.tsv の行）
    no_fuhyo: list    # 同じ年度の附表が無い○の行（hj キー）
    bad_kind: list    # 名前は一致したが kind が決まらない行（文）
    toku: int = 0     # 対象にしない特別会計・企業会計の主な内容の行（t の行）の数


def build(inp):
    order = gy.years_order(inp.fuhyo)
    items = {y.fid: gy.year_items(y.fid, inp.fuhyo[y.fid]) for y in order}
    year_fid = {y.year: y.fid for y in order}
    rows, ambiguous, unmatched, no_fuhyo, bad = [], [], [], [], []
    maru = sorted(k for k in inp.struct.rows if k[0] == hosei.MARU)
    for t in (k for k in maru if is_maru_key(k)):
        r = inp.struct.rows[t]
        key = f"hj:{t[1]}/{t[2]}"
        fid = year_fid.get(int(inp.struct.kai[t[1]]["fiscal_year"]))
        if fid is None:
            no_fuhyo.append(key)
            continue
        n = mention.normalize(r["name"])
        same = [x for x in items[fid] if x["n"] == n]
        if len(same) > 1:
            ambiguous += [{"from": key, "to": gy.fh(fid, x["key"]), "name": x["name"], "kan": x["kan"],
                           "dept": "・".join(x["dept"])} for x in same]
            continue
        if not same:
            unmatched.append({"from": key, "name": r["name"], "amount": r["amount"], "kind": none_kind(r),
                              "desc_head": (r["desc"] or "")[:DESC_HEAD]})
            continue
        x = same[0]
        kind = fh_kind(r)
        if kind is None:
            bad.append(f"{key}：名前は {gy.fh(fid, x['key'])} と一致したが、kind が決まらない（金額 {r['amount']!r}）")
            continue
        rows.append(_row(key, fid, x, n, NAME, f"事業名が同じ（§4 の正規化のあと）。補正の種類は{_why(kind)}から", kind))
    gm._fail("kind が決まらない名前の一致の行（§7 hosei-fuhyo）", bad)
    keys = [(r["from"], r["to"], r["method"]) for r in rows]
    if len(set(keys)) != len(keys):
        raise gm.GenError("候補で (from, to, method) が重なっている")
    return HoseiBuilt(inp, order, items, year_fid, sorted(rows, key=lambda r: (r["from"], r["to"], r["method"])),
                      ambiguous, sorted(unmatched, key=lambda u: u["from"]), no_fuhyo, bad,
                      sum(1 for k in maru if not is_maru_key(k)))


def _why(kind):
    return "金額が0で説明に「財源」の字がある" if kind == ZAIGEN else "金額の符号"


def _row(key, fid, x, n, method, note, kind):
    return {"from": key, "to": gy.fh(fid, x["key"]), "method": method, "evidence": n, "where": "name",
            "context": n, "to_label": x["name"], "status": ledger.CANDIDATE, "reviewer": "", "date": "",
            "note": note, "kind": kind}


def generated_rows(built):
    return [{c: r[c] for c in COLUMNS} for r in built.rows]


def corpus(built):
    """§5 の照合の相手（from は主な内容の行、to は附表の事業）。"""
    return ledger.Corpus(texts={}, by_pos={}, fields={}, names={}, refs=None, struct=built.inputs.struct,
                         fuhyo={(fid, f["key"]): f for fid, its in built.items.items() for f in its})


def read_hosei_inputs(gi, lock):
    return HoseiInputs(lock, hosei.read_struct(gi),
                       {fid: gf.read_fuhyo_json(gi, fid, p) for fid, p in gf.named_fuhyo(lock)})


def load_built():
    lock = gm.load_lock(gm.LOCK_PATH)
    gi = gm.GitInputs(gm.INPUTS_ROOT, lock)
    gi.verify()
    return build(read_hosei_inputs(gi, lock))


def _parts(built, frm, to):
    """from の○の行と回の年度、to の附表の事業と附表の年度。無ければ None。"""
    t = hosei.KEY_FORMS["hj"].fullmatch(frm or "")
    r = built.inputs.struct.row_of(frm) if t else None
    fy = int(built.inputs.struct.kai[t.group(1)]["fiscal_year"]) if r is not None else None
    fid, _, k = (to or "")[3:].partition("/")
    x = next((i for i in built.items.get(fid, []) if i["key"] == k), None) if to.startswith("fh:") else None
    ty = next((y.year for y in built.order if y.fid == fid), None)
    return r, fy, x, fid, ty


def manual_row(built, frm, to, d):
    """人が確かめた manual の行（§6・§7 hosei-fuhyo）。返り値は（行、誤りの文の一覧）。d は判定の一覧の行。"""
    r, fy, x, fid, ty = _parts(built, frm, to)
    bad = []
    if r is None:
        bad.append(f"from が lock の版の主な内容の行に無い（{frm}）")
    elif not frm.split("/", 1)[1].startswith(MARU_HEAD):
        bad.append(f"from が○の行（key の頭が m）でない（{frm}）")
    if x is None:
        bad.append(f"to が lock の附表の事業に無い（{to}）")
    if bad:
        return None, bad
    n = mention.normalize(r["name"])
    if fy != ty:
        bad.append(f"from の回の年度（{fy}）と to の附表の年度（{ty}）が違う")
    if n == x["n"]:
        bad.append("from と to の名前が同じ（名前の一致の行にする）")
    if d["context"] != n:
        bad.append("context が from の名前（§4 の正規化を通した値）と違う")
    kind = fh_kind(r)
    if kind is None:
        bad.append(f"kind が金額の符号と額から決まらない（金額 {r['amount']!r}）")
    row = dict(_row(frm, fid, x, n, MANUAL, d["note"], kind or ""), status=d["status"], reviewer=d["reviewer"],
               date=d["date"])
    return row, bad


# ---- ○の行と附表の対応（§11） ----

def hosei_errors(rows, built):
    """§11 ○の行と附表の対応の誤り（文の一覧）。空なら合格。rejected の行は見ない（kind の形は全行で見る）。
    同じ hj が from に2行以上無い。from が○の行で、その回の年度と to の附表の年度が同じ。name の行は名前が同じで manual の行は違う。
    kind が増額・減額・財源更正を「,」で並べたもの。confirmed の行の from の hj が検収の済んだ行（§2）。confirmed の name の行の
    note に「判定：」があり、「名前の一致の規則と一覧（<N>行）」の N が、date と N の組ごとの行の数と同じ。confirmed の manual の
    行の note が「説明と概要の一致：「」で始まり、「判定：」がある。manual の candidate は台帳の形の検査（tools/ledger.py）で止める。"""
    st = built.inputs.struct
    errs = []
    for r in rows:
        at = f"{r['from']} {r['to']} {r['method']}"
        ks = r["kind"].split(",") if r["kind"] else []
        if not ks or any(k not in FH_KINDS for k in ks) or len(set(ks)) != len(ks):
            errs.append(f"{at}：kind が増額・減額・財源更正を「,」で並べたものでない（{r['kind']!r}。新規・附表に無いは台帳に付けない）")
        if r["status"] == ledger.REJECTED:
            continue
        f, fy, x, _, ty = _parts(built, r["from"], r["to"])
        if f is not None and x is not None:   # 無ければ §5 の照合で停止になる
            if fy != ty:
                errs.append(f"{at}：from の回の年度（{fy}）と to の附表の年度（{ty}）が違う")
            same = mention.normalize(r["to_label"]) == r["context"]
            if r["method"] == NAME and not same:
                errs.append(f"{at}：name の行で from と to の名前が違う")
            if r["method"] == MANUAL and same:
                errs.append(f"{at}：manual の行で from と to の名前が同じ")
        if r["status"] != ledger.CONFIRMED:
            continue
        if not st.is_checked(r["from"]):
            errs.append(f"{at}：confirmed の行の from が検収の済んだ行でない（LINK_SCHEMA §2）")
        if r["method"] == NAME and JUDGED not in r["note"]:
            errs.append(f"{at}：confirmed の name の行の note に「{JUDGED}」が無い")
        if r["method"] == MANUAL and not (r["note"].startswith(MANUAL_HEAD) and JUDGED in r["note"]):
            errs.append(f"{at}：confirmed の manual の行の note が「{MANUAL_HEAD}」で始まらないか、「{JUDGED}」が無い")
    live = [r for r in rows if r["status"] != ledger.REJECTED]
    counts = Counter(r["from"] for r in live)
    errs += [f"{k}：rejected でない行が {n} 行ある（1つまで）" for k, n in sorted(counts.items()) if n > 1]
    groups = Counter()
    for r in live:
        m = COUNT_RE.search(r["note"])
        if r["method"] == NAME and r["status"] == ledger.CONFIRMED and m:
            groups[(r["date"], int(m.group(1)))] += 1
    errs += [f"{d} の判定：note の行数 {n} と、その note の confirmed の name の行の数 {c} が違う"
             for (d, n), c in sorted(groups.items()) if c != n]
    return errs


def count_lines(rows, built):
    """件数の行：主な内容の行の数（○の行・対象にしない t の行）、名前の一致、附表に当たらない○の行（kind ごと）、manual。"""
    un = Counter(u["kind"] for u in built.unmatched)
    name_kind = Counter(k for r in rows if r["method"] == NAME for k in r["kind"].split(","))
    n_maru = sum(1 for k in built.inputs.struct.rows if is_maru_key(k))
    return [f"- 主な内容の行：○の行 {n_maru}・対象にしない特別会計・企業会計の行 {built.toku}",
            f"- 名前の一致の行：{sum(1 for r in rows if r['method'] == NAME)}（kind "
            + ("・".join(f"{k} {name_kind[k]}" for k in FH_KINDS if name_kind[k]) or "0") + "）",
            f"- manual の行：{sum(1 for r in rows if r['method'] == MANUAL)}",
            f"- 附表に名前の一致する事業が無い○の行：{len(built.unmatched)}（"
            + ("・".join(f"{k} {un[k]}" for k in NONE_KINDS if un[k]) or "0") + "。name_unmatched.tsv。台帳には書かない）",
            f"- 同じ年度の附表に同じ名前の事業が2つ以上ある○の行：{len({a['from'] for a in built.ambiguous})}"
            "（name_ambiguous.tsv）",
            f"- 同じ年度の附表が無い○の行：{len(built.no_fuhyo)}"]


def write_lists(outdir, built):
    os.makedirs(outdir, exist_ok=True)
    return ledger._write_files(outdir, [("name_ambiguous.tsv", AMBIGUOUS_COLUMNS, built.ambiguous),
                                        ("name_unmatched.tsv", UNMATCHED_COLUMNS, built.unmatched)])


def report_lines(built):
    return ["# ○の行と附表の対応の候補（build/hosei-fuhyo/）", "",
            f"- 候補：{len(built.rows)} 行"] + count_lines(built.rows, built)


def main():
    try:
        built = load_built()
        os.makedirs(OUT_DIR, exist_ok=True)
        gm.write_tsv(os.path.join(OUT_DIR, "candidates.tsv"), COLUMNS, generated_rows(built))
        names = ["candidates.tsv"] + write_lists(OUT_DIR, built)
        with open(os.path.join(OUT_DIR, "report.md"), "wb") as f:
            f.write(("\n".join(report_lines(built)) + "\n").encode("utf-8"))
    except gm.GenError as e:
        print(f"停止：{e}", file=sys.stderr)
        return 1
    print("\n".join(report_lines(built)[2:]))
    print(f"書き出し：{OUT_DIR}/ の {'・'.join(names + ['report.md'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
