"""hino-town-docs の構造化の層（補正予算の5つの表と検収の台帳）を読み、hs・hj・hk・hz のキーの行と、
検収の済んだ行を決める（LINK_SCHEMA.md §2・§10・§11、DESIGN.md ADR-34 の3・12）。

読むのは inputs.lock.json の hino-town-docs の版の、files に名指しした5つの表（hosei-kai・hosei-shiryo・hosei-kan・
hosei-maru・hosei-jiko）と、検収の台帳（data/struct/audit/hosei-<年度>.tsv）だけ。会計の額（hosei-kaikei）と決算・
財政指標の表は読まない（§10）。表は全部の行を読み、キーが無い行と検収の済んでいない行を分けて示す（§10）。

検収の済んだ行（§2）：
- hj・hk・hz：検収の台帳で table と row（<回の id>/<行の key>）が同じ行が、(1) 台帳の key が、lock の版の表の行から
  DOCS_SCHEMA §13.10 の作り方で作り直した key と同じ、(2) checked が ✓、(3) note が「要人確認:」で始まらない、の3つを満たす
- hs：その回を kai に持つ hosei-kan・hosei-maru・hosei-jiko の行が1行以上あり、それがすべて検収の済んだ行

DOCS_SCHEMA §13.10 の key の作り方：table・row・cols・value・unit・source を U+001F でつないだものの SHA-256 の先頭16桁。
cols は表ごとに決まった列（款の行は当初予算額から対当初までの9列、主な内容の行は name,amount、事項は
kind,kubun,kaikei,name,amount）、value はその列の値を「|」でつないだもの、source は「<資料の id> p.<ページ>」。
このリポジトリは hino-town-docs に書かない（不変の制約4）。key が合わない行は、検収の済んでいない行として数えて示す。
"""
import hashlib
import re
from dataclasses import dataclass, field

import gen_mentions as gm
import mention

KAI, SHIRYO, KAN, MARU, JIKO = "hosei-kai", "hosei-shiryo", "hosei-kan", "hosei-maru", "hosei-jiko"
TABLES = (KAI, SHIRYO, KAN, MARU, JIKO)
ROW_TABLES = (KAN, MARU, JIKO)          # 検収の台帳の行を持つ表（hs の検収はこの3つで決める）
AUDIT_PATTERN = "data/struct/audit/hosei-*.tsv"
AUDIT_PATH = re.compile(r"data/struct/audit/hosei-([a-z][0-9]+)\.tsv")
AUDIT_COLUMNS = ["key", "table", "row", "cols", "value", "unit", "source", "checked", "reviewer", "date", "note"]
CHECKED_MARK = "✓"
HUMAN_CHECK = "要人確認:"
# DOCS_SCHEMA §13.10 の cols（検収の対象の列）。款の行は §13.6 の表の当初予算額から対当初までの9列
AUDIT_COLS = {
    KAN: ["tosho", "tosho_ippan", "mae", "mae_ippan", "hosei", "hosei_ippan", "hoseigo", "hoseigo_ippan", "taitosho"],
    MARU: ["name", "amount"],
    JIKO: ["kind", "kubun", "kaikei", "name", "amount"],
}
# 表ごとに読む列（DOCS_SCHEMA §13.6）。表にこの列が無ければ止める
NEED = {
    KAI: ["id", "fiscal_year", "kaikei", "gou", "title"],
    SHIRYO: ["kai", "doc", "part", "pages"],
    KAN: ["kai", "key", "kan_no", "name", "unit", "doc", "page"] + AUDIT_COLS[KAN],
    MARU: ["kai", "key", "kind", "name", "amount", "unit", "desc", "doc", "page"],
    JIKO: ["kai", "key", "kind", "kubun", "kaikei", "name", "amount", "unit", "doc", "page"],
}

ID = r"[a-z0-9][a-z0-9-]*"
# §2 のキーの形。行の種類は key の頭で分ける（hk は in-・out-・sei-、hj は m・t、hz は z）
KEY_FORMS = {
    "hs": re.compile(rf"hs:({ID})"),
    "hj": re.compile(rf"hj:({ID})/([mt][a-z0-9-]*)"),
    "hk": re.compile(rf"hk:({ID})/((?:in|out|sei)-[a-z0-9-]*)"),
    "hz": re.compile(rf"hz:({ID})/(z[a-z0-9-]*)"),
}
TABLE_OF = {"hj": MARU, "hk": KAN, "hz": JIKO}
PREFIX_OF = {MARU: "hj", KAN: "hk", JIKO: "hz"}
# 回の題から会計の名前を取る（§2：「令和N年度日野町」と「補正予算（第N号）」を除いた字。§4 の正規化のあと）
TITLE_HEAD = re.compile(r"^令和(?:[0-9]+|元)年度日野町")
TITLE_TAIL = re.compile(r"補正予算\(第[0-9]+号\)$")


def kind_of(key):
    """hs・hj・hk・hz のどれか（形に合わなければ None）。"""
    for k, rx in KEY_FORMS.items():
        if rx.fullmatch(key or ""):
            return k
    return None


def rebuild_key(table, row, cols, value, unit, source):
    """DOCS_SCHEMA §13.10 の照合キー：6つを U+001F でつないだものの SHA-256 の先頭16桁。"""
    raw = "\x1f".join([table, row, cols, value, unit, source])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def parse_table(data, name, need):
    """構造化の表（§1 の形：UTF-8・LF・1行目が見出し）を読む。見出しに need の列が無いか、列の数が違えば止める。"""
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as e:
        raise gm.GenError(f"{name}：UTF-8 でない（{e}）") from None
    if text.startswith("﻿") or "\r" in text:
        raise gm.GenError(f"{name}：BOM か CR がある")
    lines = text.rstrip("\n").split("\n") if text else []
    if not lines:
        raise gm.GenError(f"{name}：見出しの行が無い")
    head = lines[0].split("\t")
    gm._fail(f"{name}：見出しに無い列", [c for c in need if c not in head])
    rows, errs = [], []
    for n, line in enumerate(lines[1:], start=2):
        cells = line.split("\t")
        if len(cells) != len(head):
            errs.append(f"{n}行目：列の数が {len(cells)}（{len(head)} のはず）")
            continue
        rows.append(dict(zip(head, cells)))
    gm._fail(f"{name}：表の形の誤り", errs)
    return rows


@dataclass
class Struct:
    """lock の版の構造化の層。"""
    kai: dict                         # 回の id → hosei-kai の行
    rows: dict                        # (表, 回の id, 行の key) → 行（hosei-kan・hosei-maru・hosei-jiko）
    shiryo: list                      # hosei-shiryo の行
    audit: dict                       # (表, row) → 検収の台帳の行（読む表の行だけ）
    audit_other: int = 0              # 検収の台帳のうち、読まない表（hosei-kaikei など）の行の数
    rebuilt: dict = field(default_factory=dict)   # (表, 回の id, 行の key) → 作り直した key
    errors: list = field(default_factory=list)    # 表どうしの食い違い（文）。止める
    by_kai: dict = field(default_factory=dict)    # 回の id → その回の (表, 回の id, 行の key) の並び

    def __post_init__(self):
        for k in sorted(self.rows):
            self.by_kai.setdefault(k[1], []).append(k)

    # ---- キー ----

    def row_of(self, key):
        """hj・hk・hz のキー → 表の行。無ければ None。"""
        k = kind_of(key)
        if k not in TABLE_OF:
            return None
        m = KEY_FORMS[k].fullmatch(key)
        return self.rows.get((TABLE_OF[k], m.group(1), m.group(2)))

    def exists(self, key):
        """§11 対象の照合の (1)：hs は回の表に、hj・hk・hz はその表に、同じ kai と key の行がある。"""
        k = kind_of(key)
        if k == "hs":
            return key[3:] in self.kai
        return self.row_of(key) is not None

    def audit_state(self, t):
        """(表, 回の id, 行の key) の検収の状態：済み・key が違う・未検収・要人確認・台帳に無い。"""
        a = self.audit.get((t[0], f"{t[1]}/{t[2]}"))
        if a is None:
            return "台帳に無い"
        if a["key"] != self.rebuilt.get(t):
            return "key が違う"
        if a["note"].startswith(HUMAN_CHECK):
            return "要人確認"
        if a["checked"] != CHECKED_MARK:
            return "未検収"
        return "済み"

    def row_checked(self, t):
        return self.audit_state(t) == "済み"

    def is_checked(self, key):
        """§2 の検収の済んだ行。hs は、その回の款の行・主な内容の行・事項が1行以上あり、すべて検収の済んだ行。"""
        k = kind_of(key)
        if k == "hs":
            ts = self.by_kai.get(key[3:], [])
            return bool(ts) and key[3:] in self.kai and all(self.row_checked(t) for t in ts)
        if k in TABLE_OF:
            m = KEY_FORMS[k].fullmatch(key)
            t = (TABLE_OF[k], m.group(1), m.group(2))
            return t in self.rows and self.row_checked(t)
        return False

    def kai_of(self, key):
        """hs・hj・hk・hz のキーの回の id。"""
        k = kind_of(key)
        if k is None:
            return None
        return KEY_FORMS[k].fullmatch(key).group(1)

    def audit_keys_of(self, key):
        """前の版との比べ方（§10）に使う、キーの検収の台帳の key。hs はその回の行の (row, key) の集まり。"""
        k = kind_of(key)
        if k == "hs":
            return frozenset((f"{t[0]}/{t[1]}/{t[2]}", (self.audit.get((t[0], f"{t[1]}/{t[2]}")) or {}).get("key", ""))
                             for t in self.by_kai.get(key[3:], []))
        m = KEY_FORMS[k].fullmatch(key)
        a = self.audit.get((TABLE_OF[k], f"{m.group(1)}/{m.group(2)}"))
        return a["key"] if a else ""

    # ---- 会計の名前（§2・§7 gian-yosan） ----

    def kaikei_names(self):
        """回の題から「令和N年度日野町」と「補正予算（第N号）」を除いた字（§4 の正規化のあと）→ kaikei。
        同じ名前が2つの kaikei に当たるか、同じ kaikei に2つの名前があれば止める。"""
        by_name, by_kaikei, errs = {}, {}, []
        for kid, r in sorted(self.kai.items()):
            name = TITLE_TAIL.sub("", TITLE_HEAD.sub("", mention.normalize(r["title"])))
            if not name or name == mention.normalize(r["title"]):
                errs.append(f"{kid}：title から会計の名前が取れない（{r['title']}）")
                continue
            by_name.setdefault(name, set()).add(r["kaikei"])
            by_kaikei.setdefault(r["kaikei"], set()).add(name)
        errs += [f"会計の名前「{n}」が2つ以上の kaikei に当たる（{'・'.join(sorted(ks))}）"
                 for n, ks in sorted(by_name.items()) if len(ks) > 1]
        errs += [f"kaikei {k} の会計の名前が2つ以上ある（{'・'.join(sorted(ns))}）"
                 for k, ns in sorted(by_kaikei.items()) if len(ns) > 1]
        gm._fail("回の表の会計の名前の誤り（LINK_SCHEMA §2）", errs)
        return {n: next(iter(ks)) for n, ks in by_name.items()}

    # ---- 件数 ----

    def counts(self):
        """表ごとの行の数と、検収の状態ごとの行の数。"""
        out = {"回": len(self.kai), "資料のページ": len(self.shiryo)}
        for t in ROW_TABLES:
            out[t] = sum(1 for k in self.rows if k[0] == t)
        states = {}
        for t in self.rows:
            s = self.audit_state(t)
            states[s] = states.get(s, 0) + 1
        return out, states

    def rekey_counts(self):
        """§10・§2 の (1)：検収の台帳の行（読む表）で、作り直した key が台帳の key と同じ行・違う行・表に行が無い行の数と、
        読まない表の台帳の行の数。"""
        same = diff = orphan = 0
        for (table, row), a in self.audit.items():
            kai, _, key = row.partition("/")
            t = (table, kai, key)
            if t not in self.rows:
                orphan += 1
            elif a["key"] == self.rebuilt[t]:
                same += 1
            else:
                diff += 1
        return same, diff, orphan, self.audit_other

    def mismatched(self):
        """作り直した key が台帳の key と違う行（(表, row, 台帳の key, 作り直した key)）。"""
        out = []
        for (table, row), a in sorted(self.audit.items()):
            kai, _, key = row.partition("/")
            t = (table, kai, key)
            if t in self.rows and a["key"] != self.rebuilt[t]:
                out.append((table, row, a["key"], self.rebuilt[t]))
        return out


def build_struct(tables, audits):
    """tables：表の名前 → 行の並び。audits：検収の台帳の行の並び（全年度）。Struct を返す。
    回の id や行の key の重なり、§2 のキーの形に合わない id と key があれば止める。"""
    errs = []
    kai = {}
    for r in tables[KAI]:
        if not re.fullmatch(ID, r["id"]):
            errs.append(f"{KAI}：id の形が違う（{r['id']!r}）")
        if r["id"] in kai:
            errs.append(f"{KAI}：id が重なっている（{r['id']}）")
        if not re.fullmatch(r"[0-9]{4}", r["fiscal_year"]) or not re.fullmatch(r"[1-9][0-9]*", r["gou"]):
            errs.append(f"{KAI} {r['id']}：fiscal_year か gou が数でない（{r['fiscal_year']!r}・{r['gou']!r}）")
        kai[r["id"]] = r
    rows = {}
    for table in ROW_TABLES:
        prefix = PREFIX_OF[table]
        for r in tables[table]:
            t = (table, r["kai"], r["key"])
            if t in rows:
                errs.append(f"{table}：kai と key が重なっている（{r['kai']}/{r['key']}）")
                continue
            if not KEY_FORMS[prefix].fullmatch(f"{prefix}:{r['kai']}/{r['key']}"):
                errs.append(f"{table}：kai か key が §2 の {prefix} の形でない（{r['kai']}/{r['key']}）")
            if r["kai"] not in kai:
                errs.append(f"{table}：kai が回の表に無い（{r['kai']}/{r['key']}）")
            rows[t] = r
    gm._fail("構造化の層の表の誤り（LINK_SCHEMA §2）", errs)
    audit, other, aerrs = {}, 0, []
    for a in audits:
        if a["table"] not in ROW_TABLES:
            other += 1
            continue
        k = (a["table"], a["row"])
        if k in audit:
            aerrs.append(f"検収の台帳：table と row が重なっている（{a['table']} {a['row']}）")
        audit[k] = a
    gm._fail("検収の台帳の誤り", aerrs)
    st = Struct(kai=kai, rows=rows, shiryo=list(tables[SHIRYO]), audit=audit, audit_other=other)
    for t, r in rows.items():
        cols = AUDIT_COLS[t[0]]
        st.rebuilt[t] = rebuild_key(t[0], f"{t[1]}/{t[2]}", ",".join(cols), "|".join(r[c] for c in cols), r["unit"],
                                    f"{r['doc']} p.{r['page']}")
    return st


def read_struct(gi, optional=False):
    """lock の版の構造化の層を読む。optional なら、その版に無い表は0行とする（前の版との比べ方。§10）。"""
    tables = {}
    for t in TABLES:
        path = f"data/struct/{t}.tsv"
        if optional and not gi.has(gm.TD, path):
            tables[t] = []
            continue
        tables[t] = parse_table(gi.read_bytes(gm.TD, path), f"{gm.TD} {path}", NEED[t])
    audits = []
    for path in gi.expand(gm.TD, AUDIT_PATTERN, allow_empty=optional):
        if not AUDIT_PATH.fullmatch(path):
            raise gm.GenError(f"{gm.TD} {path}：検収の台帳の名前が audit/hosei-<年度>.tsv の形でない")
        audits += parse_table(gi.read_bytes(gm.TD, path), f"{gm.TD} {path}", AUDIT_COLUMNS)
    return build_struct(tables, audits)


def lock_with_sha(lock, sha):
    """hino-town-docs の sha だけを替えた lock（前の版を読む。§10）。files はいまの lock のまま。"""
    if not re.fullmatch(r"[0-9a-f]{40}", sha or ""):
        raise gm.GenError(f"前の版の sha が40桁の16進数でない（{sha!r}）")
    out = {r: dict(v) for r, v in lock.items()}
    out[gm.TD]["sha"] = sha
    return out


def changes(prev, now, keys):
    """§10 の比べ方：記録の target の hs・hj・hk・hz のキーごとに、前の版にあった行で、いまの版で
    行が無くなった・検収の台帳の key が変わった・検収が済まなくなったもの。返り値は キー → 変わり方。"""
    out = {}
    for key in sorted(set(keys)):
        if kind_of(key) is None or not prev.exists(key):
            continue
        if not now.exists(key):
            out[key] = "行が無くなった"
        elif prev.audit_keys_of(key) != now.audit_keys_of(key):
            out[key] = "key が変わった"
        elif prev.is_checked(key) and not now.is_checked(key):
            out[key] = "検収が済まなくなった"
    return out
