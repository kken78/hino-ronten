"""同じ年度の中で回をまたいで出る同じ事業の○の行の対応の候補を作る（LINK_SCHEMA.md §2・§3・§5・§6・§7 hosei-tsuzuki・
§10・§11、DESIGN.md ADR-35）。

inputs.lock.json の版の hino-town-docs の構造化の層（回の表 data/struct/hosei-kai.tsv と主な内容の行 hosei-maru.tsv。
tools/hosei.py で読む）を git show で読み、§7 hosei-tsuzuki の名前の一致（method が name）の候補を作って
build/hosei-tsuzuki/ に書く。台帳（links/）には書かない。ツールが作るのは candidate まで（DESIGN.md ADR-2）。
台帳の更新は tools/update_links.py --ledger hosei-tsuzuki。回をまたぐ同じ事業（§11）の検査（tsuzuki_errors）もここに置く。

実行: python3 -B tools/gen_hosei_tsuzuki.py
入力の clone の場所は、環境変数 HINO_RONTEN_INPUTS で変えられる（gen_mentions.py と同じ）。
終了コード：0 は build/hosei-tsuzuki/ への書き出しまで終えた。1 は入力の誤りで止めた（件数と該当を表示する）。

§7 hosei-tsuzuki の決まり：
- 対象は○の行（hj のうち key の頭が m の行）。同じ年度（fiscal_year）・同じ会計（kaikei）の中だけでつなぐ
- 回の順は、回の表の prev をたどった順。prev の列が無い、prev が空の回が1つでない、2つの回が同じ回を prev に持つ、
  prev がほかの年度・会計の回を指す、たどって全部の回に届かない、のどれかなら止める
- 名前の一致：前の回を近い順に見て、§4 の正規化のあとで名前が同じ○の行がある最初の回の、その行を to にする。
  同じ回に同じ名前の○の行が2つ以上あるときはつながず、件数を報告に出す。それより前の回は見ない
"""
import os
import sys
from collections import Counter
from dataclasses import dataclass

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import gen_mentions as gm  # noqa: E402
import hosei  # noqa: E402
import ledger  # noqa: E402
import mention  # noqa: E402

OUT_DIR = os.path.join(gm.ROOT, "build", "hosei-tsuzuki")
METHOD = "hosei-tsuzuki"   # 台帳のファイル名（links/hosei-tsuzuki.tsv）
NAME = "name"              # 行の method（§3）
COLUMNS = ledger.columns_of(METHOD)
MARU_HEAD = "m"
JUDGED = "判定："
NOTE = "名前が同じ（§4 の正規化のあと）。前の回をたどって最初に同じ名前が出る回"


@dataclass
class TsuzukiBuilt:
    struct: object        # hosei.Struct
    order: dict           # (fiscal_year, kaikei) → 回の id の並び（prev をたどった順）
    pos: dict             # 回の id → (fiscal_year, kaikei, 順の番号)
    rows: list            # 候補の行（台帳の11列）
    ambiguous: list       # 同じ回に同じ名前の○の行が2つ以上あって、つながなかった○の行（hj キー）
    maru: int = 0         # ○の行の数


def kai_order(struct):
    """§7 hosei-tsuzuki の回の順。返り値は (order, pos)。誤りがあれば止める。"""
    errs, groups = [], {}
    for kid, r in sorted(struct.kai.items()):
        if "prev" not in r:
            errs.append(f"{kid}：回の表に prev の列が無い")
            continue
        groups.setdefault((r["fiscal_year"], r["kaikei"]), []).append(kid)
    gm._fail("回の順の誤り（LINK_SCHEMA §7 hosei-tsuzuki）", errs)
    order, pos = {}, {}
    for g, kids in sorted(groups.items()):
        roots = [k for k in kids if not struct.kai[k]["prev"]]
        nxt = {}
        for k in kids:
            p = struct.kai[k]["prev"]
            if not p:
                continue
            if p not in struct.kai or (struct.kai[p]["fiscal_year"], struct.kai[p]["kaikei"]) != g:
                errs.append(f"{k}：prev（{p}）が同じ年度・会計の回でない")
            elif p in nxt:
                errs.append(f"{p}：2つの回（{nxt[p]}・{k}）の prev になっている")
            else:
                nxt[p] = k
        if len(roots) != 1:
            errs.append(f"{g[0]}年度 {g[1]}：prev が空の回が {len(roots)} 個（1つのはず）")
            continue
        seq, cur = [], roots[0]
        while cur and cur not in seq:
            seq.append(cur)
            cur = nxt.get(cur)
        if sorted(seq) != sorted(kids):
            errs.append(f"{g[0]}年度 {g[1]}：prev をたどって届かない回がある（{'・'.join(sorted(set(kids) - set(seq)))}）")
            continue
        order[g] = seq
        for i, k in enumerate(seq):
            pos[k] = (g[0], g[1], i)
    gm._fail("回の順の誤り（LINK_SCHEMA §7 hosei-tsuzuki）", errs)
    return order, pos


def is_maru(t):
    return t[0] == hosei.MARU and t[2].startswith(MARU_HEAD)


def build(struct):
    order, pos = kai_order(struct)
    by_kai = {}
    for t, r in struct.rows.items():
        if is_maru(t):
            by_kai.setdefault(t[1], []).append((t, mention.normalize(r["name"])))
    rows, ambiguous = [], []
    for g, seq in sorted(order.items()):
        for i, kid in enumerate(seq):
            for t, n in sorted(by_kai.get(kid, [])):
                for j in range(i - 1, -1, -1):
                    same = [u for u, m in by_kai.get(seq[j], []) if m == n]
                    if not same:
                        continue
                    if len(same) > 1 or sum(1 for _, m in by_kai.get(kid, []) if m == n) > 1:
                        ambiguous.append(f"hj:{t[1]}/{t[2]}")
                        break
                    u = same[0]
                    between = seq[j + 1:i]
                    note = NOTE
                    if between:
                        note += f"。間の回（{between[0]}" + (f"〜{between[-1]}" if len(between) > 1 else "") + \
                                "）には同じ名前の○の行が無い"
                    rows.append({"from": f"hj:{t[1]}/{t[2]}", "to": f"hj:{u[1]}/{u[2]}", "method": NAME,
                                 "evidence": n, "where": "name", "context": n,
                                 "to_label": struct.rows[u]["name"], "status": ledger.CANDIDATE, "reviewer": "",
                                 "date": "", "note": note})
                    break
    rows.sort(key=lambda r: (r["from"], r["to"], r["method"]))
    return TsuzukiBuilt(struct, order, pos, rows, sorted(set(ambiguous)), sum(1 for t in struct.rows if is_maru(t)))


def generated_rows(built):
    return [{c: r[c] for c in COLUMNS} for r in built.rows]


def corpus(built):
    """§5 の照合の相手（from も to も主な内容の行）。"""
    return ledger.Corpus(texts={}, by_pos={}, fields={}, names={}, refs=None, struct=built.struct)


def load_built():
    lock = gm.load_lock(gm.LOCK_PATH)
    gi = gm.GitInputs(gm.INPUTS_ROOT, lock)
    gi.verify()
    return build(hosei.read_struct(gi))


# ---- 回をまたぐ同じ事業（§11） ----

def tsuzuki_errors(rows, built):
    """§11 回をまたぐ同じ事業の誤り（文の一覧）。空なら合格。rejected の行は見ない。"""
    st = built.struct
    errs = []
    for r in rows:
        if r["status"] == ledger.REJECTED:
            continue
        at = f"{r['from']} {r['to']} {r['method']}"
        f, t = st.row_of(r["from"]), st.row_of(r["to"])
        if f is None or t is None:   # 無ければ §5 の照合で停止になる
            continue
        fk, tk = st.kai_of(r["from"]), st.kai_of(r["to"])
        pf, pt = built.pos.get(fk), built.pos.get(tk)
        if pf is None or pt is None or pf[:2] != pt[:2]:
            errs.append(f"{at}：from と to が同じ年度・同じ会計の回でない")
        elif pf[2] <= pt[2]:
            errs.append(f"{at}：from の回（{fk}）が to の回（{tk}）より後でない")
        if r["method"] == NAME and mention.normalize(r["to_label"]) != r["context"]:
            errs.append(f"{at}：name の行で from と to の名前が違う")
        if r["status"] != ledger.CONFIRMED:
            continue
        for k in (r["from"], r["to"]):
            if not st.is_checked(k):
                errs.append(f"{at}：confirmed の行の {k} が検収の済んだ行でない（LINK_SCHEMA §2）")
        if JUDGED not in r["note"]:
            errs.append(f"{at}：confirmed の行の note に「{JUDGED}」が無い")
    counts = Counter(r["from"] for r in rows if r["status"] != ledger.REJECTED)
    errs += [f"{k}：rejected でない行が {n} 行ある（1つまで）" for k, n in sorted(counts.items()) if n > 1]
    return errs


def count_lines(rows, built):
    return [f"- ○の行：{built.maru}",
            f"- 回をまたぐ同じ事業の組：{sum(1 for r in rows if r['status'] != ledger.REJECTED)}"
            f"（rejected {sum(1 for r in rows if r['status'] == ledger.REJECTED)}）",
            f"- 同じ回に同じ名前の○の行が2つ以上あって、つながなかった○の行：{len(built.ambiguous)}"
            + (f"（{'・'.join(built.ambiguous)}）" if built.ambiguous else "")]


def report_lines(built):
    return ["# 回をまたぐ同じ事業の候補（build/hosei-tsuzuki/）", "",
            f"- 候補：{len(built.rows)} 行"] + count_lines(built.rows, built)


def main():
    try:
        built = load_built()
        os.makedirs(OUT_DIR, exist_ok=True)
        gm.write_tsv(os.path.join(OUT_DIR, "candidates.tsv"), COLUMNS, generated_rows(built))
        with open(os.path.join(OUT_DIR, "report.md"), "wb") as f:
            f.write(("\n".join(report_lines(built)) + "\n").encode("utf-8"))
    except gm.GenError as e:
        print(f"停止：{e}", file=sys.stderr)
        return 1
    print("\n".join(report_lines(built)[2:]))
    print(f"書き出し：{OUT_DIR}/ の candidates.tsv・report.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
