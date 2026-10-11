"""リンク台帳の読み書き・照合・併合（LINK_SCHEMA.md §1〜§3・§5・§6・§11、DESIGN.md §5 工程4-3・4-4）。

台帳（links/<method>.tsv）の形を確かめて読み書きし、§5 の照合と §6 の併合、§11 の sentinel を行う関数を置く。
入力のリポジトリは読まない。読むのは tools/update_links.py・tools/check_links.py が gen_mentions で
lock の版から作ったデータだけ（§10）。機械は status を confirmed・rejected にしない（DESIGN.md ADR-2）。
"""
import os
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import date as Date

import gen_mentions as gm
import mention

LEDGER_COLUMNS = ["from", "to", "method", "evidence", "where", "context", "to_label",
                  "status", "reviewer", "date", "note"]
MOVED_COLUMNS = ["from", "to", "method", "status", "moved_to", "context"]
STOPPED_COLUMNS = ["from", "to", "method", "status", "reason", "context"]  # rejected_unmatched.tsv も同じ
VANISHED_COLUMNS = LEDGER_COLUMNS + ["check"]
NOTE_CHANGED_COLUMNS = ["from", "to", "method", "old_note", "new_note"]

CANDIDATE, CONFIRMED, REJECTED = "candidate", "confirmed", "rejected"
STATUSES = (CANDIDATE, CONFIRMED, REJECTED)
METHODS = ("mention", "program", "semantic")
MATCH, MOVED, STOPPED = "一致", "移動", "停止"
NEIGHBORS = 5  # §5：連番の前後5以内
SENTINEL_MARKS = ("〓", "※")  # §11：context に「〓」が含まれるときは「※」

KEY_FORMS = {
    "bq": re.compile(r"bq:[0-9]+/[^/\s]+/[0-9]+"),
    "sp": re.compile(r"sp:[0-9]{10}_[^\s]+_[0-9]{4}"),
    "plan": re.compile(r"plan:[a-z0-9][a-z0-9-]*"),
    "lin": re.compile(r"lin:[a-z0-9][a-z0-9-]*/[0-9]+"),
    "node": re.compile(r"node:[a-z0-9][a-z0-9-]*/[^/\s]+/[^/\s]+/[^/\s]+"),
}
FROM_KINDS, TO_KINDS = ("bq", "sp"), ("plan", "lin", "node")
TO_KINDS_OF = {"mention": ("plan", "lin")}  # §11：mention の台帳の to は plan・lin だけ
WHERES = {"bq": tuple(gm.BQ_FIELDS), "sp": ("text",)}


class LedgerError(gm.GenError):
    """台帳の形の誤り（§1・§3・§11）。件数と該当の行を示して止める。"""


def _fail(title, items):
    """items が1件以上なら、件数と全件を示して止める（gen_mentions._fail と同じ形。LedgerError を出す）。"""
    if items:
        raise LedgerError(f"{title}：{len(items)} 件\n" + "\n".join(f"  - {x}" for x in items))


def _kind(key):
    return key.partition(":")[0]


def _key(row):
    return (row["from"], row["to"], row["method"])


# ---- 台帳の読み書き（§1・§3・§11） ----

def _row_errors(n, r, method):
    """1行の §11 の検査（キーの形式・状態・欄の値・方法の制限）。誤りの文の一覧を返す。"""
    errs = []
    fk, tk = _kind(r["from"]), _kind(r["to"])
    if fk not in FROM_KINDS or not KEY_FORMS[fk].fullmatch(r["from"]):
        errs.append(f"from の形が違う（{r['from']!r}）")
    if tk not in TO_KINDS or not KEY_FORMS[tk].fullmatch(r["to"]):
        errs.append(f"to の形が違う（{r['to']!r}）")
    elif tk not in TO_KINDS_OF.get(method, TO_KINDS):
        errs.append(f"{method} の台帳の to に {tk} は使えない（{r['to']}）")
    if r["method"] != method:
        errs.append(f"method が台帳のファイル（{method}）と違う（{r['method']!r}）")
    if fk == "sp" and KEY_FORMS["sp"].fullmatch(r["from"]):
        try:
            gm._split_sid(r["from"][3:])
        except gm.GenError as e:
            errs.append(str(e))
    st = r["status"]
    if st not in STATUSES:
        errs.append(f"status が {'・'.join(STATUSES)} でない（{st!r}）")
    elif st == CANDIDATE:
        if r["reviewer"] or r["date"]:
            errs.append("candidate に reviewer か date がある")
    else:
        if not r["reviewer"]:
            errs.append(f"{st} に reviewer が無い")
        if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", r["date"]):
            errs.append(f"{st} の date が YYYY-MM-DD でない（{r['date']!r}）")
        else:
            try:
                Date.fromisoformat(r["date"])
            except ValueError:
                errs.append(f"{st} の date が日付として正しくない（{r['date']}）")
        if st == REJECTED and not r["note"]:
            errs.append("rejected の note が空")
    if fk in WHERES and r["where"] not in WHERES[fk]:
        errs.append(f"where が {'・'.join(WHERES[fk])} でない（{r['where']!r}）")
    for c in ("evidence", "context"):
        if not r[c] or mention.normalize(r[c]) != r[c]:
            errs.append(f"{c} が空か、§4 の正規化を通した値でない")
    if r["evidence"] and r["evidence"] not in r["context"]:
        errs.append("context に evidence が含まれない")
    return [f"{n}行目 {r['from']} {r['to']}：{e}" for e in errs]


def parse_ledger(data, method):
    """台帳のバイト列を読み、§1・§3・§11 の形を確かめる。誤りがあれば全件を示して止める（並べ直さない）。"""
    if method not in METHODS:
        raise LedgerError(f"台帳の method が {'・'.join(METHODS)} でない（{method!r}）")
    if data.startswith(b"\xef\xbb\xbf"):
        raise LedgerError("台帳が BOM で始まっている")
    if b"\r" in data:
        raise LedgerError("台帳に CR がある（改行は LF だけ）")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as e:
        raise LedgerError(f"台帳が UTF-8 でない（{e}）") from None
    if not text.endswith("\n"):
        raise LedgerError("台帳の最後の行が改行で終わっていない")
    lines = text[:-1].split("\n")
    if lines[0].split("\t") != LEDGER_COLUMNS:
        raise LedgerError(f"台帳のヘッダが {LEDGER_COLUMNS} でない（{lines[0].split(chr(9))}）")
    rows, errs = [], []
    for n, line in enumerate(lines[1:], start=2):
        cells = line.split("\t")
        if len(cells) != len(LEDGER_COLUMNS):
            errs.append(f"{n}行目：列の数が {len(cells)}（{len(LEDGER_COLUMNS)} のはず）")
            continue
        r = dict(zip(LEDGER_COLUMNS, cells))
        errs += _row_errors(n, r, method)
        rows.append(r)
    seen = Counter(_key(r) for r in rows)
    errs += [f"(from, to, method) が重なっている：{k}（{c} 行）" for k, c in sorted(seen.items()) if c > 1]
    keys = [_key(r) for r in rows]
    for n in range(1, len(keys)):
        if keys[n - 1] > keys[n]:
            errs.append(f"{n + 2}行目：行が from → to → method の文字コード順でない（{keys[n - 1]} の後に {keys[n]}）")
    _fail("台帳の誤り（§1・§3・§11）", errs)
    return rows


def read_ledger(path, method, missing_ok=False):
    """台帳を読む。missing_ok なら、ファイルが無いときは空の台帳とする（初めて書くとき）。"""
    if not os.path.exists(path):
        if missing_ok:
            return []
        raise LedgerError(f"台帳が無い（{path}）")
    with open(path, "rb") as f:
        return parse_ledger(f.read(), method)


def format_ledger(rows):
    """§1 の形のバイト列。行は from → to → method の文字コード順（キーが一意なので全列の順と同じ）。"""
    return _format(LEDGER_COLUMNS, rows)


def _format(columns, rows):
    bad = [f"{_key(r)} の {c}" for r in rows for c in columns
           if not isinstance(r[c], str) or any(ch in r[c] for ch in "\t\n\r")]
    _fail("台帳・一覧に書けない値（タブ・改行を含むか、文字列でない）", bad)
    lines = ["\t".join(columns)] + ["\t".join(r[c] for c in columns) for r in sorted(rows, key=lambda r: [r[c] for c in columns])]
    return ("\n".join(lines) + "\n").encode("utf-8")


def write_ledger(path, rows):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "wb") as f:
        f.write(format_ledger(rows))


# ---- 照合の相手（lock の版の入力から作る） ----

@dataclass
class Corpus:
    texts: dict    # sid → 正規化した本文
    by_pos: dict   # (会議ID, 真ん中, 連番) → sid
    fields: dict   # bq のキー → {where: [正規化した本文, …]}
    names: dict    # manifest の id → name
    refs: object


def make_corpus(inputs, refs):
    """gm.Inputs と参照表から、§5 の照合の相手を作る。"""
    texts, by_pos = {}, {}
    for e in inputs.index:
        sid = e["sid"]
        if sid in texts:
            raise gm.GenError(f"索引で sid が重なっている（{sid}）")
        texts[sid] = mention.normalize(e.get("text") or "")
        h, b, n = gm._split_sid(sid)
        by_pos[(h, b, int(n))] = sid
    fields = {}
    for q in inputs.questions:
        f = fields.setdefault(gm.bq_key(q), {})
        for where, text in gm._bq_parts(q):
            f.setdefault(where, []).append(mention.normalize(text))
    return Corpus(texts, by_pos, fields, gm.plan_names(inputs.manifest, refs), refs)


# ---- 照合（§5） ----

@dataclass(frozen=True)
class Match:
    result: str        # 一致・移動・停止
    moved_to: str = ""  # 移動のときの移動先（sp:<sid>）
    reason: str = ""


def match_row(row, corpus, context=None):
    """1行の §5 の照合。context を渡すと、台帳の context の代わりに使う（sentinel 用）。"""
    ctx = mention.normalize(row["context"] if context is None else context)
    kind = _kind(row["from"])
    if kind == "sp":
        sid = row["from"][3:]
        if ctx in corpus.texts.get(sid, ""):
            return Match(MATCH)
        h, b, n = gm._split_sid(sid)
        hits = [corpus.by_pos[(h, b, k)] for k in range(int(n) - NEIGHBORS, int(n) + NEIGHBORS + 1)
                if k != int(n) and (h, b, k) in corpus.by_pos and ctx in corpus.texts[corpus.by_pos[(h, b, k)]]]
        if len(hits) == 1:
            return Match(MOVED, f"sp:{hits[0]}")
        where = "sid が無く" if sid not in corpus.texts else "sid の本文に含まれず"
        return Match(STOPPED, reason=f"{where}、前後{NEIGHBORS}件で {len(hits)} 件" + (f"（{'・'.join(hits)}）" if hits else ""))
    if kind == "bq":
        f = corpus.fields.get(row["from"])
        if f is None:
            return Match(STOPPED, reason="質問が無い")
        if any(ctx in t for t in f.get(row["where"], [])):
            return Match(MATCH)
        return Match(STOPPED, reason=f"欄（{row['where']}）に含まれない")
    raise LedgerError(f"from の形が違う（{row['from']}）")


def match_label(row, corpus):
    """plan・lin の to_label の照合（§5）。node は工程8で足す。"""
    try:
        name = gm.to_label(row["to"], corpus.names, corpus.refs)
    except gm.GenError:
        return Match(STOPPED, reason="to の名称が見つからない")
    if name != row["to_label"]:
        return Match(STOPPED, reason=f"名称が違う（いまの名称：{name}）")
    return Match(MATCH)


@dataclass
class Checked:
    counts: Counter = field(default_factory=Counter)  # 一致・移動・停止の件数（confirmed・candidate）
    moved: list = field(default_factory=list)
    stopped: list = field(default_factory=list)
    rejected_unmatched: list = field(default_factory=list)


def _listed(row, columns, **extra):
    out = {c: row[c] for c in columns if c in row}
    out.update(extra)
    return out


def check_rows(rows, corpus):
    """台帳の全行に §5 の照合をかける。confirmed・candidate は from と to_label、rejected は sp の移動だけ。"""
    ck = Checked()
    for r in rows:
        if r["status"] == REJECTED:
            if _kind(r["from"]) != "sp":
                continue
            m = match_row(r, corpus)
            if m.result == MOVED:
                ck.moved.append(_listed(r, MOVED_COLUMNS, moved_to=m.moved_to))
            elif m.result == STOPPED:
                ck.rejected_unmatched.append(_listed(r, STOPPED_COLUMNS, reason=m.reason))
            continue
        m = match_row(r, corpus)
        if m.result == MATCH:
            m = match_label(r, corpus)
        ck.counts[m.result] += 1
        if m.result == MOVED:
            ck.moved.append(_listed(r, MOVED_COLUMNS, moved_to=m.moved_to))
        elif m.result == STOPPED:
            ck.stopped.append(_listed(r, STOPPED_COLUMNS, reason=m.reason))
    return ck


def mutate_context(context):
    """§11 の sentinel：真ん中（文字数を2で割り、切り捨てた位置）の1文字を「〓」に替える（「〓」があれば「※」）。"""
    mark = SENTINEL_MARKS[0] if SENTINEL_MARKS[0] not in context else SENTINEL_MARKS[1]
    if mark in context:
        raise LedgerError(f"context に「〓」と「※」の両方がある（{context}）")
    i = len(context) // 2
    return context[:i] + mark + context[i + 1:]


def sentinel(rows, corpus):
    """§11：confirmed・candidate の全行で context の1文字を替えて照合し、一致になった行を返す（空なら合格）。"""
    bad = []
    for r in rows:
        if r["status"] == REJECTED:
            continue
        changed = mutate_context(r["context"])
        if match_row(r, corpus, context=changed).result == MATCH:
            bad.append({"from": r["from"], "to": r["to"], "method": r["method"], "context": changed})
    return bad


# ---- 併合（§6） ----

def generated_rows(built):
    """gm.build の結果から、台帳の11列の行を作る（speech_date・scene は台帳に入れない）。"""
    return [{c: r[c] for c in LEDGER_COLUMNS} for r in built.bulletin.candidates + built.minutes.candidates]


@dataclass
class Merged:
    rows: list
    added: list = field(default_factory=list)
    updated: list = field(default_factory=list)       # 11列のどれかが変わった candidate
    removed: list = field(default_factory=list)       # 削除した candidate
    note_changed: list = field(default_factory=list)
    vanished: list = field(default_factory=list)      # 出なくなった confirmed・rejected（移動を除く）。check 列つき
    suppressed: list = field(default_factory=list)    # 移動先なので candidate にしなかった組

    @property
    def vanished_confirmed(self):
        return [r for r in self.vanished if r["status"] == CONFIRMED]


def merge(ledger_rows, gen_rows, corpus):
    """§6：台帳に生成の結果を合わせた新しい台帳を作る。機械は status を confirmed・rejected にしない。"""
    gen = {}
    for r in gen_rows:
        if r["status"] != CANDIDATE or r["reviewer"] or r["date"]:
            raise LedgerError(f"生成の結果が candidate でない（{_key(r)}）")
        if _key(r) in gen:
            raise LedgerError(f"生成の結果で (from, to, method) が重なっている（{_key(r)}）")
        gen[_key(r)] = r
    # 1回目：生成の結果に無い confirmed・rejected の sp の行の移動先を先に決める。
    # 移動先の組は、台帳に candidate の行があっても candidate にしない（続く発言が同じ計画に触れていた場合）
    found = {_key(r): match_row(r, corpus) for r in ledger_rows
             if r["status"] != CANDIDATE and _key(r) not in gen and _kind(r["from"]) == "sp"}
    dests = {k: (m.moved_to, k[1], k[2]) for k, m in found.items() if m.result == MOVED}
    suppressed = {d for d in dests.values() if d in gen}
    out = Merged(rows=[])
    for r in ledger_rows:
        k = _key(r)
        if r["status"] == CANDIDATE:
            if k in suppressed:
                continue
            if k not in gen:
                out.removed.append(r)
                continue
            g = dict(gen[k])
            if g != r:
                out.updated.append(g)
            if g["note"] != r["note"]:
                out.note_changed.append({"from": r["from"], "to": r["to"], "method": r["method"],
                                         "old_note": r["note"], "new_note": g["note"]})
            out.rows.append(g)
            continue
        out.rows.append(r)
        if k in gen:
            continue
        if k in found:
            if dests.get(k) in suppressed:
                continue
            check = found[k].result
        else:
            check = "照合しない" if r["status"] == REJECTED else match_row(r, corpus).result
        out.vanished.append(dict(r, check=check))
    have = {_key(r) for r in out.rows}
    for k, g in gen.items():
        if k in have:
            continue
        if k in suppressed:
            out.suppressed.append(g)
            continue
        out.rows.append(dict(g))
        out.added.append(g)
    out.rows.sort(key=_key)
    return out


# ---- 台帳と lock の版（§6・§11） ----

@dataclass
class Report:
    checked: Checked
    merged: Merged
    stale: list          # 作り直した台帳といまの台帳で違う行（(from, to, method)）
    sentinel_failures: list

    @property
    def exit_code(self):
        bad = (self.checked.stopped or self.merged.vanished_confirmed or self.stale or self.sentinel_failures)
        return 1 if bad else 0


def check_ledger(ledger_rows, gen_rows, corpus):
    """台帳を確かめる（§5・§6・§11）。台帳は parse_ledger を通したものを渡す。"""
    merged = merge(ledger_rows, gen_rows, corpus)
    now = {_key(r): r for r in ledger_rows}
    redo = {_key(r): r for r in merged.rows}
    stale = sorted(k for k in now.keys() | redo.keys() if now.get(k) != redo.get(k))
    return Report(check_rows(ledger_rows, corpus), merged, stale, sentinel(ledger_rows, corpus))


def write_lists(outdir, checked, merged, update):
    """§11 の一覧を build/links/<method>/ に書く。removed・note_changed は更新のときだけ。返り値は書いたファイルの名前。"""
    os.makedirs(outdir, exist_ok=True)
    files = [("moved.tsv", MOVED_COLUMNS, checked.moved),
             ("stopped.tsv", STOPPED_COLUMNS, checked.stopped),
             ("rejected_unmatched.tsv", STOPPED_COLUMNS, checked.rejected_unmatched),
             ("vanished.tsv", VANISHED_COLUMNS, merged.vanished)]
    if update:
        files += [("removed.tsv", LEDGER_COLUMNS, merged.removed),
                  ("note_changed.tsv", NOTE_CHANGED_COLUMNS, merged.note_changed)]
    for name, columns, rows in files:
        with open(os.path.join(outdir, name), "wb") as f:
            f.write(_format(columns, rows))
    return [name for name, _, _ in files]
