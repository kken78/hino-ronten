"""テーマのノートの画面 build/pages/<theme>-<事業の番号>.html を作る（LINK_SCHEMA.md §16、DESIGN.md ADR-25）。

build/theme/<theme>.json（tools/build_theme.py が作る。§13）だけを読み、ひな形 tools/pages/note.html にデータを入れて書く。
lock の版の入力は読まない。外から何も読み込まない1つの HTML の文書になる。同じデータからは同じファイルができる。

実行: python3 -B tools/build_pages.py <theme> <node キー>（例 hoiku node:jisshi/e008）
終了コード：0 は作った。1 は止めた（理由を表示する）。
"""
import hashlib
import html
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
TEMPLATE = os.path.join(HERE, "pages", "note.html")
THEME_DIR = os.path.join(ROOT, "build", "theme")
OUT_DIR = os.path.join(ROOT, "build", "pages")
PLACEHOLDERS = ("__TITLE__", "__DATA__", "__PAGE__")
RE_NODE = re.compile(r"node:([a-z0-9_-]+)/(e[0-9]+)")
# 外から読み込む書き方（§16 の形：外から何も読み込まない）
RE_EXTERNAL = re.compile(r"<(?:script|img|iframe|link|source|video|audio)\b[^>]*\b(?:src|href)\s*=\s*[\"']?(?:https?:)?//"
                         r"|@import|url\(\s*[\"']?(?:https?:)?//", re.I)


class PageError(ValueError):
    pass


def script_json(obj):
    """<script type="application/json"> に入れる JSON。`</` を `<\\/` に替える（§16）。"""
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")


def render(template, data_bytes, program):
    """ひな形にデータを入れた HTML の文書を返す。"""
    for p in PLACEHOLDERS:
        if template.count(p) != 1:
            raise PageError(f"ひな形の {p} が1つでない（{template.count(p)}）")
    if RE_EXTERNAL.search(template):
        raise PageError("ひな形に外から読み込む書き方がある")
    data = json.loads(data_bytes.decode("utf-8"))
    prog = next((p for p in data.get("programs") or [] if p.get("key") == program), None)
    if prog is None:
        raise PageError(f"テーマ {data.get('theme')} の programs に {program} が無い")
    if not any(s.get("program") == program for s in data.get("sheets") or []):
        raise PageError(f"テーマ {data.get('theme')} の sheets に {program} が無い")
    for k in ("names", "theme_questions"):
        if k not in data:
            raise PageError(f"テーマのノートのデータに {k} が無い（tools/build_theme.py で作り直す）")
    page = {"program": program, "theme": data["theme"], "source_sha256": hashlib.sha256(data_bytes).hexdigest()}
    out = template.replace("__TITLE__", html.escape(f"{prog['name']}ノート"))
    out = out.replace("__PAGE__", script_json(page))
    out = out.replace("__DATA__", script_json(data))   # データの中の __PAGE__ などを置き換えないよう最後に入れる
    head = '<!doctype html>\n<html lang="ja">\n<head>\n<meta charset="utf-8">\n' \
           '<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">\n'
    i = out.index("<style>")
    return head + out[:i] + out[i:].replace("<div class=\"wrap\">", "</head>\n<body>\n<div class=\"wrap\">", 1) \
        + "</body>\n</html>\n"


def out_path(theme, program):
    m = RE_NODE.fullmatch(program)
    if not m:
        raise PageError(f"node キーの形でない：{program}")
    return os.path.join(OUT_DIR, f"{theme}-{m.group(2)}.html")


def main(argv):
    if len(argv) != 3:
        print("使い方: python3 -B tools/build_pages.py <theme> <node キー>", file=sys.stderr)
        return 1
    theme, program = argv[1], argv[2]
    src = os.path.join(THEME_DIR, f"{theme}.json")
    try:
        if not os.path.exists(src):
            raise PageError(f"{os.path.relpath(src, ROOT)} が無い（先に tools/build_theme.py {theme} を動かす）")
        path = out_path(theme, program)
        with open(TEMPLATE, encoding="utf-8") as f:
            template = f.read()
        with open(src, "rb") as f:
            data_bytes = f.read()
        doc = render(template, data_bytes, program)
    except PageError as e:
        print(f"止めた：{e}", file=sys.stderr)
        return 1
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(doc)
    print(f"{os.path.relpath(path, ROOT)}：{len(doc.encode('utf-8'))} バイト（データ build/theme/{theme}.json "
          f"{hashlib.sha256(data_bytes).hexdigest()[:12]}）")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
