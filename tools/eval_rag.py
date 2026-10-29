"""持ち込み用の資料を渡した生成AIの出力を、道具で数える（docs/eval-shisaku1.md §6）。

判定はしない。基準 K1（出典）・K2（引用）・K4（未確認）に当たる箇所を一覧にし、判定シートの材料にする。
出力を見る前に作る（docs/eval-shisaku1.md §5）。標準ライブラリだけ。

実行: python3 -B tools/eval_rag.py <出力の .md> <本編の .md> <記録編の .md>
      → build/eval/<出力の名前>-check.md
終了コード：0 は書いた。1 は止めた。
"""
import os
import re
import sys
import unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT_DIR = os.path.join(ROOT, "build", "eval")
RE_URL = re.compile(r"https?://[^\s）」』、，,］\]\)]+")
RE_CITE = re.compile(r"[［\[（(]\s*出典\s*[：:]([^］\]）)]*)[］\]）)]")   # 資料と同じ（出典：url）の形も出典とみなす
RE_SKIP = re.compile(r"^\s*(#|---+\s*$|\|?\s*:?-{3,})")
RE_ITEM = re.compile(r"^\s*(?:[-*・]\s+|\d+[.)．]\s*)")
UNCONFIRMED = "【未確認】"
ISSUES = "照合結果（未確認）"


def norm(s):
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", s))


# ---- 持ち込み用の資料 ----

class Material:
    """本編と記録編。url ごとに、出てくる章と、確定の段落に出てくるかを持つ。"""

    def __init__(self, files):
        self.text = ""
        self.urls = {}          # url → {"chapters": [..], "confirmed": bool}
        for path, part in files:
            with open(path, encoding="utf-8") as f:
                t = f.read()
            self.text += t + "\n"
            chapter, issues = "", False
            for line in t.split("\n"):
                m = re.match(r"(#{1,3}) (.*)", line)
                if m:
                    if len(m.group(1)) == 1:
                        chapter = m.group(2).split("：", 1)[-1]
                    if len(m.group(1)) <= 2:
                        issues = ISSUES in m.group(2)
                    continue
                unconfirmed = issues or UNCONFIRMED in line
                for u in RE_URL.findall(line):
                    x = self.urls.setdefault(u, {"chapters": [], "confirmed": False})
                    where = f"{part}：{chapter}"
                    if where not in x["chapters"]:
                        x["chapters"].append(where)
                    if not unconfirmed:
                        x["confirmed"] = True
        self.ntext = norm(self.text)

    def has_quote(self, q):
        parts = [p for p in re.split(r"\.\.\.+|…+", unicodedata.normalize("NFKC", q)) if norm(p)]
        return all(norm(p) in self.ntext for p in parts) if parts else True


# ---- 出力 ----

def split_sentences(line):
    """「。」で分ける。かぎかっこの中では分けない。"""
    out, buf, depth = [], "", 0
    for ch in line:
        buf += ch
        if ch in "「『":
            depth += 1
        elif ch in "」』" and depth:
            depth -= 1
        elif ch == "。" and depth == 0:
            out.append(buf)
            buf = ""
    if buf.strip():
        out.append(buf)
    # 「。」のあとに続く［出典：…］は前の文に付ける
    merged = []
    for s in out:
        if merged and RE_CITE.match(s.strip()) and not RE_CITE.sub("", s).strip(" 　。"):
            merged[-1] += s
        else:
            merged.append(s)
    return [s.strip() for s in merged if s.strip(" 　")]


def sentences(text):
    out = []
    for n, line in enumerate(text.split("\n"), 1):
        if not line.strip() or RE_SKIP.match(line):
            continue
        body = RE_ITEM.sub("", line).strip()
        if body.startswith("|"):
            body = " ".join(c.strip() for c in body.strip("|").split("|"))
        for s in split_sentences(body):
            out.append((n, s))
    return out


def quotes(s):
    """かぎかっこ「」の中の文（入れ子は外側）。"""
    out, buf, depth = [], "", 0
    for ch in s:
        if ch == "「":
            depth += 1
            if depth == 1:
                buf = ""
                continue
        elif ch == "」" and depth:
            depth -= 1
            if depth == 0:
                out.append(buf)
                continue
        if depth:
            buf += ch
    return out


def cites(s):
    us = []
    for m in RE_CITE.finditer(s):
        us += RE_URL.findall(m.group(1))
    return us


def check(output, mat):
    ss = sentences(output)
    res = {"sentences": len(ss), "cited": 0, "quotes": 0, "no_cite": [], "unknown_url": [], "no_quote": [],
           "unconfirmed": [], "chapters": {}}
    for n, s in ss:
        us = cites(s)
        if us:
            res["cited"] += 1
        else:
            res["no_cite"].append((n, s))
        for u in us:
            x = mat.urls.get(u)
            if x is None:
                res["unknown_url"].append((n, u))
                continue
            for c in x["chapters"]:
                res["chapters"][c] = res["chapters"].get(c, 0) + 1
        if any(u in mat.urls and not mat.urls[u]["confirmed"] for u in us) and "未確認" not in s:
            res["unconfirmed"].append((n, s))
        for q in quotes(RE_CITE.sub("", s)):
            res["quotes"] += 1
            if not mat.has_quote(q):
                res["no_quote"].append((n, q))
    return res


def report(name, res):
    def lines(xs):
        return [f"- {n}行目：{t}" for n, t in xs] or ["- なし"]
    out = [f"# {name} の道具による一覧（docs/eval-shisaku1.md §6）", "",
           "判定はしていない。判定シートの材料。", "",
           f"- 文の数：{res['sentences']}", f"- 出典の付いた文：{res['cited']}", f"- 引用の数：{res['quotes']}", "",
           f"## K1 出典の無い文（{len(res['no_cite'])}）", "", "事実を述べる文かどうかは人が見る。", ""]
    out += lines(res["no_cite"])
    out += ["", f"## K1 持ち込み用の資料に無い url（{len(res['unknown_url'])}）", ""] + lines(res["unknown_url"])
    out += ["", f"## K2 持ち込み用の資料に無い引用（{len(res['no_quote'])}）", ""] + lines(res["no_quote"])
    out += ["", f"## K4 未確認の出典を使い、「未確認」と書いていない文（{len(res['unconfirmed'])}）", ""] + lines(res["unconfirmed"])
    out += ["", "## 参考：出典の url がある章", ""]
    out += [f"- {c}：{k}" for c, k in sorted(res["chapters"].items(), key=lambda x: (-x[1], x[0]))] or ["- なし"]
    return "\n".join(out) + "\n"


def main(argv):
    if len(argv) != 4:
        print("使い方: python3 -B tools/eval_rag.py <出力の .md> <本編の .md> <記録編の .md>", file=sys.stderr)
        return 1
    for p in argv[1:]:
        if not os.path.exists(p):
            print(f"止めた：{p} が無い", file=sys.stderr)
            return 1
    mat = Material([(argv[2], "本編"), (argv[3], "記録編")])
    with open(argv[1], encoding="utf-8") as f:
        res = check(f.read(), mat)
    name = os.path.splitext(os.path.basename(argv[1]))[0]
    os.makedirs(OUT_DIR, exist_ok=True)
    path = os.path.join(OUT_DIR, f"{name}-check.md")
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(report(name, res))
    print(f"{os.path.relpath(path, ROOT)}：文 {res['sentences']}・出典の無い文 {len(res['no_cite'])}・資料に無い url "
          f"{len(res['unknown_url'])}・資料に無い引用 {len(res['no_quote'])}・未確認の書き落とし {len(res['unconfirmed'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
