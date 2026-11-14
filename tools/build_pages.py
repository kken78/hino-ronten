"""テーマのノートの画面 build/pages/<theme>-<見方の名前>.html を作る（LINK_SCHEMA.md §16、DESIGN.md ADR-25・ADR-31）。

build/theme/<theme>.json（tools/build_theme.py が作る。§13）だけを読み、ひな形 tools/pages/note.html にデータを入れて書く。
lock の版の入力は読まない。外から何も読み込まない1つの HTML の文書になる。同じデータからは同じファイルができる。

実行: python3 -B tools/build_pages.py <theme> <見方のキー>（例 hoiku node:jisshi/e008）
見方のキーは node・plan・fa・dist・org・waku（枠の要素）のキーか、テーマの id（テーマ全体）。見方の名前は、事業は node キーの
最後の部分（e008）、期の計画は計画の id（kaigo9）、施設は fa の key（nishioji-yo）、地区は dist の key（hino）、組織は org の key
（kucho-kai）、枠の要素は枠の id と要素の番号を「-」でつないだもの（kaigo-hokenryo-6。DESIGN.md ADR-37）、
テーマ自体は theme（hoiku-theme.html）。
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
RE_NODE = re.compile(r"node:([a-z0-9_-]+)/([A-Za-z0-9_-]+)")
RE_PLAN = re.compile(r"plan:([a-z0-9][a-z0-9-]*)")
RE_FA = re.compile(r"fa:([a-z0-9][a-z0-9-]*)")
RE_DIST = re.compile(r"dist:([a-z0-9][a-z0-9-]*)")
RE_ORG = re.compile(r"org:([a-z0-9][a-z0-9-]*)")
RE_WAKU = re.compile(r"waku:([a-z0-9][a-z0-9-]*)/([1-9][0-9]*)")   # 枠の要素（LINK_SCHEMA §2・§16。ADR-37）
RE_THEME = re.compile(r"[a-z]+")
# 外から読み込む書き方（§16 の形：外から何も読み込まない）
RE_EXTERNAL = re.compile(r"<(?:script|img|iframe|link|source|video|audio)\b[^>]*\b(?:src|href)\s*=\s*[\"']?(?:https?:)?//"
                         r"|@import|url\(\s*[\"']?(?:https?:)?//", re.I)


class PageError(ValueError):
    pass


def script_json(obj):
    """<script type="application/json"> に入れる JSON。`</` を `<\\/` に替える（§16）。"""
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")


def view_name(theme, view):
    """見方のキー → 見方の名前（§16）。形が合わなければ止める。"""
    m = RE_WAKU.fullmatch(view)
    if m:
        return f"{m.group(1)}-{m.group(2)}"
    for rx in (RE_NODE, RE_PLAN, RE_FA, RE_DIST, RE_ORG):
        m = rx.fullmatch(view)
        if m:
            return m.group(m.lastindex)
    if view == theme and RE_THEME.fullmatch(view):
        return "theme"
    raise PageError(f"見方のキー（node・plan・fa・dist・org・waku のキーか、テーマの id）の形でない：{view}")


def render(template, data_bytes, view):
    """ひな形にデータを入れた HTML の文書を返す。"""
    for p in PLACEHOLDERS:
        if template.count(p) != 1:
            raise PageError(f"ひな形の {p} が1つでない（{template.count(p)}）")
    if RE_EXTERNAL.search(template):
        raise PageError("ひな形に外から読み込む書き方がある")
    data = json.loads(data_bytes.decode("utf-8"))
    for k in ("names", "theme_questions", "chushin"):
        if k not in data:
            raise PageError(f"テーマのノートのデータに {k} が無い（tools/build_theme.py で作り直す）")
    sheet = next((s for s in data.get("sheets") or [] if s.get("view") == view), None)
    if sheet is None:
        raise PageError(f"テーマ {data.get('theme')} の sheets に見方 {view} が無い")
    if sheet.get("view_kind") == "事業" and not any(p.get("key") == view for p in data.get("programs") or []):
        raise PageError(f"テーマ {data.get('theme')} の programs に {view} が無い")
    page = {"view": view, "view_kind": sheet.get("view_kind", ""), "name": sheet.get("name", ""), "theme": data["theme"],
            "source_sha256": hashlib.sha256(data_bytes).hexdigest()}
    out = template.replace("__TITLE__", html.escape(f"{page['name']}ノート"))
    out = out.replace("__PAGE__", script_json(page))
    out = out.replace("__DATA__", script_json(data))   # データの中の __PAGE__ などを置き換えないよう最後に入れる
    head = '<!doctype html>\n<html lang="ja">\n<head>\n<meta charset="utf-8">\n' \
           '<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">\n'
    i = out.index("<style>")
    return head + out[:i] + out[i:].replace("<div class=\"wrap\">", "</head>\n<body>\n<div class=\"wrap\">", 1) \
        + "</body>\n</html>\n"


def out_path(theme, view):
    return os.path.join(OUT_DIR, f"{theme}-{view_name(theme, view)}.html")


def main(argv):
    if len(argv) != 3:
        print("使い方: python3 -B tools/build_pages.py <theme> <見方のキー>（node・plan・fa・dist・org・waku のキーか、テーマの id）",
              file=sys.stderr)
        return 1
    theme, view = argv[1], argv[2]
    src = os.path.join(THEME_DIR, f"{theme}.json")
    try:
        if not os.path.exists(src):
            raise PageError(f"{os.path.relpath(src, ROOT)} が無い（先に tools/build_theme.py {theme} を動かす）")
        path = out_path(theme, view)
        with open(TEMPLATE, encoding="utf-8") as f:
            template = f.read()
        with open(src, "rb") as f:
            data_bytes = f.read()
        doc = render(template, data_bytes, view)
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
