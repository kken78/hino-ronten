"""応用編の確かめ（docs/eval-shisaku1.md §8.2）：tools/run_oyo.py の答えを、MCP の道具が返しうる文と照らして数える。

判定はしない。答えごとに、出典の url が道具の返したものか、かぎかっこの引用が道具の返した文にあるかを数え、
合わないものを一覧にする。引用は空白だけを除いて比べ、NFKC にそろえたときだけ合うものは「字の幅などを変えた引用」として別に数える。
道具が返しうる文は、tools/mcp_ronten.py の道具（overview・links・issues・council・topic・speeches と、すべての記載）を
その場で呼んで集める。標準ライブラリだけ。

実行: python3 -B tools/eval_mcp.py <回の名前> [--theme hoiku] [--program node:jisshi/e008]
      → build/eval/<回の名前>/check.md
終了コード：0 は書いた。1 は止めた。
"""
import argparse
import glob
import json
import os
import re
import sys
import unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import mcp_ronten as mr  # noqa: E402

ROOT = os.path.dirname(HERE)
RE_URL = re.compile(r"https?://[A-Za-z0-9._~:/?#@!$&'+,;=%\-]+")
RE_SPLIT = re.compile(r"…+|\.\.\.+|（中略）")


def ws(s):
    return re.sub(r"\s+", "", s)


def nk(s):
    return ws(unicodedata.normalize("NFKC", s))


def collect(server):
    """道具が返しうる文を1つの文字列にする。"""
    out = [server.t_overview({}), server.t_links({}), server.t_issues({}), server.t_council({})]
    out += [server.t_issues({"type": t}) for t in sorted({x["type"] for x in server.d.get("issues") or []})]
    names = set(server.r.kot) | {it["key"] for it in server.items.values() if it["key"]}
    for n in sorted(names):
        try:
            out.append(server.t_topic({"name": n}))
        except mr.McpError:
            pass
    out += [it["text"] for it in server.items.values()]
    for n in sorted(server.speech_of):
        out.append(server.t_speeches({"exchange": f"exchange:{n}"}))
    return "\n".join(out)


class Corpus:
    def __init__(self, text):
        self.ws = ws(text)
        self.nk = nk(text)
        self.urls = {u.rstrip("-.,;:") for u in RE_URL.findall(text)}


def answers(md):
    """tools/run_oyo.py の <モデル>-<会話>.md：[(依頼の名前, 答え)]。"""
    out, req, buf, on = [], None, [], False
    for line in md.split("\n"):
        m = re.fullmatch(r"## (依頼\d+)", line)
        if m:
            if req:
                out.append((req, "\n".join(buf)))
            req, buf, on = m.group(1), [], False
            continue
        if line.strip() == "### 答え" and req:
            on, buf = True, []
            continue
        if on:
            buf.append(line)
    if req:
        out.append((req, "\n".join(buf)))
    return out


def quotes(line):
    """かぎかっこ「」の中の文（入れ子は外側）。1行ごとに見る。"""
    out, buf, depth = [], "", 0
    for ch in line:
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


def check(text, corpus):
    urls = [u.rstrip("-.,;:") for u in RE_URL.findall(text)]
    qs = [q for line in text.split("\n") for q in quotes(line)]
    not_in, width = [], []
    for q in qs:
        parts = [p for p in RE_SPLIT.split(q) if ws(p)]
        if all(ws(p) in corpus.ws for p in parts):
            continue
        (width if all(nk(p) in corpus.nk for p in parts) else not_in).append(q)
    return {"chars": len(ws(text)), "urls": len(urls), "url_kinds": len(set(urls)),
            "bad_urls": sorted({u for u in urls if u not in corpus.urls}), "quotes": len(qs),
            "not_in": not_in, "width": width}


def report(run, rows):
    out = [f"# {run}：道具で照らした結果（docs/eval-shisaku1.md §8.2）", "",
           "判定はしない。合わない引用には、点検した答弁案の言い回しや、自分で作った問い・見出しが入る。どれに当たるかは人が見る。", "",
           "| 答え | 字数 | url（種類） | 道具が返していない url | 引用 | 道具の返した文に無い引用 | 字の幅などを変えた引用 |",
           "| --- | --- | --- | --- | --- | --- | --- |"]
    for name, req, r in rows:
        out.append(f"| {name} {req} | {r['chars']} | {r['urls']}（{r['url_kinds']}） | {len(r['bad_urls'])} | {r['quotes']} | "
                   f"{len(r['not_in'])} | {len(r['width'])} |")
    for name, req, r in rows:
        if r["bad_urls"] or r["not_in"] or r["width"]:
            out += ["", f"## {name} {req}", ""]
            out += [f"- 道具が返していない url：{u}" for u in r["bad_urls"]]
            out += [f"- 字の幅などを変えた引用：「{q}」" for q in r["width"]]
            out += [f"- 道具の返した文に無い引用：「{q}」" for q in r["not_in"]]
    return "\n".join(out) + "\n"


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("run")
    ap.add_argument("--theme", default="hoiku")
    ap.add_argument("--program", default="node:jisshi/e008")
    a = ap.parse_args(argv[1:])
    d = os.path.join(ROOT, "build", "eval", a.run)
    files = sorted(glob.glob(os.path.join(d, "*-*.md")))
    files = [f for f in files if os.path.basename(f) not in ("summary.md", "all.md", "check.md")]
    if not files:
        print(f"止めた：{d} に答えのファイルが無い", file=sys.stderr)
        return 1
    try:
        with open(os.path.join(mr.THEME_DIR, f"{a.theme}.json"), "rb") as f:
            raw = f.read()
        server = mr.Server(raw, a.program, mr.theme_words(mr.THEMES_TSV, a.theme), mr.load_speeches(json.loads(raw)))
    except (OSError, ValueError) as e:
        print(f"止めた：{e}", file=sys.stderr)
        return 1
    corpus = Corpus(collect(server))
    rows = []
    for path in files:
        name = os.path.basename(path)[:-3]
        with open(path, encoding="utf-8") as f:
            for req, text in answers(f.read()):
                rows.append((name, req, check(text, corpus)))
    with open(os.path.join(d, "check.md"), "w", encoding="utf-8", newline="\n") as f:
        f.write(report(a.run, rows))
    for name, req, r in rows:
        print(f"{name} {req}：url {r['urls']}・返していない url {len(r['bad_urls'])}・引用 {r['quotes']}・"
              f"文に無い {len(r['not_in'])}・字の幅など {len(r['width'])}")
    print(f"書いた：{os.path.join(d, 'check.md')}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
