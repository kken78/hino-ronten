"""mention の照合関数（LINK_SCHEMA.md §4・§7〜§9）。

計画名の言及を、正規化した本文から最長一致で探し、系譜表で期を判別する。
ツールが作るのは candidate の材料まで（DESIGN.md ADR-2）。議長の発言を除くことと、
発言日を決めること（LINK_SCHEMA.md §8）は、呼ぶ側が行う。
"""
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date as Date

# §4 の空白：hino-council-search scripts/check-sid-stability.mjs の \s（JavaScript の空白の集合）と同じ
JS_WHITESPACE = "[\t\n\v\f\r    -     　﻿]"

LINEAGE_COLUMNS = ["series", "edition", "plan", "name", "start_fy", "end_fy", "source", "note"]
ALIASES_COLUMNS = ["series", "term", "kind", "note"]
FORMAL, ABBREV, EXCLUDE = "正式名", "略称", "除外"
KINDS = (FORMAL, ABBREV, EXCLUDE)

CONTEXT_CHARS = 15  # §3：evidence の前後各15文字

KANJI_DIGITS = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
NUMBER = r"([0-9]+|[一二三四五六七八九十]+)"
EDITION_BEFORE = re.compile(r"第" + NUMBER + r"([期次])(?:日野町)?$")
EDITION_AFTER = re.compile(r"\(第" + NUMBER + r"([期次])\)")


def normalize(text):
    """§4 の正規化：NFKC → 改行に続くページ番号の除去 → 「-数字-」の除去 → 空白の除去。"""
    text = unicodedata.normalize("NFKC", text or "")
    text = re.sub(r"\n[0-9]+-[0-9]+", "", text)
    text = re.sub(r"-[0-9]+-", "", text)
    return re.sub(JS_WHITESPACE, "", text)


class RefError(ValueError):
    """参照表（ref/lineage.tsv・ref/aliases.tsv）の形式の誤り。"""


@dataclass(frozen=True)
class LineageRow:
    series: str
    edition: str
    plan: str
    name: str
    start_fy: int | None
    end_fy: int | None
    source: str
    note: str

    @property
    def key(self):
        return f"plan:{self.plan}" if self.plan else f"lin:{self.series}/{self.edition}"


@dataclass(frozen=True)
class Term:
    series: str
    term: str
    kind: str


@dataclass(frozen=True)
class Refs:
    lineage: tuple
    terms: tuple

    def rows_of(self, series):
        return [r for r in self.lineage if r.series == series]

    def edition_row(self, series, edition):
        for r in self.lineage:
            if r.series == series and r.edition == str(edition):
                return r
        return None


@dataclass
class Mention:
    """台帳に行を作るもの（candidate の材料）。to_label は manifest から呼ぶ側が付ける（§3）。"""
    to: str
    series: str
    edition: str
    evidence: str
    context: str
    note: str
    pos: int


@dataclass
class Listed:
    """build/ の一覧に出すもの（期の行なし・期間外）。edition は明記された N（期間外では空）。"""
    series: str
    edition: str
    evidence: str
    context: str
    fiscal_year: int
    note: str
    pos: int


@dataclass
class Result:
    rows: list = field(default_factory=list)
    no_edition: list = field(default_factory=list)
    out_of_period: list = field(default_factory=list)


def _read_tsv(path, columns):
    with open(path, "rb") as f:
        raw = f.read()
    if raw.startswith(b"\xef\xbb\xbf"):
        raise RefError(f"{path}: BOM がある")
    if b"\r" in raw:
        raise RefError(f"{path}: 改行に CR がある")
    lines = raw.decode("utf-8").split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    if not lines or lines[0].split("\t") != columns:
        raise RefError(f"{path}: ヘッダが {columns} でない")
    rows = []
    for n, line in enumerate(lines[1:], 2):
        cells = line.split("\t")
        if len(cells) != len(columns):
            raise RefError(f"{path}:{n}: 列の数が {len(cells)}（{len(columns)} であるべき）")
        rows.append((n, dict(zip(columns, cells))))
    return rows


def _fiscal_year_cell(path, n, name, value):
    if value == "":
        return None
    if not re.fullmatch(r"[12][0-9]{3}", value):
        raise RefError(f"{path}:{n}: {name} が4桁の西暦でない（{value}）")
    return int(value)


def load_refs(lineage_path, aliases_path):
    """2つの参照表を読み、形式が違えば RefError で止める。"""
    lineage = []
    seen_edition = set()
    seen_blank = set()
    for n, c in _read_tsv(lineage_path, LINEAGE_COLUMNS):
        if not re.fullmatch(r"[a-z][a-z0-9-]*", c["series"]):
            raise RefError(f"{lineage_path}:{n}: series の形が違う（{c['series']}）")
        if c["edition"] and not re.fullmatch(r"[1-9][0-9]*", c["edition"]):
            raise RefError(f"{lineage_path}:{n}: edition が正の整数でない（{c['edition']}）")
        if not c["plan"] and not c["edition"]:
            raise RefError(f"{lineage_path}:{n}: plan も edition も空")
        if not c["name"]:
            raise RefError(f"{lineage_path}:{n}: name が空")
        s = _fiscal_year_cell(lineage_path, n, "start_fy", c["start_fy"])
        e = _fiscal_year_cell(lineage_path, n, "end_fy", c["end_fy"])
        if (s is None) != (e is None):
            raise RefError(f"{lineage_path}:{n}: start_fy と end_fy の片方だけがある")
        if s is not None and s > e:
            raise RefError(f"{lineage_path}:{n}: start_fy が end_fy より後")
        if s is not None and not c["source"]:
            raise RefError(f"{lineage_path}:{n}: 期間があるのに source が無い")
        if c["edition"]:
            k = (c["series"], c["edition"])
            if k in seen_edition:
                raise RefError(f"{lineage_path}:{n}: (series, edition) が重なっている {k}")
            seen_edition.add(k)
        else:
            if c["series"] in seen_blank:
                raise RefError(f"{lineage_path}:{n}: edition が空の行が同じ series に2つある（{c['series']}）")
            seen_blank.add(c["series"])
        lineage.append(LineageRow(c["series"], c["edition"], c["plan"], c["name"], s, e, c["source"], c["note"]))
    lineage_series = {r.series for r in lineage}

    terms = []
    seen_pair = set()
    owner = {}
    for n, c in _read_tsv(aliases_path, ALIASES_COLUMNS):
        if c["kind"] not in KINDS:
            raise RefError(f"{aliases_path}:{n}: kind が {KINDS} のどれでもない（{c['kind']}）")
        if not c["term"] or normalize(c["term"]) != c["term"]:
            raise RefError(f"{aliases_path}:{n}: term が空か、§4 の正規化後の形でない（{c['term']}）")
        if c["series"] not in lineage_series:
            raise RefError(f"{aliases_path}:{n}: 系譜表に無い series（{c['series']}）")
        if (c["series"], c["term"]) in seen_pair:
            raise RefError(f"{aliases_path}:{n}: (series, term) が重なっている（{c['series']}, {c['term']}）")
        seen_pair.add((c["series"], c["term"]))
        if c["kind"] != EXCLUDE:
            if owner.setdefault(c["term"], c["series"]) != c["series"]:
                raise RefError(f"{aliases_path}:{n}: 同じ語が2つの series にある（{c['term']}：{owner[c['term']]}・{c['series']}）")
        terms.append(Term(c["series"], c["term"], c["kind"]))

    formal_series = {t.series for t in terms if t.kind == FORMAL}
    missing = sorted(lineage_series - formal_series)
    if missing:
        raise RefError(f"{aliases_path}: 正式名の行が無い series {missing}")
    for t in terms:
        if t.kind != EXCLUDE:
            continue
        if t.term in owner:
            raise RefError(f"{aliases_path}: 除外の語が日野町の計画の語と同じ（{t.term}）")
        own = [u.term for u in terms if u.series == t.series and u.kind != EXCLUDE and u.term in t.term]
        if not own:
            raise RefError(f"{aliases_path}: 除外の語が同じ series の語を含まない（{t.series}, {t.term}）")
    return Refs(tuple(lineage), tuple(terms))


def _number(s):
    """算用数字、または漢数字（一〜九十九の範囲の「十」を使う書き方）を整数にする。読めなければ None。"""
    if s.isdigit():
        return int(s)
    if "十" not in s:
        return KANJI_DIGITS.get(s) if len(s) == 1 else None
    tens, _, ones = s.partition("十")
    if (tens and tens not in KANJI_DIGITS) or (ones and ones not in KANJI_DIGITS) or "十" in ones:
        return None
    return (KANJI_DIGITS[tens] if tens else 1) * 10 + (KANJI_DIGITS[ones] if ones else 0)


def _parse_date(value):
    if isinstance(value, Date):
        return value
    if isinstance(value, str) and re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
        return Date.fromisoformat(value)  # 月日の誤りは ValueError
    raise ValueError(f"発言日が YYYY-MM-DD でない（{value!r}）")


def fiscal_year(day):
    """年度（4月1日から翌年3月31日まで。§8）。"""
    return day.year if day.month >= 4 else day.year - 1


def wareki_fiscal_year(fy):
    """年度の和暦。2019年度以降は令和（2019年度は令和元年度）、それより前は平成。"""
    if fy >= 2019:
        n = fy - 2018
        return f"令和{'元' if n == 1 else n}年度"
    return f"平成{fy - 1988}年度"


def _longest_matches(text, terms):
    """§7：全 series の語（除外の語を含む）をまとめて、長い一致から順に重ならないものを採る。
    長さが同じで重なる場合は、本文で先に出た方を採る。"""
    found = []
    for t in terms:
        i = text.find(t.term)
        while i >= 0:
            found.append((i, i + len(t.term), t))
            i = text.find(t.term, i + 1)
    found.sort(key=lambda m: (-(m[1] - m[0]), m[0]))
    taken = [False] * len(text)
    chosen = []
    for s, e, t in found:
        if any(taken[s:e]):
            continue
        for i in range(s, e):
            taken[i] = True
        chosen.append((s, e, t))
    chosen.sort(key=lambda m: m[0])
    return chosen


def _explicit_edition(text, s, e):
    """期の明記：直前の「第N期／第N次」（間に「日野町」を挟んでもよい）と、直後の「(第N期)／(第N次)」。
    返り値は (N, 期か次, 前後で違う場合の note)。明記が無ければ (None, None, "")。"""
    before = EDITION_BEFORE.search(text[:s])
    after = EDITION_AFTER.match(text, e)
    b = (_number(before.group(1)), before.group(2)) if before else None
    a = (_number(after.group(1)), after.group(2)) if after else None
    if b and b[0] is None:
        b = None
    if a and a[0] is None:
        a = None
    if b and a and b[0] != a[0]:
        return b[0], b[1], f"期の明記が前後で違う（第{b[0]}{b[1]}・第{a[0]}{a[1]}）"
    if b:
        return b[0], b[1], ""
    if a:
        return a[0], a[1], ""
    return None, None, ""


def find_mentions(text, date, refs):
    """正規化した本文から計画名の言及を探し、期を判別する（§7）。

    返り値の Result は、台帳に行を作るもの（rows）と、build/ の一覧に出すもの
    （no_edition：期の行なし、out_of_period：期間外）に分かれる。
    rows は同じ to を1件にまとめる。evidence・context は本文で先に出た一致を使い、
    ほかに一致した語は note に書く（§7 同じ plan への一致）。"""
    day = _parse_date(date)
    fy = fiscal_year(day)
    norm = normalize(text)
    result = Result()
    hits = []  # (to, series, edition, evidence, context, note, pos)
    listed_seen = set()

    for s, e, t in _longest_matches(norm, refs.terms):
        if t.kind == EXCLUDE:
            continue  # 除外の語の範囲に含まれる一致は数えない
        context = norm[max(0, s - CONTEXT_CHARS):e + CONTEXT_CHARS]
        n, mark, conflict = _explicit_edition(norm, s, e)
        if n is not None:
            row = refs.edition_row(t.series, n)
            notes = [f"期の明記（第{n}{mark}）"] + ([conflict] if conflict else [])
            if row is None:
                k = ("no_edition", t.series, str(n))
                if k not in listed_seen:
                    listed_seen.add(k)
                    result.no_edition.append(Listed(t.series, str(n), t.term, context, fy,
                                                    "。".join(notes + ["系譜表にこの期の行が無い"]), s))
                continue
            hits.append((row.key, t.series, row.edition, t.term, context, "。".join(notes), s))
            continue
        rows = refs.rows_of(t.series)
        inside = [r for r in rows if r.start_fy is not None and r.start_fy <= fy <= r.end_fy]
        unknown = [r for r in rows if r.start_fy is None]
        for r in inside:
            note = f"{day.isoformat()} は{wareki_fiscal_year(fy)}。{r.name}（{r.start_fy}〜{r.end_fy}年度）"
            hits.append((r.key, t.series, r.edition, t.term, context, note, s))
        for r in unknown:
            hits.append((r.key, t.series, r.edition, t.term, context, "期間不明", s))
        if not inside and not unknown:
            k = ("out_of_period", t.series)
            if k not in listed_seen:
                listed_seen.add(k)
                result.out_of_period.append(Listed(t.series, "", t.term, context, fy,
                                                   f"{day.isoformat()} は{wareki_fiscal_year(fy)}。{t.series} のどの期の期間にも入らない", s))

    by_to = {}
    for to, series, edition, evidence, context, note, pos in hits:
        if to not in by_to:
            by_to[to] = [Mention(to, series, edition, evidence, context, note, pos), []]
        elif evidence != by_to[to][0].evidence and evidence not in by_to[to][1]:
            by_to[to][1].append(evidence)
    for m, others in by_to.values():
        if others:
            m.note = f"{m.note}。ほかに一致した語：{'・'.join(others)}"
        result.rows.append(m)
    result.rows.sort(key=lambda m: m.pos)
    return result
