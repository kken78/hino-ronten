"""記録の台帳（records/）・テーマの定義（ref/themes.tsv）・施設の参照表（ref/shisetsu.tsv）を確かめる関数
（LINK_SCHEMA.md §1・§2・§11・§12・§15、DESIGN.md ADR-19・ADR-21〜ADR-24）。

入力（lock の版の会議録・議会だより・計画・町の公開資料）は Inputs にまとめて渡す。読むのは tools/check_records.py。
台帳には書かない。誤りは Report.errors に、人が見る一覧は Report の各一覧に入れる。
"""
import io
import re
import unicodedata
from dataclasses import dataclass, field

import mention

STATUSES = ("candidate", "confirmed", "rejected")
COMMON = ["status", "reviewer", "date", "note"]

# §15 の各台帳の列（status・reviewer・date・note は最後に置く。§15.1）
COLUMNS = {
    "yaritori": ["question", "n", "row", "side", "sid", "quote", "speaker", "round", "stage", "kind", "answers",
                 "point", "bq", "bulletin"] + COMMON,
    "shitsugi": ["question", "n", "row", "bills", "side", "sid", "quote", "speaker", "round", "stage", "kind",
                 "answers", "point"] + COMMON,
    "kotogara": ["theme", "point", "program", "source", "source_date", "quote", "target", "kind", "prev", "reason",
                 "yaritori"] + COMMON,
    "tsunagari": ["theme", "link", "upper", "upper_ref", "lower", "lower_ref", "source", "source_date", "quote"] + COMMON,
    "katei": ["theme", "step", "name", "from", "to", "sources", "quote"] + COMMON,
    "kisai": ["theme", "title", "about", "source", "source_date", "quote"] + COMMON,
    "shisetsu": ["facility", "aspect", "value", "source", "source_date", "quote", "target", "kind", "prev"] + COMMON,
    "nozoki": ["question", "n", "sid", "quote", "reason"] + COMMON,
}
# 行のキー（§15 の各台帳）。row と step は数の順、ほかは文字コード順（§1）
KEYS = {
    "yaritori": ("question", "row"),
    "shitsugi": ("question", "row"),
    "kotogara": ("theme", "point", "source", "quote"),
    "tsunagari": ("theme", "link", "upper", "lower", "source"),
    "katei": ("theme", "step"),
    "kisai": ("theme", "title", "source"),
    "shisetsu": ("facility", "aspect", "source", "quote"),
    "nozoki": ("question", "n", "sid", "quote"),
}
NUMERIC = ("row", "step")
LEDGERS = tuple(COLUMNS)          # nozoki は無ければ0行（DESIGN.md ADR-24）
OPTIONAL = ("nozoki",)

THEME_COLUMNS = ["theme", "kind", "value", "source", "reviewer", "date", "note"]
THEME_KINDS = ("名前", "系列", "施策", "事業", "議案", "語", "除外の語", "問い", "資料", "質疑", "事柄", "記載", "施設")
SHISETSU_COLUMNS = ["key", "name", "aliases", "district", "source", "reviewer", "date", "note"]

SIDES = ("問い", "答え")
STAGES = ("課題", "投入", "活動", "手続き", "結果", "成果", "めざす姿")
Q_KINDS = ("事実の確認", "数字・見込み", "方針・考え", "提案への考え", "住民意見・手続き", "時期・手順", "要望", "その他")
A_KINDS = ("事実・数字", "方針・考え", "留保", "考えていない", "時期・手順", "その他")
BULLETIN = ("載っている", "載っていない", "言い回しが違う")
TIME_KINDS = ("済んだこと", "いまのこと", "予定", "変更")
LINKS = ("目的と手段", "もとにした")
ASPECTS = ("種類", "運営", "役割", "状態")
FIRST = "最初の問い"
ROUND = re.compile(r"最初の問い|再質問[1-9][0-9]*")
QUOTE_MAX = 200                   # 不変の制約9

SID = r"[0-9]{10}_[^\s/,:]+_[0-9]{4}"
RE_SP = re.compile(r"sp:" + SID)
RE_IQ = re.compile(r"iq:" + SID)
RE_SQ = re.compile(r"sq:" + SID)
RE_BQ = re.compile(r"bq:[0-9]+/[^/\s]+/[0-9]+")
RE_DOC_PAGE = re.compile(r"doc:([a-z0-9][a-z0-9-]*)/([1-9][0-9]*)")
RE_DOC = re.compile(r"doc:([a-z0-9][a-z0-9-]*)")
RE_PT_PAGE = re.compile(r"pt:([a-z0-9][a-z0-9-]*)/([A-Za-z0-9_.-]+)/([1-9][0-9]*)")
RE_GI = re.compile(r"gi:([0-9]{10})/([^/,\s]+)")
RE_NODE = re.compile(r"node:([a-z0-9][a-z0-9-]*)/([A-Za-z0-9_-]+)")
RE_PLAN = re.compile(r"plan:([a-z0-9][a-z0-9-]*)")
RE_PLAN_ITEM = re.compile(r"plan:([a-z0-9][a-z0-9-]*)/[A-Za-z0-9_-]+/[a-z_]+/[1-9][0-9]*/[1-9][0-9]*")
RE_FA = re.compile(r"fa:[a-z0-9][a-z0-9-]*")
RE_DAY = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
RE_MONTH = re.compile(r"[0-9]{4}-[0-9]{2}(-[0-9]{2})?")
RE_INT = re.compile(r"[1-9][0-9]*")

# 引用の前後（§11）：§4 の正規化のあとの頭の指示語。文の終わりの字
DEMONSTRATIVES = ("その", "この", "これ", "それ", "あの", "こうした", "そうした", "こういった", "そういった", "上記", "前述",
                  "同様", "先ほど", "さきほど", "今申し上げ", "以上")
# つなぎの言葉と、前の文を指さない時の語は、指示語として数えない（判定シート18 で、このまま とした語）
NOT_DEMONSTRATIVE = ("それと", "それから", "それぞれ", "それでは", "これまで", "これから", "このあと")
SENTENCE_END = "。？！?!"   # §4 の正規化（NFKC）のあとでは「？」「！」は「?」「!」になる

# 一覧の列
ROUND_DIFF_COLUMNS = ["ledger", "question", "n", "row", "sid", "round", "turns_round"]
QUOTE_MISMATCH_COLUMNS = ["ledger", "key", "status", "source", "quote"]
TORIKOBOSHI_COLUMNS = ["ledger", "question", "n", "sid", "quote"]
QUOTE_CONTEXT_COLUMNS = ["ledger", "key", "source", "kind", "quote"]


class RecordsError(ValueError):
    """台帳や参照表を読めない（形が §1 に合わない）。"""


@dataclass
class Inputs:
    """lock の版の入力から、検査に要るものだけを持つ。"""
    statements: dict            # sid → {"text", "role", "meetingId"}
    order: list                 # 索引の sid の並び
    segments: dict              # 一般質問・議案の質疑の場面：from の sid → 場面（kind・member・turns・bills・meetingId）
    gian: dict                  # 会議 id → 議案番号の集まり
    bulletin: dict              # bq のキー → 議会だよりの問いの本文の並び（§3 の where の順）
    docs: set                   # hino-town-docs の id
    doc_text: object            # (id, 層) → 本文（ページは改ページで区切る）か None。層は "text"・"text_raw"
    pt_text: object             # (計画 id, 名前, 層) → 本文か None
    plans: set                  # manifest の計画の id
    nodes: set                  # node キー（node:<id>/<key>）
    series: set                 # 系譜表の series
    pos: dict = field(default_factory=dict)
    qturns: dict = field(default_factory=dict)  # 一般質問の問い（q）の最初の発言の sid → 場面の from（§2 の iq）

    def __post_init__(self):
        self.pos = {s: i for i, s in enumerate(self.order)}
        for f, sg in self.segments.items():
            if sg["kind"] != "ippan" or f not in self.pos:
                continue
            for t in sg.get("turns") or []:
                k = self.pos[f] + t[0]
                if t[1] == "q" and k < len(self.order):
                    self.qturns[self.order[k]] = f

    def segment_of(self, key):
        """iq（q の最初の発言）か sq（まとまりの from）→ 場面。無ければ None。"""
        if RE_IQ.fullmatch(key or ""):
            f = self.qturns.get(key[3:])
            return self.segments.get(f) if f else None
        if RE_SQ.fullmatch(key or ""):
            sg = self.segments.get(key[3:])
            return sg if sg and sg["kind"] == "shitsugi" else None
        return None


@dataclass
class Report:
    errors: list = field(default_factory=list)          # 止める誤り（文）
    counts: dict = field(default_factory=dict)          # 台帳ごとの行の数
    round_diff: list = field(default_factory=list)
    quote_mismatch: list = field(default_factory=list)
    torikoboshi: list = field(default_factory=list)
    quote_context: list = field(default_factory=list)

    def err(self, where, msg):
        self.errors.append(f"{where}：{msg}")


# ---- §1 の形 ----

def parse_tsv(data, columns, name):
    """§1 の形（UTF-8・BOMなし・LF・1行目がヘッダ・セルにタブや改行が無い）を読む。合わなければ止める。"""
    if data.startswith(b"\xef\xbb\xbf"):
        raise RecordsError(f"{name}：BOM がある")
    if b"\r" in data:
        raise RecordsError(f"{name}：改行が LF でない")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as e:
        raise RecordsError(f"{name}：UTF-8 でない（{e}）") from None
    if not text.endswith("\n"):
        raise RecordsError(f"{name}：最後の行が改行で終わっていない")
    lines = text[:-1].split("\n")
    if lines[0].split("\t") != columns:
        raise RecordsError(f"{name}：ヘッダが {columns} でない（{lines[0].split(chr(9))}）")
    rows, errs = [], []
    for n, line in enumerate(lines[1:], start=2):
        cells = line.split("\t")
        if len(cells) != len(columns):
            errs.append(f"{n}行目：列の数が {len(cells)}（{len(columns)} のはず）")
            continue
        rows.append(dict(zip(columns, cells)))
    if errs:
        raise RecordsError(f"{name}：" + "、".join(errs))
    return rows


def sort_key(row, key_cols):
    return tuple((0, int(row[c])) if c in NUMERIC and RE_INT.fullmatch(row[c]) else (1, row[c]) for c in key_cols)


def check_order(rows, key_cols, name, rep):
    """行の同一性（キーの重複0件）と、§1 の並び（row と step は数の順、ほかは文字コード順）。"""
    keys = [tuple(r[c] for c in key_cols) for r in rows]
    seen = set()
    for k in keys:
        if k in seen:
            rep.err(name, f"行のキーが重なっている（{k}）")
        seen.add(k)
    for i in range(1, len(rows)):
        if sort_key(rows[i - 1], key_cols) > sort_key(rows[i], key_cols):
            rep.err(name, f"{i + 2}行目：行がキーの順でない（{keys[i - 1]} の後に {keys[i]}）")
            break


def label(name, row):
    return f"{name} {'/'.join(row[c] for c in KEYS[name])}"


# ---- 引用の照合（§15.1） ----

def norm(s):
    return mention.normalize(s)


def page_of(text, page):
    if text is None:
        return None
    parts = text.split("\f")
    return parts[page - 1] if 1 <= page <= len(parts) else None


def source_texts(inp, key):
    """資料のキー → 照らす本文の並び（§15.1）。キーの形が違うか、入力に無ければ None。"""
    if RE_SP.fullmatch(key):
        st = inp.statements.get(key[3:])
        return None if st is None else [st["text"] or ""]
    if RE_BQ.fullmatch(key):
        return inp.bulletin.get(key)
    m = RE_DOC_PAGE.fullmatch(key)
    if m:
        did, page = m.group(1), int(m.group(2))
        if did not in inp.docs:
            return None
        out = [page_of(inp.doc_text(did, layer), page) for layer in ("text", "text_raw")]
        out = [t for t in out if t is not None]
        return out or None
    m = RE_PT_PAGE.fullmatch(key)
    if m:
        pid, name, page = m.group(1), m.group(2), int(m.group(3))
        out = [page_of(inp.pt_text(pid, name, layer), page) for layer in ("text", "text_raw")]
        out = [t for t in out if t is not None]
        return out or None
    return None


def quote_in(inp, key, quote):
    texts = source_texts(inp, key)
    if texts is None:
        return None
    q = norm(quote)
    return any(q in norm(t) for t in texts)


def check_quote(inp, name, row, key, rep):
    """引用が資料の本文にあるか。資料が入力に無ければ誤り。本文に無ければ一覧に出し、confirmed なら誤り。"""
    q = row["quote"]
    if not q:
        rep.err(label(name, row), "quote が空")
        return
    if len(q) > QUOTE_MAX:
        rep.err(label(name, row), f"quote が{QUOTE_MAX}字を超える（{len(q)}字）")
    found = quote_in(inp, key, q)
    if found is None:
        rep.err(label(name, row), f"資料が入力に無いか、照らせない資料のキー（{key}）")
        return
    if not found:
        rep.quote_mismatch.append({"ledger": name, "key": "/".join(row[c] for c in KEYS[name]),
                                   "status": row["status"], "source": key, "quote": q})
        if row["status"] == "confirmed":
            rep.err(label(name, row), f"confirmed の引用が資料の本文に無い（{key}）")


# ---- 共通の列（§15.1） ----

def check_common(name, row, rep):
    w = label(name, row)
    s = row["status"]
    if s not in STATUSES:
        rep.err(w, f"status が {STATUSES} のどれでもない（{s}）")
        return
    if s == "candidate":
        if row["reviewer"] or row["date"]:
            rep.err(w, "candidate に reviewer か date がある")
    else:
        if not row["reviewer"] or not RE_DAY.fullmatch(row["date"]):
            rep.err(w, f"{s} に reviewer か date（YYYY-MM-DD）が無い")
    if s == "rejected" and not row["note"]:
        rep.err(w, "rejected の note が空")
    if not row["note"].startswith("下書き："):
        rep.err(w, "note の頭が「下書き：」でない（§15.1）")


def is_source_key(key):
    return bool(RE_SP.fullmatch(key) or RE_BQ.fullmatch(key) or RE_DOC_PAGE.fullmatch(key)
                or RE_PT_PAGE.fullmatch(key) or RE_GI.fullmatch(key))


def check_source_date(name, row, rep):
    if not RE_MONTH.fullmatch(row["source_date"]):
        rep.err(label(name, row), f"source_date が YYYY-MM-DD か YYYY-MM でない（{row['source_date']}）")


# ---- テーマの定義（§12）と施設の参照表（§15.8） ----

@dataclass
class Theme:
    rows: list
    by_kind: dict          # (theme, kind) → 値の集まり

    def values(self, theme, *kinds):
        out = set()
        for k in kinds:
            out |= self.by_kind.get((theme, k), set())
        return out

    def themes_of(self, kind, value):
        return sorted({t for (t, k), vs in self.by_kind.items() if k == kind and value in vs})


def check_themes(rows, inp, shisetsu_keys, rep):
    name = "ref/themes.tsv"
    check_order(rows, ("theme", "kind", "value"), name, rep)
    by = {}
    for r in rows:
        w = f"{name} {r['theme']}/{r['kind']}/{r['value']}"
        k, v = r["kind"], r["value"]
        by.setdefault((r["theme"], k), set()).add(v)
        if not re.fullmatch(r"[a-z]+", r["theme"]):
            rep.err(w, "theme が英小文字でない")
        if not r["reviewer"] or not RE_DAY.fullmatch(r["date"]):
            rep.err(w, "reviewer か date（YYYY-MM-DD）が無い")
        if k not in THEME_KINDS:
            rep.err(w, f"kind が §12 の{len(THEME_KINDS)}のどれでもない")
            continue
        ok = True
        if k == "系列":
            ok = v in inp.series
        elif k in ("施策", "事業"):
            ok = bool(RE_NODE.fullmatch(v)) and v in inp.nodes
        elif k == "議案":
            m = RE_GI.fullmatch(v)
            ok = bool(m) and m.group(2) in inp.gian.get(m.group(1), set())
        elif k == "問い":
            seg = inp.segment_of(v) if RE_IQ.fullmatch(v) else None
            ok = bool(seg)
            if ok and not member_in(seg["member"], r["source"]):
                rep.err(w, f"source の議員の名前が審議の記録の member（{seg['member']}）と合わない")
        elif k == "質疑":
            seg = inp.segment_of(v) if RE_SQ.fullmatch(v) else None
            ok = bool(seg)
            if ok and not member_in(seg["member"], r["source"]):
                rep.err(w, f"source の議員の名前が審議の記録の member（{seg['member']}）と合わない")
        elif k == "資料":
            m = RE_DOC.fullmatch(v)
            ok = bool(m) and m.group(1) in inp.docs
        elif k == "施設":
            ok = v in shisetsu_keys
        elif k in ("語", "除外の語"):
            ok = bool(v) and norm(v) == v
        else:
            ok = bool(v)
        if not ok:
            rep.err(w, "value が kind の形に合わないか、lock の版の入力に無い")
    for t in sorted({r["theme"] for r in rows}):
        if len(by.get((t, "名前"), ())) != 1:
            rep.err(f"{name} {t}", "名前 の行が1行でない")
    return Theme(rows, by)


def member_in(member, source):
    """§2 の mb のそろえ方（NFKC・空白を除く）で、source に議員の名前が書いてあるか。"""
    m = re.sub(r"\s", "", unicodedata.normalize("NFKC", member or ""))
    s = re.sub(r"\s", "", unicodedata.normalize("NFKC", source or ""))
    return bool(m) and m in s


def check_shisetsu_ref(rows, rep):
    name = "ref/shisetsu.tsv"
    check_order(rows, ("key",), name, rep)
    for r in rows:
        w = f"{name} {r['key']}"
        if not RE_FA.fullmatch(r["key"]):
            rep.err(w, "key が §2 の fa の形でない")
        if not r["reviewer"] or not RE_DAY.fullmatch(r["date"]):
            rep.err(w, "reviewer か date（YYYY-MM-DD）が無い")
    return {r["key"] for r in rows}


# ---- 審議の記録の場面と turns ----

def turn_rounds(inp, seg):
    """場面の発言（索引の並び）→ (問番号, turns から求めた round)。答えはその前の問いの round。"""
    base = inp.pos[seg["from"]]
    out, rq, cur = {}, {}, None
    turns = sorted(seg.get("turns") or [], key=lambda t: t[0])
    for i, t in enumerate(turns):
        off, typ = t[0], t[1]
        qn = t[2] if len(t) > 2 else None
        if typ == "q":
            cur = (qn, FIRST)
        elif typ == "rq":
            rq[qn] = rq.get(qn, 0) + 1
            cur = (qn, f"再質問{rq[qn]}")
        if cur is None:
            continue
        end = turns[i + 1][0] if i + 1 < len(turns) else inp.pos[seg["to"]] - base + 1
        for k in range(off, end):
            if base + k < len(inp.order):
                out.setdefault(inp.order[base + k], cur)
    return out


def segment_sids(inp, seg):
    a, b = inp.pos[seg["from"]], inp.pos[seg["to"]]
    return inp.order[a:b + 1]


def turn_sids(inp, seg):
    """turns に載った発言（議長の進行発言を含めない）を、索引の並びで。(sid, 種別)。"""
    base = inp.pos[seg["from"]]
    return [(inp.order[base + t[0]], t[1]) for t in sorted(seg.get("turns") or [], key=lambda t: t[0])]


# ---- 台帳ごとの検査 ----

def check_exchange(name, rows, inp, theme, rep):
    """やりとりの記録（§15.2）と質疑の記録（§15.7）。"""
    seg_kind = "ippan" if name == "yaritori" else "shitsugi"
    re_q = RE_IQ if name == "yaritori" else RE_SQ
    tkind = "問い" if name == "yaritori" else "質疑"
    by_q = {}
    for r in rows:
        by_q.setdefault(r["question"], []).append(r)
    for q, rs in by_q.items():
        seg = inp.segment_of(q) if re_q.fullmatch(q) else None
        if not seg or seg["kind"] != seg_kind:
            rep.err(f"{name} {q}", "question が審議の記録の場面に無い")
            continue
        themes = theme.themes_of(tkind, q)
        if not themes:
            rep.err(f"{name} {q}", f"question がテーマの定義の kind {tkind} に無い")
        points = set()
        for t in themes:
            points |= theme.values(t, "事柄", "記載")
        sids = set(segment_sids(inp, seg))
        rounds = turn_rounds(inp, seg)
        q_rows = {(r["n"], r["row"]): r for r in rs if r["side"] == "問い"}
        if name == "shitsugi":
            want = ",".join(f"gi:{seg['meetingId']}/{b}" for b in seg.get("bills") or [])
        for r in rs:
            w = label(name, r)
            check_common(name, r, rep)
            if not RE_INT.fullmatch(r["n"]) or not RE_INT.fullmatch(r["row"]):
                rep.err(w, "n か row が1からの整数でない")
            if r["side"] not in SIDES:
                rep.err(w, f"side が {SIDES} のどれでもない")
                continue
            if not RE_SP.fullmatch(r["sid"]) or r["sid"][3:] not in sids:
                rep.err(w, f"sid が、この問いの場面の発言でない（{r['sid']}）")
            else:
                check_quote(inp, name, r, r["sid"], rep)
                tr = rounds.get(r["sid"][3:])
                if tr and tr[1] != r["round"]:
                    rep.round_diff.append({"ledger": name, "question": q, "n": r["n"], "row": r["row"],
                                           "sid": r["sid"], "round": r["round"], "turns_round": tr[1]})
            if not ROUND.fullmatch(r["round"]):
                rep.err(w, f"round が「最初の問い」か「再質問N」でない（{r['round']}）")
            if r["side"] == "問い":
                if r["speaker"] != "議員":
                    rep.err(w, "問いの行の speaker が「議員」でない")
                if r["stage"] not in STAGES:
                    rep.err(w, f"問いの行の stage が {STAGES} のどれでもない（{r['stage']}）")
                if r["kind"] not in Q_KINDS:
                    rep.err(w, f"問いの行の kind が §15.2 の値でない（{r['kind']}）")
                if r["answers"]:
                    rep.err(w, "問いの行に answers がある")
            else:
                if not r["speaker"] or r["speaker"] == "議員":
                    rep.err(w, "答えの行の speaker が役職でない")
                if r["stage"]:
                    rep.err(w, "答えの行に stage がある")
                if r["kind"] not in A_KINDS:
                    rep.err(w, f"答えの行の kind が §15.2 の値でない（{r['kind']}）")
                ans = r["answers"].split(",") if r["answers"] else []
                if not ans:
                    rep.err(w, "答えの行に answers が無い")
                for a in ans:
                    if (r["n"], a) not in q_rows:
                        rep.err(w, f"answers の {a} が、同じ問いの番号の問いの行でない")
            if r["point"] and r["point"] not in points:
                rep.err(w, f"point がテーマの kind 事柄か記載の値でない（{r['point']!r}）")
            if name == "yaritori":
                if r["side"] == "問い" and r["bq"]:
                    if not RE_BQ.fullmatch(r["bq"]) or r["bq"] not in inp.bulletin:
                        rep.err(w, f"bq が議会だよりに無い（{r['bq']}）")
                if r["side"] == "答え" and r["bq"]:
                    rep.err(w, "答えの行に bq がある")
                if r["bulletin"] and r["bulletin"] not in BULLETIN:
                    rep.err(w, f"bulletin が {BULLETIN} のどれでもない")
            else:
                if r["bills"] != want:
                    rep.err(w, f"bills が審議の記録のまとまりの bills（{want}）と違う")
    return by_q


def check_kotogara(rows, inp, theme, yaritori_keys, rep):
    name = "kotogara"
    prog = {}
    for r in rows:
        w = label(name, r)
        check_common(name, r, rep)
        if r["point"] not in theme.values(r["theme"], "事柄"):
            rep.err(w, "point がそのテーマの kind 事柄の値でない")
        if r["program"]:
            if r["program"] not in inp.nodes:
                rep.err(w, f"program が計画の事業に無い（{r['program']}）")
            prev = prog.setdefault((r["theme"], r["point"]), r["program"])
            if prev != r["program"]:
                rep.err(w, f"同じテーマ・同じ point の program が違う（{prev} と {r['program']}）")
        if r["kind"] not in TIME_KINDS:
            rep.err(w, f"kind が {TIME_KINDS} のどれでもない")
        if r["kind"] != "変更" and (r["prev"] or r["reason"]):
            rep.err(w, "変更でない行に prev か reason がある")
        if r["yaritori"] and r["yaritori"] not in yaritori_keys:
            rep.err(w, f"yaritori の参照がやりとりの記録に無い（{r['yaritori']}）")
        check_source(name, r, inp, rep)


def check_source(name, r, inp, rep):
    w = label(name, r)
    if not is_source_key(r["source"]):
        rep.err(w, f"source が §2 の sp・bq・doc（ページあり）・pt（ページあり）・gi の形でない（{r['source']}）")
        return
    check_source_date(name, r, rep)
    if RE_GI.fullmatch(r["source"]):
        rep.err(w, "source が gi の行は、引用を照らせない")
        return
    check_quote(inp, name, r, r["source"], rep)


def ref_ok(inp, ref):
    """つながりの記録の upper_ref・lower_ref：資料のキーか、計画のキーか、計画の記載の参照（§13.1）。"""
    if not ref:
        return True
    if RE_PLAN.fullmatch(ref):
        return ref[5:] in inp.plans
    m = RE_PLAN_ITEM.fullmatch(ref)
    if m:
        return m.group(1) in inp.plans
    return source_texts(inp, ref) is not None


def check_tsunagari(rows, inp, theme, rep):
    name = "tsunagari"
    for r in rows:
        w = label(name, r)
        check_common(name, r, rep)
        if r["link"] not in LINKS:
            rep.err(w, f"link が {LINKS} のどれでもない")
        kisai = theme.values(r["theme"], "記載")
        for c in ("upper", "lower"):
            if r[c] not in kisai:
                rep.err(w, f"{c} がそのテーマの kind 記載の値でない（{r[c]}）")
            if not ref_ok(inp, r[f"{c}_ref"]):
                rep.err(w, f"{c}_ref が入力に無い（{r[c + '_ref']}）")
        check_source(name, r, inp, rep)


def check_katei(rows, inp, theme, rep):
    name = "katei"
    steps = {}
    for r in rows:
        w = label(name, r)
        check_common(name, r, rep)
        if not RE_INT.fullmatch(r["step"]):
            rep.err(w, "step が1からの整数でない")
        else:
            steps.setdefault(r["theme"], []).append(int(r["step"]))
        for c in ("from", "to"):
            if r[c] and not RE_MONTH.fullmatch(r[c]):
                rep.err(w, f"{c} が YYYY-MM-DD か YYYY-MM でない")
        srcs = r["sources"].split(",") if r["sources"] else []
        if not srcs:
            rep.err(w, "sources が空")
            continue
        for s in srcs:
            if not is_source_key(s) or (not RE_GI.fullmatch(s) and source_texts(inp, s) is None):
                rep.err(w, f"sources の資料が入力に無い（{s}）")
        check_quote(inp, name, r, srcs[0], rep)
    for t, ss in steps.items():
        if sorted(ss) != list(range(1, len(ss) + 1)):
            rep.err(f"{name} {t}", "step が1からの続いた番号でない")


def check_kisai(rows, inp, theme, rep):
    name = "kisai"
    for r in rows:
        w = label(name, r)
        check_common(name, r, rep)
        if not r["title"]:
            rep.err(w, "title が空")
        if r["about"] and r["about"] not in theme.values(r["theme"], "事柄", "記載"):
            rep.err(w, f"about がそのテーマの kind 事柄か記載の値でない（{r['about']}）")
        check_source(name, r, inp, rep)


def check_shisetsu(rows, inp, theme, shisetsu_keys, rep):
    name = "shisetsu"
    themed = {v for (t, k), vs in theme.by_kind.items() if k == "施設" for v in vs}
    for r in rows:
        w = label(name, r)
        check_common(name, r, rep)
        if r["facility"] not in shisetsu_keys:
            rep.err(w, "facility が ref/shisetsu.tsv に無い")
        elif r["facility"] not in themed:
            rep.err(w, "facility がテーマの定義の kind 施設に無い")
        if r["aspect"] not in ASPECTS:
            rep.err(w, f"aspect が {ASPECTS} のどれでもない")
        if not r["value"]:
            rep.err(w, "value が空")
        if r["kind"] not in TIME_KINDS:
            rep.err(w, f"kind が {TIME_KINDS} のどれでもない")
        if r["kind"] != "変更" and r["prev"]:
            rep.err(w, "変更でない行に prev がある")
        check_source(name, r, inp, rep)


def check_nozoki(rows, inp, exchanges, rep):
    """記録しない文（§15.9）。question・n が、やりとりの記録か質疑の記録にある問いで、sid がその場面の発言で、quote がその発言にある。"""
    name = "nozoki"
    known = {(q, x["n"]) for q, rs in exchanges.items() for x in rs}
    for r in rows:
        w = label(name, r)
        check_common(name, r, rep)
        if (r["question"], r["n"]) not in known:
            rep.err(w, "question と n が、やりとりの記録か質疑の記録に無い")
            continue
        seg = inp.segment_of(r["question"])
        if not RE_SP.fullmatch(r["sid"]) or r["sid"][3:] not in set(segment_sids(inp, seg)):
            rep.err(w, "sid がその問いの場面の発言でない")
            continue
        if not r["reason"]:
            rep.err(w, "reason が空")
        check_quote(inp, name, r, r["sid"], rep)


# ---- 発言の取りこぼし（§11、ADR-24） ----

def sentences(text):
    """§4 の正規化のあとの本文を、「。」「？」「！」のあとで区切る。(始まり, 終わり, 文)。"""
    t = norm(text)
    out, start = [], 0
    for i, ch in enumerate(t):
        if ch in SENTENCE_END:
            out.append((start, i + 1, t[start:i + 1]))
            start = i + 1
    if start < len(t):
        out.append((start, len(t), t[start:]))
    return t, out


def uncovered(inp, sid, quotes, nozoki_quotes, words=None):
    """発言の中で、引用と1字も重ならず、記録しない文の台帳にも無い文。words があれば、その語を含む文だけを見る。"""
    st = inp.statements.get(sid)
    if st is None:
        return []
    t, ss = sentences(st["text"] or "")
    spans = []
    for q in quotes:
        nq = norm(q)
        i = t.find(nq) if nq else -1
        if i >= 0:
            spans.append((i, i + len(nq)))
    skip = {norm(q) for q in nozoki_quotes}
    out = []
    for a, b, s in ss:
        if words is not None and not any(wd in s for wd in words):
            continue
        if any(x < b and a < y for x, y in spans):
            continue
        if s in skip or s[:QUOTE_MAX] in skip:
            continue
        out.append(s)
    return out


def torikoboshi(inp, exchanges, nozoki, theme, rep):
    noz = {}
    for r in nozoki:
        noz.setdefault((r["question"], r["n"], r["sid"][3:]), []).append(r["quote"])
    for name, by_q in exchanges.items():
        for q, rs in sorted(by_q.items()):
            seg = inp.segment_of(q)
            if not seg:
                continue
            by_n = {}
            for r in rs:
                by_n.setdefault(r["n"], []).append(r)
            tsids = turn_sids(inp, seg)
            order = [s for s, _ in tsids]
            words = None
            if name == "shitsugi":
                words = set()
                for t in theme.themes_of("質疑", q):
                    words |= theme.values(t, "語")
            for n, nrs in sorted(by_n.items(), key=lambda x: int(x[0]) if RE_INT.fullmatch(x[0]) else 0):
                if name == "yaritori":
                    idx = [order.index(r["sid"][3:]) for r in nrs if r["sid"][3:] in order]
                    if not idx:
                        continue
                    lo, hi = min(idx), max(idx)
                    look = order[lo:hi + 1]
                    last_member = tsids[hi][1] in ("q", "rq")
                    if not last_member:
                        nxt = [s for s, typ in tsids[hi + 1:] if typ in ("q", "rq")][:1]
                        look += nxt
                else:
                    look = order
                for sid in look:
                    quotes = [r["quote"] for r in rs if r["sid"][3:] == sid]
                    for s in uncovered(inp, sid, quotes, noz.get((q, n, sid), []), words):
                        rep.torikoboshi.append({"ledger": name, "question": q, "n": n, "sid": "sp:" + sid,
                                                "quote": s})


# ---- 引用の前後（§11） ----

def quote_context(inp, name, rows, rep):
    for r in rows:
        key = r.get("sid") or r.get("source") or (r.get("sources") or "").split(",")[0]
        q = norm(r["quote"])
        if not q:
            continue
        k = "/".join(r[c] for c in KEYS[name])
        if q.startswith(DEMONSTRATIVES) and not q.startswith(NOT_DEMONSTRATIVE):
            rep.quote_context.append({"ledger": name, "key": k, "source": key, "kind": "指示語で始まる",
                                      "quote": r["quote"]})
        texts = source_texts(inp, key) or []
        ends = False
        for t in texts:
            nt = norm(t)
            i = nt.find(q)
            if i < 0:
                continue
            nxt = nt[i + len(q):i + len(q) + 1]
            if q[-1] in SENTENCE_END or nxt == "" or nxt in SENTENCE_END:
                ends = True
            break
        else:
            continue
        if not ends:
            rep.quote_context.append({"ledger": name, "key": k, "source": key, "kind": "文の途中で終わる",
                                      "quote": r["quote"]})


# ---- 全体 ----

def check_all(ledgers, themes_rows, shisetsu_rows, inp):
    """ledgers：台帳の名前 → 行の並び（nozoki は無ければ []）。Report を返す。"""
    rep = Report()
    shisetsu_keys = check_shisetsu_ref(shisetsu_rows, rep)
    theme = check_themes(themes_rows, inp, shisetsu_keys, rep)
    for name in LEDGERS:
        rows = ledgers.get(name, [])
        rep.counts[name] = len(rows)
        check_order(rows, KEYS[name], f"records/{name}.tsv", rep)
    yar = check_exchange("yaritori", ledgers["yaritori"], inp, theme, rep)
    shi = check_exchange("shitsugi", ledgers["shitsugi"], inp, theme, rep)
    ykeys = {f"{r['question']}/{r['row']}" for r in ledgers["yaritori"]}
    check_kotogara(ledgers["kotogara"], inp, theme, ykeys, rep)
    check_tsunagari(ledgers["tsunagari"], inp, theme, rep)
    check_katei(ledgers["katei"], inp, theme, rep)
    check_kisai(ledgers["kisai"], inp, theme, rep)
    check_shisetsu(ledgers["shisetsu"], inp, theme, shisetsu_keys, rep)
    check_nozoki(ledgers.get("nozoki", []), inp, {**yar, **shi}, rep)
    live = {n: [r for r in ledgers[n] if r["status"] != "rejected"] for n in ("yaritori", "shitsugi")}
    torikoboshi(inp, {"yaritori": group(live["yaritori"]), "shitsugi": group(live["shitsugi"])},
                ledgers.get("nozoki", []), theme, rep)
    for name in LEDGERS:
        if name != "nozoki":
            quote_context(inp, name, [r for r in ledgers[name] if r["status"] != "rejected"], rep)
    return rep


def group(rows):
    out = {}
    for r in rows:
        out.setdefault(r["question"], []).append(r)
    return out


def format_tsv(columns, rows):
    buf = io.StringIO()
    buf.write("\t".join(columns) + "\n")
    for r in rows:
        buf.write("\t".join(str(r[c]).replace("\t", " ").replace("\n", " ") for c in columns) + "\n")
    return buf.getvalue()
