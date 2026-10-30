"""答弁で外せない語の再現性を数える（docs/eval-shisaku1.md §7）。

§7.1 の2つの表（場面と外せない語、語の原文と語の骨）を docs/eval-shisaku1.md から読み、
build/eval/<回の名前>-<場面>-<モデル>-<番号>.md を数えて build/eval/<回の名前>-words.md に書く。判定はしない。標準ライブラリだけ。

実行: python3 -B tools/eval_words.py <回の名前>
終了コード：0 は書いた。1 は止めた。
"""
import glob
import os
import re
import statistics
import sys
import unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DOC = os.path.join(ROOT, "docs", "eval-shisaku1.md")
EVAL = os.path.join(ROOT, "build", "eval")
SEP = "／"
RE_W = re.compile(r"W(\d+)")
RE_FILE = re.compile(r"-(T\d+)-([a-z0-9]+)-(\d+)\.md$")


class WordsError(ValueError):
    pass


def norm(s):
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", s))


def expand(cell):
    """「W1・W2」「W1〜W8・W19」「W10〜W12」を番号の並びにする。"""
    out = []
    for part in re.split(r"[・、,]", cell):
        m = re.fullmatch(r"\s*W(\d+)\s*〜\s*W(\d+)\s*", part)
        if m:
            out += [f"W{i}" for i in range(int(m.group(1)), int(m.group(2)) + 1)]
        elif RE_W.fullmatch(part.strip()):
            out.append(part.strip())
        elif part.strip():
            raise WordsError(f"外せない語の欄が読めない：{cell}")
    return out


def read_tables(text):
    """§7.1 の表を読む。返り値：(場面 → 外せない語の番号の並び, 番号 → (原文の語の並び, 語の骨の並び))。"""
    s = text.find("### 7.1")
    if s < 0:
        raise WordsError("docs/eval-shisaku1.md に §7.1 が無い")
    e = text.find("\n### ", s + 1)
    sec = text[s:e if e > 0 else len(text)]
    scenes, words = {}, {}
    for line in sec.split("\n"):
        if not line.startswith("|") or line.startswith("| ---"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if re.fullmatch(r"T\d+", cells[0]) and len(cells) == 3:
            scenes[cells[0]] = expand(cells[2])
        elif RE_W.fullmatch(cells[0]) and len(cells) == 3:
            words[cells[0]] = ([x for x in cells[1].split(SEP) if x], [x for x in cells[2].split(SEP) if x])
    if not scenes or not words:
        raise WordsError("§7.1 の表が読めない")
    for sc, ws in scenes.items():
        for w in ws:
            if w not in words:
                raise WordsError(f"{sc} の {w} が語の表に無い")
    return scenes, words


def has(text, parts):
    t = norm(text)
    return all(norm(p) in t for p in parts)


def count(rnd, scenes, words, eval_dir=EVAL):
    """場面・モデルごとの結果の並び。"""
    files = {}
    for f in sorted(glob.glob(os.path.join(eval_dir, f"{glob.escape(rnd)}-T*-*-*.md"))):
        m = RE_FILE.search(f)
        if m and m.group(1) in scenes:
            files.setdefault((m.group(1), m.group(2)), []).append(f)
    out = []
    for (sc, model), fs in sorted(files.items(), key=lambda x: (int(x[0][0][1:]), x[0][1])):
        ws = scenes[sc]
        strict, loose, per = [], [], {w: [0, 0] for w in ws}
        for f in fs:
            with open(f, encoding="utf-8") as fh:
                t = fh.read()
            a = [has(t, words[w][0]) for w in ws]
            b = [has(t, words[w][1]) for w in ws]
            for w, x, y in zip(ws, a, b):
                per[w][0] += x
                per[w][1] += y
            strict.append(sum(a) / len(ws))
            loose.append(sum(b) / len(ws))
        out.append({"scene": sc, "model": model, "n": len(fs), "mean": statistics.mean(strict),
                    "sd": statistics.pstdev(strict), "min": min(strict), "loose": statistics.mean(loose), "per": per})
    return out


def report(rnd, rows):
    out = [f"# {rnd} の外せない語（docs/eval-shisaku1.md §7）", "", "判定はしていない。割合は場面の外せない語のうち入った割合の平均。", "",
           "| 場面 | モデル | 回数 | 原文のまま | ばらつき | 最小 | 語の骨 | 語ごと（原文のまま／語の骨） |", "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    for r in rows:
        out.append(f"| {r['scene']} | {r['model']} | {r['n']} | {r['mean']:.0%} | {r['sd']:.0%} | {r['min']:.0%} | {r['loose']:.0%} | "
                   + " ".join(f"{w}:{a}/{b}" for w, (a, b) in r["per"].items()) + " |")
    return "\n".join(out) + "\n"


def main(argv):
    if len(argv) != 2:
        print("使い方: python3 -B tools/eval_words.py <回の名前>", file=sys.stderr)
        return 1
    rnd = argv[1]
    try:
        with open(DOC, encoding="utf-8") as f:
            scenes, words = read_tables(f.read())
        rows = count(rnd, scenes, words)
        if not rows:
            raise WordsError(f"build/eval/{rnd}-T*-*-*.md が無い")
    except WordsError as e:
        print(f"止めた：{e}", file=sys.stderr)
        return 1
    path = os.path.join(EVAL, f"{rnd}-words.md")
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(report(rnd, rows))
    for r in rows:
        print(f"{r['scene']}-{r['model']}（{r['n']}回）：原文のまま {r['mean']:.0%}（ばらつき {r['sd']:.0%}、最小 {r['min']:.0%}）／語の骨 {r['loose']:.0%}")
    print(os.path.relpath(path, ROOT))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
