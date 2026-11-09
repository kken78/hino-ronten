"""予算の議案と補正予算の回の対応の候補を作る（LINK_SCHEMA.md §2・§3・§5・§7 gian-yosan・§10・§11、DESIGN.md ADR-34 の4）。

inputs.lock.json の版の hino-council-search の public/data/gian.json（議案）と、hino-town-docs の構造化の層の
回の表（data/struct/hosei-kai.tsv。tools/hosei.py で読む）を git show で読み、§7 gian-yosan の決まりで候補
（method が title）を作って build/gian-yosan/ に書く。台帳（links/）には書かない。ツールが作るのは candidate まで
（DESIGN.md ADR-2）。台帳の更新は tools/update_links.py --ledger gian-yosan。

実行: python3 -B tools/gen_gian_yosan.py
入力の clone の場所は、環境変数 HINO_RONTEN_INPUTS で変えられる（gen_mentions.py と同じ）。
終了コード：0 は build/gian-yosan/ への書き出しまで終えた。1 は入力の誤りで止めた（件数と該当を表示する）。

§7 gian-yosan の決まり：
- 対象は補正予算の議案（専決処分の承認と報告の議案を含む）。決算の認定と当初予算の議案は対象にしない
- 議案の題から年度・会計・号を取る。専決処分の議案は題のかっこの中から取る。数字は §4 の正規化で半角にそろえる。
  題の末尾に余計な字があっても、年度・会計・号が取れれば通す
- 題の年度は「令和N年度」を西暦（N＋2018。元年は1）にして回の fiscal_year と、号は整数にして gou と、会計の名前は
  §2 の title と kaikei の組で比べる。当たる回が回の表に無い議案は行を作らず、一覧（no_kai.tsv）に出す
- 題が「補正予算（第N号）」を含むが、「令和N年度日野町…補正予算（第N号）」の形で年度・会計・号が取れない議案
  （平成の年度の議案）は、§7 に決まりが無いので行も一覧も作らず、件数だけを示す
"""
import os
import re
import sys
from collections import Counter
from dataclasses import dataclass

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import gen_mentions as gm  # noqa: E402
import hosei  # noqa: E402
import ledger  # noqa: E402
import mention  # noqa: E402

OUT_DIR = os.path.join(gm.ROOT, "build", "gian-yosan")
METHOD = "gian-yosan"   # 台帳のファイル名（links/gian-yosan.tsv）
TITLE = "title"         # 行の method（§3）
GIAN = "public/data/gian.json"
HOSEI_WORD = "補正予算"
SENKETSU = re.compile(r"^専決処分(?:の報告)?について\((.*)\)$")
# §7：題（§4 の正規化のあと）から年度・会計・号を取る。末尾の余計な字は通す
BILL_TITLE = re.compile(r"^令和([0-9]+|元)年度日野町(.+?)補正予算\(第([0-9]+)号\)")
NO_KAI_COLUMNS = ["from", "title"]


@dataclass
class Bill:
    key: str        # gi:<会議id>/<議案番号>
    title: str      # gian.json の title（原典の字）
    senketsu: bool  # 専決処分の承認か報告の議案（題のかっこの中から取った）
    year: int = 0   # 西暦
    kaikei_name: str = ""
    gou: int = 0
    ok: bool = False  # 年度・会計・号が取れた


def parse_title(title):
    """§7：議案の題 → (年度（西暦）, 会計の名前, 号, 専決処分か)。取れなければ (None, None, None, 専決処分か)。"""
    n = mention.normalize(title)
    m = SENKETSU.fullmatch(n)
    inner = m.group(1) if m else n
    b = BILL_TITLE.match(inner)
    if not b:
        return None, None, None, bool(m)
    y = 1 if b.group(1) == "元" else int(b.group(1))
    return y + 2018, b.group(2), int(b.group(3)), bool(m)


def hosei_bills(gian):
    """gian.json から補正予算の議案（題に「補正予算」の字を含むもの）を読む。同じ会議に同じ番号の議案が2つ以上あれば止める（§2）。"""
    out, dup = [], []
    for mid in sorted(gian):
        nos = Counter(a.get("no") for a in gian[mid].get("agenda") or [])
        for a in gian[mid].get("agenda") or []:
            title = a.get("title") or ""
            if HOSEI_WORD not in title:
                continue
            if nos[a.get("no")] > 1:
                dup.append(f"{mid} {a.get('no')}")
                continue
            y, name, gou, senketsu = parse_title(title)
            b = Bill(f"gi:{mid}/{a['no']}", title, senketsu)
            if y is not None:
                b.year, b.kaikei_name, b.gou, b.ok = y, name, gou, True
            out.append(b)
    gm._fail("同じ会議に同じ番号の議案が2つ以上ある（LINK_SCHEMA §2。その会議の gi は作らない）", sorted(set(dup)))
    return out


def note_of(bill, kai):
    note = (f"題の年度・会計・号（{kai['fiscal_year']}年度・{bill.kaikei_name}・第{bill.gou}号）が"
            "回の fiscal_year・kaikei・gou と同じ")
    if bill.senketsu:
        note += "。専決処分の題のかっこの中から取った"
    return note


@dataclass
class GianInputs:
    lock: dict
    gian: dict
    struct: object  # hosei.Struct


@dataclass
class GianBuilt:
    inputs: GianInputs
    bills: list      # 補正予算の議案（Bill）
    rows: list       # 候補の行（台帳の11列。from → to → method の順）
    no_kai: list     # 当たる回が回の表に無い議案（no_kai.tsv の行）
    no_title: list   # 題から年度・会計・号が取れない議案（件数だけを示す）


def build(inp):
    names = inp.struct.kaikei_names()
    index = {}
    for kid, r in inp.struct.kai.items():
        index.setdefault((int(r["fiscal_year"]), r["kaikei"], int(r["gou"])), []).append(kid)
    bills = hosei_bills(inp.gian)
    rows, no_kai, no_title = [], [], []
    for b in bills:
        if not b.ok:
            no_title.append({"from": b.key, "title": b.title})
            continue
        kaikei = names.get(b.kaikei_name)
        kids = index.get((b.year, kaikei, b.gou), []) if kaikei else []
        if not kids:
            no_kai.append({"from": b.key, "title": b.title})
            continue
        ev = mention.normalize(b.title)
        for kid in kids:
            kai = inp.struct.kai[kid]
            rows.append({"from": b.key, "to": f"hs:{kid}", "method": TITLE, "evidence": ev, "where": "title",
                         "context": ev, "to_label": kai["title"], "status": ledger.CANDIDATE, "reviewer": "",
                         "date": "", "note": note_of(b, kai)})
    keys = [(r["from"], r["to"], r["method"]) for r in rows]
    if len(set(keys)) != len(keys):
        raise gm.GenError("候補で (from, to, method) が重なっている")
    return GianBuilt(inp, bills, sorted(rows, key=lambda r: (r["from"], r["to"], r["method"])),
                     sorted(no_kai, key=lambda r: r["from"]), sorted(no_title, key=lambda r: r["from"]))


def generated_rows(built):
    return [{c: r[c] for c in ledger.LEDGER_COLUMNS} for r in built.rows]


def corpus(built):
    """§5 の照合の相手（to の hs。from の gi は §5 に決まりが無いので照合しない）。"""
    return ledger.Corpus(texts={}, by_pos={}, fields={}, names={}, refs=None, struct=built.inputs.struct)


def read_gian_inputs(gi, lock):
    return GianInputs(lock, gi.read_json(gm.HS, GIAN), hosei.read_struct(gi))


def load_built():
    lock = gm.load_lock(gm.LOCK_PATH)
    gi = gm.GitInputs(gm.INPUTS_ROOT, lock)
    gi.verify()
    return build(read_gian_inputs(gi, lock))


def kaikei_counts(rows, struct):
    """行の数を会計ごとに（回の kaikei）。"""
    c = Counter(struct.kai[r["to"][3:]]["kaikei"] for r in rows if r["to"][3:] in struct.kai)
    return "・".join(f"{k} {n}" for k, n in sorted(c.items()))


def year_counts(rows_):
    """一覧の議案の数を、題の年度ごとに。"""
    c = Counter()
    for r in rows_:
        y, _, _, _ = parse_title(r["title"])
        c[f"{y}年度" if y else "年度が取れない"] += 1
    return "・".join(f"{k} {n}" for k, n in sorted(c.items()))


def count_lines(rows, built):
    return [f"- 補正予算の議案：{len(built.bills)}（年度・会計・号が取れた {sum(1 for b in built.bills if b.ok)}・"
            f"取れない {len(built.no_title)}）",
            f"- 会計ごとの行の数：{kaikei_counts(rows, built.inputs.struct) or '0'}",
            f"- 当たる回が回の表に無い議案：{len(built.no_kai)}（{year_counts(built.no_kai) or '0'}。no_kai.tsv）"]


def write_lists(outdir, built):
    """no_kai.tsv（from の文字コード順。§11）を書く。"""
    os.makedirs(outdir, exist_ok=True)
    return ledger._write_files(outdir, [("no_kai.tsv", NO_KAI_COLUMNS, built.no_kai)])


def report_lines(built):
    return ["# 議案と回の対応の候補（build/gian-yosan/）", "",
            f"- 候補：{len(built.rows)} 行"] + count_lines(built.rows, built)


def main():
    try:
        built = load_built()
        os.makedirs(OUT_DIR, exist_ok=True)
        gm.write_tsv(os.path.join(OUT_DIR, "candidates.tsv"), ledger.LEDGER_COLUMNS, generated_rows(built))
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
