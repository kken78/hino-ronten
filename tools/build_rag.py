"""持ち込み用の資料 build/rag/<theme>-<事業の番号>-honpen・-kiroku（.md と .docx）と -prompt.md を作る
（LINK_SCHEMA.md §17、DESIGN.md ADR-26）。

build/theme/<theme>.json（tools/build_theme.py が作る。§13）だけを読み、lock の版の入力は読まない。
標準ライブラリだけで作る（DOCX は zipfile と XML で書く）。同じデータからは同じファイルができる。

実行: python3 -B tools/build_rag.py <theme> <node キー>（例 hoiku node:jisshi/e008）
終了コード：0 は作った。1 は止めた（理由を表示する）。
"""
import hashlib
import json
import os
import re
import sys
import zipfile
from xml.sax.saxutils import escape

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import records  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
THEME_DIR = os.path.join(ROOT, "build", "theme")
OUT_DIR = os.path.join(ROOT, "build", "rag")
PROMPT = os.path.join(ROOT, "prompts", "shisaku1-common-v2.md")
RE_NODE = re.compile(r"node:([a-z0-9_-]+)/(e[0-9]+)")
RE_DATE = re.compile(r"([0-9]{4})-([0-9]{2})(?:-([0-9]{2}))?")
CONFIRMED = "確定"
NONE = "町の資料に記載なし"
# 表示の言葉（LINK_SCHEMA §16.3）
KIND = {"留保": "今後検討", "考えていない": "予定なし", "事実・数字": "事実・数値", "方針・考え": "方針・考え方",
        "数字・見込み": "数値・見込み", "提案への考え": "提案への見解"}
STAGE = {"投入": "投入（予算・人員）", "結果": "結果（施設・定員等）"}
ASPECT = {"種類": "種別", "状態": "状況"}
CATEGORY = {"koho": "広報ひの", "shingi": "懇話会・審議会", "jigyo": "事業資料", "yosan": "予算", "kessan": "決算",
            "kofukin": "交付金", "bosai": "防災"}
LEDGER_NAMES = [("kotogara", "事柄"), ("shisetsu", "施設"), ("yaritori", "やりとり（一般質問）"), ("shitsugi", "質疑（議案）"),
                ("tsunagari", "つながり"), ("katei", "過程"), ("kisai", "構造にしていない記載")]
ZIP_TIME = (1980, 1, 1, 0, 0, 0)
UNASKED = "問われていない点"
KISAI_NONE = "（記載の名前なし）"


class RagError(ValueError):
    pass


def jd(s):
    m = RE_DATE.fullmatch(s or "")
    if not m:
        return s or "日付不明"
    return f"{m.group(1)}年{int(m.group(2))}月" + (f"{int(m.group(3))}日" if m.group(3) else "")


def fy_name(y):
    return f"令和{'元' if y == 2019 else y - 2018}年度" if y >= 2019 else f"{y}年度"


def fiscal_year(d):
    y, m = int(d[:4]), int(d[5:7])
    return y if m >= 4 else y - 1


class Doc:
    """Markdown の行を積む。DOCX も同じ行から作る。"""

    def __init__(self):
        self.lines = []

    def h(self, level, text):
        self.lines += [f"{'#' * level} {text}", ""]

    def p(self, text):
        self.lines += [text, ""]

    def li(self, text):
        self.lines.append(f"- {text}")

    def end_list(self):
        self.lines.append("")

    def markdown(self):
        out = "\n".join(self.lines).rstrip("\n") + "\n"
        return re.sub(r"\n{3,}", "\n\n", out)


class Rag:
    def __init__(self, data, data_bytes, program):
        self.d = data
        self.R = data["records"]
        self.names = (data.get("names") or {}).get("sources") or {}
        self.fac = (data.get("names") or {}).get("facilities") or {}
        self.prog = next((p for p in data.get("programs") or [] if p.get("key") == program), None)
        if self.prog is None:
            raise RagError(f"テーマ {data.get('theme')} の programs に {program} が無い")
        self.sheet = next((s for s in data.get("sheets") or [] if s.get("program") == program), None)
        if self.sheet is None:
            raise RagError(f"テーマ {data.get('theme')} の sheets に {program} が無い")
        for k in ("names", "theme_questions"):
            if k not in data:
                raise RagError(f"テーマのノートのデータに {k} が無い（tools/build_theme.py で作り直す）")
        self.sha = hashlib.sha256(data_bytes).hexdigest()
        self.pname = self.prog["name"]
        self.bud = next((b for b in data.get("budget") or [] if b.get("program") == program), None)
        self.pol = next((p for p in data.get("policies") or [] if p.get("kind") == "基本施策"), None)
        self.kot = {}
        for r in self.R.get("kotogara") or []:
            if r.get("program") in (program, ""):
                self.kot.setdefault(r["point"], []).append(r)
        for rows in self.kot.values():
            rows.sort(key=lambda r: (r["source_date"], r["source"]))

    # ---- 共通 ----
    def name(self, key):
        return self.names.get(key, key)

    def entry(self, date, source, quote, url, fields=(), layer=CONFIRMED):
        """記載1つの段落：［資料の日付］資料の名前：欄：値。「引用」（出典：url）（LINK_SCHEMA §17.1）。"""
        head = "【未確認】" if layer != CONFIRMED else ""
        f = "".join(f"{k}：{v}。" for k, v in fields if v)
        q = f"「{quote}」" if quote else ""
        return f"{head}［{jd(date)}］{source}：{f}{q}（出典：{url or '出典なし'}）"

    def latest_date(self):
        ds = []
        for n, rows in self.R.items():
            for x in rows:
                if n in ("yaritori", "shitsugi"):
                    ds.append(x.get("date") or "")
                else:
                    ds += [x.get("source_date") or "", x.get("from") or "", x.get("to") or ""]
        ds += [x.get("date", "") for x in self.d.get("exchanges") or []]
        ds += [x.get("date", "") for x in self.d.get("docs") or [] if x.get("date")]
        return max(d for d in ds if d)

    def guide(self, doc, part):
        other = "記録編（…-kiroku）" if part == "本編" else "本編（…-honpen）"
        lock = "、".join(f"{r} {s[:7]}" for r, s in sorted((self.d.get("lock") or {}).items()))
        doc.h(1, f"{self.pname}（{part}）：この資料の読み方")
        doc.li(f"日野町の公開資料から、{self.pname}（テーマ「{self.d.get('name', '')}」）にかかわる記載を抜き出し、出典付きで整理した{part}です。あわせて{other}を使ってください")
        doc.li(f"作ったデータ：build/theme/{self.d.get('theme')}.json（sha256 {self.sha[:12]}）。入力の版：{lock}")
        doc.li(f"取り込んだ資料のうち、いちばん新しい記載の資料の日付は {jd(self.latest_date())} です。それより後の資料は入っていません")
        doc.li("記載は1つごとに1段落で、「［資料の日付］資料の名前：欄：値。「引用」（出典：url）」の形で書いています。引用は資料の文を原文のまま写したものです")
        doc.li("「【未確認】」の段落と「照合結果（未確認）」の節は、機械による照合の結果か、人による確認が済んでいない記録です")
        doc.li("評価や判断は加えていません。議員ごとの件数や順位は示していません")
        doc.end_list()

    # ---- 本編 ----
    def ordered_points(self):
        def doc_date(p):
            ds = [r["source_date"] for r in self.kot[p] if not r["source"].startswith("sp:")]
            return max(ds) if ds else ""

        def key(p):
            d = doc_date(p)
            return (0 if d else 1, "".join(chr(0x10FFFF - ord(c)) for c in d), -len(self.kot[p]), p)
        prog = sorted({p for p, rows in self.kot.items() if any(r.get("program") for r in rows)}, key=key)
        theme = sorted({p for p, rows in self.kot.items() if not any(r.get("program") for r in rows)}, key=key)
        return prog + theme

    def latest(self, p):
        base = [r for r in self.kot[p] if not r["source"].startswith("sp:")]
        if not base:
            return None
        d = base[-1]["source_date"]
        last = [r for r in base if r["source_date"] == d]
        for r in last:
            if (r.get("value") or r.get("target")) and r.get("kind") != "変更":
                return r
        for r in last:
            if r.get("value") or r.get("target"):
                return r
        return last[-1]

    def kot_entry(self, r):
        kind = "会議録" if r["source"].startswith("sp:") else "町の資料"
        return self.entry(r["source_date"], self.name(r["source"]), r["quote"], r.get("url"),
                          [("資料の種類", kind), ("値", r.get("value")), ("対象の時期", r.get("target")),
                           ("書き方", r.get("kind")), ("変更前", r.get("prev"))], r.get("layer"))

    def honpen(self):
        doc, P, d = Doc(), self.prog, self.d
        self.guide(doc, "本編")
        doc.h(1, f"{self.pname}（本編）：1 事業の要点")
        yrs = [int(str(y).lstrip("R")) for y in P.get("years") or [] if str(y).lstrip("R").isdigit()]
        doc.p(self.entry("", "実施計画", P.get("desc"), P.get("source"),
                         [("事業名", self.pname), ("分野", f"{P.get('field_no', '')} {P.get('field_name', '')}".strip())]).replace("［日付不明］", ""))
        if P.get("cost"):
            c = P["cost"]
            span = f"令和{yrs[0]}〜{yrs[-1]}年度" if yrs else ""
            doc.p(f"実施計画：{c.get('label')}（{span}）：{c.get('amount'):,}{c.get('unit')}（出典：{P.get('source')}）")
        if self.bud:
            b = self.bud
            fy = (re.match(r"fh:fuhyo-r(\d+)/", b["key"]) or [None, ""])[1]
            doc.p(f"令和{fy}年度当初予算の附表：{b.get('name')}：当初予算額 {b.get('amount'):,}{b.get('unit')}。区分：{'・'.join(b.get('kubun') or []) or 'なし'}。担当課：{'・'.join(b.get('dept') or [])}（出典：{b.get('url')}）")
        if self.pol:
            doc.p(f"総合計画：{P.get('field_no')} {P.get('field_name')}／基本施策{self.pol.get('no')} {self.pol.get('name')}（出典：{self.pol.get('source') or self.pol.get('url')}）")

        doc.h(1, f"{self.pname}（本編）：2 概要")
        doc.h(2, f"{self.pname}：主な事項")
        for p in self.ordered_points():
            c = self.latest(p)
            doc.h(3, f"{self.pname}：主な事項：{p}")
            if c:
                v = c.get("value") or c.get("target") or ""
                doc.p(f"町の資料の最新の記載（{jd(c['source_date'])}、{self.name(c['source'])}）：{v}{'（予定）' if v and c.get('kind') == '予定' else ''}（出典：{c.get('url')}）")
                chg = [r for r in self.kot[p] if r.get("kind") == "変更"]
                for r in chg:
                    doc.p(f"当初：{r.get('prev')}　→　{jd(r['source_date'])}に変更。変更理由：「{r.get('reason')}」（出典：{r.get('url')}）" if r.get("reason")
                          else f"当初：{r.get('prev')}　→　{jd(r['source_date'])}に変更（出典：{r.get('url')}）")
            else:
                doc.p(f"{NONE}。会議録の発言を日付順に示します。")
            doc.p("記載の推移（日付順）：")
            for r in self.kot[p]:
                doc.li(self.kot_entry(r))
            doc.end_list()

        doc.h(2, f"{self.pname}：経過")
        doc.p("検討の段階、議決、一般質問、予定の変更を日付順に示します。")
        ev = []
        for k in self.R.get("katei") or []:
            span = f"{jd(k.get('from'))}〜{jd(k.get('to'))}" if k.get("to") and k.get("to") != k.get("from") else (f"{jd(k.get('from'))}〜（継続中）" if k.get("from") and not k.get("to") else jd(k.get("from")))
            ev.append((k.get("from") or "", self.entry(k.get("from") or "", "検討の段階", k.get("quote"), k.get("url"),
                                                      [("段階", k.get("name")), ("期間", span)], k.get("layer"))))
        for b in d.get("bills") or []:
            ev.append((b["date"], f"［{jd(b['date'])}］議決：{b.get('meeting')}の{b.get('no')} {b.get('title')}。議決結果：{b.get('result')}。採決方法：{b.get('method')}（出典：{b.get('url')}）"))
        for x in d.get("exchanges") or []:
            ev.append((x["date"], self.exchange_line(x)))
        for r in self.R.get("kotogara") or []:
            if r.get("kind") == "変更" and r.get("program") in (P["key"], ""):
                ev.append((r["source_date"], self.entry(r["source_date"], self.name(r["source"]), r["quote"], r.get("url"),
                                                        [("予定の変更", r["point"]), ("変更前", r.get("prev")), ("変更後", r.get("target"))], r.get("layer"))))
        for _, t in sorted(ev, key=lambda e: (e[0] == "", e[0], e[1])):
            doc.li(t)
        doc.end_list()

        doc.h(2, f"{self.pname}：施設の再編")
        fs = {}
        for r in self.R.get("shisetsu") or []:
            fs.setdefault(r["facility"], []).append(r)
        for fk in sorted(fs, key=lambda k: (-len(fs[k]), k)):
            f = self.fac.get(fk) or {}
            doc.h(3, f"{self.pname}：施設の再編：{f.get('name') or fk}{'（' + f['district'] + '地区）' if f.get('district') else ''}")
            for r in sorted(fs[fk], key=lambda r: (r["source_date"], r["source"])):
                doc.li(self.shisetsu_entry(r))
            doc.end_list()

        doc.h(2, f"{self.pname}：資料と関連計画")
        for x in sorted(d.get("docs") or [], key=lambda x: (x.get("date") or x.get("fiscal_year") or ""), reverse=True):
            doc.li(f"［{jd(x['date']) if x.get('date') else (x.get('fiscal_year') or '') + '年度'}］{CATEGORY.get(x.get('category'), x.get('category'))}：{x.get('title')}（出典：{x.get('url')}）")
        for x in d.get("plans") or []:
            doc.li(f"関連計画：{x.get('name')}（計画期間 {x.get('start_fy')}〜{x.get('end_fy')}年度{'、' + x['posted'] if x.get('posted') else ''}）（出典：{x.get('url')}）")
        doc.end_list()

        doc.h(1, f"{self.pname}（本編）：3 論点整理")
        doc.h(2, f"{self.pname}：事項ごとの質問・答弁")
        qa = {}
        for n in ("yaritori", "shitsugi"):
            for q in self.R.get(n) or []:
                for r in q["rows"]:
                    if r.get("point"):
                        qa.setdefault(r["point"], []).append((n, q, r))
        rq = len(self.R.get("yaritori") or [])
        doc.p(f"質問・答弁を項目ごとに記録したのは、関連する一般質問{d.get('theme_questions')}問のうち{rq}問と、議案質疑{len(self.R.get('shitsugi') or [])}件です。")
        for p in sorted(qa, key=lambda p: (-len(qa[p]), p)):
            doc.h(3, f"{self.pname}：事項ごとの質問・答弁：{p}")
            rows = [(q["date"], self.qa_entry(n, q, r)) for n, q, r in qa[p]]
            rows += [(r["source_date"], self.kot_entry(r)) for r in self.kot.get(p, []) if not r["source"].startswith("sp:")]
            for _, t in sorted(rows, key=lambda e: (e[0], e[1])):
                doc.li(t)
            doc.end_list()

        doc.h(2, f"{self.pname}：照合結果（未確認）")
        doc.p("資料を機械的に照合した結果で、人による確認は済んでいません。比べ方ごとに、照合の文と、比べた記載を示します。")
        types = []
        for x in d.get("issues") or []:
            if x["type"] not in types:
                types.append(x["type"])
        for t in types:
            doc.h(3, f"{self.pname}：照合結果（未確認）：{t}")
            for x in d["issues"]:
                if x["type"] != t:
                    continue
                doc.p(f"【未確認】{x['statement']}")
                refs = x.get("refs") or []
                if t == UNASKED:
                    where, refs = self.kiroku_sections(refs)
                    if where:
                        doc.p(f"比べた記載：記録編の{'、'.join(f'「{k}」に{v}件' for k, v in where)}")
                for r in refs:
                    doc.li("比べた記載：" + self.ref_entry(r))
                doc.end_list()

        doc.h(2, f"{self.pname}：一般質問と議案")
        doc.p("関連する一般質問（日付順）：")
        for x in d.get("exchanges") or []:
            doc.li(self.exchange_line(x))
        doc.end_list()
        doc.p("関係議案と議決結果：")
        for b in d.get("bills") or []:
            deb = "・".join(f"{x.get('stance')}（{x['member'].get('name')} 議員）" for x in b.get("debates") or []) or "なし"
            doc.li(f"［{jd(b['date'])}］{b.get('meeting')}の{b.get('no')} {b.get('title')}。議決結果：{b.get('result')}。採決方法：{b.get('method')}。討論：{deb}（出典：{b.get('url')}）")
        doc.end_list()

        doc.h(1, f"{self.pname}（本編）：4 事業の運営")
        doc.h(2, f"{self.pname}：目的と手段の関係")
        doc.p("資料に記載された関係のみを示し、記載のない関係は加えていません。ロジックモデル（課題・投入・活動・結果・成果）への位置付けは、担当課が判断します。")
        for r in sorted(self.R.get("tsunagari") or [], key=lambda r: (r["link"], r["upper"], r["lower"], r["source_date"])):
            doc.li(self.tsunagari_entry(r))
        doc.end_list()
        doc.h(2, f"{self.pname}：総合計画のめざす姿と、計画に掲げる課題")
        for v in self.sheet.get("vision") or []:
            doc.li(f"総合計画のめざす姿：「{re.sub(r'^めざす姿:', '', v.get('text', ''))}」（出典：{v.get('source') or v.get('url')}）")
        for k in self.sheet.get("kadai") or []:
            plan = next((x["name"] for x in d.get("plans") or [] if k.get("ref", "").startswith(x["key"] + "/")), "計画")
            pg = re.search(r"p\.(\d+)(?:-(\d+))?", k.get("source") or "")
            where = f" {pg.group(1)}{'〜' + pg.group(2) if pg.group(2) else ''}ページ" if pg else ""
            doc.li(f"{plan}{where}に掲げる課題：「{k.get('text')}」（出典：{k.get('url')}）")
        doc.end_list()
        doc.h(2, f"{self.pname}：年度ごとの節目")
        years = {}

        def add(date, text):
            if date:
                years.setdefault(fiscal_year(date), []).append((date, text))
        for k in self.R.get("katei") or []:
            add(k.get("from"), f"検討の段階：{k.get('name')}（出典：{k.get('url')}）")
        for b in d.get("bills") or []:
            add(b["date"], f"議決：{b.get('meeting')}の{b.get('no')} {b.get('title')}（出典：{b.get('url')}）")
        for x in d.get("exchanges") or []:
            add(x["date"], f"一般質問：{x.get('meeting')}　質問者：{x['member'].get('name')} 議員（出典：{(x.get('turns') or [{}])[0].get('url')}）")
        for q in self.R.get("shitsugi") or []:
            add(q["date"], f"議案質疑：{q.get('meeting')}　質問者：{q['member'].get('name')} 議員（出典：{(q.get('rows') or [{}])[0].get('url')}）")
        for r in self.R.get("kotogara") or []:
            if r.get("kind") in ("予定", "変更") and r.get("program") in (P["key"], ""):
                add(r["source_date"], f"予定の記載：{r['point']}：{r.get('target') or r.get('value') or ''}{'（変更）' if r.get('kind') == '変更' else ''}（出典：{r.get('url')}）")
        for y in sorted(years):
            doc.h(3, f"{self.pname}：年度ごとの節目：{fy_name(y)}")
            for dt, t in sorted(years[y]):
                doc.li(f"［{jd(dt)}］{t}")
            doc.end_list()
        if self.bud:
            fy = (re.match(r"fh:fuhyo-r(\d+)/", self.bud["key"]) or [None, ""])[1]
            doc.p(f"令和{fy}年度の当初予算額は {self.bud.get('amount'):,}{self.bud.get('unit')}（出典：{self.bud.get('url')}）。それより前の年度の予算額は、まだ取り込んでいません。")
        return doc

    def ref_index(self):
        if not hasattr(self, "_refs"):
            self._refs = {}
            for n, rows in self.R.items():
                for x in rows:
                    if n in ("yaritori", "shitsugi"):
                        self._refs[f"records/{n}/{x['question']}"] = (n, x)
                        for row in x["rows"]:
                            self._refs[f"records/{n}/{x['question']}/{row['row']}"] = (n + "/row", (x, row))
                    elif n in records.KEYS:
                        self._refs[f"records/{n}/" + "/".join(str(x[c]) for c in records.KEYS[n])] = (n, x)
        return self._refs

    def kiroku_sections(self, refs):
        """比べ方「問われていない点」の比べた記載が、記録編のどの節にあるか（§17.1）。
        返り値：［(節の名前, 件数)］と、記録の行に当たらず、そのまま並べる比べた記載。"""
        where, rest = {}, []
        for r in refs:
            n, x = self.ref_index().get(r.get("ref"), (None, None))
            if n == "kotogara":
                k = f"事柄：{x['point']}"
            elif n == "kisai":
                k = f"構造にしていない記載：{x.get('about') or KISAI_NONE}"
            elif n == "shisetsu":
                k = f"施設：{(self.fac.get(x['facility']) or {}).get('name') or x['facility']}"
            elif n == "tsunagari":
                k = "つながり"
            elif n == "katei":
                k = "過程"
            else:
                rest.append(r)
                continue
            where[k] = where.get(k, 0) + 1
        return list(where.items()), rest

    def ref_entry(self, r):
        """照合結果の比べた記載。記録の行が分かれば、資料の日付と名前を添える。"""
        hit = self.ref_index().get(r.get("ref"))
        if hit is None:
            head = "【未確認】" if r.get("layer") != CONFIRMED else ""
            return f"{head}{r.get('text') or ''}（出典：{r.get('url')}）"
        n, x = hit
        if n.endswith("/row"):
            q, row = x
            return self.qa_entry(n.split("/")[0], q, row)
        if n in ("yaritori", "shitsugi"):
            kind = "一般質問" if n == "yaritori" else "議案質疑"
            return f"［{jd(x['date'])}］{x.get('meeting')}の{kind}　質問者：{x['member'].get('name')} 議員（出典：{r.get('url')}）"
        if n == "kotogara":
            return self.kot_entry(x)
        if n == "shisetsu":
            return self.shisetsu_entry(x)
        if n == "tsunagari":
            return self.tsunagari_entry(x)
        src = x.get("source") or (x.get("sources") or "").split(",")[0]
        return self.entry(x.get("source_date") or x.get("from") or "", self.name(src), x.get("quote"), r.get("url"), layer=x.get("layer"))

    def exchange_line(self, x):
        t = (x.get("titles") or [{}])[0].get("title", "")
        return (f"［{jd(x['date'])}］一般質問：{x.get('meeting')}　質問者：{x['member'].get('name')} 議員"
                f"{'　議会だよりの見出し「' + t + '」' if t else ''}（出典：{(x.get('turns') or [{}])[0].get('url')}）")

    def qa_entry(self, n, q, r):
        side = "質問" if r["side"] == "問い" else "答弁"
        who = f"{q['member'].get('name')} 議員" if r["side"] == "問い" else r.get("speaker")
        src = f"{q.get('meeting')}の{'一般質問' if n == 'yaritori' else '議案質疑'}"
        return self.entry(q["date"], src, r["quote"], r.get("url"),
                          [("発言", side), ("発言者", who), ("回", r.get("round")), ("区分", STAGE.get(r.get("stage"), r.get("stage")) if r["side"] == "問い" else ""),
                           ("種類", KIND.get(r.get("kind"), r.get("kind")))], r.get("layer"))

    def shisetsu_entry(self, r):
        return self.entry(r["source_date"], self.name(r["source"]), r["quote"], r.get("url"),
                          [("面", ASPECT.get(r.get("aspect"), r.get("aspect"))), ("値", r.get("value")), ("対象の時期", r.get("target")),
                           ("書き方", r.get("kind")), ("変更前", r.get("prev"))], r.get("layer"))

    def tsunagari_entry(self, r):
        return self.entry(r["source_date"], self.name(r["source"]), r["quote"], r.get("url"),
                          [("関係", r.get("link")), ("上位の記載", r.get("upper")), ("下位の記載", r.get("lower"))], r.get("layer"))

    # ---- 記録編 ----
    def kiroku(self):
        doc = Doc()
        self.guide(doc, "記録編")
        R = self.R
        for name, label in LEDGER_NAMES:
            doc.h(1, f"{self.pname}（記録編）：{label}")
            if name == "kotogara":
                for p in sorted(self.kot):
                    doc.h(2, f"{self.pname}：記録：事柄：{p}")
                    for r in self.kot[p]:
                        doc.li(self.kot_entry(r))
                    doc.end_list()
            elif name == "shisetsu":
                fs = {}
                for r in R.get("shisetsu") or []:
                    fs.setdefault(r["facility"], []).append(r)
                for fk in sorted(fs):
                    f = self.fac.get(fk) or {}
                    doc.h(2, f"{self.pname}：記録：施設：{f.get('name') or fk}")
                    for r in sorted(fs[fk], key=lambda r: (r["source_date"], r["source"])):
                        doc.li(self.shisetsu_entry(r))
                    doc.end_list()
            elif name in ("yaritori", "shitsugi"):
                for q in R.get(name) or []:
                    kind = "一般質問" if name == "yaritori" else "議案質疑"
                    doc.h(2, f"{self.pname}：記録：{kind}：{jd(q['date'])} {q.get('meeting')}　質問者：{q['member'].get('name')} 議員")
                    for r in sorted(q["rows"], key=lambda r: int(r["row"])):
                        doc.li(self.qa_entry(name, q, r) + (f"　点：{r['point']}" if r.get("point") else ""))
                    doc.end_list()
            elif name == "tsunagari":
                for r in sorted(R.get("tsunagari") or [], key=lambda r: (r["link"], r["upper"], r["lower"], r["source_date"])):
                    doc.li(self.tsunagari_entry(r))
                doc.end_list()
            elif name == "katei":
                for k in sorted(R.get("katei") or [], key=lambda k: int(k["step"])):
                    span = f"{jd(k.get('from'))}〜{jd(k.get('to'))}" if k.get("to") else jd(k.get("from"))
                    doc.li(self.entry(k.get("from") or "", "検討の段階", k.get("quote"), k.get("url"),
                                      [("段階", k.get("name")), ("期間", span)], k.get("layer")))
                doc.end_list()
            elif name == "kisai":
                by = {}
                for r in R.get("kisai") or []:
                    by.setdefault(r.get("about") or KISAI_NONE, []).append(r)
                for a in sorted(by):
                    doc.h(2, f"{self.pname}：記録：構造にしていない記載：{a}")
                    for r in sorted(by[a], key=lambda r: (r["source_date"], r["source"], r["title"])):
                        doc.li(self.entry(r["source_date"], self.name(r["source"]), r["quote"], r.get("url"),
                                          [("見出し", r.get("title"))], r.get("layer")))
                    doc.end_list()
        return doc


# ---- DOCX（標準ライブラリだけ） ----

CONTENT_TYPES = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                 '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                 '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                 '<Default Extension="xml" ContentType="application/xml"/>'
                 '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
                 '<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>'
                 '</Types>')
RELS = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
        '</Relationships>')
DOC_RELS = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
            '</Relationships>')
W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'


def styles_xml():
    def heading(n, size):
        return (f'<w:style w:type="paragraph" w:styleId="Heading{n}"><w:name w:val="heading {n}"/><w:basedOn w:val="Normal"/>'
                f'<w:next w:val="Normal"/><w:qFormat/><w:pPr><w:keepNext/><w:spacing w:before="240" w:after="120"/>'
                f'<w:outlineLvl w:val="{n - 1}"/></w:pPr><w:rPr><w:b/><w:sz w:val="{size}"/></w:rPr></w:style>')
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            f'<w:styles {W}><w:docDefaults><w:rPrDefault><w:rPr>'
            '<w:rFonts w:ascii="Yu Gothic" w:eastAsia="Yu Gothic" w:hAnsi="Yu Gothic"/><w:sz w:val="21"/><w:lang w:val="ja-JP" w:eastAsia="ja-JP"/>'
            '</w:rPr></w:rPrDefault></w:docDefaults>'
            '<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/><w:qFormat/>'
            '<w:pPr><w:spacing w:after="80"/></w:pPr></w:style>'
            + heading(1, 32) + heading(2, 28) + heading(3, 24) + heading(4, 22) + '</w:styles>')


def document_xml(markdown):
    ps = []
    for line in markdown.split("\n"):
        if not line.strip():
            continue
        m = re.match(r"(#{1,4}) (.*)", line)
        if m:
            style, text = f"Heading{len(m.group(1))}", m.group(2)
        elif line.startswith("- "):
            style, text = None, "・" + line[2:]
        else:
            style, text = None, line
        ppr = f'<w:pPr><w:pStyle w:val="{style}"/></w:pPr>' if style else ""
        ps.append(f'<w:p>{ppr}<w:r><w:t xml:space="preserve">{escape(text)}</w:t></w:r></w:p>')
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            f'<w:document {W}><w:body>{"".join(ps)}'
            '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="1418" w:right="1418" w:bottom="1418" w:left="1418" w:header="851" w:footer="992" w:gutter="0"/></w:sectPr>'
            '</w:body></w:document>')


def write_docx(path, markdown):
    parts = [("[Content_Types].xml", CONTENT_TYPES), ("_rels/.rels", RELS), ("word/_rels/document.xml.rels", DOC_RELS),
             ("word/styles.xml", styles_xml()), ("word/document.xml", document_xml(markdown))]
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for name, text in parts:
            info = zipfile.ZipInfo(name, date_time=ZIP_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            z.writestr(info, text.encode("utf-8"))


def prompt_text(path=PROMPT):
    with open(path, encoding="utf-8") as f:
        t = f.read()
    if "\n---\n" not in t:
        raise RagError(f"{os.path.relpath(path, ROOT)} に「---」の区切りが無い")
    return t.split("\n---\n", 1)[1].lstrip("\n")


def build(data_bytes, program):
    data = json.loads(data_bytes.decode("utf-8"))
    r = Rag(data, data_bytes, program)
    return r.honpen().markdown(), r.kiroku().markdown()


def main(argv):
    if len(argv) != 3:
        print("使い方: python3 -B tools/build_rag.py <theme> <node キー>", file=sys.stderr)
        return 1
    theme, program = argv[1], argv[2]
    src = os.path.join(THEME_DIR, f"{theme}.json")
    try:
        m = RE_NODE.fullmatch(program)
        if not m:
            raise RagError(f"node キーの形でない：{program}")
        if not os.path.exists(src):
            raise RagError(f"{os.path.relpath(src, ROOT)} が無い（先に tools/build_theme.py {theme} を動かす）")
        with open(src, "rb") as f:
            data_bytes = f.read()
        honpen, kiroku = build(data_bytes, program)
        prompt = prompt_text()
    except RagError as e:
        print(f"止めた：{e}", file=sys.stderr)
        return 1
    os.makedirs(OUT_DIR, exist_ok=True)
    base = os.path.join(OUT_DIR, f"{theme}-{m.group(2)}")
    outs = []
    for part, md in (("honpen", honpen), ("kiroku", kiroku)):
        with open(f"{base}-{part}.md", "w", encoding="utf-8", newline="\n") as f:
            f.write(md)
        write_docx(f"{base}-{part}.docx", md)
        outs += [f"{base}-{part}.md", f"{base}-{part}.docx"]
    with open(f"{base}-prompt.md", "w", encoding="utf-8", newline="\n") as f:
        f.write(prompt)
    outs.append(f"{base}-prompt.md")
    for p in outs:
        print(f"{os.path.relpath(p, ROOT)}：{os.path.getsize(p)} バイト")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
