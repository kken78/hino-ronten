"""mention の候補を作る（LINK_SCHEMA.md §2・§3・§7・§8・§10、DESIGN.md §5 工程4）。

inputs.lock.json に書いた版の、書いたファイルだけを git show で読み、tools/mention.py の
find_mentions で照合して、候補と一覧を build/mention/ に書く。台帳（links/）には書かない。
ツールが作るのは candidate まで（DESIGN.md ADR-2）。

実行: python3 -B tools/gen_mentions.py
入力の clone の場所は、環境変数 HINO_RONTEN_INPUTS で変えられる（省略時 /home/kken78/GitHub）。
参照表の場所は、環境変数 HINO_RONTEN_LINEAGE・HINO_RONTEN_ALIASES で変えられる（test_mention.py と同じ）。
終了コード：0 は build/mention/ への書き出しまで終えた。1 は入力・参照表の誤りで止めた（件数と該当を表示する）。

工程4-2 で決めた扱い：
- 会議の日付は、meetings.json の各会議の date 項目（hino-council-search #22。LINK_SCHEMA.md §8）。
  dateFrom が pdf の会議は date が日付のある PDF のうち最も早い日（会議の初日）と一致すること、
  dateFrom が name の会議は日付のある PDF が無いことを確かめ、合わなければ止める。date 項目の無い
  会議があれば止める（古い版の meetings.json は使わない）。日付のある PDF が2つの年度にまたがる
  会議は日付なしとする（D1）
- sid に日付が無く、会議の日付も無い（date が null か、D1 で日付なしとした）発言は照合せず、
  no_date.tsv に出す。索引の date 項目は参考として出すだけで、照合には使わない（D2。LINK_SCHEMA.md §8）
- 会議録は role が「議長」と完全に一致する発言だけを除く（D3。§7）
- 会議録の目次の項目（sid の真ん中に mokuji を含むもの）は、発言ではないため照合の対象から除く（§7。2026-10-11 の決定）
- 議会だよりは title・question_text・answer_title・answers の順に欄ごとに照合し、同じ to は最初の欄の
  行を採る。後の欄は note に「ほかに一致した欄」として書く。answers の要素から出た行の where は
  「answers」とする（D4。§3）
- 計画は manifest の name だけを使い、data/plans/*.json は読まない（D5）
- 文脈で決める略称（§7。2026-10-15 の決定）の「同じやりとり」：会議録は、その発言を含む一般質問・議案質疑の
  場面（proceedings.json の segments のうち kind が ippan・shitsugi のもの）で、その発言より前の発言の本文を
  sid の順に渡す（議長の発言や目次の項目も、場面の中にあれば含める）。場面に入らない発言は何も渡さない。
  議会だよりは、同じ問いの中でその欄より前の欄の本文を渡す
"""
import hashlib
import json
import os
import re
import subprocess
import sys
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date as Date
from fnmatch import fnmatchcase

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import mention  # noqa: E402

LOCK_PATH = os.path.join(ROOT, "inputs.lock.json")
OUT_DIR = os.path.join(ROOT, "build", "mention")
INPUTS_ROOT = os.environ.get("HINO_RONTEN_INPUTS", "/home/kken78/GitHub")
LINEAGE = os.environ.get("HINO_RONTEN_LINEAGE", os.path.join(ROOT, "ref", "lineage.tsv"))
ALIASES = os.environ.get("HINO_RONTEN_ALIASES", os.path.join(ROOT, "ref", "aliases.tsv"))

CD, HS, SP, TD = "council-dashboard", "hino-council-search", "shiga-hino-plans", "hino-town-docs"
REPOS = (CD, HS, SP, TD)   # TD は町の公開資料（DESIGN.md ADR-14）。台帳の候補と照合には使わない（LINK_SCHEMA §10）

CANDIDATE_COLUMNS = ["from", "to", "method", "evidence", "where", "context", "to_label",
                     "status", "reviewer", "date", "note", "speech_date", "scene"]
OUT_OF_PERIOD_COLUMNS = ["from", "series", "evidence", "where", "context", "speech_date", "fiscal_year", "scene", "note"]
NO_EDITION_COLUMNS = ["from", "series", "edition", "evidence", "where", "context", "speech_date", "fiscal_year",
                      "scene", "note"]
NO_DATE_COLUMNS = ["from", "meeting_id", "scene", "reason", "matched_series", "index_date"]

BQ_FIELDS = ["title", "question_text", "answer_title", "answers"]  # §3 の where。この順に照合する
CHAIR = "議長"
SCENES = {"ippan": "一般質問", "shitsugi": "議案質疑", "report": "委員長報告", "debate": "討論",
          "proposal": "提案説明", "vote": "採決"}
EXCHANGE_KINDS = ("ippan", "shitsugi")  # §7 文脈で決める略称の「同じやりとり」になる場面
OUTSIDE = "範囲外"
SCENE_ORDER = list(SCENES.values()) + [OUTSIDE]
PROPOSAL = SCENES["proposal"]


class GenError(ValueError):
    """入力の誤り、または出力できない値。件数と該当を示して止める。"""


def _fail(title, items):
    """items が1件以上なら、件数と全件を示して止める。"""
    if items:
        raise GenError(f"{title}：{len(items)} 件\n" + "\n".join(f"  - {x}" for x in items))


# ---- 入力の固定（§10） ----

def load_lock(path):
    """inputs.lock.json を読み、4つのリポジトリ・40桁の sha・files の形を確かめる。"""
    with open(path, encoding="utf-8") as f:
        lock = json.load(f)
    if not isinstance(lock, dict) or sorted(lock) != sorted(REPOS):
        raise GenError(f"{path}: リポジトリが {list(REPOS)} でない")
    for repo in REPOS:
        v = lock[repo]
        if not isinstance(v, dict) or sorted(v) != ["files", "sha"]:
            raise GenError(f"{path}: {repo} の項目が sha・files でない")
        if not isinstance(v["sha"], str) or not re.fullmatch(r"[0-9a-f]{40}", v["sha"]):
            raise GenError(f"{path}: {repo} の sha が40桁の16進数でない（{v['sha']!r}）")
        if not isinstance(v["files"], list) or not all(isinstance(p, str) and p for p in v["files"]):
            raise GenError(f"{path}: {repo} の files が文字列の配列でない")
    return lock


def match_lock(pattern, path):
    """lock の files のパターンにパスが当たるか。「*」はそのディレクトリの直下のファイル名だけに当たる。"""
    if "*" not in pattern:
        return path == pattern
    pdir, _, pbase = pattern.rpartition("/")
    fdir, _, fbase = path.rpartition("/")
    return pdir == fdir and fnmatchcase(fbase, pbase)


class GitInputs:
    """入力のリポジトリを git で読む（読むだけ。§10 の版の、lock に書いたファイルだけ）。"""

    def __init__(self, root, lock):
        self.root = root
        self.lock = lock

    def _check(self, repo, path):
        if repo not in self.lock:
            raise GenError(f"lock に無いリポジトリ（{repo}）")
        if not any(match_lock(p, path) for p in self.lock[repo]["files"]):
            raise GenError(f"lock の files に無いパス（{repo}: {path}）")

    def _git(self, repo, *args):
        r = subprocess.run(["git", "-C", os.path.join(self.root, repo), *args], capture_output=True)
        if r.returncode != 0:
            msg = r.stderr.decode("utf-8", "replace").strip()
            raise GenError(f"{repo}: git {' '.join(args)} が終了コード {r.returncode}（{msg}）")
        return r.stdout

    def verify(self):
        for repo in REPOS:
            self._git(repo, "cat-file", "-e", f"{self.lock[repo]['sha']}^{{commit}}")

    def expand(self, repo, pattern):
        """lock のパターンを、その版にあるファイルのパスに展開する。1件も無ければ止める。"""
        if repo not in self.lock or pattern not in self.lock[repo]["files"]:
            raise GenError(f"lock に無いパターン（{repo}: {pattern}）")
        pdir = pattern.rpartition("/")[0]
        out = self._git(repo, "ls-tree", self.lock[repo]["sha"], "--", (pdir + "/") if pdir else ".")
        paths = []
        for line in out.decode("utf-8").splitlines():
            meta, _, path = line.partition("\t")
            if meta.split()[1] == "blob" and match_lock(pattern, path):
                paths.append(path)
        if not paths:
            raise GenError(f"{repo}@{self.lock[repo]['sha'][:7]}: {pattern} に当たるファイルが無い")
        return sorted(paths)

    def read_bytes(self, repo, path):
        self._check(repo, path)
        return self._git(repo, "show", f"{self.lock[repo]['sha']}:{path}")

    def read_json(self, repo, path):
        return json.loads(self.read_bytes(repo, path).decode("utf-8"))


# ---- キー・日付・場面・計画 ----

def member_key(member):
    """§2 の bq の議員名：NFKC 正規化し、空白を除いたもの。"""
    return re.sub(mention.JS_WHITESPACE, "", unicodedata.normalize("NFKC", member))


def bq_key(q):
    return f"bq:{q['issue']}/{member_key(q['member'])}/{q['q_num']}"


def _split_sid(sid):
    """sid を（会議ID、真ん中、連番）に分ける。真ん中には「_」が入ることがある（9_kaigiroku など）。"""
    head, _, rest = sid.partition("_")
    body, _, num = rest.rpartition("_")
    if not re.fullmatch(r"[0-9]{10}", head) or not body or not re.fullmatch(r"[0-9]{4}", num):
        raise GenError(f"sid の形が違う（{sid}）")
    return head, body, num


def sid_date(sid):
    """sid の真ん中が8桁の数字なら、その日付。8桁でなければ None。8桁で日付として正しくなければ止める。"""
    body = _split_sid(sid)[1]
    if not re.fullmatch(r"[0-9]{8}", body):
        return None
    try:
        return Date(int(body[:4]), int(body[4:6]), int(body[6:]))
    except ValueError:
        raise GenError(f"sid の日付が正しくない（{sid}）") from None


def is_toc(sid):
    """目次（会議録の目次 PDF から作られた項目）か。"""
    return "mokuji" in _split_sid(sid)[1]


def _iso_date(value, where):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
        raise GenError(f"{where}: 日付が YYYY-MM-DD でない（{value!r}）")
    try:
        return Date.fromisoformat(value)
    except ValueError:
        raise GenError(f"{where}: 日付が正しくない（{value}）") from None


def meeting_dates(meetings):
    """会議ID →（会議の日付、日付が無い理由）。会議の日付は meetings.json の date 項目（§8）。
    dateFrom が pdf なら日付のある PDF のうち最も早い日と、name なら日付のある PDF が無いことと照らし、
    合わなければ止める。日付のある PDF が2つ以上の年度にまたがる会議は日付なしとする（D1）。"""
    out = {}
    missing, mismatch = [], []
    for m in meetings:
        mid = m["id"]
        if mid in out:
            raise GenError(f"meetings.json: 会議IDが重なっている（{mid}）")
        out[mid] = (None, "")
        if "date" not in m or "dateFrom" not in m:
            missing.append(mid)
            continue
        days = sorted({_iso_date(p["date"], f"meetings.json {mid}") for p in m["pdfs"] if p.get("date") is not None})
        src = m["dateFrom"]
        if m["date"] is None:
            if src is not None or days:
                mismatch.append(f"{mid}：date が null なのに、dateFrom が {src!r}、日付のある PDF が {len(days)} 件")
                continue
            out[mid] = (None, f"meetings.json の会議 {mid} に日付が無い（date が null）")
            continue
        md = _iso_date(m["date"], f"meetings.json {mid} の date")
        if src == "pdf":
            if not days or md != days[0]:
                first = days[0].isoformat() if days else "なし"
                mismatch.append(f"{mid}：dateFrom が pdf で date {md.isoformat()}、日付のある PDF の最も早い日 {first}")
                continue
        elif src == "name":
            if days:
                mismatch.append(f"{mid}：dateFrom が name なのに、日付のある PDF が {len(days)} 件")
                continue
        else:
            mismatch.append(f"{mid}：dateFrom が pdf・name でない（{src!r}）")
            continue
        years = sorted({mention.fiscal_year(d) for d in days})
        if len(years) > 1:
            out[mid] = (None, f"会議 {mid} の日付が2つ以上の年度にまたがる（{'・'.join(map(str, years))}年度）")
            continue
        out[mid] = (md, "")
    _fail("meetings.json: date・dateFrom 項目の無い会議（古い版の meetings.json は使わない）", missing)
    _fail("meetings.json: date・dateFrom が PDF の日付と合わない会議", mismatch)
    return out


def speech_date(entry, mdates):
    """会議録の発言日（§8）：sid の日付 → 会議の日付。どちらも無ければ（None、理由）。"""
    sid = entry["sid"]
    head = _split_sid(sid)[0]
    if entry.get("meetingId") != head:
        raise GenError(f"sid の会議IDと meetingId が違う（{sid}・{entry.get('meetingId')}）")
    if head not in mdates:
        raise GenError(f"meetings.json に無い会議（{sid}）")
    d = sid_date(sid)
    if d is not None:
        return d, ""
    md, reason = mdates[head]
    if md is not None:
        return md, ""
    return None, f"sid に日付が無く、{reason}"


def question_date(q, minutes_links, mdates):
    """議会だよりの発言日（§8）：minutes_links.json の meeting_id の会議の日付。
    返り値は（会議ID、日付、日付が無い理由）。対応する会議が無ければ（""、None、理由）。"""
    issue = minutes_links.get(str(q["issue"]), {})
    hits = [v for k, v in sorted(issue.items()) if member_key(k) == member_key(q["member"])]
    if len(hits) > 1:
        raise GenError(f"minutes_links.json: {q['issue']}号の {q['member']} が2つ以上ある")
    if not hits:
        return "", None, f"minutes_links.json に {q['issue']}号の {q['member']} の会議が無い"
    mid = hits[0].get("meeting_id")
    if mid not in mdates:
        raise GenError(f"minutes_links.json: meetings.json に無い会議（{q['issue']}号 {q['member']}：{mid}）")
    d, reason = mdates[mid]
    return mid, d, reason


def scene_of(index, proceedings):
    """sid → 場面。proceedings.json の場面の範囲を索引の並びに当て、from〜to の両端を含む。採決は sid の1件。
    どの範囲にも入らない sid は返さない（呼ぶ側で OUTSIDE とする）。"""
    pos = {}
    for i, e in enumerate(index):
        if e["sid"] in pos:
            raise GenError(f"索引で sid が重なっている（{e['sid']}）")
        pos[e["sid"]] = i
    scenes, errors = {}, []
    for mid in sorted(proceedings):
        for n, sg in enumerate(proceedings[mid].get("segments") or []):
            at = f"{mid} の場面 {n}"
            kind = sg.get("kind")
            if kind not in SCENES:
                errors.append(f"{at}：未知の場面（{kind}）")
                continue
            ends = (sg.get("sid"), sg.get("sid")) if kind == "vote" else (sg.get("from"), sg.get("to"))
            a, b = pos.get(ends[0]), pos.get(ends[1])
            if a is None or b is None:
                errors.append(f"{at}：範囲の端が索引に無い（{ends[0]}〜{ends[1]}）")
                continue
            if a > b:
                errors.append(f"{at}：from が to より後（{ends[0]}〜{ends[1]}）")
                continue
            for k in range(a, b + 1):
                sid = index[k]["sid"]
                if index[k]["meetingId"] != mid:
                    errors.append(f"{at}：別の会議の発言を含む（{sid}）")
                elif sid in scenes:
                    errors.append(f"{at}：場面が重なっている（{sid}）")
                else:
                    scenes[sid] = SCENES[kind]
    _fail("proceedings.json の場面の誤り", errors)
    return scenes


def exchanges_of(index, proceedings):
    """§7 文脈で決める略称の「同じやりとり」：sid → その発言を含む一般質問・議案質疑の場面の
    （sid、本文）を sid の順に並べたもの。場面の誤りは scene_of で確かめるため、先に scene_of を呼ぶ。"""
    pos = {e["sid"]: i for i, e in enumerate(index)}
    out = {}
    for mid in sorted(proceedings):
        for sg in proceedings[mid].get("segments") or []:
            if sg.get("kind") not in EXCHANGE_KINDS:
                continue
            group = sorted((index[k]["sid"], index[k].get("text") or "")
                           for k in range(pos[sg["from"]], pos[sg["to"]] + 1))
            for sid, _ in group:
                out[sid] = group
    return out


def plan_names(manifest, refs):
    """manifest の id → name。系譜表の plan と manifest の id が食い違えば止める（§8：43本を全件載せる）。"""
    names = {}
    for p in manifest["plans"]:
        if not p.get("id") or not p.get("name"):
            raise GenError(f"manifest.json: id か name が空（{p.get('id')!r}）")
        if p["id"] in names:
            raise GenError(f"manifest.json: id が重なっている（{p['id']}）")
        names[p["id"]] = p["name"]
    lineage_plans = {r.plan for r in refs.lineage if r.plan}
    _fail("系譜表の plan が manifest に無い", sorted(lineage_plans - names.keys()))
    _fail("manifest の id が系譜表に無い", sorted(names.keys() - lineage_plans))
    return names


def manifest_plan_paths(manifest, listed):
    """data/plans/*.json のうち、manifest に id があるものだけ（_charttest.json などは入らない。D5）。"""
    ids = {p["id"] for p in manifest["plans"]}
    return sorted(p for p in listed
                  if p.startswith("data/plans/") and p.endswith(".json") and p[len("data/plans/"):-len(".json")] in ids)


def to_label(to, names, refs):
    """§3：plan は manifest の name、lin は系譜表の name。"""
    if to.startswith("plan:") and to[len("plan:"):] in names:
        return names[to[len("plan:"):]]
    if to.startswith("lin:"):
        series, _, edition = to[len("lin:"):].partition("/")
        row = refs.edition_row(series, edition)
        if row is not None and not row.plan:
            return row.name
    raise GenError(f"to の名称が見つからない（{to}）")


def _terms_in(text, refs):
    """§7 の最長一致で、除外の語を除いた一致（開始、終了、Term）。文脈語は照合の語に使わない。"""
    return [m for m in mention._longest_matches(mention.normalize(text), refs.match_terms)
            if m[2].kind != mention.EXCLUDE]


def matched_series(texts, refs):
    """別名辞書の語（除外・文脈語を除く）に一致した series。並びは series の名前順（コードポイント順）で、
    「、」でつなぐ。文脈で決める略称は、その語の series とする（照合はしないため、文脈では決めない）。"""
    return "、".join(sorted({t.series for text in texts for _, _, t in _terms_in(text, refs)}))


# ---- 候補の生成 ----

@dataclass
class Gen:
    candidates: list = field(default_factory=list)
    out_of_period: list = field(default_factory=list)
    no_edition: list = field(default_factory=list)
    no_date: list = field(default_factory=list)
    undetermined: list = field(default_factory=list)
    trace: list = field(default_factory=list)  # 報告の d 用：(from, to, series, 期の明記か, 期間不明か, evidence, context)


def _row_key(columns):
    return lambda row: tuple(row[c] for c in columns)


def base_note(note):
    """note の先頭の「文脈で決めた（手がかり：…）。」を除いたもの（期の明記・期間不明の判定用）。"""
    return mention.CONTEXT_NOTE.sub("", note)


def _match(gen, from_key, parts, day, scene, refs, names, before=()):
    """parts（where、本文）の順に find_mentions を当て、gen に行を足す。同じ to は最初の欄の行を採る。
    before は同じやりとりの中で parts より前の本文。後の欄には、前の欄の本文も before として渡す（§7）。"""
    cands, listed = {}, {}
    prior = list(before)
    for where, text in parts:
        r = mention.find_mentions(text, day, refs, prior)
        prior.append(text)
        for m in r.rows:
            note = base_note(m.note)
            gen.trace.append((from_key, m.to, m.series, note.startswith("期の明記"), note.startswith("期間不明"),
                              m.evidence, m.context))
            if m.to in cands:
                row, others = cands[m.to]
                if where != row["where"] and where not in others:
                    others.append(where)
                continue
            cands[m.to] = ({"from": from_key, "to": m.to, "method": "mention", "evidence": m.evidence,
                            "where": where, "context": m.context, "to_label": to_label(m.to, names, refs),
                            "status": "candidate", "reviewer": "", "date": "", "note": m.note,
                            "speech_date": day.isoformat(), "scene": scene}, [])
        for kind, items in (("out_of_period", r.out_of_period), ("no_edition", r.no_edition),
                            ("undetermined", r.undetermined)):
            for x in items:
                k = (kind, x.series, x.edition)
                if k in listed:
                    continue
                listed[k] = True
                row = {"from": from_key, "series": x.series, "evidence": x.evidence, "where": where,
                       "context": x.context, "speech_date": day.isoformat(), "fiscal_year": str(x.fiscal_year),
                       "scene": scene, "note": x.note}
                if kind == "no_edition":
                    row["edition"] = x.edition
                getattr(gen, kind).append(row)
    for row, others in cands.values():
        if others:
            row["note"] = f"{row['note']}。ほかに一致した欄：{'・'.join(others)}"
        gen.candidates.append(row)


def _sort(gen):
    gen.candidates.sort(key=_row_key(CANDIDATE_COLUMNS))
    gen.out_of_period.sort(key=_row_key(OUT_OF_PERIOD_COLUMNS))
    gen.no_edition.sort(key=_row_key(NO_EDITION_COLUMNS))
    gen.no_date.sort(key=_row_key(NO_DATE_COLUMNS))
    gen.undetermined.sort(key=_row_key(OUT_OF_PERIOD_COLUMNS))
    return gen


def _bq_parts(q):
    """照合する欄（where、本文）。other と answers の label は照合しない。"""
    parts = []
    for name in BQ_FIELDS:
        if name not in q:
            continue
        if name == "answers":
            if not isinstance(q["answers"], list):
                raise GenError(f"{bq_key(q)}: answers が配列でない")
            texts = [a.get("text") for a in q["answers"]]
        else:
            texts = [q[name]]
        for t in texts:
            if not isinstance(t, str):
                raise GenError(f"{bq_key(q)}: {name} が文字列でない")
            if t:
                parts.append((name, t))
    return parts


def gen_bulletin(questions, minutes_links, mdates, refs, names):
    """議会だより：質問ごとに欄の順で照合する。対応する会議の日付が無い質問は照合せず no_date に出す。"""
    gen, seen = Gen(), set()
    for q in questions:
        key = bq_key(q)
        if key in seen:
            raise GenError(f"questions.json: bq のキーが重なっている（{key}）")
        seen.add(key)
        parts = _bq_parts(q)
        mid, day, reason = question_date(q, minutes_links, mdates)
        if day is None:
            gen.no_date.append({"from": key, "meeting_id": mid, "scene": "", "reason": reason,
                                "matched_series": matched_series([t for _, t in parts], refs), "index_date": ""})
            continue
        _match(gen, key, parts, day, "", refs, names)
    return _sort(gen)


def gen_minutes(index, mdates, scenes, refs, names, exchanges=None):
    """会議録：role が「議長」の発言と目次の項目を除き、発言ごとに照合する。発言日が無い発言は照合せず no_date に出す。
    exchanges（exchanges_of の結果）で、同じやりとりの中でその発言より前の発言の本文を before として渡す（§7）。"""
    gen, seen = Gen(), set()
    exchanges = exchanges or {}
    for e in index:
        sid = e["sid"]
        if sid in seen:
            raise GenError(f"索引で sid が重なっている（{sid}）")
        seen.add(sid)
        if e.get("role") == CHAIR or is_toc(sid):
            continue
        key = f"sp:{sid}"
        scene = scenes.get(sid, OUTSIDE)
        day, reason = speech_date(e, mdates)
        if day is None:
            gen.no_date.append({"from": key, "meeting_id": e["meetingId"], "scene": scene, "reason": reason,
                                "matched_series": matched_series([e.get("text") or ""], refs),
                                "index_date": e.get("date") or ""})
            continue
        before = [t for x, t in exchanges.get(sid, []) if x < sid]
        _match(gen, key, [("text", e.get("text") or "")], day, scene, refs, names, before)
    return _sort(gen)


# ---- 出力 ----

def write_tsv(path, columns, rows):
    """§1 の形（UTF-8・BOMなし・LF・1行目がヘッダ）で書く。行は列の順の文字コード順に並べる。"""
    bad = []
    for n, row in enumerate(rows):
        if sorted(row) != sorted(columns):
            bad.append(f"{n}: 列が {columns} でない（{sorted(row)}）")
            continue
        for c in columns:
            v = row[c]
            if not isinstance(v, str) or any(ch in v for ch in "\t\n\r"):
                bad.append(f"{n}: {c} が文字列でないか、タブ・改行を含む（{v!r}）")
    _fail(f"{path} に書けない値", bad)
    lines = ["\t".join(columns)] + ["\t".join(r[c] for c in columns) for r in sorted(rows, key=_row_key(columns))]
    with open(path, "wb") as f:
        f.write(("\n".join(lines) + "\n").encode("utf-8"))


@dataclass
class Inputs:
    lock: dict
    questions: list
    minutes_links: dict
    meetings: list
    index: list
    proceedings: dict
    manifest: dict
    plan_listing: list
    ref_hashes: dict


@dataclass
class Built:
    inputs: Inputs
    refs: object
    bulletin: Gen
    minutes: Gen
    scenes: dict


def build(inp, refs):
    names = plan_names(inp.manifest, refs)
    mdates = meeting_dates(inp.meetings)
    scenes = scene_of(inp.index, inp.proceedings)
    exchanges = exchanges_of(inp.index, inp.proceedings)
    bulletin = gen_bulletin(inp.questions, inp.minutes_links, mdates, refs, names)
    minutes = gen_minutes(inp.index, mdates, scenes, refs, names, exchanges)
    return Built(inp, refs, bulletin, minutes, scenes)


def write_outputs(outdir, built):
    """build/mention/ の6つのファイルを書く。返り値は書いたファイルの名前。"""
    os.makedirs(outdir, exist_ok=True)
    b, m = built.bulletin, built.minutes
    files = [("candidates.tsv", CANDIDATE_COLUMNS, b.candidates + m.candidates),
             ("out_of_period.tsv", OUT_OF_PERIOD_COLUMNS, b.out_of_period + m.out_of_period),
             ("no_edition.tsv", NO_EDITION_COLUMNS, b.no_edition + m.no_edition),
             ("no_date.tsv", NO_DATE_COLUMNS, b.no_date + m.no_date),
             ("undetermined.tsv", OUT_OF_PERIOD_COLUMNS, b.undetermined + m.undetermined)]
    for name, columns, rows in files:
        write_tsv(os.path.join(outdir, name), columns, rows)
    with open(os.path.join(outdir, "report.md"), "wb") as f:
        f.write(("\n".join(report_lines(built)) + "\n").encode("utf-8"))
    return [name for name, _, _ in files] + ["report.md"]


# ---- 報告（report.md） ----

EXAMPLES = 5
EDITION_FORM = re.compile(r"第" + mention.NUMBER + r"([期次])(「|の)(?:日野町)?$")


def _examples(rows, n=EXAMPLES):
    """例：並べた行から等間隔に n 件（同じ入力なら同じ行を選ぶ）。"""
    return list(rows) if len(rows) <= n else [rows[i * len(rows) // n] for i in range(n)]


def _cell(v):
    return str(v).replace("|", "\\|")


def _table(header, rows):
    out = ["| " + " | ".join(header) + " |", "| " + " | ".join("---" for _ in header) + " |"]
    out += ["| " + " | ".join(_cell(v) for v in r) + " |" for r in rows]
    return out


def _example_table(rows, to_col="to"):
    return _table(["from", to_col, "evidence", "context"],
                  [(r["from"], r[to_col], r["evidence"], r["context"]) for r in _examples(rows)])


def _targets(built):
    """報告の d 用：照合の対象（議会だよりの各欄・議長と目次を除く発言）を（from、where、本文）で返す。"""
    for q in built.inputs.questions:
        for where, text in _bq_parts(q):
            yield bq_key(q), where, text
    for e in built.inputs.index:
        if e.get("role") != CHAIR and not is_toc(e["sid"]):
            yield f"sp:{e['sid']}", "text", e.get("text") or ""


def _edition_forms(built):
    """計画名の直前が「第N期「」「第N次「」「第N期の」「第N次の」の形の箇所
    （LINK_SCHEMA §7 の 2026-10-11 の決定で、期の明記として読む形）。"""
    found = []
    for from_key, where, text in _targets(built):
        norm = mention.normalize(text)
        for s, e, t in _terms_in(text, built.refs):
            m = EDITION_FORM.search(norm[:s])
            if m:
                found.append({"from": from_key, "series": t.series, "form": f"第N{m.group(2)}{m.group(3)}",
                              "evidence": t.term, "context": norm[max(0, m.start() - 5):e + mention.CONTEXT_CHARS]})
    return found


def _drafting(built, rows):
    """候補のうち、計画期間の前の行（note に「計画期間の前（」を含む。§7）。series は to の系譜表の行から求める。"""
    series_of = {x.key: x.series for x in built.refs.lineage}
    out = []
    for r in rows:
        if "計画期間の前（" in r["note"]:
            s = series_of[r["to"]]
            starts = [x.start_fy for x in built.refs.rows_of(s) if x.start_fy is not None]
            out.append(dict(r, series=s, first_start=str(min(starts))))
    return out


def _mixed(gen):
    """同じ発言の同じ series に、期の明記で決まった行と、発言日で決まった別の to の行があるもの。"""
    by = defaultdict(lambda: ([], []))
    for from_key, to, series, explicit, unknown, evidence, context in gen.trace:
        if explicit:
            by[(from_key, series)][0].append((to, evidence, context))
        elif not unknown:
            by[(from_key, series)][1].append((to, evidence, context))
    out = []
    for (from_key, series), (exp, dated) in sorted(by.items()):
        exp_tos = {t for t, _, _ in exp}
        other = [x for x in dated if x[0] not in exp_tos]
        if exp and other:
            out.append({"from": from_key, "series": series, "explicit": exp[0], "dated": other[0]})
    return out


def _approx_proposal(questions, manifest, fields):
    """参考：設計案の試算の方法の近似。manifest の name から「第N期／第N次」「日野町」括弧書き・空白を除いた語を、
    NFKC 正規化した欄に部分一致で当てる（最長一致・除外・日付は使わない）。"""
    terms = {}
    for p in manifest["plans"]:
        t = unicodedata.normalize("NFKC", p["name"])
        t = re.sub(r"第[0-9一二三四五六七八九十]+[期次]", "", t)
        t = re.sub(r"\([^)]*\)", "", t.replace("日野町", ""))
        t = re.sub(mention.JS_WHITESPACE, "", t)
        if t:
            terms[p["id"]] = t
    hit = {}
    for q in questions:
        texts = []
        for name in fields:
            v = q.get(name)
            if isinstance(v, list):
                texts += [a.get("text") or "" for a in v]
            elif isinstance(v, str):
                texts.append(v)
        body = re.sub(mention.JS_WHITESPACE, "", unicodedata.normalize("NFKC", "".join(texts)))
        ids = sorted(i for i, t in terms.items() if t in body)
        if ids:
            hit[bq_key(q)] = ids
    return hit


def report_lines(built):
    inp, refs, b, m = built.inputs, built.refs, built.bulletin, built.minutes
    L = ["# mention の候補（工程4-2）", "",
         "tools/gen_mentions.py が作った報告。台帳（links/）には書いていない。候補は人が確かめるまで出力に使わない。", ""]
    L += ["## 入力と参照表", ""]
    L += _table(["入力", "版"], [(r, inp.lock[r]["sha"]) for r in REPOS]) + [""]
    L += _table(["ファイル", "sha256"], sorted(inp.ref_hashes.items())) + [""]
    unread = sorted(p for p in inp.plan_listing if p not in manifest_plan_paths(inp.manifest, inp.plan_listing))
    L += ["## 前提", "",
          "- 議会だよりの行の speech_date は、minutes_links.json の会議の初日（meetings.json の date 項目。"
          "日付のある PDF のうち最も早い日、日付のある PDF が無い会議は会議名の日付）で、質問の当日ではない。"
          "日付のある PDF が2つ以上の年度にまたがる会議は日付なしとした（D1）",
          "- 会議録で除いたのは、role が「議長」と完全に一致する発言だけ（LINK_SCHEMA §7）。hino-council-search の"
          "MCP は「議長」で終わる role を除いており、範囲が違う（D3）。除いていない role は b の表のとおり",
          "- 日付なしの行（sid に日付が無く、会議の日付も無いもの。会議の date が null か、D1 で日付なしとした会議）は照合していない。索引の date 項目は参考"
          "として no_date.tsv に出すだけで、照合には使っていない（D2）",
          "- 計画は manifest の name だけを使い、data/plans/*.json は読んでいない。manifest に無いため読まない"
          f"ファイル：{'、'.join(unread) if unread else 'なし'}（D5）", ""]

    # a. 議会だより
    qkeys = [bq_key(q) for q in inp.questions]
    nodate_q = {r["from"] for r in b.no_date}
    with_cand = {r["from"] for r in b.candidates}
    listed_only = ({r["from"] for r in b.out_of_period + b.no_edition}) - with_cand
    nodate_hit = {r["from"] for r in b.no_date if r["matched_series"]}
    any_hit = with_cand | listed_only | nodate_hit
    L += ["## a. 議会だより", "",
          f"- 質問 {len(qkeys)} 問。照合した質問 {len(qkeys) - len(nodate_q)} 問、日付なし（照合していない） {len(nodate_q)} 問",
          f"- 候補の行数 {len(b.candidates)}、候補が1つ以上ある質問 {len(with_cand)} 問",
          f"- 計画名（別名辞書の語）を含む質問 {len(any_hit)} 問 ＝ 候補あり {len(with_cand)} ＋ 期間外・期の行なしだけ "
          f"{len(listed_only)} ＋ 日付なしで語に一致 {len(nodate_hit)}", ""]
    L += ["where 別の候補の行数：", ""]
    L += _table(["where", "行数"], [(w, Counter(r["where"] for r in b.candidates)[w]) for w in BQ_FIELDS]) + [""]

    # 試算（59問）との比較
    four = _approx_proposal(inp.questions, inp.manifest, BQ_FIELDS)
    five = _approx_proposal(inp.questions, inp.manifest, BQ_FIELDS + ["other"])
    L += ["設計案の試算（59問）との比較：", "",
          f"- 参考：設計案の方法の近似（manifest の name から「第N期」「日野町」括弧書きを除いた語の部分一致）で数えると、"
          f"4つの欄で {len(four)} 問、other を加えた5つの欄で {len(five)} 問",
          f"- 近似（4つの欄）にあって、別名辞書の語を含む質問に無いもの {len(set(four) - any_hit)} 問、"
          f"逆に別名辞書の語を含む質問にあって近似に無いもの {len(any_hit - set(four))} 問", ""]
    gone = sorted(set(four) - any_hit)
    if gone:
        L += ["近似にあって別名辞書の語を含む質問に無いもの（近似で当たった計画）：", ""]
        L += _table(["from", "近似で当たった計画"], [(k, "、".join(four[k])) for k in _examples(gone, len(gone))]) + [""]
    added = sorted(any_hit - set(four))
    if added:
        cand_to = defaultdict(list)
        for r in b.candidates + b.out_of_period + b.no_edition:
            cand_to[r["from"]].append(r["evidence"])
        L += ["別名辞書の語を含む質問にあって近似に無いもの（一致した語）：", ""]
        L += _table(["from", "一致した語"],
                    [(k, "、".join(sorted(set(cand_to.get(k, []))))
                      or next(r["matched_series"] for r in b.no_date if r["from"] == k)) for k in added]) + [""]

    # 計画ごとの件数
    bt, mt = Counter(r["to"] for r in b.candidates), Counter(r["to"] for r in m.candidates)
    mp = Counter(r["to"] for r in m.candidates if r["scene"] != PROPOSAL)
    labels = {r["to"]: r["to_label"] for r in b.candidates + m.candidates}
    L += ["計画ごとの候補の行数（会議録の列は b の参考）：", ""]
    L += _table(["to", "to_label", "議会だより", "会議録", "会議録（提案説明を除く）"],
                [(t, labels[t], bt[t], mt[t], mp[t]) for t in sorted(labels)]) + [""]
    L += ["議会だよりの候補の例：", ""] + _example_table(b.candidates) + [""]

    # b. 会議録
    tocs = [e for e in inp.index if e.get("role") != CHAIR and is_toc(e["sid"])]
    nonchair = [e for e in inp.index if e.get("role") != CHAIR and not is_toc(e["sid"])]
    sc_all = Counter(built.scenes.get(e["sid"], OUTSIDE) for e in nonchair)
    sc_rows = Counter(r["scene"] for r in m.candidates)
    sc_from = Counter(s for s, _ in {(r["scene"], r["from"]) for r in m.candidates})
    sc_nd = Counter(r["scene"] for r in m.no_date)
    L += ["## b. 会議録", "",
          f"- 索引 {len(inp.index)} 件のうち、role が「議長」の {len(inp.index) - len(nonchair) - len(tocs)} 件と"
          f"目次の項目 {len(tocs)} 件を除いた {len(nonchair)} 件が対象。うち日付なし（照合していない） {len(m.no_date)} 件",
          f"- 候補の行数 {len(m.candidates)}、候補のある発言 {len({r['from'] for r in m.candidates})} 件",
          f"- 提案説明を除いた候補の行数 {len(m.candidates) - sc_rows[PROPOSAL]}", ""]
    L += _table(["場面", "対象の発言", "うち日付なし", "候補の行数", "候補のある発言"],
                [(s, sc_all[s], sc_nd[s], sc_rows[s], sc_from[s]) for s in SCENE_ORDER]
                + [("計", sum(sc_all.values()), len(m.no_date), len(m.candidates),
                    len({r["from"] for r in m.candidates}))]) + [""]
    role = {f"sp:{e['sid']}": e.get("role") or "" for e in inp.index}
    chairish = Counter(role[r["from"]] for r in m.candidates if role[r["from"]].endswith(CHAIR) and role[r["from"]] != CHAIR)
    chair_all = Counter(e["role"] for e in nonchair if (e.get("role") or "").endswith(CHAIR))
    L += ["「議長」で終わる role のうち除いていないもの（D3）：", ""]
    L += _table(["role", "発言数", "候補の行数"], [(r, chair_all[r], chairish[r]) for r in sorted(chair_all)]) + [""]
    L += ["目次（sid の真ん中に mokuji を含む項目。発言ではないため照合の対象から除く。LINK_SCHEMA §7）：", "",
          f"- 除いた目次の項目 {len(tocs)} 件", ""]
    L += ["会議録の候補の例（提案説明を除く）：", ""] + _example_table([r for r in m.candidates if r["scene"] != PROPOSAL]) + [""]

    # c. 一覧の件数
    L += ["## c. 期間外・期の行なし・日付なし・期間不明・文脈で決めた行・文脈で決まらない", ""]
    for title, rows_b, rows_m, keyf in (
            ("期間外（series ごと）", b.out_of_period, m.out_of_period, lambda r: r["series"]),
            ("期の行なし（series／明記された期ごと）", b.no_edition, m.no_edition, lambda r: f"{r['series']}／{r['edition']}"),
            ("期間不明（to ごと。candidates.tsv の note が「期間不明」の行）",
             [r for r in b.candidates if base_note(r["note"]).startswith("期間不明")],
             [r for r in m.candidates if base_note(r["note"]).startswith("期間不明")], lambda r: r["to"]),
            ("文脈で決めた候補（to ごと。candidates.tsv の note が「文脈で決めた」で始まる行。LINK_SCHEMA §7）",
             [r for r in b.candidates if r["note"] != base_note(r["note"])],
             [r for r in m.candidates if r["note"] != base_note(r["note"])], lambda r: r["to"]),
            ("文脈で決まらない（一致した語の series ごと。undetermined.tsv）", b.undetermined, m.undetermined,
             lambda r: r["series"])):
        cb, cm = Counter(map(keyf, rows_b)), Counter(map(keyf, rows_m))
        L += [f"{title}：議会だより {len(rows_b)} 行、会議録 {len(rows_m)} 行", ""]
        L += _table(["計画", "議会だより", "会議録"], [(k, cb[k], cm[k]) for k in sorted(set(cb) | set(cm))]) + [""]
        to_col = "to" if "to" in (rows_b + rows_m + [{}])[0] else "series"
        L += ["例：", ""] + _example_table(rows_b + rows_m, to_col) + [""]
    nb = Counter(s for r in b.no_date for s in r["matched_series"].split("、") if s)
    nm = Counter(s for r in m.no_date for s in r["matched_series"].split("、") if s)
    L += [f"日付なし：議会だより {len(b.no_date)} 行（うち語に一致 {sum(1 for r in b.no_date if r['matched_series'])}）、"
          f"会議録 {len(m.no_date)} 行（うち語に一致 {sum(1 for r in m.no_date if r['matched_series'])}）。"
          "series ごとの件数は matched_series による（照合はしていない）", ""]
    L += _table(["series", "議会だより", "会議録"], [(k, nb[k], nm[k]) for k in sorted(set(nb) | set(nm))]) + [""]
    L += _table(["理由", "行数"], sorted(Counter(r["reason"] for r in b.no_date + m.no_date).items())) + [""]

    # d. 論点の材料
    forms = _edition_forms(built)
    L += ["## d. 論点の材料", "",
          f"### 計画名の直前が「第N期「」「第N次「」「第N期の」「第N次の」の形（2026-10-11 から期の明記として読む）：{len(forms)} 箇所", ""]
    L += _table(["形", "議会だより", "会議録"],
                [(f, sum(1 for x in forms if x["form"] == f and x["from"].startswith("bq:")),
                  sum(1 for x in forms if x["form"] == f and x["from"].startswith("sp:")))
                 for f in sorted({x["form"] for x in forms})]) + [""]
    L += ["例：", ""] + _example_table(forms, "series") + [""]
    drafting = _drafting(built, b.candidates + m.candidates)
    db = Counter(r["series"] for r in drafting if r["from"].startswith("bq:"))
    dm = Counter(r["series"] for r in drafting if r["from"].startswith("sp:"))
    L += [f"### 候補のうち、計画期間の前の行（note に「計画期間の前（」を含む。LINK_SCHEMA §7）：{len(drafting)} 行", ""]
    first = {r["series"]: r["first_start"] for r in drafting}
    L += _table(["series", "最初の期の開始年度", "議会だより", "会議録"],
                [(s, first[s], db[s], dm[s]) for s in sorted(first)]) + [""]
    L += ["例：", ""] + _example_table(drafting, "series") + [""]
    mixed = _mixed(b) + _mixed(m)
    L += [f"### 同じ発言の同じ series に、期の明記で決まった行と発言日で決まった別の期の行がある：{len(mixed)} 件"
          f"（議会だより {len(_mixed(b))}、会議録 {len(_mixed(m))}）", ""]
    L += _table(["from", "series", "期の明記で決まった to", "context", "発言日で決まった to", "context"],
                [(x["from"], x["series"], x["explicit"][0], x["explicit"][2], x["dated"][0], x["dated"][2])
                 for x in _examples(mixed)]) + [""]
    return L


# ---- 実行 ----

def _sha256(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def read_inputs(gi, lock):
    questions = gi.read_json(CD, "docs/data/questions.json")["questions"]
    minutes_links = gi.read_json(CD, "data/minutes_links.json")
    im = gi.read_json(HS, "public/data/index-manifest.json")
    shards = [f"public/data/{s['file']}" for s in im["shards"]]
    listed = gi.expand(HS, "public/data/index/*.json")
    if sorted(shards) != listed:
        raise GenError(f"index-manifest.json の shards と index/*.json が違う（{sorted(shards)}・{listed}）")
    index = [e for p in shards for e in gi.read_json(HS, p)]
    if len(index) != im["total"]:
        raise GenError(f"索引の件数 {len(index)} が index-manifest.json の total {im['total']} と違う")
    return Inputs(
        lock=lock, questions=questions, minutes_links=minutes_links,
        meetings=gi.read_json(HS, "public/data/meetings.json"), index=index,
        proceedings=gi.read_json(HS, "public/data/proceedings.json"),
        manifest=gi.read_json(SP, "data/manifest.json"), plan_listing=gi.expand(SP, "data/plans/*.json"),
        ref_hashes={"ref/lineage.tsv": _sha256(LINEAGE), "ref/aliases.tsv": _sha256(ALIASES),
                    "tools/mention.py": _sha256(mention.__file__)})


def main():
    try:
        refs = mention.load_refs(LINEAGE, ALIASES)
        lock = load_lock(LOCK_PATH)
        gi = GitInputs(INPUTS_ROOT, lock)
        gi.verify()
        built = build(read_inputs(gi, lock), refs)
        names = write_outputs(OUT_DIR, built)
    except (GenError, mention.RefError) as e:
        print(f"停止：{e}", file=sys.stderr)
        return 1
    b, m = built.bulletin, built.minutes
    print(f"議会だより：候補 {len(b.candidates)}・期間外 {len(b.out_of_period)}・期の行なし {len(b.no_edition)}・"
          f"日付なし {len(b.no_date)}・文脈で決まらない {len(b.undetermined)}")
    print(f"会議録：候補 {len(m.candidates)}・期間外 {len(m.out_of_period)}・期の行なし {len(m.no_edition)}・"
          f"日付なし {len(m.no_date)}・文脈で決まらない {len(m.undetermined)}")
    print(f"書き出し：{OUT_DIR}/ の {'・'.join(names)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
