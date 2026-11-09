"""提案理由の記録（records/teian.tsv）の下書きの手がかりとして、○の行ごとに、提案理由の発言の中の候補の文を出す
（LINK_SCHEMA.md §15.11、DESIGN.md ADR-35）。

inputs.lock.json の版の会議録の索引と、hino-town-docs の構造化の層（tools/hosei.py）と、議案と回の台帳
（links/gian-yosan.tsv）の confirmed の行を読み、一般会計の回の○の行ごとに次を build/teian/ に書く。台帳には書かない。
候補の文を選んで下書きの TSV を作るのは生成AI（下書き）で、判定は人（CLAUDE.md 不変の制約11 の (4)）。
候補の文は文の全体で、行ごとに切って「…」で省くのは下書き（§15.11 の引用の切り方）。
  candidates.tsv  ○の行ごとの候補の文（事情は歳出の段から3つまで、財源は歳入の段から2つまで）。kata は、概要の説明が
                  差し引きの型（§15.11。tools/records.py の sashihiki_kata）に当たった字（下書きが gaku を書く手がかり）
  report.md       件数

提案理由の発言の見つけ方：議案（gi）の会議の発言のうち、役職が議員と議長でないもので、索引の並びで最初に、
「<議案番号>、」と回の題（§4 の正規化のあと）を同じ文に含む発言。その文から、次の「日程第」か、ほかの議案の
「議第N号、」「報第N号、」で始まる項目の前の文までを、その議案の部分とする。部分の中で、「歳入」の字のある最初の文から、
そのあとの「歳出」の字のある最初の文の前までを歳入の段、そこから終わりまでを歳出の段とする（歳入の文が無ければ全部を歳出の段）。
候補の並べ方：事情は、○の行の名前（括弧の中と末尾の「ほか」を除く。tools/records.py の base_name）が文にあるか、
次に概要の説明（desc）と文の重なり（difflib の一致した字の数 ÷ desc の字数）の大きい順。財源は、名前が文にあるか、
次に名前と文の重なりの大きい順。desc は候補を探す手がかりにだけ使う（ADR-35 の4）。

実行: python3 -B tools/gen_teian.py
終了コード：0 は書き出しまで終えた。1 は入力の誤りで止めた。
"""
import difflib
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import check_records  # noqa: E402
import gen_mentions as gm  # noqa: E402
import hosei  # noqa: E402
import records  # noqa: E402

OUT_DIR = os.path.join(gm.ROOT, "build", "teian")
COLUMNS = ["maru", "name", "amount", "men", "rank", "name_in", "score", "bill", "sid", "sentence", "desc", "kata"]
JIJO_TOP, ZAIGEN_TOP = 3, 2
CHAIR = "議長"
RE_ITEM = re.compile(r"(?:議|報)第[0-9]+号、")


def norm(s):
    return records.norm(s)


def split_sentences(text):
    """原文を「。」のあとで文に分ける。文の中の改行は除き、前後の空白を除く（引用は原文の字のまま）。"""
    out, cur = [], ""
    for ch in text or "":
        cur += ch
        if ch == "。":
            out.append(cur)
            cur = ""
    if cur:
        out.append(cur)
    return [s for s in (x.replace("\n", "").strip(" 　\t") for x in out) if s]


def portion(text, bill_no, title):
    """発言のうち、その議案の部分の文の並び（無ければ []）。"""
    sents = split_sentences(text)
    nb, nt = norm(bill_no) + "、", norm(title)
    start = next((i for i, s in enumerate(sents) if nb in norm(s) and nt in norm(s)), None)
    if start is None:
        return []
    end = len(sents)
    for j in range(start + 1, len(sents)):
        ns = norm(sents[j])
        if "日程第" in ns or (RE_ITEM.search(ns) and nb not in ns):
            end = j
            break
    return sents[start:end]


def find_speech(inp, bill, title):
    """議案の提案理由の発言：(sid, 部分の文の並び)。見つからなければ None。"""
    m = records.RE_GI.fullmatch(bill)
    if not m:
        return None
    for sid in inp.order:
        st = inp.statements.get(sid) or {}
        role = st.get("role") or ""
        if st.get("meetingId") != m.group(1) or role == CHAIR or records.RE_GIIN.fullmatch(role):
            continue
        part = portion(st.get("text") or "", m.group(2), title)
        if part:
            return sid, part
    return None


def sections(part):
    """部分 → (歳入の段, 歳出の段)。"""
    i = next((k for k, s in enumerate(part) if "歳入" in s), None)
    if i is None:
        return [], part
    j = next((k for k in range(i + 1, len(part)) if "歳出" in part[k]), len(part))
    return part[i:j], part[j:]


def overlap(a, b):
    """a の字のうち、b と一致した字の割合（difflib のマッチングブロックの合計 ÷ a の字数）。"""
    a, b = norm(a), norm(b)
    if not a:
        return 0.0
    return sum(x.size for x in difflib.SequenceMatcher(None, a, b, autojunk=False).get_matching_blocks()) / len(a)


def ranked(sents, name, key_text, top):
    base = records.base_name(name)
    scored = [(base in norm(s), overlap(key_text, s), -i, s) for i, s in enumerate(sents)]
    scored.sort(reverse=True)
    return [(r + 1, hit, sc, s) for r, (hit, sc, _, s) in enumerate(scored[:top])]


def candidates(inp, st, report=None):
    """一般会計の回の○の行ごとの候補の行（COLUMNS）。report（dict）を渡すと件数を入れる。"""
    bill_of = {}
    for gi, hss in inp.gian_hs.items():
        for h in hss:
            bill_of.setdefault(h[3:], []).append(gi)
    out, no_bill, no_speech, rows_n = [], set(), set(), 0
    for (table, kid, key), r in sorted(st.rows.items()):
        if table != hosei.MARU or not key.startswith("m") or st.kai[kid]["kaikei"] != records.IPPAN:
            continue
        rows_n += 1
        bills = sorted(bill_of.get(kid, []))
        if len(bills) != 1:
            no_bill.add(kid)
            continue
        found = find_speech(inp, bills[0], st.kai[kid]["title"])
        if found is None:
            no_speech.add(kid)
            continue
        sid, part = found
        inc, outs = sections(part)
        maru = f"hj:{kid}/{key}"
        kata = ",".join(records.sashihiki_kata(r["desc"]))
        for men, sents, key_text, top in ((records.JIJO, outs, r["desc"], JIJO_TOP),
                                         (records.ZAIGEN, inc, r["name"], ZAIGEN_TOP)):
            for rank, hit, sc, s in ranked(sents, r["name"], key_text, top):
                out.append({"maru": maru, "name": r["name"], "amount": r["amount"], "men": men, "rank": str(rank),
                            "name_in": "1" if hit else "0", "score": f"{sc:.2f}", "bill": bills[0], "sid": f"sp:{sid}",
                            "sentence": s, "desc": r["desc"], "kata": kata})
    if report is not None:
        top1 = [c for c in out if c["men"] == records.JIJO and c["rank"] == "1"]
        report.update(rows=rows_n, no_bill=sorted(no_bill), no_speech=sorted(no_speech), targets=len(top1),
                      top1_name=sum(1 for c in top1 if c["name_in"] == "1"),
                      kata=sum(1 for c in top1 if c["kata"]))
    return out


def report_lines(rep, n):
    return ["# 提案理由の記録の候補の文（build/teian/）", "",
            f"- 一般会計の回の○の行：{rep['rows']}",
            f"- 議案と回の台帳の confirmed の行が1つに決まらない回：{len(rep['no_bill'])}"
            + (f"（{'・'.join(rep['no_bill'])}）" if rep["no_bill"] else ""),
            f"- 提案理由の発言が見つからない回：{len(rep['no_speech'])}"
            + (f"（{'・'.join(rep['no_speech'])}）" if rep["no_speech"] else ""),
            f"- 候補の文を出した○の行：{rep['targets']}（事情の1番目の文に名前がある行 {rep['top1_name']}）",
            f"- 概要の説明が差し引きの型に当たる○の行：{rep['kata']}",
            f"- 候補の行：{n}"]


def main():
    try:
        lock = gm.load_lock(gm.LOCK_PATH)
        gi = gm.GitInputs(gm.INPUTS_ROOT, lock)
        gi.verify()
        inp = check_records.read_inputs(gi)
        rep = {}
        out = candidates(inp, inp.struct, rep)
        os.makedirs(OUT_DIR, exist_ok=True)
        gm.write_tsv(os.path.join(OUT_DIR, "candidates.tsv"), COLUMNS, out)
        lines = report_lines(rep, len(out))
        with open(os.path.join(OUT_DIR, "report.md"), "wb") as f:
            f.write(("\n".join(lines) + "\n").encode("utf-8"))
    except (gm.GenError, records.RecordsError) as e:
        print(f"停止：{e}", file=sys.stderr)
        return 1
    print("\n".join(lines[2:]))
    print(f"書き出し：{OUT_DIR}/ の candidates.tsv・report.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
