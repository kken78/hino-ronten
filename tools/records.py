"""記録の台帳（records/）・テーマの定義（ref/themes.tsv）・施設の参照表（ref/shisetsu.tsv）・
地区と組織の参照表（ref/chiku.tsv・ref/soshiki.tsv）を確かめる関数
（LINK_SCHEMA.md §1・§2・§11・§12・§12.1・§15、DESIGN.md ADR-19・ADR-21〜ADR-24・ADR-31・ADR-32）。

やりとりの記録と質疑の記録の target・target_text（§15.2・§15.7）は、§11 の「対象の形」「対象の照合」「対象と議案・名前」で
確かめる。hs・hj・hk・hz は hino-town-docs の構造化の層（tools/hosei.py の Struct）で照らす（DESIGN.md ADR-34）。
提案理由の記録（records/teian.tsv。§15.11、ADR-35）は、財源の面だけの記録で、§11 の「提案理由の記録」で確かめ、
提案の区切りに入らない sid を一覧に出す。
枠の参照表（ref/waku.tsv。§12.3）と資料の種類の参照表（ref/shiryo.tsv。§12.4）を確かめ、kotogara・kisai の列 suji（筋の番号）を
資料の種類の参照表に当たる資料（監査委員の資料）について確かめる（DESIGN.md ADR-37）。check.md の「形の点検」の数も作る（§11）。
kotogara・tsunagari・kisai は theme の列を持たず、テーマへの帰属と出す見方は ref/themes.tsv の kind 事柄・記載の行
（theme・views）で決める（§15.3・§15.4・§15.6、ADR-31 の2）。届き先の信号（§11、ADR-31 の4）は一覧に出すだけで、止めない。

入力（lock の版の会議録・議会だより・計画・町の公開資料）は Inputs にまとめて渡す。読むのは tools/check_records.py。
台帳には書かない。誤りは Report.errors に、人が見る一覧は Report の各一覧に入れる。
"""
import io
import re
import unicodedata
from dataclasses import dataclass, field

import hosei
import mention

STATUSES = ("candidate", "confirmed", "rejected")
COMMON = ["status", "reviewer", "date", "note"]

# §15 の各台帳の列（status・reviewer・date・note は最後に置く。§15.1）
COLUMNS = {
    "yaritori": ["question", "n", "row", "side", "sid", "quote", "speaker", "round", "stage", "kind", "answers",
                 "target", "target_text", "point", "bq", "bulletin"] + COMMON,
    "shitsugi": ["question", "n", "row", "bills", "side", "sid", "quote", "speaker", "round", "stage", "kind",
                 "answers", "target", "target_text", "point"] + COMMON,
    "kotogara": ["point", "source", "source_date", "quote", "value", "target", "kind", "prev", "reason",
                 "yaritori", "suji"] + COMMON,                     # suji は ADR-37
    "tsunagari": ["link", "upper", "upper_ref", "lower", "lower_ref", "source", "source_date", "quote"] + COMMON,
    "katei": ["theme", "step", "cycle", "name", "from", "to", "sources", "quote"] + COMMON,
    "kisai": ["title", "about", "source", "source_date", "quote", "kind", "target", "suji"] + COMMON,
    # kind・target は ADR-36、suji は ADR-37
    "shisetsu": ["facility", "aspect", "value", "source", "source_date", "quote", "target", "kind", "prev"] + COMMON,
    "nozoki": ["question", "n", "sid", "quote", "reason"] + COMMON,
    "teian": ["maru", "bill", "sid", "quote"] + COMMON,
}
# 行のキー（§15 の各台帳）。row と step は数の順、ほかは文字コード順（§1）
KEYS = {
    "yaritori": ("question", "row"),
    "shitsugi": ("question", "row"),
    "kotogara": ("point", "source", "quote"),
    "tsunagari": ("link", "upper", "lower", "source"),
    "katei": ("theme", "step"),
    "kisai": ("title", "source"),
    "shisetsu": ("facility", "aspect", "source", "quote"),
    "nozoki": ("question", "n", "sid", "quote"),
    "teian": ("maru", "sid", "quote"),
}
NUMERIC = ("row", "step")
LEDGERS = tuple(COLUMNS)          # nozoki は無ければ0行（DESIGN.md ADR-24）
OPTIONAL = ("nozoki", "teian")   # 無ければ0行（teian は DESIGN.md ADR-35 で足した）
NOT_IN_THEME = ("teian",)         # テーマのノートのデータの ledgers に入れない台帳（渡す形は次の段で決める。ADR-35）

THEME_COLUMNS = ["theme", "kind", "value", "source", "views", "reviewer", "date", "note"]
THEME_KINDS = ("名前", "系列", "施策", "事業", "議案", "語", "除外の語", "問い", "資料", "質疑", "事柄", "記載", "施設",
               "地区", "組織", "枠")   # 枠は DESIGN.md ADR-37（報告 §15.10 はまだ置いていない）
VIEW_KINDS = ("事柄", "記載", "施設", "施策", "地区", "組織")   # views を持てる kind（§12）
POINT_KINDS = ("事柄", "記載")                  # 届き先の信号で見る点の kind（§11 届き先）
SHISETSU_COLUMNS = ["key", "name", "aliases", "district", "source", "reviewer", "date", "note"]
AREA_COLUMNS = ["key", "name", "aliases", "source", "reviewer", "date", "note"]   # ref/chiku.tsv・ref/soshiki.tsv（§12.1）
WAKU_COLUMNS = ["waku", "n", "name", "source", "reviewer", "date", "note"]          # ref/waku.tsv（§12.3。ADR-37）
SHIRYO_COLUMNS = ["shurui", "match", "tsukuru", "konkyo", "atesaki", "outou", "waku", "source", "reviewer", "date",
                  "note"]                                                            # ref/shiryo.tsv（§12.4。ADR-37。waku は経過 2026-11-14）
WAKU_JOIN = " → "   # 図の箱を2つ以上まとめた要素の名前のつなぎ（§12.3）

SIDES = ("問い", "答え")
STAGES = ("課題", "投入", "活動", "手続き", "結果", "成果", "めざす姿")
Q_KINDS = ("事実の確認", "数字・見込み", "方針・考え", "提案への考え", "住民意見・手続き", "時期・手順", "要望", "その他")
A_KINDS = ("事実・数字", "方針・考え", "留保", "考えていない", "時期・手順", "その他")
BULLETIN = ("載っている", "載っていない", "言い回しが違う")
TIME_KINDS = ("済んだこと", "いまのこと", "予定", "変更")
KISAI_KINDS = ("事実", "見通し", "評価", "要望")   # 構造にしていない記載の種類（§15.6。空でもよい。ADR-36・ADR-37 の3）
LINKS = ("目的と手段", "もとにした")
ASPECTS = ("種類", "運営", "役割", "状態", "規模")   # §15.8（規模は ADR-32）
RE_GIIN = re.compile(r"[0-9０-９]+番")   # 議員の役職（tools/build_theme.py の speaker_class と同じ形）
ELLIPSIS = "…"   # 提案理由の記録の引用で省いたところ（U+2026。§15.11）
IPPAN = "ippan"
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
# 記録の台帳とテーマの定義に書かない資料（§2・§11 書かない資料）：定例記者会見の掲載ページ。id の形で見る
RE_DOC_UNUSED = re.compile(r"doc:kaiken-[0-9]{8}-page(?![a-z0-9-])(?:/[0-9]+)?")
RE_PT_PAGE = re.compile(r"pt:([a-z0-9][a-z0-9-]*)/([A-Za-z0-9_.-]+)/([1-9][0-9]*)")
RE_GI = re.compile(r"gi:([0-9]{10})/([^/,\s]+)")
RE_NODE = re.compile(r"node:([a-z0-9][a-z0-9-]*)/([A-Za-z0-9_-]+)")
RE_PLAN = re.compile(r"plan:([a-z0-9][a-z0-9-]*)")
RE_PLAN_ITEM = re.compile(r"plan:([a-z0-9][a-z0-9-]*)/[A-Za-z0-9_-]+/[a-z_]+/[1-9][0-9]*/[1-9][0-9]*")
RE_FA = re.compile(r"fa:[a-z0-9][a-z0-9-]*")
RE_DIST = re.compile(r"dist:[a-z0-9][a-z0-9-]*")   # 地区（§2。ref/chiku.tsv）
RE_ORG = re.compile(r"org:[a-z0-9][a-z0-9-]*")     # 組織（§2。ref/soshiki.tsv）
RE_WAKU_ID = re.compile(r"[a-z0-9][a-z0-9-]*")
RE_WAKU = re.compile(r"waku:([a-z0-9][a-z0-9-]*)")                    # 枠（§2。ref/waku.tsv の n が0の行）
RE_WAKU_ELEM = re.compile(r"waku:([a-z0-9][a-z0-9-]*)/([1-9][0-9]*)")  # 枠の要素（見方。§2。ADR-37 の4）
RE_N0 = re.compile(r"0|[1-9][0-9]*")
RE_MATCH = re.compile(r"[a-z0-9*][a-z0-9*-]*")   # ref/shiryo.tsv の match の要素（§12.4）
# 枠組みの出典の法令の条項（§12.3）：<法令の名前>（<法令番号>）第<条>条…、か <法令の名前><条>条<項>項…。法令の名前は「法」か「法律」で終わる
RE_LAW = re.compile(r"(?P<law>[^\s（）、・0-9]+?(?:法律|法))(?:（[^）]*）)?第?[0-9]+条.*")
RE_DAY = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
RE_MONTH = re.compile(r"[0-9]{4}-[0-9]{2}(-[0-9]{2})?")
RE_INT = re.compile(r"[1-9][0-9]*")
RE_CHUSHIN = re.compile(r"中心の見方：([^。]*)")   # kind 名前の行の note（§12）
# confirmed の note に「判定：」の出どころを求めるのは、この日より後の date の行（§15.1）
HANTEI_SINCE = "2026-11-04"

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
SIGNAL_TODOKU_COLUMNS = ["ledger", "key", "point"]
SIGNAL_POINT_COLUMNS = ["ledger", "question", "rows", "empty", "ratio"]
SIGNAL_CHUSHIN_COLUMNS = ["theme", "chushin", "rows", "hit", "ratio"]
TARGET_UNCHECKED_COLUMNS = ["ledger", "question", "row", "status", "key"]
TARGET_BILL_COLUMNS = ["ledger", "question", "row", "key", "bills", "kai"]
TARGET_NAME_COLUMNS = ["ledger", "question", "row", "key", "name", "target_text"]
TARGET_CHANGED_COLUMNS = ["ledger", "question", "row", "key", "change"]
TEIAN_SEGMENT_COLUMNS = ["maru", "sid", "bill", "quote", "desc"]
SUJI_MISSING_COLUMNS = ["ledger", "key", "source", "shurui"]   # §11 記録の台帳（ADR-37 の2）
KATACHI_COLUMNS = ["kind", "ledger", "key", "detail"]          # §11 形の点検の (3)・(4)
SUJI_LEDGERS = ("kotogara", "kisai")                            # 列 suji を持つ台帳（§15.3・§15.6）

# 対象の形（§11・§15.2）：target のキーの種類と、target_text の種類
TARGET_LEDGERS = ("yaritori", "shitsugi")   # target を持つ台帳（審査報告の記録 §15.10 はまだ置いていない）
TARGET_KINDS = ("fh", "hs", "hj", "hk", "hz")
RE_FH = re.compile(r"fh:[a-z0-9][a-z0-9-]*/b[0-9]{3,}")
TEXT_KINDS = ("名", "款", "頁", "額", "源")


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
    plans_in_lineage: set = field(default_factory=set)   # 系譜表の plan の列（空でない値）。views の plan キーを照らす
    pos: dict = field(default_factory=dict)
    qturns: dict = field(default_factory=dict)  # 一般質問の問い（q）の最初の発言の sid → 場面の from（§2 の iq）
    fuhyo_keys: set = field(default_factory=set)   # lock の附表の事業の fh キー（対象の照合の (1)）
    struct: object = None                          # hino-town-docs の構造化の層（hosei.Struct）。無ければ None
    gian_hs: dict = field(default_factory=dict)    # 議案と回の台帳の confirmed の行：gi → hs の集まり
    hj_fh: dict = field(default_factory=dict)      # ○の行と附表の台帳の confirmed の行：hj → fh の集まり
    proposals: list = field(default_factory=list)  # 提案の区切り（kind が proposal）：(from, to, 会議 id, bills) の並び

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
    ref_counts: dict = field(default_factory=dict)      # 参照表ごとの行の数（shisetsu・chiku・soshiki）
    round_diff: list = field(default_factory=list)
    quote_mismatch: list = field(default_factory=list)
    torikoboshi: list = field(default_factory=list)
    quote_context: list = field(default_factory=list)
    signal_todoku: list = field(default_factory=list)   # 届き先の信号（§11、ADR-31 の4）。終了コードは変えない
    signal_point: list = field(default_factory=list)
    signal_chushin: list = field(default_factory=list)
    target_unchecked: list = field(default_factory=list)   # 対象の照合の (2) に合わない candidate（§11）
    target_bill: list = field(default_factory=list)        # 対象と議案・名前の (a)
    target_name: list = field(default_factory=list)        # 対象と議案・名前の (b)
    target_counts: dict = field(default_factory=dict)      # target のキーの種類ごとの数（check.md。H-7）
    text_counts: dict = field(default_factory=dict)        # target_text の種類ごとの数
    struct: object = None                                  # 照らした構造化の層（check.md に件数を出す）
    prev_sha: str = ""                                     # 前の版の hino-town-docs の SHA（--prev）
    target_changed: list = None                            # §10 の比べ方の一覧（--prev のときだけ）
    teian_segment: list = field(default_factory=list)      # 提案理由の記録の一覧（§11。終了コードは変えない）
    suji_missing: list = field(default_factory=list)       # confirmed で suji の空の監査委員の資料の行（§11。止めない）
    katachi: dict = field(default_factory=dict)            # 形の点検の数（§11。終了コードは変えない）
    katachi_rows: list = field(default_factory=list)       # 形の点検の (3)・(4) の行（katachi.tsv）
    waku: dict = field(default_factory=dict)               # 枠の参照表：枠の id → {n: 行}（§12.3）
    shiryo: object = None                                  # 資料の種類の参照表（Shiryo。§12.4）

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


def sort_key(row, key_cols, numeric=NUMERIC):
    return tuple((0, int(row[c])) if c in numeric and RE_N0.fullmatch(row[c]) else (1, row[c]) for c in key_cols)


def check_order(rows, key_cols, name, rep, numeric=NUMERIC):
    """行の同一性（キーの重複0件）と、§1 の並び（row と step は数の順、ほかは文字コード順）。
    numeric で数の順にする列を変えられる（ref/waku.tsv の n。§12.3）。"""
    keys = [tuple(r[c] for c in key_cols) for r in rows]
    seen = set()
    for k in keys:
        if k in seen:
            rep.err(name, f"行のキーが重なっている（{k}）")
        seen.add(k)
    for i in range(1, len(rows)):
        if sort_key(rows[i - 1], key_cols, numeric) > sort_key(rows[i], key_cols, numeric):
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
    # 2026-11-04 以前の confirmed は「判定：」が無くても止めない（判定シートの番号の有無も見ない。§15.1）
    if s == "confirmed" and row["date"] > HANTEI_SINCE and "判定：" not in row["note"]:
        rep.err(w, "confirmed の note に「判定：」の出どころが無い（§15.1）")


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
    views: dict = field(default_factory=dict)        # (kind, value) → 全テーマの行の views を合わせた集まり
    name_notes: dict = field(default_factory=dict)   # theme → kind 名前の行の note

    def values(self, theme, *kinds):
        out = set()
        for k in kinds:
            out |= self.by_kind.get((theme, k), set())
        return out

    def themes_of(self, kind, value):
        return sorted({t for (t, k), vs in self.by_kind.items() if k == kind and value in vs})

    def views_of(self, kind, value):
        """その kind・value を持つ全テーマの行の views を合わせた集まり（テーマは問わない。ADR-31 の2）。"""
        return set(self.views.get((kind, value), set()))

    def point_views(self, value):
        """点（kind 事柄・記載の値）の views。§11 届き先の信号で使う。"""
        out = set()
        for k in POINT_KINDS:
            out |= self.views_of(k, value)
        return out

    def chushin(self, theme):
        """kind 名前の行の note の「中心の見方：<キー>」の <キー>（「。」か行末まで）。無ければ空（§12）。"""
        m = RE_CHUSHIN.search(self.name_notes.get(theme, ""))
        return m.group(1) if m else ""


def split_views(views):
    """views の列 → キーの並び。空なら []。"""
    return views.split(",") if views else []


def check_views(r, inp, shisetsu_keys, w, rep, chiku_keys=frozenset(), soshiki_keys=frozenset(), waku=None):
    """views の形（§12）：持てる kind、空の要素・重複、テーマの id、見方のキーの形と入力・参照表にあること（§2）。
    waku は枠の参照表（枠の id → {n: 行}。無ければ空）。waku キーは n が1以上の要素だけが見方になる（ADR-37 の4）。"""
    waku = waku or {}
    vs = split_views(r["views"])
    if not vs:
        return
    if r["kind"] not in VIEW_KINDS:
        rep.err(w, f"views を持てるのは kind {'・'.join(VIEW_KINDS)} の行だけ")
        return
    if "" in vs:
        rep.err(w, "views に空の要素がある")
    seen = set()
    for v in vs:
        if not v:
            continue
        if v in seen:
            rep.err(w, f"views に同じキーが重なっている（{v}）")
        seen.add(v)
        if v == r["theme"]:
            rep.err(w, "views にテーマの id がある（テーマの id は書かない。常に含む）")
            continue
        if RE_NODE.fullmatch(v):
            ok = v in inp.nodes
        elif RE_PLAN.fullmatch(v):
            ok = v[5:] in inp.plans_in_lineage
        elif RE_FA.fullmatch(v):
            ok = v in shisetsu_keys
        elif RE_DIST.fullmatch(v):
            ok = v in chiku_keys
        elif RE_ORG.fullmatch(v):
            ok = v in soshiki_keys
        elif RE_WAKU_ELEM.fullmatch(v):
            m = RE_WAKU_ELEM.fullmatch(v)
            ok = m.group(2) in waku.get(m.group(1), {})
        else:
            rep.err(w, f"views のキーが §2 の見方のキー（node・plan・fa・dist・org・waku の要素）の形でない（{v}）")
            continue
        if not ok:
            rep.err(w, f"views のキーが入力に無い（{v}。node は計画の事業、plan は系譜表、fa は施設の参照表、"
                       "dist は地区の参照表、org は組織の参照表、waku は枠の参照表の要素）")


def check_themes(rows, inp, shisetsu_keys, rep, chiku_keys=frozenset(), soshiki_keys=frozenset(), waku=None):
    """テーマの定義（§12・§11）。chiku_keys・soshiki_keys は地区・組織の参照表の key（無ければ空）。
    waku は枠の参照表（check_waku_ref の返り値。無ければ空）。"""
    waku = waku or {}
    name = "ref/themes.tsv"
    check_order(rows, ("theme", "kind", "value"), name, rep)
    by, views, notes = {}, {}, {}
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
        elif k == "地区":
            ok = bool(RE_DIST.fullmatch(v)) and v in chiku_keys
        elif k == "組織":
            ok = bool(RE_ORG.fullmatch(v)) and v in soshiki_keys
        elif k == "枠":
            m = RE_WAKU.fullmatch(v)
            ok = bool(m) and m.group(1) in waku
        elif k in ("語", "除外の語"):
            ok = bool(v) and norm(v) == v
        else:
            ok = bool(v)
        if not ok:
            rep.err(w, "value が kind の形に合わないか、lock の版の入力に無い")
        check_views(r, inp, shisetsu_keys, w, rep, chiku_keys, soshiki_keys, waku)
        if k in VIEW_KINDS:
            views.setdefault((k, v), set()).update(x for x in split_views(r["views"]) if x)
        if k == "名前":
            notes[r["theme"]] = r["note"]
    # 施策の行の views は、同じテーマの kind 事業の node キーだけ（§12：基本施策に属する事業）。
    # 1つの事業を views に持つ施策の行は、同じテーマで1行まで（§11。§13.3 の programs の policy が1つに決まるため）
    first = {}
    for r in rows:
        if r["kind"] != "施策":
            continue
        progs = by.get((r["theme"], "事業"), set())
        for v in split_views(r["views"]):
            if v and RE_NODE.fullmatch(v) and v not in progs:
                rep.err(f"{name} {r['theme']}/{r['kind']}/{r['value']}",
                        f"施策の行の views が、同じテーマの kind 事業の行に無い（{v}）")
            elif v and not RE_NODE.fullmatch(v):
                rep.err(f"{name} {r['theme']}/{r['kind']}/{r['value']}",
                        f"施策の行の views が node キーでない（{v}）")
            if v and RE_NODE.fullmatch(v):
                if (r["theme"], v) in first:
                    rep.err(f"{name} {r['theme']}/{r['kind']}/{r['value']}",
                            f"施策の行の views に同じ事業がある（{v}。{first[(r['theme'], v)]}）")
                else:
                    first[(r["theme"], v)] = r["value"]
    for t in sorted({r["theme"] for r in rows}):
        if len(by.get((t, "名前"), ())) != 1:
            rep.err(f"{name} {t}", "名前 の行が1行でない")
    # views の waku キーの枠は、同じテーマの kind 枠の行にある（§11。ADR-37 の4）
    for r in rows:
        for v in split_views(r["views"]):
            m = RE_WAKU_ELEM.fullmatch(v or "")
            if m and f"waku:{m.group(1)}" not in by.get((r["theme"], "枠"), set()):
                rep.err(f"{name} {r['theme']}/{r['kind']}/{r['value']}",
                        f"views の {v} の枠が、同じテーマの kind 枠の行に無い")
    return Theme(rows, by, views, notes)


def member_in(member, source):
    """§2 の mb のそろえ方（NFKC・空白を除く）で、source に議員の名前が書いてあるか。"""
    m = re.sub(r"\s", "", unicodedata.normalize("NFKC", member or ""))
    s = re.sub(r"\s", "", unicodedata.normalize("NFKC", source or ""))
    return bool(m) and m in s


def check_shisetsu_ref(rows, rep, chiku_names=None):
    """施設の参照表（§11・§15.8）。chiku_names は地区の参照表の name の集まり。地区の参照表が無いか0行なら None で、
    district の照らし合わせを飛ばす。"""
    name = "ref/shisetsu.tsv"
    check_order(rows, ("key",), name, rep)
    for r in rows:
        w = f"{name} {r['key']}"
        if not RE_FA.fullmatch(r["key"]):
            rep.err(w, "key が §2 の fa の形でない")
        if not r["reviewer"] or not RE_DAY.fullmatch(r["date"]):
            rep.err(w, "reviewer か date（YYYY-MM-DD）が無い")
        if chiku_names is not None and r["district"] and r["district"] not in chiku_names:
            rep.err(w, f"district が地区の参照表（ref/chiku.tsv）の name に無い（{r['district']}）")
    return {r["key"] for r in rows}


def check_area_ref(rows, name, rx, prefix, rep):
    """地区・組織の参照表（§11・§12.1）：key の順と重複、key の形（dist: か org:）、reviewer と date。key の集まりを返す。"""
    check_order(rows, ("key",), name, rep)
    for r in rows:
        w = f"{name} {r['key']}"
        if not rx.fullmatch(r["key"]):
            rep.err(w, f"key が §2 の {prefix} の形でない")
        if not r["reviewer"] or not RE_DAY.fullmatch(r["date"]):
            rep.err(w, "reviewer か date（YYYY-MM-DD）が無い")
    return {r["key"] for r in rows}


# ---- 枠の参照表（§12.3）と資料の種類の参照表（§12.4）。DESIGN.md ADR-37 ----

def law_of(source):
    """枠組みの出典が法令の条項（§12.3）なら法令の名前、そうでなければ空。"""
    m = RE_LAW.fullmatch(source or "")
    return m.group("law") if m else ""


def check_waku_ref(rows, inp, rep, shiryo_rows=()):
    """枠の参照表（§11・§12.3）。枠の id → {n の字: 行} を返す（誤りのある枠も入れる。誤りは rep に）。
    出典は doc か pt のページのキーか、法令の条項。法令の名前は資料の種類の参照表（shiryo_rows）の source にあるものだけ。"""
    name = "ref/waku.tsv"
    laws = " ".join(r.get("source") or "" for r in shiryo_rows)
    check_order(rows, ("waku", "n"), name, rep, numeric=("n",))
    out = {}
    for r in rows:
        w = f"{name} {r['waku']}/{r['n']}"
        if not RE_WAKU_ID.fullmatch(r["waku"]):
            rep.err(w, "waku が英小文字・数字・ハイフンでない")
        if not RE_N0.fullmatch(r["n"]):
            rep.err(w, "n が0からの整数でない")
            continue
        out.setdefault(r["waku"], {})[r["n"]] = r
        if not r["name"]:
            rep.err(w, "name が空")
        if not r["reviewer"] or not RE_DAY.fullmatch(r["date"]):
            rep.err(w, "reviewer か date（YYYY-MM-DD）が無い")
        if not r["source"] or law_of(r["source"]):
            continue     # 法令の条項と空の出典は、枠組みごとにまとめて下で確かめる（§12.3）
        if not (RE_DOC_PAGE.fullmatch(r["source"]) or RE_PT_PAGE.fullmatch(r["source"])):
            rep.err(w, f"source が §2 の doc か pt のページのキーでも法令の条項でもない（{r['source']}）")
            continue
        texts = source_texts(inp, r["source"])
        if texts is None:
            rep.err(w, f"source が lock の版の入力に無い（{r['source']}）")
            continue
        body = [norm(t) for t in texts]
        for part in r["name"].split(WAKU_JOIN):
            if not part or not any(norm(part) in t for t in body):
                rep.err(w, f"name の「{part}」が source のページの原典の文字に無い（要素の名前は出典の語のまま。§12.3）")
    for wid, els in out.items():
        head_law = law_of((els.get("0") or {}).get("source"))
        for n, r in els.items():
            w = f"{name} {wid}/{n}"
            if not r["source"]:
                if n == "0" or not head_law:
                    rep.err(w, "source が空（空にできるのは、n が0の行の出典が法令の条項の枠組みの要素だけ。§12.3）")
            elif law_of(r["source"]):
                if not head_law:
                    rep.err(w, "source が法令の条項なのに、n が0の行の source が法令の条項でない（§12.3）")
                if law_of(r["source"]) not in laws:
                    rep.err(w, f"法令「{law_of(r['source'])}」が資料の種類の参照表の source に無い（§12.3）")
        if "0" not in els:
            rep.err(f"{name} {wid}", "n が0の行（枠そのもの）が無い")
        ns = sorted(int(n) for n in els if n != "0")
        if ns != list(range(1, len(ns) + 1)):
            rep.err(f"{name} {wid}", "要素の番号が1からの続いた番号でない")
    return out


def match_regex(pat):
    """ref/shiryo.tsv の match の要素 → 正規表現（`*` は英小文字・数字・ハイフンの0字以上の並び。§12.4）。"""
    return re.compile("".join("[a-z0-9-]*" if c == "*" else re.escape(c) for c in pat))


@dataclass
class Shiryo:
    """資料の種類の参照表（§12.4）。資料の id か資料のキーから、資料の種類（shurui）を引く。"""
    rows: list = field(default_factory=list)
    pats: list = field(default_factory=list)    # (shurui, [正規表現])

    def shurui_of(self, did):
        for shurui, rxs in self.pats:
            if any(rx.fullmatch(did or "") for rx in rxs):
                return shurui
        return ""

    def of_key(self, key):
        """資料のキー（doc:<id> か doc:<id>/<ページ>）→ 資料の種類。doc でなければ空。"""
        m = RE_DOC_PAGE.fullmatch(key or "") or RE_DOC.fullmatch(key or "")
        return self.shurui_of(m.group(1)) if m else ""

    def row_of(self, shurui):
        return next((r for r in self.rows if r["shurui"] == shurui), None)

    def waku_of(self, shurui):
        """資料の種類が当たる枠組みの要素の見方のキー（列 waku。§12.4）。無ければ空。"""
        return ((self.row_of(shurui) or {}).get("waku") or "")


def check_shiryo_ref(rows, inp, rep, waku=None):
    """資料の種類の参照表（§11・§12.4）。Shiryo を返す。waku は枠の参照表（check_waku_ref の返り値）。
    列 waku は空か、枠の参照表にある要素の見方のキー（DESIGN.md ADR-37 の経過、2026-11-14）。"""
    waku = waku or {}
    name = "ref/shiryo.tsv"
    check_order(rows, ("shurui",), name, rep)
    pats = []
    for r in rows:
        w = f"{name} {r['shurui']}"
        for c in ("shurui", "match", "tsukuru", "konkyo", "source"):
            if not r[c]:
                rep.err(w, f"{c} が空")
        if not r["reviewer"] or not RE_DAY.fullmatch(r["date"]):
            rep.err(w, "reviewer か date（YYYY-MM-DD）が無い")
        if r.get("waku"):
            m = RE_WAKU_ELEM.fullmatch(r["waku"])
            if not m or m.group(2) not in waku.get(m.group(1), {}):
                rep.err(w, f"waku が枠組みの参照表の要素の見方のキーでない（{r['waku']}）")
        rxs = []
        for pat in r["match"].split(",") if r["match"] else []:
            if not RE_MATCH.fullmatch(pat):
                rep.err(w, f"match の要素が §12.4 の形でない（{pat!r}）")
                continue
            rx = match_regex(pat)
            if not any(rx.fullmatch(d) for d in inp.docs):
                rep.err(w, f"match の {pat} に当たる資料が lock の版の hino-town-docs に無い")
            rxs.append(rx)
        pats.append((r["shurui"], rxs))
    for d in sorted(inp.docs):
        hit = [sh for sh, rxs in pats if any(rx.fullmatch(d) for rx in rxs)]
        if len(hit) > 1:
            rep.err(name, f"資料 {d} が2つ以上の行に当たる（{'・'.join(hit)}）")
    return Shiryo(rows, pats)


def check_suji(name, r, shiryo, rep):
    """列 suji（§15.3・§15.6。ADR-37 の2）：空か1からの整数、空でなければ資料が doc のページのキー。
    資料の種類の参照表に当たる資料の candidate の行は空でない。confirmed で空なら一覧に出す（止めない）。"""
    w = label(name, r)
    if r["suji"] and not RE_INT.fullmatch(r["suji"]):
        rep.err(w, f"suji が1からの整数でも空でもない（{r['suji']}）")
    if r["suji"] and not RE_DOC_PAGE.fullmatch(r["source"]):
        rep.err(w, "suji のある行の資料が doc のページのキーでない（筋は同じ資料の行のまとまり。§15.3）")
    sh = shiryo.of_key(r["source"]) if shiryo else ""
    if not sh or r["suji"]:
        return
    if r["status"] == "candidate":
        rep.err(w, f"資料の種類の参照表に当たる資料（{sh}）の candidate の行の suji が空")
    elif r["status"] == "confirmed":
        rep.suji_missing.append({"ledger": name, "key": "/".join(r[c] for c in KEYS[name]), "source": r["source"],
                                 "shurui": sh})


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


def check_kotogara(rows, inp, theme, yaritori_keys, rep, shiryo=None):
    """事柄の記録（§15.3）。point は、どれかのテーマの kind 事柄の値（テーマは問わない。ADR-31 の2）。"""
    name = "kotogara"
    for r in rows:
        w = label(name, r)
        check_common(name, r, rep)
        check_suji(name, r, shiryo, rep)
        if not theme.themes_of("事柄", r["point"]):
            rep.err(w, f"point がどのテーマの kind 事柄の値でもない（{r['point']!r}）")
        if r["kind"] not in TIME_KINDS:
            rep.err(w, f"kind が {TIME_KINDS} のどれでもない")
        if r["kind"] != "変更" and (r["prev"] or r["reason"]):
            rep.err(w, "変更でない行に prev か reason がある")
        if r["value"] and mention.normalize(r["value"]) not in mention.normalize(r["quote"]):
            rep.err(w, f"value が引用の中に無い（{r['value']}）")
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
    """つながりの記録（§15.4）。upper・lower は、どれかのテーマの kind 記載の値（テーマは問わない）。"""
    name = "tsunagari"
    for r in rows:
        w = label(name, r)
        check_common(name, r, rep)
        if r["link"] not in LINKS:
            rep.err(w, f"link が {LINKS} のどれでもない")
        for c in ("upper", "lower"):
            if not theme.themes_of("記載", r[c]):
                rep.err(w, f"{c} がどのテーマの kind 記載の値でもない（{r[c]}）")
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
        if r["cycle"] != r["cycle"].strip():
            rep.err(w, "cycle の前後に空白がある")
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


def check_kisai(rows, inp, theme, rep, shiryo=None):
    """構造にしていない記載（§15.6）。about は空か、どれかのテーマの kind 事柄か記載の値。
    kind は空か、事実・見通し・評価・要望（ADR-36・ADR-37 の3）。同じ title は1つの about を指す（台帳全体で。rejected の行は除く）。"""
    name = "kisai"
    about_of = {}
    for r in rows:
        w = label(name, r)
        check_common(name, r, rep)
        check_suji(name, r, shiryo, rep)
        if not r["title"]:
            rep.err(w, "title が空")
        if r["about"] and not (theme.themes_of("事柄", r["about"]) or theme.themes_of("記載", r["about"])):
            rep.err(w, f"about がどのテーマの kind 事柄か記載の値でもない（{r['about']}）")
        if r["kind"] and r["kind"] not in KISAI_KINDS:
            rep.err(w, f"kind が {KISAI_KINDS} のどれでも空でもない（{r['kind']}）")
        if r["status"] != "rejected":
            prev = about_of.setdefault(r["title"], r["about"])
            if prev != r["about"]:
                rep.err(w, f"同じ title の about が違う（{prev!r} と {r['about']!r}）")
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


# ---- 届き先の信号（§11 届き先、DESIGN.md ADR-31 の4） ----

def row_points(name, r):
    """記録の行の点：kotogara は point、kisai は about（空なら無し）、tsunagari は upper と lower。"""
    if name == "kotogara":
        return [r["point"]]
    if name == "kisai":
        return [r["about"]] if r["about"] else []
    return [r["upper"], r["lower"]]


def ratio(a, b):
    return f"{a / b:.4f}" if b else ""


def signals(ledgers, theme, rep):
    """届き先の信号を3つ作る。一覧に出すだけで、errors には入れない（止める値は幼保と介護で測ってから決める）。"""
    point_ledgers = ("kotogara", "kisai", "tsunagari")
    conf = {n: [r for r in ledgers.get(n, []) if r["status"] == "confirmed"] for n in LEDGERS}
    # (a) views の無い点の確定行
    for name in point_ledgers:
        for r in conf[name]:
            for p in row_points(name, r):
                if not theme.point_views(p):
                    rep.signal_todoku.append({"ledger": name, "key": "/".join(r[c] for c in KEYS[name]), "point": p})
    # (b) 問いごとの点が空の割合（問いと答えの両方の行を数える）
    for name in ("yaritori", "shitsugi"):
        by_q = {}
        for r in conf[name]:
            c = by_q.setdefault(r["question"], [0, 0])
            c[0] += 1
            c[1] += 0 if r["point"] else 1
        for q, (n, e) in sorted(by_q.items()):
            rep.signal_point.append({"ledger": name, "question": q, "rows": n, "empty": e, "ratio": ratio(e, n)})
    # (c) テーマごとに、中心の見方に出る行の割合
    for t in sorted({r["theme"] for r in theme.rows}):
        ch = theme.chushin(t)
        points = theme.values(t, *POINT_KINDS)
        n = hit = 0
        for name in point_ledgers:
            for r in conf[name]:
                ps = row_points(name, r)
                if not any(p in points for p in ps):
                    continue
                n += 1
                if ch and any(ch in theme.point_views(p) for p in ps):
                    hit += 1
        rep.signal_chushin.append({"theme": t, "chushin": ch, "rows": n, "hit": hit,
                                   "ratio": ratio(hit, n) if ch else ""})


# ---- 形の点検（§11。点検の報告の E.2。終了コードは変えない） ----

def zero_values(ledgers):
    """値の決まった列で、定数にあって0行の値。[(台帳, 列, 値)]。"""
    def vals(name, col, side=None):
        return {r[col] for r in ledgers.get(name, []) if side is None or r.get("side") == side}
    out = []
    checks = []
    for n in ("yaritori", "shitsugi"):
        checks += [(n, "side", None, SIDES), (n, "stage", "問い", STAGES), (n, "kind", "問い", Q_KINDS),
                   (n, "kind", "答え", A_KINDS)]
    checks += [("yaritori", "bulletin", None, BULLETIN), ("kotogara", "kind", None, TIME_KINDS),
               ("shisetsu", "kind", None, TIME_KINDS), ("shisetsu", "aspect", None, ASPECTS),
               ("kisai", "kind", None, KISAI_KINDS), ("tsunagari", "link", None, LINKS)]
    for n, col, side, consts in checks:
        have = vals(n, col, side)
        for c in consts:
            if c not in have:
                out.append((n, f"{col}（{side}）" if side else col, c))
    return out


def katachi(ledgers, rep):
    """形の点検の4つの数（§11）。rep.katachi と rep.katachi_rows に入れる。"""
    empty = {}
    for n in LEDGERS:
        rows = ledgers.get(n, [])
        cols = []
        for c in COLUMNS[n]:
            if c in COMMON:
                continue
            e = sum(1 for r in rows if not r[c])
            if e:
                cols.append((c, e, len(rows)))
        empty[n] = cols
    pairs = []
    for n, col in (("kotogara", "point"), ("kisai", "about")):
        by = {}
        for r in ledgers.get(n, []):
            if r["status"] != "rejected":
                by.setdefault((r["source"], norm(r["quote"])), []).append(r)
        for (src, _), rs in sorted(by.items()):
            if len({r[col] for r in rs}) > 1:
                pairs.append((n, rs))
                for r in rs:
                    rep.katachi_rows.append({"kind": "同じ引用で点が違う", "ledger": n,
                                             "key": "/".join(r[c] for c in KEYS[n]), "detail": r[col]})
    target = []
    for n in ("kotogara", "kisai", "shisetsu"):
        for r in ledgers.get(n, []):
            if r["status"] != "rejected" and r["target"] and norm(r["target"]) not in norm(r["quote"]):
                target.append((n, r))
                rep.katachi_rows.append({"kind": "target が引用に無い", "ledger": n,
                                         "key": "/".join(r[c] for c in KEYS[n]), "detail": r["target"]})
    by_led = {}
    for n, r in target:
        st = by_led.setdefault(n, {})
        st[r["status"]] = st.get(r["status"], 0) + 1
    rep.katachi = {"empty": empty, "zero": zero_values(ledgers), "pairs": pairs, "target": by_led}


# ---- 対象の形・対象の照合・対象と議案・名前（§11。DESIGN.md ADR-34 の1・2） ----

def target_kind(key):
    """target のキーの種類（fh・hs・hj・hk・hz）。形に合わなければ None。"""
    if RE_FH.fullmatch(key):
        return "fh"
    return hosei.kind_of(key)


def split_text(text):
    """target_text → [(種類, 字)]。形に合わなければ None（区切りの半角の「;」と、種類の後ろの半角の「:」だけを見る）。"""
    if not text:
        return []
    out = []
    for part in text.split(";"):
        if part.count(":") != 1:
            return None
        k, _, s = part.partition(":")
        if k not in TEXT_KINDS or not s:
            return None
        out.append((k, s))
    return out


def check_targets(name, rows, inp, rep):
    """§11 の対象の形・対象の照合・対象と議案・名前。一覧は rep.target_*。行の並びは ledger → question → row。"""
    st = inp.struct
    for r in rows:
        w = label(name, r)
        keys = r["target"].split(",") if r["target"] else []
        parts = split_text(r["target_text"])
        # 対象の形
        bad = [k for k in keys if target_kind(k) is None]
        if bad:
            rep.err(w, f"target が §2 の fh・hs・hj・hk・hz の形のキーを「,」で区切ったものでない（{'・'.join(bad) or '空の要素'}）")
        if len(set(keys)) != len(keys):
            rep.err(w, "target に同じキーが2つある")
        if parts is None:
            rep.err(w, f"target_text が「種類:字」を「;」で区切ったもの（種類は {'・'.join(TEXT_KINDS)}）でない"
                       f"（{r['target_text']!r}）")
            parts = []
        if keys and not r["target_text"]:
            rep.err(w, "target が空でないのに target_text が空")
        for k in keys:
            kind = target_kind(k)
            if kind:
                rep.target_counts[kind] = rep.target_counts.get(kind, 0) + 1
        for k, _ in parts:
            rep.text_counts[k] = rep.text_counts.get(k, 0) + 1
        if bad:
            continue
        # 対象の照合（1）〜（4）
        for k in keys:
            kind = target_kind(k)
            if kind == "fh":
                if k not in inp.fuhyo_keys:
                    rep.err(w, f"target の {k} が lock の版の附表に無い（対象の照合の (1)）")
                continue
            if st is None or not st.exists(k):
                rep.err(w, f"target の {k} が lock の版の構造化の層に無い（対象の照合の (1)）")
                continue
            if not st.is_checked(k):
                if r["status"] == "confirmed":
                    rep.err(w, f"confirmed の行の target の {k} が検収の済んだ行でない（対象の照合の (2)）")
                elif r["status"] == "candidate":
                    rep.target_unchecked.append({"ledger": name, "question": r["question"], "row": r["row"],
                                                 "status": r["status"], "key": k})
        st_text = norm((inp.statements.get(r["sid"][3:]) or {}).get("text") or "") if RE_SP.fullmatch(r["sid"]) else ""
        for k, s in parts:
            if norm(s) not in st_text:
                rep.err(w, f"target_text の字「{s}」が、その行の sid の発言の本文に無い（対象の照合の (3)）")
        for k in keys:
            if target_kind(k) == "hj":
                both = sorted(inp.hj_fh.get(k, set()) & set(keys))
                if both:
                    rep.err(w, f"target に {k} と、○の行と附表の台帳で引ける {'・'.join(both)} が両方ある（対象の照合の (4)）")
        # 対象と議案・名前（一覧だけ。(1) に合わないキーは見ない）
        if st is None:
            continue
        keys = [k for k in keys if target_kind(k) == "fh" or st.exists(k)]
        if name == "shitsugi":
            bills = r["bills"].split(",") if r["bills"] else []
            kai = sorted({h[3:] for b in bills for h in inp.gian_hs.get(b, set())})
            for k in keys:
                if target_kind(k) in ("hs", "hj", "hk", "hz") and st.kai_of(k) not in kai:
                    rep.target_bill.append({"ledger": name, "question": r["question"], "row": r["row"], "key": k,
                                            "bills": r["bills"], "kai": ",".join(f"hs:{x}" for x in kai)})
        words = [norm(s) for kk, s in parts if kk in ("名", "款")]
        for k in keys:
            kind = target_kind(k)
            if kind not in ("hj", "hk", "hz"):
                continue
            row = st.row_of(k)
            names = [norm(row["name"])] + ([norm(row["kan_no"])] if kind == "hk" and row.get("kan_no") else [])
            if not any(n and n in wd for n in names for wd in words):
                rep.target_name.append({"ledger": name, "question": r["question"], "row": r["row"], "key": k,
                                        "name": row["name"], "target_text": r["target_text"]})


def target_order(rows):
    """一覧の並び（§11）：ledger → question の文字コード順、同じ question の中は row の数の順。"""
    return sorted(rows, key=lambda x: (x["ledger"], x["question"],
                                       int(x["row"]) if RE_INT.fullmatch(x["row"]) else 0, x.get("key", "")))


def target_changed(ledgers, prev, now):
    """§10・§11：lock の hino-town-docs を上げるときの比べ方の一覧（target_changed.tsv の行）。"""
    keys = [k for n in TARGET_LEDGERS for r in ledgers.get(n, []) for k in (r["target"].split(",") if r["target"] else [])]
    ch = hosei.changes(prev, now, keys)
    out = []
    for n in TARGET_LEDGERS:
        for r in ledgers.get(n, []):
            for k in (r["target"].split(",") if r["target"] else []):
                if k in ch:
                    out.append({"ledger": n, "question": r["question"], "row": r["row"], "key": k, "change": ch[k]})
    return target_order(out)


# ---- 提案理由の記録（§11・§15.11。DESIGN.md ADR-35） ----

def teian_parts(quote):
    """quote を「…」で分ける（§15.11）。返り値は (頭を省いたか, 終わりを省いたか, 部分（§4 の正規化のあと）, 誤り)。"""
    raw = quote.split(ELLIPSIS)
    head = len(raw) > 1 and raw[0] == ""
    tail = len(raw) > 1 and raw[-1] == ""
    mid = raw[(1 if head else 0):(len(raw) - 1 if tail else len(raw))]
    parts = [norm(p) for p in mid]
    errs = []
    if not any(parts):
        errs.append("quote に「…」のほかの字が無い")
    elif any(len(p) < 2 for p in parts):
        errs.append("「…」で分けた部分に2字に満たないもの（空を含む）がある")
    return head, tail, parts, errs


@dataclass
class Placement:
    """§15.11 の当て方の結果。sentence はもとの文の番号（0から）、start・end はその文の本文の中の位置、spans は部分の位置。"""
    sentence: int
    start: int
    end: int
    spans: list
    text: str


def teian_place(text, parts):
    """§15.11 の当て方：本文（§4 の正規化のあと）の文のうち、部分がこの順で重ならずにある文ごとの Placement の並び。"""
    t, ss = sentences(text or "")
    out = []
    for n, (a, b, s) in enumerate(ss):
        pos, spans = 0, []
        for p in parts:
            i = s.find(p, pos)
            if i < 0:
                break
            spans.append((a + i, a + i + len(p)))
            pos = i + len(p)
        else:
            out.append(Placement(n, a, b, spans, t))
    return out


def teian_quote(inp, r, rep, name="teian"):
    """提案理由の記録の引用の照合（§11・§15.11）。もとの文が1つに決まれば Placement、決まらなければ None。
    引用が本文に無いときは、ほかの台帳と同じく quote_mismatch.tsv に出し、confirmed なら誤り。"""
    w, q, key = label(name, r), r["quote"], r["sid"]
    if not q:
        rep.err(w, "quote が空")
        return None
    if len(q) > QUOTE_MAX:
        rep.err(w, f"quote が{QUOTE_MAX}字を超える（{len(q)}字）")
    _, _, parts, errs = teian_parts(q)
    for e in errs:
        rep.err(w, e)
    if errs:
        return None
    texts = source_texts(inp, key)
    if texts is None:
        rep.err(w, f"資料が入力に無いか、照らせない資料のキー（{key}）")
        return None
    hits = teian_place(texts[0], parts)
    if not hits:
        rep.quote_mismatch.append({"ledger": name, "key": "/".join(r[c] for c in KEYS[name]),
                                   "status": r["status"], "source": key, "quote": q})
        if r["status"] == "confirmed":
            rep.err(w, f"confirmed の引用が資料の本文に無い（{key}）")
        return None
    if len(hits) > 1:
        rep.err(w, f"quote の部分がこの順である文が {len(hits)} つあり、当て方が1つに決まらない（部分を長くする）")
        return None
    h = hits[0]
    if any(x[1] == y[0] for x, y in zip(h.spans, h.spans[1:])):
        rep.err(w, "「…」の前後の部分が本文で続いている（省いた字が無い）")
    return h


def in_proposal(inp, sid, bill):
    """sid が、bills に bill の議案番号を持つ提案の区切りに入っているか（§11 の (a)）。"""
    m = RE_GI.fullmatch(bill)
    p = inp.pos.get(sid)
    if not m or p is None:
        return False
    for f, t, mid, bills in inp.proposals:
        if mid == m.group(1) and m.group(2) in (bills or []) and f in inp.pos and t in inp.pos \
                and inp.pos[f] <= p <= inp.pos[t]:
            return True
    return False


def check_teian(rows, inp, rep):
    """提案理由の記録（§15.11。財源の面だけ）。誤りは rep.errors、一覧は rep.teian_segment。"""
    name = "teian"
    st = inp.struct
    desc_of = lambda t: ((st.row_of(t) or {}).get("desc", "") if st is not None else "")  # noqa: E731
    for r in rows:
        w = label(name, r)
        check_common(name, r, rep)
        t = r["maru"]
        if hosei.kind_of(t) != "hj" or not t.partition("/")[2].startswith("m"):
            rep.err(w, f"maru が §2 の hj の○の行（key の頭が m）のキー1つでない（{t}）")
            t_ok = False
        elif st is None or not st.exists(t):
            rep.err(w, f"maru が lock の版の構造化の層に無い（{t}）")
            t_ok = False
        else:
            t_ok = True
            kai = st.kai.get(st.kai_of(t)) or {}
            if kai.get("kaikei") != IPPAN:
                rep.err(w, f"maru の回の会計が一般会計でない（{kai.get('kaikei')}）")
            if r["status"] == "confirmed" and not st.is_checked(t):
                rep.err(w, f"confirmed の行の maru が検収の済んだ行でない（{t}）")
        m = RE_GI.fullmatch(r["bill"])
        if not m or m.group(2) not in inp.gian.get(m.group(1), set()):
            rep.err(w, f"bill が §2 の gi の形でないか、gian.json に無い（{r['bill']}）")
        elif t_ok and f"hs:{st.kai_of(t)}" not in inp.gian_hs.get(r["bill"], set()):
            rep.err(w, f"bill が、議案と回の台帳の confirmed の行で maru の回（hs:{st.kai_of(t)}）に対応しない")
        sid = r["sid"][3:] if RE_SP.fullmatch(r["sid"]) else None
        stmt = inp.statements.get(sid) if sid else None
        if stmt is None:
            rep.err(w, f"sid が §2 の sp の形でないか、lock の版の索引に無い（{r['sid']}）")
            continue
        if RE_GIIN.fullmatch(stmt.get("role") or ""):
            rep.err(w, f"sid の発言の役職が議員（{stmt.get('role')}）")
        teian_quote(inp, r, rep)
        if r["status"] == "rejected":
            continue
        if not in_proposal(inp, sid, r["bill"]):
            rep.teian_segment.append({"maru": t, "sid": r["sid"], "bill": r["bill"], "quote": r["quote"],
                                      "desc": desc_of(t) if t_ok else ""})
    rep.teian_segment.sort(key=lambda x: (x["maru"], x["sid"], x["quote"]))


def teian_context(inp, rows, rep):
    """§11 引用の前後の、提案理由の記録の分（「…」で分けた部分で見る。DESIGN.md ADR-35）。"""
    name = "teian"
    for r in rows:
        q = norm(r["quote"])
        if not q:
            continue
        k = "/".join(r[c] for c in KEYS[name])
        if q.startswith(DEMONSTRATIVES) and not q.startswith(NOT_DEMONSTRATIVE):
            rep.quote_context.append({"ledger": name, "key": k, "source": r["sid"], "kind": "指示語で始まる",
                                      "quote": r["quote"]})
        head, tail, parts, errs = teian_parts(r["quote"])
        texts = source_texts(inp, r["sid"]) if not errs else None
        hits = teian_place(texts[0], parts) if texts else []
        if len(hits) != 1:
            continue
        h = hits[0]
        if not head and h.spans[0][0] != h.start:
            rep.quote_context.append({"ledger": name, "key": k, "source": r["sid"], "kind": "文の途中から始まる",
                                      "quote": r["quote"]})
        e = h.spans[-1][1]
        if not tail and not (e == h.end or h.text[e:e + 1] in ("",) or h.text[e] in SENTENCE_END):
            rep.quote_context.append({"ledger": name, "key": k, "source": r["sid"], "kind": "文の途中で終わる",
                                      "quote": r["quote"]})


# ---- 全体 ----

# 資料を書く欄（§11 書かない資料）。記録の台帳と、テーマの定義
UNUSED_LEDGER_COLUMNS = ("source", "sources", "upper_ref", "lower_ref")
UNUSED_THEME_COLUMNS = ("value", "source")


def check_unused_docs(ledgers, themes_rows, rep):
    """§2 で書かないとした資料（定例記者会見の掲載ページ）が、記録の台帳の資料の欄とテーマの定義に無いこと（§11）。"""
    for name in LEDGERS:
        for r in ledgers.get(name, []):
            for c in UNUSED_LEDGER_COLUMNS:
                for m in RE_DOC_UNUSED.finditer(r.get(c, "")):
                    rep.err(label(name, r), f"{c} に書かない資料がある（{m.group(0)}。記者会見の掲載ページ。§2）")
    for r in themes_rows:
        for c in UNUSED_THEME_COLUMNS:
            for m in RE_DOC_UNUSED.finditer(r.get(c, "")):
                rep.err(f"ref/themes.tsv {r['theme']}/{r['kind']}/{r['value']}",
                        f"{c} に書かない資料がある（{m.group(0)}。記者会見の掲載ページ。§2）")


def check_all(ledgers, themes_rows, shisetsu_rows, inp, chiku_rows=(), soshiki_rows=(), waku_rows=(), shiryo_rows=()):
    """ledgers：台帳の名前 → 行の並び（nozoki は無ければ []）。chiku_rows・soshiki_rows は地区・組織の参照表の行
    （ファイルが無ければ []。§12.1）。waku_rows・shiryo_rows は枠と資料の種類の参照表の行（無ければ []。§12.3・§12.4）。
    Report を返す。"""
    rep = Report()
    rep.ref_counts = {"shisetsu": len(shisetsu_rows), "chiku": len(chiku_rows), "soshiki": len(soshiki_rows),
                      "waku": len(waku_rows), "shiryo": len(shiryo_rows)}
    rep.waku = check_waku_ref(list(waku_rows), inp, rep, list(shiryo_rows))
    rep.shiryo = check_shiryo_ref(list(shiryo_rows), inp, rep, rep.waku)
    chiku_keys = check_area_ref(chiku_rows, "ref/chiku.tsv", RE_DIST, "dist", rep)
    soshiki_keys = check_area_ref(soshiki_rows, "ref/soshiki.tsv", RE_ORG, "org", rep)
    # 地区の参照表が無いか0行なら、施設の参照表の district は照らさない（§11 施設の参照表）
    chiku_names = {r["name"] for r in chiku_rows} if chiku_rows else None
    shisetsu_keys = check_shisetsu_ref(shisetsu_rows, rep, chiku_names)
    theme = check_themes(themes_rows, inp, shisetsu_keys, rep, chiku_keys, soshiki_keys, rep.waku)
    for name in LEDGERS:
        rows = ledgers.get(name, [])
        rep.counts[name] = len(rows)
        check_order(rows, KEYS[name], f"records/{name}.tsv", rep)
    yar = check_exchange("yaritori", ledgers["yaritori"], inp, theme, rep)
    shi = check_exchange("shitsugi", ledgers["shitsugi"], inp, theme, rep)
    ykeys = {f"{r['question']}/{r['row']}" for r in ledgers["yaritori"]}
    check_kotogara(ledgers["kotogara"], inp, theme, ykeys, rep, rep.shiryo)
    check_tsunagari(ledgers["tsunagari"], inp, theme, rep)
    check_katei(ledgers["katei"], inp, theme, rep)
    check_kisai(ledgers["kisai"], inp, theme, rep, rep.shiryo)
    check_shisetsu(ledgers["shisetsu"], inp, theme, shisetsu_keys, rep)
    check_nozoki(ledgers.get("nozoki", []), inp, {**yar, **shi}, rep)
    check_teian(ledgers.get("teian", []), inp, rep)
    check_unused_docs(ledgers, themes_rows, rep)
    for name in TARGET_LEDGERS:
        check_targets(name, ledgers[name], inp, rep)
    rep.target_unchecked = target_order(rep.target_unchecked)
    rep.target_bill = target_order(rep.target_bill)
    rep.target_name = target_order(rep.target_name)
    live = {n: [r for r in ledgers[n] if r["status"] != "rejected"] for n in ("yaritori", "shitsugi")}
    torikoboshi(inp, {"yaritori": group(live["yaritori"]), "shitsugi": group(live["shitsugi"])},
                ledgers.get("nozoki", []), theme, rep)
    for name in LEDGERS:
        live = [r for r in ledgers.get(name, []) if r["status"] != "rejected"]
        if name == "teian":
            teian_context(inp, live, rep)
        elif name != "nozoki":
            quote_context(inp, name, live, rep)
    signals(ledgers, theme, rep)
    rep.suji_missing.sort(key=lambda x: (x["ledger"], x["key"]))
    katachi(ledgers, rep)
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
