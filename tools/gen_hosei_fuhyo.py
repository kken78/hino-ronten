"""補正予算の概要の○の行と附表の事業の対応の候補を作る（LINK_SCHEMA.md §2・§3・§5・§7 hosei-fuhyo・§10・§11、
DESIGN.md ADR-34 の5）。

inputs.lock.json の版の hino-town-docs の構造化の層（主な内容の行 data/struct/hosei-maru.tsv と回の表。
tools/hosei.py で読む）と、shiga-hino-plans の files に名指しした附表（data/fuhyo/<附表id>.json）を git show で読み、
§7 hosei-fuhyo の名前の一致（method が name）の候補を作って build/hosei-fuhyo/ に書く。台帳（links/）には書かない。
ツールが作るのは candidate まで（DESIGN.md ADR-2）。台帳の更新は tools/update_links.py --ledger hosei-fuhyo。
○の行と附表の対応（§11）の検査（hosei_errors）もここに置き、tools/update_links.py・tools/check_links.py から使う。

実行: python3 -B tools/gen_hosei_fuhyo.py
入力の clone の場所は、環境変数 HINO_RONTEN_INPUTS で変えられる（gen_mentions.py と同じ）。
終了コード：0 は build/hosei-fuhyo/ への書き出しまで終えた。1 は入力の誤りで止めた（件数と該当を表示する）。

§7 hosei-fuhyo の決まり：
- 対象は、主な内容の行（○の行と特別会計・企業会計の主な内容の行。hj）と、同じ年度（回の fiscal_year と附表の
  fiscal_year.year が同じ）の附表の事業（fh）
- 名前の一致：○の行の名前と、同じ年度の附表の事業名が §4 の正規化のあとで完全に一致する事業を候補にする。
  同じ年度の附表に同じ名前の事業が2つ以上あるときは name ではつながず、一覧（name_ambiguous.tsv）に出す
- kind（§3）：金額が正なら増額、負なら減額、0 で説明に「財源」の字があれば財源更正。どれにも当たらなければ止める
- 名前が一致しない行：§7 は、to を none:<附表id> にした行（method が manual）を候補にすると書くが、§11 は manual の行に
  candidate を置かないと書く（PR の問い）。この道具は、決まるまで none の行を作らず、件数と行（unmatched）を示すだけにする
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
NONE_LABEL = "附表に無い"   # §3：none の to_label
SHINKI_WORDS = ("新規計上", "新たに")
ZAIGEN_WORD = "財源"
RE_AMOUNT = re.compile(r"-?[0-9]+")
AMBIGUOUS_COLUMNS = ["from", "to", "name", "kan", "dept"]


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
    """附表に当たらない行の kind（§3・§7）：説明に「新規計上」か「新たに」の字があれば新規、無ければ附表に無い。"""
    return SHINKI if any(w in (row["desc"] or "") for w in SHINKI_WORDS) else NASHI


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
    unmatched: list   # 附表に名前の一致する事業が無い行（(hj キー, 主な内容の行, 附表id, none の kind)）
    no_fuhyo: list    # 同じ年度の附表が無い行（hj キー）
    bad_kind: list    # 名前は一致したが kind が決まらない行（文）


def build(inp):
    order = gy.years_order(inp.fuhyo)
    items = {y.fid: gy.year_items(y.fid, inp.fuhyo[y.fid]) for y in order}
    year_fid = {y.year: y.fid for y in order}
    rows, ambiguous, unmatched, no_fuhyo, bad = [], [], [], [], []
    for t in sorted(k for k in inp.struct.rows if k[0] == hosei.MARU):
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
            unmatched.append((key, r, fid, none_kind(r)))
            continue
        x = same[0]
        kind = fh_kind(r)
        if kind is None:
            bad.append(f"{key}：名前は {gy.fh(fid, x['key'])} と一致したが、kind が決まらない（金額 {r['amount']!r}）")
            continue
        why = "金額が0で説明に「財源」の字がある" if kind == ZAIGEN else "金額の符号"
        rows.append({"from": key, "to": gy.fh(fid, x["key"]), "method": NAME, "evidence": n, "where": "name",
                     "context": n, "to_label": x["name"], "status": ledger.CANDIDATE, "reviewer": "", "date": "",
                     "note": f"事業名が同じ（§4 の正規化のあと）。補正の種類は{why}から", "kind": kind})
    gm._fail("kind が決まらない名前の一致の行（§7 hosei-fuhyo）", bad)
    keys = [(r["from"], r["to"], r["method"]) for r in rows]
    if len(set(keys)) != len(keys):
        raise gm.GenError("候補で (from, to, method) が重なっている")
    return HoseiBuilt(inp, order, items, year_fid, sorted(rows, key=lambda r: (r["from"], r["to"], r["method"])),
                      ambiguous, unmatched, no_fuhyo, bad)


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


# ---- ○の行と附表の対応（§11） ----

def hosei_errors(rows, struct):
    """§11 ○の行と附表の対応の誤り（文の一覧）。空なら合格。
    confirmed の行で同じ hj が from に2行以上無い。kind が5つの値を「,」で並べたもので、to が fh なら増額・減額・財源更正、
    none なら新規・附表に無いだけ。confirmed の行の from の hj が検収の済んだ行（§2）。manual の candidate は台帳の形の
    検査（tools/ledger.py）で止める。"""
    errs = []
    for r in rows:
        at = f"{r['from']} {r['to']} {r['method']}"
        ks = r["kind"].split(",") if r["kind"] else []
        if not ks or any(k not in KINDS for k in ks) or len(set(ks)) != len(ks):
            errs.append(f"{at}：kind が §3 の5つの値を「,」で並べたものでない（{r['kind']!r}）")
        else:
            allowed = FH_KINDS if r["to"].startswith("fh:") else NONE_KINDS
            wrong = [k for k in ks if k not in allowed]
            if wrong:
                errs.append(f"{at}：to が {r['to'].partition(':')[0]} の行に kind {'・'.join(wrong)} は付けない")
        if r["status"] == ledger.CONFIRMED and not struct.is_checked(r["from"]):
            errs.append(f"{at}：confirmed の行の from が検収の済んだ行でない（LINK_SCHEMA §2）")
    counts = Counter(r["from"] for r in rows if r["status"] == ledger.CONFIRMED)
    errs += [f"{k}：confirmed の行が {n} 行ある（1つまで）" for k, n in sorted(counts.items()) if n > 1]
    return errs


def count_lines(rows, built):
    """件数の行：主な内容の行の数（○の行・特別会計の行）、名前の一致、附表に当たらない行（kind ごと）。"""
    st = built.inputs.struct
    maru = [k for k in st.rows if k[0] == hosei.MARU]
    by_kind = Counter(st.rows[k]["kind"] for k in maru)
    un = Counter((u[1]["kind"], u[3]) for u in built.unmatched)
    name_kind = Counter(k for r in rows if r["method"] == NAME for k in r["kind"].split(","))
    return [f"- 主な内容の行：{len(maru)}（" + "・".join(f"{k} {n}" for k, n in sorted(by_kind.items())) + "）",
            f"- 名前の一致の行：{sum(1 for r in rows if r['method'] == NAME)}（kind "
            + ("・".join(f"{k} {name_kind[k]}" for k in FH_KINDS if name_kind[k]) or "0") + "）",
            f"- 附表に名前の一致する事業が無い行：{len(built.unmatched)}（"
            + ("・".join(f"{k} {kd} {n}" for (k, kd), n in sorted(un.items())) or "0")
            + "。none の行は作っていない：§7 と §11 の食い違い）",
            f"- 同じ年度の附表に同じ名前の事業が2つ以上ある行：{len({a['from'] for a in built.ambiguous})}"
            "（name_ambiguous.tsv）",
            f"- 同じ年度の附表が無い行：{len(built.no_fuhyo)}"]


def write_lists(outdir, built):
    os.makedirs(outdir, exist_ok=True)
    return ledger._write_files(outdir, [("name_ambiguous.tsv", AMBIGUOUS_COLUMNS, built.ambiguous)])


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
