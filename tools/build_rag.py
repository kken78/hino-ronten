"""持ち込み用の資料 build/rag/<theme>-<見方の名前>-honpen・-kiroku（.md と .docx）と -prompt.md を作る
（LINK_SCHEMA.md §17、DESIGN.md ADR-26・ADR-31）。

build/theme/<theme>.json（tools/build_theme.py が作る。§13）だけを読み、lock の版の入力は読まない。
標準ライブラリだけで作る（DOCX は zipfile と XML で書く。圧縮しない）。同じデータからは、どの環境でも同じファイルができる。

実行: python3 -B tools/build_rag.py <theme> <見方のキー>（例 hoiku node:jisshi/e008）
見方のキーは node・plan・fa・dist・org・waku（枠の要素）のキーか、テーマの id（テーマ全体）。見方の名前は tools/build_pages.py と同じ（§16）。
枠組みの表・資料の種類と根拠法令・記載の行の事項の所への出し方・項目（列 suji）の段落は LINK_SCHEMA §17.1〜§17.3（DESIGN.md ADR-37）。
項目の段落は、本編の年度ごとの節目の枠組みの流れか、資料の種類の節に置く（記録編の章「同じ項目の記載」は置かない。ADR-37 の経過、2026-11-14）。
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
import build_pages  # noqa: E402
import records  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
THEME_DIR = os.path.join(ROOT, "build", "theme")
OUT_DIR = os.path.join(ROOT, "build", "rag")
PROMPT = os.path.join(ROOT, "prompts", "shisaku1-common-v2.md")
RE_DATE = re.compile(r"([0-9]{4})-([0-9]{2})(?:-([0-9]{2}))?")
RE_YM = re.compile(r"(令和|平成)?(元|[0-9]+)年([0-9]{1,2})月")
ERA = {"令和": 2018, "平成": 1988}
CONFIRMED = "確定"
NONE = "町の資料に記載なし"
NOREC = "未記録"
PROGRAM = "事業"
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
KOHO = "doc:koho-"


class RagError(ValueError):
    pass


def jd(s):
    m = RE_DATE.fullmatch(s or "")
    if not m:
        return s or "日付不明"
    return f"{m.group(1)}年{int(m.group(2))}月" + (f"{int(m.group(3))}日" if m.group(3) else "")


def fy_name(y):
    return f"令和{'元' if y == 2019 else y - 2018}年度" if y >= 2019 else f"{y}年度"


def posted_date(posted):
    """計画の meta の posted の文のうち、最後に出る年月（YYYY-MM）。無ければ空（LINK_SCHEMA §17.1）。"""
    ms = list(RE_YM.finditer(posted or ""))
    if not ms:
        return ""
    era, y, mo = ms[-1].groups()
    y = 1 if y == "元" else int(y)
    return f"{y + ERA[era] if era else y:04d}-{int(mo):02d}"


def fiscal_year(d):
    y, m = int(d[:4]), int(d[5:7])
    return y if m >= 4 else y - 1


NOT_CHECKED = "どの問いに当たるかは確かめていない"
ARCHIVE_NOTE = "出典の url のうち web.archive.org のものは、町のサイトに載らなくなった資料の、Webアーカイブの保存版です"


def cycle_of(k):
    """過程の記録の期（LINK_SCHEMA §15.5、DESIGN.md ADR-30）。期の無い行は空。"""
    return f"期：{k['cycle']}。" if k.get("cycle") else ""


def bulletin_titles(x):
    """一般質問の議会だよりの見出しの部分（LINK_SCHEMA §17.1、DESIGN.md ADR-28）。見出しが無ければ空。"""
    ts = x.get("titles") or []
    if not ts:
        return ""
    body = "、".join(f"問{t.get('n')}「{t.get('title')}」" for t in ts)
    return f"　議会だよりの見出し{'' if x.get('titles_chosen') or len(ts) == 1 else '（' + NOT_CHECKED + '）'}：{body}"


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


def kot_ref(r):
    """事柄の記録の行の参照（LINK_SCHEMA §13.1。行のキーは (point, source, quote)）。"""
    return "records/kotogara/" + "/".join(str(r[c]) for c in records.KEYS["kotogara"])


def kis_ref(r):
    """構造にしていない記載の行の参照（行のキーは (title, source)）。"""
    return "records/kisai/" + "/".join(str(r[c]) for c in records.KEYS["kisai"])


# LINK_SCHEMA §16.4 の決まった文（DESIGN.md ADR-37 の経過、2026-11-14 の2つめ）
NO_SHURUI = "資料は、まだ記録していません。"
NO_BILL = "この年度の決算の議案は、まだ記録していません。"
NO_PROPOSAL = "提案の説明は、まだ記録していません。"
NO_STEPS = "質疑・委員長の報告・討論は、まだ記録していません。"
RE_LAW_ARTICLE = re.compile(r"([^\s（）、・0-9]+?(?:法律|法))(?:（[^）]*）)?第?([0-9]+)条")


def law_article(text):
    """法令の条項の字（ref/waku.tsv の source、ref/shiryo.tsv の konkyo）の最初の条項 →「地方自治法233条」。取れなければ空
    （LINK_SCHEMA §16.4。2026-11-14 の3つめ）。"""
    m = RE_LAW_ARTICLE.match(text or "")
    return f"{m.group(1)}{m.group(2)}条" if m else ""


def flow_lead(w):
    """年度ごとの節目の<枠組みの名前>の頭の最初の文（LINK_SCHEMA §16.4）。"""
    la = law_article(w.get("source"))
    return f"{la}の手続きの順に、資料と議案を示します。" if la else f"{w.get('name')}の要素の順に、資料と議案を示します。"


def section_lead(sh_row, shurui, flows):
    """<資料の種類>の節の頭の文（LINK_SCHEMA §16.4）。konkyo から法令の条が取れなければ最初の文を書かない。"""
    la = law_article((sh_row or {}).get("konkyo"))
    return (f"{la}による{shurui}です。" if la else "") + (f"{'・'.join(w['name'] for w in flows)}とは別のものです。" if flows else "")
NO_IINKAI = "委員会の会議録はありません。"
WAKU_NOTE = ("要素の名前は出典の語のままです。要素間の関係は、出典の図をご覧ください。"
             "「資料別の記載年」は資料の日付の年で、未確認の記録を含みます。"
             "「議会での質問・答弁の記録数」は、その事項について記録した一般質問・議案質疑の、確定した行の数です。")


class Rag:
    def __init__(self, data, data_bytes, view):
        self.d = data
        self.R = data["records"]
        self.view = view
        self.names = (data.get("names") or {}).get("sources") or {}
        self.fac = (data.get("names") or {}).get("facilities") or {}
        self.vnames = (data.get("names") or {}).get("views") or {}   # 見方のキーごとの名前（§13.3 names.views）
        for k in ("names", "theme_questions", "chushin"):
            if k not in data:
                raise RagError(f"テーマのノートのデータに {k} が無い（tools/build_theme.py で作り直す）")
        self.sheet = next((s for s in data.get("sheets") or [] if s.get("view") == view), None)
        if self.sheet is None:
            raise RagError(f"テーマ {data.get('theme')} の sheets に見方 {view} が無い")
        self.view_kind = self.sheet.get("view_kind", "")
        self.prog = None
        if self.view_kind == PROGRAM:
            self.prog = next((p for p in data.get("programs") or [] if p.get("key") == view), None)
            if self.prog is None:
                raise RagError(f"テーマ {data.get('theme')} の programs に {view} が無い")
        self.sha = hashlib.sha256(data_bytes).hexdigest()
        self.pname = self.sheet.get("name") or view
        self.bud = next((b for b in data.get("budget") or [] if b.get("program") == view), None) if self.prog else None
        pkey = (self.prog or {}).get("policy")
        self.pol = next((p for p in data.get("policies") or [] if pkey and p.get("key") == pkey), None)
        # 事柄の範囲（LINK_SCHEMA §16.2・§17.2）：その見方の事柄と、テーマ全体の事柄（テーマ以外のどの見方のシートにも無い点）
        refs = {x["ref"] for x in self.sheet.get("kotogara") or []}
        others = {x["ref"] for s in data.get("sheets") or [] if s.get("view_kind") != "テーマ" for x in s.get("kotogara") or []}
        rows = self.R.get("kotogara") or []
        self.view_points = {r["point"] for r in rows if kot_ref(r) in refs}
        other_points = {r["point"] for r in rows if kot_ref(r) in others}
        self.theme_points = {r["point"] for r in rows} - other_points - self.view_points
        self.kot, self.kot_all = {}, {}
        for r in rows:
            self.kot_all.setdefault(r["point"], []).append(r)     # 記録編はテーマの全行（§17.3）
            if self.in_scope(r):
                self.kot.setdefault(r["point"], []).append(r)
        for rows in list(self.kot.values()) + list(self.kot_all.values()):
            rows.sort(key=lambda r: (r["source_date"], r["source"]))
        # 会議録の発言の回：やりとりの記録の確定した行の round（LINK_SCHEMA §17.1）
        self.rounds = {}
        for q in self.R.get("yaritori") or []:
            for row in sorted(q["rows"], key=lambda r: int(r["row"])):
                if row.get("layer") == CONFIRMED and row.get("sid") and row.get("round"):
                    rs = self.rounds.setdefault(row["sid"], [])
                    if row["round"] not in rs:
                        rs.append(row["round"])
        self.doc_dates = {x.get("id"): x.get("date") or "" for x in data.get("docs") or [] if x.get("id")}
        # 筋（§13 の suji）と、about ごとの記載の行（点の所に出す。LINK_SCHEMA §17.2。DESIGN.md ADR-37）
        self.suji = {x["key"]: x for x in data.get("suji") or []}
        self.kis = {}
        for r in self.R.get("kisai") or []:
            if r.get("about"):
                self.kis.setdefault(r["about"], []).append(r)
        for rows in self.kis.values():
            rows.sort(key=lambda r: (r["source_date"], r["source"], r["title"]))
        # 項目の置き場所（LINK_SCHEMA §16.1・§17.2）：要素に資料の種類が当たる枠組みの年度ごとの要素か、<資料の種類>の節
        self.flows = [w for w in data.get("waku") or [] if w.get("nendo")]
        self.place = {}
        for w in self.flows:
            for y in w["nendo"]:
                for ye in y["elements"]:
                    e = next((z for z in w["elements"] if z["n"] == ye["n"]), {})
                    for x in ye["docs"]:
                        for k in x["suji"]:
                            self.place[k] = f"{w['name']}：{fy_name(int(y['fiscal_year']))}：要素{ye['n']} {e.get('name', '')}"
        self.sections = {}
        for x in data.get("suji") or []:
            if x["key"] not in self.place:
                sh = x.get("shurui") or self.kind_of(x["doc"])
                self.sections.setdefault(sh, []).append(x)
                self.place[x["key"]] = sh

    # ---- 共通 ----
    def in_scope(self, r):
        """事柄の記録の行が、この見方の本編に出る範囲か（その見方の事柄か、テーマ全体の事柄）。"""
        return r["point"] in self.view_points or r["point"] in self.theme_points

    def name(self, key):
        return self.names.get(key, key)

    def entry(self, date, source, quote, url, fields=(), layer=CONFIRMED):
        """記載1つの段落：［資料の日付］資料の名前：欄：値。「引用」（出典：url）（LINK_SCHEMA §17.1）。"""
        head = "【未確認】" if layer != CONFIRMED else ""
        f = "".join(f"{k}：{v}。" for k, v in fields if v)
        q = f"「{quote}」" if quote else ""
        return f"{head}［{jd(date)}］{source}：{f}{q}（出典：{url or '出典なし'}）"

    @staticmethod
    def kind_of(source):
        """記録の行の資料の種類：会議録の発言は「会議録」、広報ひのは「広報ひの」、ほかは「町の資料」（LINK_SCHEMA §17.1）。"""
        if (source or "").startswith("sp:"):
            return "会議録"
        if (source or "").startswith(KOHO):
            return "広報ひの"
        return "町の資料"

    def shurui_of(self, r, source):
        """記録の行の資料の種類：資料の種類の参照表に当たれば shurui、当たらなければ kind_of（LINK_SCHEMA §17.1。ADR-37 の5）。"""
        return r.get("shurui") or self.kind_of(source)

    def suji_text(self, r, ref):
        """欄「項目」：<資料の名前>の項目<n>（N件のうちK件目。suji:<資料の id>/<n>）。suji が無ければ空（LINK_SCHEMA §17.1）。"""
        x = self.suji.get(r.get("suji_key") or "")
        if not x:
            return ""
        k = next((i for i, y in enumerate(x["rows"], 1) if y["ref"] == ref), 0)
        return f"{self.suji_doc(x)}の項目{x['n']}（{len(x['rows'])}件のうち{k}件目。{x['key']}）"

    def suji_doc(self, x):
        """項目の資料の名前（項目の1つめの行の資料のキーから。§13 の names）。"""
        return self.name(x["rows"][0]["source"]) if x.get("rows") else x["doc"]

    def point_rows(self, p, docs_only=False):
        """事項の所の行：事柄の記録（この見方の範囲）と、about がその点の記載の行を資料の日付の順に（§17.2）。(日付, 段落)。"""
        out = [(r["source_date"], r["source"], self.kot_entry(r)) for r in self.kot.get(p, [])
               if not (docs_only and r["source"].startswith("sp:"))]
        out += [(r["source_date"], r["source"], self.kisai_entry(r)) for r in self.kis.get(p, [])]
        return [(d, t) for d, _, t in sorted(out, key=lambda e: (e[0], e[1]))]

    def waku_lines(self, doc):
        """枠組みの表と、資料の種類と根拠法令（LINK_SCHEMA §17.1・§17.2。表は使わない。要素の note は出さない）。"""
        for w in self.d.get("waku") or []:
            doc.h(2, f"{self.pname}：{w.get('name')}と、資料の記載状況")
            doc.p(f"枠組み：{w.get('name')}。出典：{self.name(w.get('source'))}（{w.get('source')}）（出典：{w.get('url')}）" if w.get("url")
                  else f"枠組み：{w.get('name')}。出典：{w.get('source')}")
            for e in w.get("elements") or []:
                rec = "・".join(f"{k}：{'・'.join(v)}" for k, v in (e.get("rec") or {}).items()) or NOREC
                pts = "、".join(e.get("points") or []) or "該当する事項なし"
                src = f"（{e['source']}）" if e.get("source") and e.get("source") != w.get("source") else ""
                doc.li(f"要素{e.get('n')}：{e.get('name')}{src}。該当する事項：{pts}。資料別の記載年：{rec}"
                       + (f"。議会での質問・答弁の記録数：{e.get('gikai')}" if e.get("points") else ""))
            doc.end_list()
            doc.p(WAKU_NOTE)
        sh = self.d.get("shiryo") or []
        if sh:
            doc.h(2, f"{self.pname}：資料の種類と根拠法令")
            for x in sh:
                doc.li(f"資料の種類：{x.get('shurui')}。作成者：{x.get('tsukuru')}。根拠法令：{x.get('konkyo')}。提出先・公表：{x.get('atesaki')}。"
                       f"対応状況を確認できる資料：{x.get('outou')}。出典：{x.get('source')}")
            doc.end_list()

    def round_of(self, source):
        """会議録の発言（sp）の回。やりとりの記録に無ければ「未記録」。sp でなければ空（LINK_SCHEMA §17.1）。"""
        if not (source or "").startswith("sp:"):
            return ""
        return "・".join(self.rounds.get(source) or []) or "未記録"

    def source_date(self, key):
        """資料のキーから分かる資料の日付：sp は発言の日、doc は町の公開資料の台帳の date。ほかは空（LINK_SCHEMA §17.1）。"""
        m = re.fullmatch(r"sp:[0-9]+_([0-9]{4})([0-9]{2})([0-9]{2})_[0-9]+", key or "")
        if m:
            return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
        m = records.RE_DOC_PAGE.fullmatch(key or "") or records.RE_DOC.fullmatch(key or "")
        if m:
            return self.doc_dates.get(m.group(1), "")
        return ""

    @staticmethod
    def katei_span(k):
        """過程の記録の期間（LINK_SCHEMA §17.1）。"""
        a, b = k.get("from"), k.get("to")
        if not a:
            return jd(a)
        if not b:
            return f"{jd(a)}〜（継続中）"
        return jd(a) if a == b else f"{jd(a)}〜{jd(b)}"

    def katei_entry(self, k):
        """過程の記録の段落：［ ］を付けず、期間と1つめの資料の名前（分かれば資料の日付）、その資料の種類と回を書く（LINK_SCHEMA §17.1）。"""
        head = "【未確認】" if k.get("layer") != CONFIRMED else ""
        src = (k.get("sources") or "").split(",")[0]
        sd = self.source_date(src)
        rd = self.round_of(src)
        q = f"「{k.get('quote')}」" if k.get("quote") else ""
        return (f"{head}検討の段階：{cycle_of(k)}段階：{k.get('name')}。期間：{self.katei_span(k)}。資料：{self.name(src)}"
                f"{'（' + jd(sd) + '）' if sd else ''}。資料の種類：{self.shurui_of(k, src)}。{'回：' + rd + '。' if rd else ''}"
                f"{q}（出典：{k.get('url') or '出典なし'}）")

    def policy_of(self, ref):
        key = (ref or "").split("/", 1)[1] if (ref or "").startswith("policies/") else ""
        return next((p for p in self.d.get("policies") or [] if key and p.get("key") == key), None)

    def vision_line(self, v):
        """総合計画のめざす姿。policies の posted から資料の日付を付ける（LINK_SCHEMA §17.1）。"""
        pd = posted_date((self.policy_of(v.get("ref")) or {}).get("posted"))
        return (f"{'［' + jd(pd) + '］' if pd else ''}総合計画のめざす姿：「{re.sub(r'^めざす姿:', '', v.get('text', ''))}」"
                f"（出典：{v.get('source') or v.get('url')}）")

    def kadai_line(self, k):
        """計画に掲げる課題：［資料の日付］計画の名前 ページに掲げる課題：「引用」（LINK_SCHEMA §17.1）。"""
        plan = next((x for x in self.d.get("plans") or [] if k.get("ref", "").startswith(x["key"] + "/")), None)
        pg = re.search(r"p\.(\d+)(?:-(\d+))?", k.get("source") or "")
        where = f" {pg.group(1)}{'〜' + pg.group(2) if pg.group(2) else ''}ページ" if pg else ""
        pd = posted_date((plan or {}).get("posted"))
        return (f"{'［' + jd(pd) + '］' if pd else ''}{(plan or {}).get('name') or '計画'}{where}に掲げる課題：「{k.get('text')}」"
                f"（出典：{k.get('url')}）")

    def none_text(self, p):
        """町の資料の行が無い事柄（LINK_SCHEMA §17.1）。"""
        n = sum(1 for r in self.kot_all.get(p) or [] if r["source"].startswith("sp:"))
        return f"{NONE}（会議録の発言 {n} 件）"

    def ref_date(self, r):
        """比べた記載の資料の日付。記録の行に当たらないものと、資料の日付の無い過程の記録は空。"""
        hit = self.ref_index().get(r.get("ref"))
        if hit is None:
            return ""
        n, x = hit
        if n.endswith("/row"):
            return x[0].get("date") or ""
        if n in ("yaritori", "shitsugi"):
            return x.get("date") or ""
        return x.get("source_date") or ""

    def issue_statement(self, x):
        """照合結果の文。問われていない点のほかは、比べた記載の出典を資料の日付の順に付ける（LINK_SCHEMA §17.1）。"""
        s = f"【未確認】{x['statement']}"
        if x["type"] == UNASKED:
            return s
        refs = list(enumerate(x.get("refs") or []))
        dated = sorted(((self.ref_date(r), i, r) for i, r in refs if self.ref_date(r)), key=lambda t: (t[0], t[1]))
        undated = [(i, r) for i, r in refs if not self.ref_date(r)]
        urls = []
        for u in [r.get("url") for _, _, r in dated] + [r.get("url") for _, r in undated]:
            if u and u not in urls:
                urls.append(u)
        return s + (f"（比べた記載の出典：{'、'.join(urls)}）" if urls else "")

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
        doc.li("検討の段階（政策の過程）の記載は、資料の日付ではなく期間を書くため、［ ］を付けていません")
        doc.li("欄「資料の種類」は、会議録（会議録の発言）、広報ひの、町の資料（広報ひののほかの町の公開資料と計画）の別です。"
               "根拠法令を確認した資料（定期監査の報告・決算審査の意見書など）は、その種類の名前を書き、本編の節「資料の種類と根拠法令」に作成者・根拠法令などを書いています。"
               "会議録の発言の記載には、欄「回」（最初の問い・再質問1…。やりとりの記録に無いときは「未記録」）を書いています")
        doc.li("欄「記載の種類」の事実・見通し・評価・要望は、資料の作成者（監査委員など）が記した内容の種類です。"
               "評価・要望・見通しの区分は論点ノートによる評価ではありません")
        doc.li("欄「項目」は、その記載が資料のどの項目（監査委員の資料では意見の項目）の何件目の文かを示します。項目の全部の文は、本編の「年度ごとの節目」の枠組みの流れ（決算の認定までの流れなど）か、資料の種類の節（定期監査の報告など）に、項目ごとの段落で書いています。"
               "項目の段落では、文の前の［ ］が記載の種類、文の後ろの（事項：…）が対応づけた事項（論点）です。"
               "決算の認定までの流れでは、要素ごとに、要素に当たる資料の項目か、議案（提案の説明・質疑・委員長の報告・討論・議決）を書いています")
        doc.li("「【未確認】」の段落と「照合結果（未確認）」の節は、機械による照合の結果か、人による確認が済んでいない記録です")
        doc.li(ARCHIVE_NOTE)
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
        view = sorted((p for p in self.kot if p in self.view_points), key=key)
        theme = sorted((p for p in self.kot if p not in self.view_points), key=key)
        return view + theme

    def latest_all(self, p):
        """町の資料の最新の日付の行：value か target のある行を全部（変更でない行を先に、同じなら行の順）。
        無ければ最後の行だけ（LINK_SCHEMA §16.2・§14 topic）。"""
        base = [r for r in self.kot_all[p] if not r["source"].startswith("sp:")]
        if not base:
            return []
        d = base[-1]["source_date"]
        last = [r for r in base if r["source_date"] == d]
        v = [r for r in last if r.get("value") or r.get("target")]
        if not v:
            return [last[-1]]
        return [r for r in v if r.get("kind") != "変更"] + [r for r in v if r.get("kind") == "変更"]

    def latest(self, p):
        a = self.latest_all(p)
        return a[0] if a else None

    def latest_value(self, p):
        """最新の記載の値（複数の行は「／」でつなぐ。§16.2）。"""
        return "／".join(v for v in ((r.get("value") or r.get("target") or "") for r in self.latest_all(p)) if v)

    @staticmethod
    def katei_ordered(K):
        """過程の記録を step の順に並べ、from の無い段階に1つ前の段階の from を並べ替えのキーとして付ける（§16.2）。
        返すのは (キー, 行) の組。"""
        out, prev = [], ""
        for k in sorted(K, key=lambda k: int(k["step"])):
            key = k.get("from") or prev
            prev = key
            out.append((key, k))
        return out

    def kot_entry(self, r):
        return self.entry(r["source_date"], self.name(r["source"]), r["quote"], r.get("url"),
                          [("資料の種類", self.shurui_of(r, r["source"])), ("回", self.round_of(r["source"])), ("値", r.get("value")), ("対象の時期", r.get("target")),
                           ("書き方", r.get("kind")), ("変更前", r.get("prev")), ("項目", self.suji_text(r, kot_ref(r)))], r.get("layer"))

    def youten(self, doc):
        """本編の章1：見方の要点（LINK_SCHEMA §14 の overview・§17.2 の1）。どの段落も出典つき。"""
        P, d = self.prog, self.d
        if P:
            doc.h(1, f"{self.pname}（本編）：1 事業の要点")
            yrs = [int(str(y).lstrip("R")) for y in P.get("years") or [] if str(y).lstrip("R").isdigit()]
            pd = posted_date(P.get("posted"))
            doc.p(self.entry(pd, "実施計画", P.get("desc"), P.get("source"),
                             [("事業名", self.pname), ("分野", f"{P.get('field_no', '')} {P.get('field_name', '')}".strip())]).replace("［日付不明］", ""))
            if P.get("cost"):
                c = P["cost"]
                span = f"令和{yrs[0]}〜{yrs[-1]}年度" if yrs else ""
                doc.p(f"{'［' + jd(pd) + '］' if pd else ''}実施計画：{c.get('label')}（{span}）：{c.get('amount'):,}{c.get('unit')}（出典：{P.get('source')}）")
            if self.bud:
                b = self.bud
                fy = (re.match(r"fh:fuhyo-r(\d+)/", b["key"]) or [None, ""])[1]
                doc.p(f"令和{fy}年度当初予算の附表：{b.get('name')}：当初予算額 {b.get('amount'):,}{b.get('unit')}。区分：{'・'.join(b.get('kubun') or []) or 'なし'}。担当課：{'・'.join(b.get('dept') or [])}（出典：{b.get('url')}）")
            if self.pol:
                gd = posted_date(self.pol.get("posted"))
                doc.p(f"{'［' + jd(gd) + '］' if gd else ''}総合計画：{P.get('field_no')} {P.get('field_name')}／基本施策{self.pol.get('no')} {self.pol.get('name')}"
                      f"（出典：{self.pol.get('source') or self.pol.get('url')}）")
            return
        doc.h(1, f"{self.pname}（本編）：1 見方の要点")
        if self.view_kind == "期の計画":
            pl = next((x for x in d.get("plans") or [] if x.get("key") == self.view), {})
            pd = posted_date(pl.get("posted"))
            doc.p(f"{'［' + jd(pd) + '］' if pd else ''}計画：{pl.get('name')}。計画期間：{pl.get('start_fy')}〜{pl.get('end_fy')}年度"
                  f"{'。策定・改正：' + pl['posted'] if pl.get('posted') else ''}（出典：{pl.get('url')}）")
            for k in self.sheet.get("kadai") or []:
                doc.p(self.kadai_line(k))
        elif self.view_kind == "施設":
            f = self.fac.get(self.view) or {}
            states = sorted((r for r in self.R.get("shisetsu") or [] if r["facility"] == self.view and r.get("aspect") == "状態"),
                            key=lambda r: (r["source_date"], r["source"]))
            doc.p(f"施設：{f.get('name') or self.pname}。地区：{f.get('district') or NOREC}")   # 参照表の名前。出典の url は無い
            if states:
                doc.p("いまの状態：" + self.shisetsu_entry(states[-1]))
            else:
                doc.p(f"いまの状態：{NOREC}")
        elif self.view_kind == "地区":
            # 地区の名前と、その地区の施設の名前（names.views の施設のうち district がその地区の名前のもの。§14）
            fs = [v.get("name") or k for k, v in self.vnames.items()
                  if k.startswith("fa:") and v.get("district") and v.get("district") == self.pname]
            doc.p(f"地区：{self.pname}。施設：{'、'.join(fs) or NOREC}")   # 参照表の名前。出典の url は無い
        elif self.view_kind == "枠の要素":
            # 枠組みの名前・要素・該当する事項（§14・§16.1。ADR-37）。参照表の名前。出典は枠組みの図のページ
            w = next((x for x in d.get("waku") or [] if self.view.startswith(x["key"] + "/")), {})
            e = next((x for x in w.get("elements") or [] if x.get("view") == self.view), {})
            doc.p(f"枠組み：{w.get('name')}。要素{e.get('n')}：{e.get('name')}。該当する事項：{'、'.join(e.get('points') or []) or NOREC}（出典：{w.get('url')}）")
        elif self.view_kind == "組織":
            # 組織の名前と、ほかの表記（参照表の aliases。§14）
            al = (self.vnames.get(self.view) or {}).get("aliases") or []
            doc.p(f"組織：{self.pname}。ほかの表記：{'、'.join(al) or NOREC}")   # 参照表の名前。出典の url は無い
        else:
            plans = "、".join(f"{x.get('name')}（出典：{x.get('url')}）" for x in d.get("plans") or []) or NOREC
            ch = d.get("chushin") or ""
            sh = next((s for s in d.get("sheets") or [] if s.get("view") == ch and s.get("view_kind") != "テーマ"), None)
            doc.p(f"テーマ：{d.get('name')}")   # 参照表の名前。出典の url は無い
            doc.p(f"系列の計画：{plans}")
            doc.p(f"中心の見方：{(sh['name'] + '（' + ch + '）') if sh else (ch or NOREC)}")

    def doc_title(self, key, x=None):
        """資料の名前（docs の title。無ければ項目の最初の行の資料の名前）。"""
        did = key.split(":", 1)[1].split("/")[0] if key.startswith("doc:") else ""
        t = next((y.get("title") for y in self.d.get("docs") or [] if y.get("id") == did), "")
        return t or (self.name(x["rows"][0]["source"]) if x and x.get("rows") else key)

    def doc_url(self, key, x=None):
        did = key.split(":", 1)[1].split("/")[0] if key.startswith("doc:") else ""
        return next((y.get("url") for y in self.d.get("docs") or [] if y.get("id") == did), "") or (x or {}).get("url", "")

    def item_text(self, x):
        """項目の段落（LINK_SCHEMA §17.1）：［<資料の日付>］<資料の名前>の項目<n>（suji:…）：［<記載の種類>］「<文>」（事項：…）…（出典：url）。"""
        parts = []
        for b in x.get("bun") or []:
            pts = [(y["point"] + (f"（{y['kind']}）" if y["kind"] != b["kind"] else "")) for y in b["points"] if y.get("point")]
            parts.append(f"{'【未確認】' if b.get('layer') != CONFIRMED else ''}［{b['kind']}］「{b['quote']}」" + (f"（事項：{'、'.join(pts)}）" if pts else ""))
        date = min((r["source_date"] for r in x.get("rows") or []), default="")
        return f"［{jd(date)}］{self.doc_title(x['doc'], x)}の項目{x['n']}（{x['key']}）：{''.join(parts)}（出典：{self.doc_url(x['doc'], x)}）"

    @staticmethod
    def item_order(x):
        r = (x.get("rows") or [{}])[0]
        return (r.get("page", 0), r.get("pos", -1) < 0, r.get("pos", -1), x["n"])

    def flow_lines(self, doc):
        """年度ごとの節目の<枠組みの名前>（LINK_SCHEMA §16.1・§17.2）。資料の年度ごとに要素を番号の順に全部。"""
        for w in self.flows:
            for y in w["nendo"]:
                doc.h(3, f"{self.pname}：年度ごとの節目：{w['name']}（{fy_name(int(y['fiscal_year']))}）")
                doc.p(f"{flow_lead(w)}資料の記載は項目ごとの段落です。年度は資料の年度です。")
                gpos = [z["n"] for z in y["elements"] if "gian" in z]
                for ye in y["elements"]:
                    e = next((z for z in w["elements"] if z["n"] == ye["n"]), {})
                    head = f"要素{ye['n']}：{e.get('name', '')}" + (f"（{e['source']}）" if e.get("source") else "")
                    if "gian" in ye:
                        bills = [b for b in self.d.get("bills") or [] if b["key"] in ye["gian"]]
                        if not bills:
                            doc.p(f"{head}。{NO_BILL}")
                        for b in bills:
                            doc.p(f"{head}。")
                            for t in self.bill_lines(gpos.index(ye["n"]), b):
                                doc.li(t)
                            doc.end_list()
                        continue
                    if not ye["docs"]:
                        doc.p(f"{head}。{NOREC if e.get('shiryo') else NO_SHURUI}")
                        continue
                    for x in ye["docs"]:
                        doc.p(f"{head}。資料：{self.doc_title(x['doc'], self.suji.get((x['suji'] or [''])[0]))}（{jd(x['date'])}）")
                        for k in x["suji"]:
                            if k in self.suji:
                                doc.li(self.item_text(self.suji[k]))
                        doc.end_list()
                        if x.get("nosuji"):
                            doc.p(f"この資料には、ここに出していない記載が{x['nosuji']}件あります（事項の所に出ます）。")

    @staticmethod
    def bill_lines(pos, b):
        """議案を置く枠組みの要素の箇条（LINK_SCHEMA §16.1・§17.2）。pos は議案を置く要素の中の順（0 提出・1 審議・2 議決）。"""
        k = b.get("kessan") or {}
        giin = lambda m: f"{(m.get('seat') + ' ') if m.get('seat') else ''}{m.get('name')} 議員"
        if pos == 0:
            out = [f"議案：{b.get('meeting')}の{b.get('no')}「{b.get('title')}」（出典：{b.get('url')}）"]
            out += [f"［{jd(x['date'])}］提案の説明：{x.get('role')}（出典：{x.get('url')}）" for x in k.get("proposals") or []] or [NO_PROPOSAL]
            return out
        if pos == 1:
            out = []
            for x in k.get("steps") or []:
                if x["kind"] == "質疑":
                    out.append(f"［{jd(x['date'])}］質疑：{giin(x['member'])}（{x['nbills']}議案について）（出典：{x.get('url')}）")
                elif x["kind"] == "委員長の報告":
                    out.append(f"［{jd(x['date'])}］委員長の報告：{x.get('committee')}（{x['nbills']}議案について）（出典：{x.get('url')}）")
                else:
                    out.append(f"［{jd(x['date'])}］討論：{giin(x['member'])}" + (f"。賛否：{x['stance']}" if x.get("stance") else "")
                               + f"（出典：{x.get('url')}）")
            return (out or [NO_STEPS]) + [NO_IINKAI]
        return [f"議決：{b.get('result')}。採決の方法：{b.get('method')}。" + (f"採決の日付：{jd(k['vote_date'])}。" if k.get("vote_date") else "")
                + f"議決の会議：{k.get('decided_meeting') or b.get('meeting')}（出典：{b.get('url')}）"]

    def section_lines(self, doc):
        """<資料の種類>の節（LINK_SCHEMA §16.1・§17.2）：資料ごとに項目の段落。資料の並びは資料の日付の順。"""
        for sh, items in self.sections.items():
            doc.h(2, f"{self.pname}：{sh}")
            doc.p("資料ごとに、記録した項目を段落で示します。"
                  + section_lead(next((x for x in self.d.get("shiryo") or [] if x.get("shurui") == sh), None), sh, self.flows))
            by = {}
            for x in items:
                by.setdefault(x["doc"], []).append(x)
            dates = {k: min(r["source_date"] for x in v for r in x["rows"]) for k, v in by.items()}
            for k in sorted(by, key=lambda k: (dates[k], k)):
                doc.h(3, f"{self.pname}：{sh}：{self.doc_title(k, by[k][0])}（{jd(dates[k])}）")
                for x in sorted(by[k], key=self.item_order):
                    doc.li(self.item_text(x))
                doc.end_list()

    def honpen(self):
        doc, d = Doc(), self.d
        self.guide(doc, "本編")
        self.youten(doc)

        doc.h(1, f"{self.pname}（本編）：2 概要")
        doc.h(2, f"{self.pname}：主な事項")
        for p in self.ordered_points():
            c = self.latest(p)
            doc.h(3, f"{self.pname}：主な事項：{p}")
            if c:
                v = self.latest_value(p)
                doc.p(f"町の資料の最新の記載（{jd(c['source_date'])}、{self.name(c['source'])}）：{v}{'（予定）' if v and c.get('kind') == '予定' else ''}（出典：{c.get('url')}）")
                chg = [r for r in self.kot[p] if r.get("kind") == "変更"]
                for r in chg:
                    doc.p(f"当初：{r.get('prev')}　→　{jd(r['source_date'])}に変更。変更理由：「{r.get('reason')}」（出典：{r.get('url')}）" if r.get("reason")
                          else f"当初：{r.get('prev')}　→　{jd(r['source_date'])}に変更（出典：{r.get('url')}）")
            else:
                doc.p(f"{self.none_text(p)}。会議録の発言を日付順に示します。")
            doc.p("記載の推移（日付順）：")
            for _, t in self.point_rows(p):
                doc.li(t)
            doc.end_list()

        self.waku_lines(doc)

        doc.h(2, f"{self.pname}：経過")
        doc.p("検討の段階、議決、一般質問、予定の変更を日付順に示します。")
        ev = []
        # 過程の段階は step の順。from の無い段階は1つ前の段階の直後（§16.2）。並べ替えのキーに段階の番号を含める
        for i, (key, k) in enumerate(self.katei_ordered(self.R.get("katei") or [])):
            ev.append((key, f"{i:04d}" + self.katei_entry(k)))
        for b in d.get("bills") or []:
            ev.append((b["date"], f"［{jd(b['date'])}］議決：{b.get('meeting')}の{b.get('no')} {b.get('title')}。議決結果：{b.get('result')}。採決方法：{b.get('method')}（出典：{b.get('url')}）"))
        for x in d.get("exchanges") or []:
            ev.append((x["date"], self.exchange_line(x)))
        for r in self.R.get("kotogara") or []:
            if r.get("kind") == "変更" and self.in_scope(r):
                ev.append((r["source_date"], self.entry(r["source_date"], self.name(r["source"]), r["quote"], r.get("url"),
                                                        [("予定の変更", r["point"]), ("変更前", r.get("prev")), ("変更後", r.get("target"))], r.get("layer"))))
        for _, t in sorted(ev, key=lambda e: (e[0] == "", e[0], e[1])):
            doc.li(t[4:] if t[:4].isdigit() else t)
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
            doc.li(f"［{jd(x['date']) if x.get('date') else (x.get('fiscal_year') or '') + '年度'}］{CATEGORY.get(x.get('category'), x.get('category'))}：{x.get('title')}（出典：{x.get('url')}）"
                   + (f"。町のサイトに載らなくなったため、Webアーカイブの保存版（{jd(x['archived'])}保存）を示す。町の元の url：{x.get('original_url')}"
                      if x.get("archived") else ""))
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
            rows += self.point_rows(p, docs_only=True)
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
                doc.p(self.issue_statement(x))
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
            doc.li(self.vision_line(v))
        for k in self.sheet.get("kadai") or []:
            doc.li(self.kadai_line(k))
        doc.end_list()
        doc.h(2, f"{self.pname}：年度ごとの節目")
        years = {}

        def add(date, text, bracket=True):
            if date:
                years.setdefault(fiscal_year(date), []).append((date, text, bracket))
        for _, k in self.katei_ordered(self.R.get("katei") or []):
            # 過程の記録は資料の日付が無いので［ ］を付けない（LINK_SCHEMA §17.1）。from の無い段階は「年度不明」（§16.2）
            t = f"検討の段階：{cycle_of(k)}{k.get('name')}。期間：{self.katei_span(k)}（出典：{k.get('url')}）"
            if k.get("from"):
                add(k.get("from"), t, bracket=False)
            else:
                years.setdefault("nodate", []).append((f"{int(k['step']):04d}", t, False))     # 並びは step の順
        for b in d.get("bills") or []:
            add(b["date"], f"議決：{b.get('meeting')}の{b.get('no')} {b.get('title')}（出典：{b.get('url')}）")
        for x in d.get("exchanges") or []:
            add(x["date"], f"一般質問：{x.get('meeting')}　質問者：{x['member'].get('name')} 議員（出典：{(x.get('turns') or [{}])[0].get('url')}）")
        for q in self.R.get("shitsugi") or []:
            add(q["date"], f"議案質疑：{q.get('meeting')}　質問者：{q['member'].get('name')} 議員（出典：{(q.get('rows') or [{}])[0].get('url')}）")
        for r in self.R.get("kotogara") or []:
            if r.get("kind") in ("予定", "変更") and self.in_scope(r):
                add(r["source_date"], f"予定の記載：{r['point']}：{r.get('target') or r.get('value') or ''}{'（変更）' if r.get('kind') == '変更' else ''}（出典：{r.get('url')}）")
        for y in sorted(years, key=lambda y: (y == "nodate", y if y != "nodate" else 0)):
            doc.h(3, f"{self.pname}：年度ごとの節目：{'年度不明' if y == 'nodate' else fy_name(y)}")
            for dt, t, bracket in sorted(years[y]):
                doc.li(f"［{jd(dt)}］{t}" if bracket else t)
            doc.end_list()
        if self.bud:
            fy = (re.match(r"fh:fuhyo-r(\d+)/", self.bud["key"]) or [None, ""])[1]
            doc.p(f"令和{fy}年度の当初予算額は {self.bud.get('amount'):,}{self.bud.get('unit')}（出典：{self.bud.get('url')}）。それより前の年度の予算額は、まだ取り込んでいません。")
        self.flow_lines(doc)
        self.section_lines(doc)
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
        if n == "katei":
            return self.katei_entry(x)
        if n == "kisai":
            return self.kisai_entry(x)
        src = x.get("source") or (x.get("sources") or "").split(",")[0]
        return self.entry(x.get("source_date") or x.get("from") or "", self.name(src), x.get("quote"), r.get("url"), layer=x.get("layer"))

    def exchange_line(self, x):
        return (f"［{jd(x['date'])}］一般質問：{x.get('meeting')}　質問者：{x['member'].get('name')} 議員"
                f"{bulletin_titles(x)}（出典：{(x.get('turns') or [{}])[0].get('url')}）")

    def qa_entry(self, n, q, r):
        side = "質問" if r["side"] == "問い" else "答弁"
        who = f"{q['member'].get('name')} 議員" if r["side"] == "問い" else r.get("speaker")
        src = f"{q.get('meeting')}の{'一般質問' if n == 'yaritori' else '議案質疑'}"
        return self.entry(q["date"], src, r["quote"], r.get("url"),
                          [("発言", side), ("発言者", who), ("回", r.get("round")), ("区分", STAGE.get(r.get("stage"), r.get("stage")) if r["side"] == "問い" else ""),
                           ("種類", KIND.get(r.get("kind"), r.get("kind")))], r.get("layer"))

    def shisetsu_entry(self, r):
        return self.entry(r["source_date"], self.name(r["source"]), r["quote"], r.get("url"),
                          [("資料の種類", self.shurui_of(r, r["source"])), ("回", self.round_of(r["source"])), ("面", ASPECT.get(r.get("aspect"), r.get("aspect"))), ("値", r.get("value")), ("対象の時期", r.get("target")),
                           ("書き方", r.get("kind")), ("変更前", r.get("prev"))], r.get("layer"))

    def tsunagari_entry(self, r):
        return self.entry(r["source_date"], self.name(r["source"]), r["quote"], r.get("url"),
                          [("資料の種類", self.shurui_of(r, r["source"])), ("回", self.round_of(r["source"])), ("関係", r.get("link")), ("上位の記載", r.get("upper")),
                           ("下位の記載", r.get("lower"))], r.get("layer"))

    def kisai_entry(self, r):
        """構造にしていない記載の行。記載の種類（kind）と対象の時期（target）と項目は空なら書かない（LINK_SCHEMA §17.1。ADR-36・ADR-37）。"""
        return self.entry(r["source_date"], self.name(r["source"]), r["quote"], r.get("url"),
                          [("資料の種類", self.shurui_of(r, r["source"])), ("回", self.round_of(r["source"])), ("見出し", r.get("title")),
                           ("記載の種類", r.get("kind")), ("対象の時期", r.get("target")), ("項目", self.suji_text(r, kis_ref(r)))],
                          r.get("layer"))

    def suji_text_full(self, x):
        """MCP の fetch の suji:（LINK_SCHEMA §14）：項目の置き場所と、項目の段落。"""
        return f"置き場所：{self.place.get(x['key'], '')}\n{self.item_text(x)}"

    # ---- 記録編 ----
    def kiroku(self):
        doc = Doc()
        self.guide(doc, "記録編")
        R = self.R
        for name, label in LEDGER_NAMES:
            doc.h(1, f"{self.pname}（記録編）：{label}")
            if name == "kotogara":
                for p in sorted(self.kot_all):
                    doc.h(2, f"{self.pname}：記録：事柄：{p}")
                    for r in self.kot_all[p]:
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
                        doc.li(self.qa_entry(name, q, r) + (f"　事項：{r['point']}" if r.get("point") else ""))
                    doc.end_list()
            elif name == "tsunagari":
                for r in sorted(R.get("tsunagari") or [], key=lambda r: (r["link"], r["upper"], r["lower"], r["source_date"])):
                    doc.li(self.tsunagari_entry(r))
                doc.end_list()
            elif name == "katei":
                for k in sorted(R.get("katei") or [], key=lambda k: int(k["step"])):
                    doc.li(self.katei_entry(k))
                doc.end_list()
            elif name == "kisai":
                by = {}
                for r in R.get("kisai") or []:
                    by.setdefault(r.get("about") or KISAI_NONE, []).append(r)
                for a in sorted(by):
                    doc.h(2, f"{self.pname}：記録：構造にしていない記載：{a}")
                    for r in sorted(by[a], key=lambda r: (r["source_date"], r["source"], r["title"])):
                        doc.li(self.kisai_entry(r))
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
    # 圧縮しない。圧縮したバイト列は zlib の実装で変わり、PC とクラウドで sha256 が合わなくなるため
    with zipfile.ZipFile(path, "w", zipfile.ZIP_STORED) as z:
        for name, text in parts:
            info = zipfile.ZipInfo(name, date_time=ZIP_TIME)
            info.compress_type = zipfile.ZIP_STORED
            info.external_attr = 0o644 << 16
            z.writestr(info, text.encode("utf-8"))


def prompt_text(path=PROMPT):
    with open(path, encoding="utf-8") as f:
        t = f.read()
    if "\n---\n" not in t:
        raise RagError(f"{os.path.relpath(path, ROOT)} に「---」の区切りが無い")
    return t.split("\n---\n", 1)[1].lstrip("\n")


def build(data_bytes, view):
    data = json.loads(data_bytes.decode("utf-8"))
    r = Rag(data, data_bytes, view)
    return r.honpen().markdown(), r.kiroku().markdown()


def main(argv):
    if len(argv) != 3:
        print("使い方: python3 -B tools/build_rag.py <theme> <見方のキー>（node・plan・fa・dist・org・waku のキーか、テーマの id）",
              file=sys.stderr)
        return 1
    theme, view = argv[1], argv[2]
    src = os.path.join(THEME_DIR, f"{theme}.json")
    try:
        try:
            vname = build_pages.view_name(theme, view)
        except build_pages.PageError as e:
            raise RagError(str(e))
        if not os.path.exists(src):
            raise RagError(f"{os.path.relpath(src, ROOT)} が無い（先に tools/build_theme.py {theme} を動かす）")
        with open(src, "rb") as f:
            data_bytes = f.read()
        honpen, kiroku = build(data_bytes, view)
        prompt = prompt_text()
    except RagError as e:
        print(f"止めた：{e}", file=sys.stderr)
        return 1
    os.makedirs(OUT_DIR, exist_ok=True)
    base = os.path.join(OUT_DIR, f"{theme}-{vname}")
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
