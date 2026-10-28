"""テーマのノートのデータ build/theme/<theme>.json を作る（LINK_SCHEMA.md §13・§13.3、DESIGN.md ADR-12・ADR-19・ADR-24）。

確定の層の9つの項目（plans・policies・programs・budget・council・exchanges・bills・docs・records）と、
語の一致（hits）・整理シート（sheets）・論点の候補（issues）を作る（§13.1・§13.2・§13.4）。

先に tools/records.py の検査（LINK_SCHEMA §11 のテーマの定義・施設の参照表・記録の台帳）をかけ、誤りがあれば作らない。
入力は inputs.lock.json の版だけを git で読む。台帳と参照表は作業ツリーの版を読み、その sha256 を ledgers に書く。

実行: python3 -B tools/build_theme.py [テーマ]（省けば ref/themes.tsv の全テーマ）
終了コード：0 は作った。1 は止めた（理由を表示する）。
"""
import csv
import hashlib
import json
import os
import re
import sys
import unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import check_records  # noqa: E402
import gen_mentions as gm  # noqa: E402
import mention  # noqa: E402
import records  # noqa: E402

OUT_DIR = os.path.join(gm.ROOT, "build", "theme")
LEDGERS = ["links/mention.tsv", "links/relink.tsv", "links/fuhyo.tsv", "ref/themes.tsv", "ref/shisetsu.tsv",
           "ref/lineage.tsv", "ref/aliases.tsv"] + [f"records/{n}.tsv" for n in records.LEDGERS]
PLAN_PAGE = "https://kken78.github.io/shiga-hino-plans/plans/{}.html"
SEARCH = "https://kken78.github.io/hino-council-search/#thread={}&focus={}"
CONFIRMED = "確定"
UNCONFIRMED = "記録（未確認）"
HIT = "語の一致（未確認）"
OCR = "OCR の下書き"
ISSUE = "論点の候補（未確認）"
TEXT = "原典の文字"
NOT_RECORDED = "記録に無い"
CHAIRS = ("議長", "副議長", "臨時議長", "新議長", "新副議長")
EXCERPT = 200


class BuildError(ValueError):
    pass


# ---- 小さな道具 ----

def sha256_file(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def read_tsv_rows(path):
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f, delimiter="\t"))


def speaker_class(role):
    """役職の区分（LINK_SCHEMA §13、docs/review-2026-10-21.md §5.3 e）。議席は議員、議長類は議長、空はその他、ほかは当局。"""
    role = role or ""
    if re.fullmatch(r"[0-9０-９]+番", role):
        return "議員"
    if role in CHAIRS:
        return "議長"
    if not role or role.endswith("委員長") and role != "選挙管理委員長" or role in ("事務局長", "議会事務局長"):
        return "その他"
    return "当局"


def mb_key(name):
    return "mb:" + re.sub(r"\s", "", unicodedata.normalize("NFKC", name or ""))


def head(text, n=EXCERPT):
    return (text or "")[:n]


def page_url(url, page):
    return f"{url}#page={page}" if url else ""


# ---- 入力 ----

class Data:
    """build に要る入力。tools/check_records.py の Inputs（検査の入力）に、画面に出す欄を足す。"""

    def __init__(self, gi, inp):
        self.inp = inp
        im = gi.read_json(gm.HS, "public/data/index-manifest.json")
        self.index = {e["sid"]: e for p in im["shards"] for e in gi.read_json(gm.HS, f"public/data/{p['file']}")}
        self.proceedings = gi.read_json(gm.HS, "public/data/proceedings.json")
        self.meetings = {m["id"]: m for m in gi.read_json(gm.HS, "public/data/meetings.json")}
        self.gian = gi.read_json(gm.HS, "public/data/gian.json")
        self.questions = {gm.bq_key(q): q for q in gi.read_json(gm.CD, "docs/data/questions.json")["questions"]}
        self.manifest = {p["id"]: p for p in gi.read_json(gm.SP, "data/manifest.json")["plans"]}
        self.plans = {}
        for path in gi.expand(gm.SP, "data/plans/*.json"):
            p = gi.read_json(gm.SP, path)
            self.plans[p["id"]] = p
        self.sources_index = list(csv.DictReader(gi.read_bytes(gm.SP, "data/sources_index.tsv").decode("utf-8")
                                                 .splitlines(), delimiter="\t"))
        self.fuhyo = {"fuhyo-r8": gi.read_json(gm.SP, "data/fuhyo/fuhyo-r8.json")}
        self.docs = {r["id"]: r for r in csv.DictReader(gi.read_bytes(gm.TD, "data/sources.tsv").decode("utf-8")
                                                        .splitlines(), delimiter="\t")}
        self.doc_files = set(gi.expand(gm.TD, "data/text/*.txt")) | set(gi.expand(gm.TD, "data/text_raw/*.txt")) \
            | set(gi.expand(gm.TD, "data/ocr/*.txt"))
        self.doc_text = {p: gi.read_bytes(gm.TD, p).decode("utf-8") for p in sorted(self.doc_files)}
        self.scenes = gm.scene_of([self.index[s] for s in inp.order], self.proceedings)
        self.votes, self.debates = {}, {}
        for mid, m in self.proceedings.items():
            for sg in m.get("segments") or []:
                for b in sg.get("bills") or []:
                    if sg.get("kind") == "vote":
                        self.votes.setdefault((mid, b), []).append(sg)
                    elif sg.get("kind") == "debate":
                        self.debates.setdefault((mid, b), []).append(sg)

    def sp_url(self, sid):
        """会議録の発言：やりとり（一般質問・議案の質疑）の中なら検索の画面、外なら会議録の原本 PDF（§13）。"""
        for f, sg in self.inp.segments.items():
            a, b = self.inp.pos.get(sg["from"]), self.inp.pos.get(sg["to"])
            p = self.inp.pos.get(sid)
            if a is not None and p is not None and a <= p <= b:
                return SEARCH.format(sg["from"], sid)
        return (self.index.get(sid) or {}).get("pdf") or ""

    def bq_url(self, key):
        q = self.questions.get(key) or {}
        return q.get("minutes_exchange") or q.get("bulletin") or ""

    def source_pdf(self, pid, file):
        for r in self.sources_index:
            if r["id"] == pid and r["file"] == file:
                return r["url"]
        return ""

    def key_url(self, key):
        """資料のキー（§2）→ 出典の url。"""
        if key.startswith("sp:"):
            return self.sp_url(key[3:])
        if key.startswith("bq:"):
            return self.bq_url(key)
        m = records.RE_DOC_PAGE.fullmatch(key)
        if m:
            return page_url((self.docs.get(m.group(1)) or {}).get("url"), m.group(2))
        m = records.RE_DOC.fullmatch(key)
        if m:
            return (self.docs.get(m.group(1)) or {}).get("url", "")
        m = records.RE_PT_PAGE.fullmatch(key)
        if m:
            return page_url(self.source_pdf(m.group(1), m.group(2) + ".pdf"), m.group(3))
        m = records.RE_GI.fullmatch(key)
        if m:
            return (self.meetings.get(m.group(1)) or {}).get("url", "")
        if key.startswith("plan:"):
            return PLAN_PAGE.format(key[5:].split("/")[0])
        return ""


# ---- 項目（§13.3） ----

def build_plans(d, series, lineage_rows):
    out = []
    for r in lineage_rows:
        if r["series"] not in series:
            continue
        if r["plan"]:
            key = f"plan:{r['plan']}"
            posted = (d.plans.get(r["plan"]) or {}).get("meta", {}).get("posted", "")
            url = PLAN_PAGE.format(r["plan"])
        else:
            key = f"lin:{r['series']}/{r['edition']}"
            posted = ""
            m = re.fullmatch(r"([a-z0-9-]+)/([A-Za-z0-9_.-]+\.pdf) p\.([0-9]+)", r["source"] or "")
            url = page_url(d.source_pdf(m.group(1), m.group(2)), m.group(3)) if m else ""
        out.append(dict(key=key, series=r["series"], edition=r["edition"], name=r["name"], start_fy=r["start_fy"],
                        end_fy=r["end_fy"], posted=posted, url=url, layer=CONFIRMED))
    return sorted(out, key=lambda x: x["key"])


def program_items(plan):
    """programs ブロックの事業（tools/gen_fuhyo.py と同じ取り方）と、その分野（group）。"""
    for t in plan.get("tabs") or []:
        for b in t.get("blocks") or []:
            if b.get("type") != "programs":
                continue
            for g in b.get("groups") or []:
                for it in g.get("items") or []:
                    yield t, g, None, it
                for s in g.get("subgroups") or []:
                    for it in s.get("items") or []:
                        yield t, g, s, it


def plan_pdf(plan):
    return ((plan.get("sources") or [{}])[0]).get("url", "")


def build_policies(d, keys):
    out = []
    for key in sorted(keys):
        pid, k = key[5:].split("/")
        plan = d.plans[pid]
        for t, g, s, it in program_items(plan):
            if it.get("key") != k:
                continue
            desc = it.get("desc") or ""
            kind = "分野" if any(line.startswith("めざす姿:") for line in desc.split("\n")) else "基本施策"
            out.append(dict(key=key, kind=kind, no=it.get("no", ""), name=it.get("name", ""), desc=desc,
                            source=plan_pdf(plan), url=PLAN_PAGE.format(pid), layer=CONFIRMED))
    return out


def build_programs(d, keys):
    out = []
    for key in sorted(keys):
        pid, k = key[5:].split("/")
        plan = d.plans[pid]
        for t, g, s, it in program_items(plan):
            if it.get("key") != k:
                continue
            out.append(dict(key=key, plan=f"plan:{pid}", field_no=g.get("no", ""), field_name=g.get("name", ""),
                            name=it.get("name", ""), desc=it.get("desc", ""), years=it.get("years") or [],
                            cost=it.get("cost") or {}, source=plan_pdf(plan), url=PLAN_PAGE.format(pid), layer=CONFIRMED))
    return out


def build_budget(d, program_keys, fuhyo_rows):
    out = []
    for r in fuhyo_rows:
        if r["status"] != "confirmed" or r["to"] not in program_keys:
            continue
        fid, k = r["from"][3:].split("/")
        fh = d.fuhyo[fid]
        it = next(x for p in fh["pillars"] for x in p["items"] if x["key"] == k)
        m = re.search(r"メモ：区分：([^。]+)", r["note"])
        out.append(dict(key=r["from"], program=r["to"], category=m.group(1) if m else "", name=it["name"],
                        desc=it.get("desc", ""), kan=it.get("kan", ""), kubun=it.get("kubun") or [], amount=it.get("amount"),
                        unit="千円", dept=it.get("dept") or [], page=it.get("page"),
                        url=page_url(d.source_pdf(fh["source"]["id"], fh["source"]["file"]), it.get("page")),
                        layer=CONFIRMED))
    return sorted(out, key=lambda x: x["key"])


def build_council(d, plan_keys, link_rows):
    """link_rows：言及の台帳（mention と relink）の行。"""
    out = []
    for r in link_rows:
        if r["status"] != "confirmed" or r["to"] not in plan_keys:
            continue
        if r["from"].startswith("sp:"):
            e = d.index[r["from"][3:]]
            date, role = e["date"], e.get("role") or ""
            url = d.sp_url(r["from"][3:])
            scene = d.scenes.get(r["from"][3:], gm.OUTSIDE)
            kind = "sp"
        else:
            q = d.questions.get(r["from"]) or {}
            date, role, url, scene, kind = q.get("pub_date", ""), "", d.bq_url(r["from"]), "議会だより", "bq"
        # 議会だよりは、問いの欄（title・question_text）は議員、答えの欄（answer_title・answers）は当局
        speaker = speaker_class(role) if kind == "sp" else ("当局" if r["where"] in ("answer_title", "answers") else "議員")
        out.append(dict(**{"from": r["from"]}, to=r["to"], to_label=r["to_label"], method=r["method"], date=date,
                        kind=kind, speaker=speaker, role=role, scene=scene,
                        excerpt=head(r["context"]), url=url, layer=CONFIRMED))
    return sorted(out, key=lambda x: (x["date"], x["from"], x["to"], x["method"]))


def question_turns(d, seg, qn):
    """一般質問の場面のうち、turns の問番号が qn の発言（議長の進行発言を含めない）。"""
    base = d.inp.pos[seg["from"]]
    return [(d.inp.order[base + t[0]], t[1]) for t in sorted(seg.get("turns") or [], key=lambda t: t[0])
            if len(t) > 2 and t[2] == qn]


def member_of(seg):
    return dict(key=mb_key(seg.get("member")), name=seg.get("member", ""), seat=seg.get("seat", ""))


def build_exchanges(d, council, questions=()):
    """council の会議録の言及を含む一般質問の問いと、テーマの問い（§12 の kind 問い）。turns の問番号の単位。
    議会だよりの言及（bq）からは作らない。"""
    groups = {}
    starts = [(c["from"][3:], c["from"]) for c in council if c["kind"] == "sp"] + [(q[3:], None) for q in sorted(questions)]
    for sid, mention_key in starts:
        for sg in d.inp.segments.values():
            if sg["kind"] != "ippan":
                continue
            a, b, p = d.inp.pos[sg["from"]], d.inp.pos[sg["to"]], d.inp.pos[sid]
            if not a <= p <= b:
                continue
            base = a
            qn = None
            for t in sorted(sg.get("turns") or [], key=lambda t: t[0]):
                if base + t[0] <= p and len(t) > 2:
                    qn = t[2]
            if qn is None:
                continue
            g = groups.setdefault((sg["from"], qn), {"seg": sg, "mentions": set()})
            if mention_key:
                g["mentions"].add(mention_key)
    out = []
    for (f, qn), g in groups.items():
        sg = g["seg"]
        turns = question_turns(d, sg, qn)
        first_q = next((s for s, t in turns if t == "q"), turns[0][0])
        mid = sg["meetingId"]
        titles = [dict(title=x.get("title", ""), theme=x.get("theme", ""), issue=x.get("issue", ""))
                  for x in sg.get("topics") or [] if x.get("n") == qn and x.get("src") == "bulletin"]
        out.append(dict(meeting_id=mid, meeting=(d.meetings.get(mid) or {}).get("name", ""), date=d.index[first_q]["date"],
                        n=qn, question=f"iq:{first_q}", member=member_of(sg), titles=titles,
                        turns=[dict(sid=f"sp:{s}", side="答え" if t == "a" else "問い", speaker=speaker_class(d.index[s].get("role")),
                                    role=d.index[s].get("role") or "", excerpt=head(d.index[s].get("text")),
                                    url=SEARCH.format(sg["from"], s)) for s, t in turns],
                        mentions=sorted(g["mentions"]), layer=CONFIRMED))
    return sorted(out, key=lambda x: (x["date"], x["question"]))


def build_bills(d, keys):
    out = []
    for key in sorted(keys):
        mid, no = key[3:].split("/")
        a = next(x for x in d.gian[mid]["agenda"] if x["no"] == no)
        votes = d.votes.get((mid, no)) or []
        date = votes[0]["date"] if votes else (d.meetings.get(mid) or {}).get("date", "")
        debates = [dict(date=sg.get("date", ""), member=member_of(sg), stance=sg.get("stance", ""), sid=f"sp:{sg['from']}",
                        url=d.sp_url(sg["from"])) for sg in d.debates.get((mid, no)) or []]
        out.append(dict(key=key, meeting_id=mid, meeting=(d.meetings.get(mid) or {}).get("name", ""), date=date, no=no,
                        kind=a.get("kind", ""), title=a.get("title", ""), committee=a.get("committee", ""),
                        result=a.get("result", ""), method=a.get("method", ""),
                        debates=sorted(debates, key=lambda x: (x["date"], x["sid"])),
                        url=(d.meetings.get(mid) or {}).get("url", ""), layer=CONFIRMED))
    return sorted(out, key=lambda x: (x["date"], x["key"]))


def build_docs(d, keys):
    out = []
    for key in sorted(keys):
        did = key[4:]
        r = d.docs[did]
        layers = []
        if f"data/text/{did}.txt" in d.doc_files or f"data/text_raw/{did}.txt" in d.doc_files:
            layers.append("原典の文字")
        if f"data/ocr/{did}.txt" in d.doc_files:
            layers.append("OCR の下書き")
        out.append(dict(id=did, category=r.get("category", ""), title=r.get("title", ""), fiscal_year=r.get("fiscal_year", ""),
                        date=r.get("date", ""), pages=r.get("pages", ""), check=r.get("check", ""), text_layers=layers,
                        url=r.get("url", ""), layer=CONFIRMED))
    return out


def row_out(d, name, r):
    """記録の行：§15 の列と、資料の url と layer。"""
    x = {c: r[c] for c in records.COLUMNS[name]}
    src = r.get("sid") or r.get("source") or (r.get("sources") or "").split(",")[0]
    x["url"] = d.key_url(src) if src else ""
    x["layer"] = CONFIRMED if r["status"] == "confirmed" else UNCONFIRMED
    return x


def build_records(d, ledgers, theme, tkeys):
    out = {}
    for name in ("katei", "kotogara", "tsunagari", "kisai"):
        out[name] = [row_out(d, name, r) for r in ledgers[name] if r["theme"] == theme and r["status"] != "rejected"]
    out["shisetsu"] = [row_out(d, "shisetsu", r) for r in ledgers["shisetsu"]
                       if r["facility"] in tkeys["施設"] and r["status"] != "rejected"]
    for name, kind in (("yaritori", "問い"), ("shitsugi", "質疑")):
        groups = {}
        for r in ledgers[name]:
            if r["question"] in tkeys[kind] and r["status"] != "rejected":
                groups.setdefault(r["question"], []).append(row_out(d, name, r))
        items = []
        for q, rows in groups.items():
            seg = d.inp.segment_of(q)
            mid = seg["meetingId"]
            items.append(dict(question=q, meeting_id=mid, meeting=(d.meetings.get(mid) or {}).get("name", ""),
                              date=d.index[q[3:]]["date"], member=member_of(seg), rows=rows))
        out[name] = sorted(items, key=lambda x: (x["date"], x["question"]))
    return out


# ---- 語の一致（§13 hits） ----

class Words:
    """テーマの語（§12 の kind 語）と除外の語。本文に §4 の正規化をかけて探す。除外の語の中で一致した語は数えない。"""

    def __init__(self, words, excluded):
        self.words = sorted(words)
        self.excluded = sorted(excluded)

    def find(self, text):
        """正規化した本文 → (正規化した本文, 語ごとの回数 {語: 回数}, 最初に一致した位置, その語)。一致が無ければ回数は空。"""
        t = mention.normalize(text)
        bad = set()
        for x in self.excluded:
            for m in re.finditer(re.escape(x), t):
                bad.update(range(m.start(), m.end()))
        counts, first = {}, None
        for w in self.words:
            for m in re.finditer(re.escape(w), t):
                if bad.intersection(range(m.start(), m.end())):
                    continue
                counts[w] = counts.get(w, 0) + 1
                if first is None or (m.start(), -len(w)) < (first[0], -len(first[1])):
                    first = (m.start(), w)
        return t, counts, (first[0] if first else None), (first[1] if first else "")


def around(t, pos, word, n=EXCERPT):
    """一致した語を中心に、前後あわせて n 字（§13）。"""
    if pos is None:
        return t[:n]
    start = max(0, min(pos - (n - len(word)) // 2, len(t) - n))
    return t[start:start + n]


def add_counts(total, counts):
    for w, c in counts.items():
        total[w] = total.get(w, 0) + c


def words_out(total):
    return [dict(word=w, count=c) for w, c in sorted(total.items())]


def hit_unit(d, words, sg, sids, titles):
    """問いか質疑のまとまりの発言（sids）と題名から、語の一致を求める。一致が無ければ None。"""
    total, from_sid, excerpt = {}, None, ""
    for x in titles:
        add_counts(total, words.find(x.get("title"))[1])
    for s in sids:
        t, counts, pos, w = words.find(d.index[s].get("text"))
        add_counts(total, counts)
        if counts and from_sid is None:
            from_sid, excerpt = s, around(t, pos, w)
    if not total:
        return None
    if from_sid is None:  # 題名だけで一致：問いの最初の発言の頭から
        from_sid = sids[0]
        excerpt = around(mention.normalize(d.index[from_sid].get("text")), None, "")
    return dict(words=words_out(total), **{"from": f"sp:{from_sid}"}, excerpt=excerpt, first_sid=f"sp:{sids[0]}",
                url=SEARCH.format(sg["from"], from_sid))


def build_hits_council(d, words, council, exchanges, tk):
    """一般質問の問い（exchanges に無いもの）、議案の質疑のまとまり（テーマの質疑に無く、council の発言を含まないもの）、
    議会だよりの問い（council に無いもの）のうち、題名か本文にテーマの語が一致したもの。"""
    out = []
    in_exchanges = {x["question"] for x in exchanges}
    council_sp = {c["from"][3:] for c in council if c["kind"] == "sp"}
    council_bq = {c["from"] for c in council if c["kind"] == "bq"}
    for f, sg in sorted(d.inp.segments.items()):
        mid = sg["meetingId"]
        meeting = (d.meetings.get(mid) or {}).get("name", "")
        if sg["kind"] == "ippan":
            for qn in sorted({t[2] for t in sg.get("turns") or [] if len(t) > 2}):
                turns = question_turns(d, sg, qn)
                if not turns:
                    continue
                first_q = next((s for s, t in turns if t == "q"), turns[0][0])
                if f"iq:{first_q}" in in_exchanges:
                    continue
                topics = [x for x in sg.get("topics") or [] if x.get("n") == qn]
                h = hit_unit(d, words, sg, [s for s, t in turns], topics)
                if h:
                    out.append(dict(kind="問い", meeting_id=mid, meeting=meeting, date=d.index[first_q]["date"], n=qn,
                                    question=f"iq:{first_q}", member=member_of(sg), bills=[],
                                    titles=[dict(title=x.get("title", ""), theme=x.get("theme", ""), issue=x.get("issue", ""),
                                                 src=x.get("src", "")) for x in topics], **h, layer=HIT))
        elif sg["kind"] == "shitsugi":
            a, b = d.inp.pos[sg["from"]], d.inp.pos[sg["to"]]
            sids = d.inp.order[a:b + 1]
            if f"sq:{f}" in tk["質疑"] or council_sp.intersection(sids):
                continue
            h = hit_unit(d, words, sg, sids, [])
            if h:
                out.append(dict(kind="質疑", meeting_id=mid, meeting=meeting, date=d.index[f]["date"], n="",
                                question=f"sq:{f}", member=member_of(sg),
                                bills=[f"gi:{mid}/{x}" for x in sg.get("bills") or []], titles=[], **h, layer=HIT))
    for key, q in sorted(d.questions.items()):
        if key in council_bq:
            continue
        parts = [q.get("title"), q.get("question_text"), q.get("answer_title")] + \
            [a.get("text") if isinstance(a, dict) else a for a in q.get("answers") or []]
        total, excerpt = {}, ""
        for p in parts:
            t, counts, pos, w = words.find(p)
            add_counts(total, counts)
            if counts and not excerpt:
                excerpt = around(t, pos, w)
        if not total:
            continue
        out.append(dict(kind="議会だより", meeting_id="", meeting="", date=q.get("pub_date", ""), n=q.get("q_num", ""),
                        question=key, member=dict(key=mb_key(q.get("member")), name=q.get("member", ""), seat=""), bills=[],
                        titles=[dict(title=q.get("title", ""), theme=q.get("theme", ""), issue=q.get("issue", ""),
                                     src="bulletin")],
                        words=words_out(total), **{"from": key}, excerpt=excerpt, first_sid="", url=d.bq_url(key),
                        layer=HIT))
    return sorted(out, key=lambda x: (x["date"], x["from"]))


RE_UNEXPECTED = re.compile(r"想定外の字のあるページ：([^。]+)")


def unexpected_pages(note):
    m = RE_UNEXPECTED.search(note or "")
    return {int(p) for p in re.findall(r"([0-9]+)（", m.group(1))} if m else set()


def build_hits_docs(d, words):
    """町の公開資料のページのうち、テーマの語が一致したもの。原典の文字（data/text、無ければ data/text_raw）で探し、
    当たらないページは data/text_raw、それでも当たらないページは OCR の下書き（data/ocr）で探す。"""
    out = []
    for did, r in sorted(d.docs.items()):
        layers = [(TEXT, d.doc_text.get(f"data/text/{did}.txt")), (TEXT, d.doc_text.get(f"data/text_raw/{did}.txt")),
                  (OCR, d.doc_text.get(f"data/ocr/{did}.txt"))]
        pages = [(name, (text or "").split("\f")) for name, text in layers if text]
        if not pages:
            continue
        unexpected = unexpected_pages(r.get("note"))
        n = max(len(p) for _, p in pages)
        for i in range(n):
            for name, p in pages:
                if i >= len(p):
                    continue
                t, counts, pos, w = words.find(p[i])
                if counts:
                    out.append(dict(doc=f"doc:{did}", title=r.get("title", ""), category=r.get("category", ""),
                                    fiscal_year=r.get("fiscal_year", ""), date=r.get("date", ""), page=i + 1,
                                    words=words_out(counts), text_layer=name, excerpt=around(t, pos, w),
                                    unexpected=(i + 1) in unexpected, url=page_url(r.get("url"), i + 1),
                                    layer=OCR if name == OCR else HIT))
                    break
    return sorted(out, key=lambda x: (x["date"], x["doc"], x["page"]))


# ---- 整理シート（§13.1） ----

def plan_source_url(plan, source):
    """計画の記載の source（例「honpen p.18-19」）→ 原典の PDF のページ（計画の sources の pdf_page_offset を足す）。"""
    m = re.fullmatch(r"([A-Za-z0-9_-]+) p\.([0-9]+)(?:-[0-9]+)?", source or "")
    if not m:
        return ""
    s = next((x for x in plan.get("sources") or [] if x.get("id") == m.group(1)), None)
    return page_url(s.get("url"), int(m.group(2)) + int(s.get("pdf_page_offset") or 0)) if s else ""


def challenges_of(d, plans):
    out = []
    for p in plans:
        if not p["key"].startswith("plan:"):
            continue
        pid = p["key"][5:]
        plan = d.plans.get(pid) or {}
        for t in plan.get("tabs") or []:
            bn = 0
            for b in t.get("blocks") or []:
                if b.get("type") != "challenges":
                    continue
                bn += 1
                for i, it in enumerate(b.get("items") or [], 1):
                    out.append(dict(ref=f"plan:{pid}/{t['id']}/challenges/{bn}/{i}", text=it.get("title", ""),
                                    source=f"{pid}/{b.get('source', '')}", url=plan_source_url(plan, b.get("source")),
                                    layer=CONFIRMED))
    return out


def record_key(name, r):
    return "/".join(str(r[c]) for c in records.KEYS[name])


def rec_ref(name, r):
    return dict(ref=f"records/{name}/{record_key(name, r)}", text=r.get("quote", ""), source=r.get("source") or r.get("sid") or
                (r.get("sources") or "").split(",")[0], url=r["url"], layer=r["layer"])


def program_names(themes_rows, theme, program):
    """テーマの定義の kind 事柄・記載のうち、source にこの事業の node キーを書いた値（§13.1 の「この事業にかかわる」）。"""
    return {r["value"] for r in themes_rows if r["theme"] == theme and r["kind"] in ("事柄", "記載")
            and program in r["source"]}


def stage_counts(rows):
    c = {s: 0 for s in records.STAGES}
    for r in rows:
        if r["side"] == "問い" and r["stage"] in c:
            c[r["stage"]] += 1
    return c


def group_layer(rows):
    return CONFIRMED if all(r["layer"] == CONFIRMED for r in rows) else UNCONFIRMED


SHEET_COLUMNS = ("kadai", "cost", "desc", "vision", "tsunagari", "kotogara", "katei", "asked")


def build_sheets(d, data, themes_rows, theme):
    R = data["records"]
    kadai = challenges_of(d, data["plans"])
    vision = [dict(ref=f"policies/{p['key']}", text=line, source=p["source"], url=p["url"], layer=p["layer"])
              for p in data["policies"] if p["kind"] == "分野" for line in p["desc"].split("\n") if line.startswith("めざす姿:")]
    katei = [rec_ref("katei", r) for r in sorted(R["katei"], key=lambda r: int(r["step"]))]
    asked = []
    for name in ("yaritori", "shitsugi"):
        for q in R[name]:
            asked.append(dict(ref=f"records/{name}/{q['question']}", text=f"{q['date']} {q['meeting']}",
                              value=stage_counts(q["rows"]), source=q["question"], url=d.key_url("sp:" + q["question"][3:]),
                              layer=group_layer(q["rows"])))
    out = []
    for p in data["programs"]:
        cost = [dict(ref=f"programs/{p['key']}", value=dict(years=p["years"], cost=p["cost"]), source=p["source"],
                     url=p["url"], layer=p["layer"])]
        cost += [dict(ref=f"budget/{b['key']}", value=dict(amount=b["amount"], unit=b["unit"], category=b["category"]),
                      source=b["key"], url=b["url"], layer=b["layer"]) for b in data["budget"] if b["program"] == p["key"]]
        desc = [dict(ref=f"programs/{p['key']}", text=p["desc"], source=p["source"], url=p["url"], layer=p["layer"])] \
            if p["desc"] else []
        names = program_names(themes_rows, theme, p["key"])
        tsunagari = [rec_ref("tsunagari", r) for r in R["tsunagari"] if r["upper"] in names or r["lower"] in names]
        kotogara = [rec_ref("kotogara", r) for r in sorted((r for r in R["kotogara"] if r["program"] == p["key"]),
                                                           key=lambda r: (r["point"], r["source_date"], r["source"]))]
        out.append(dict(program=p["key"], name=p["name"], kadai=kadai, cost=cost, desc=desc, vision=vision,
                        tsunagari=tsunagari, kotogara=kotogara, katei=katei, asked=asked))
    return out


# ---- 論点の候補（§13.2） ----

RE_ERA_YEAR = re.compile(r"(令和|平成|昭和)(元|[0-9]+)年")


def era_years(target):
    """対象の時期の表記から、元号と年の数の並び（「令和10年度」「令和10年4月」はどちらも (令和, 10)）。"""
    return tuple((e, 1 if y == "元" else int(y)) for e, y in RE_ERA_YEAR.findall(unicodedata.normalize("NFKC", target or "")))


def is_after(a, base):
    """資料の日付 a が base より後か。月だけの日付は、その月が base の月より後のときに後とする。"""
    if not a or not base:
        return False
    if len(a) == 7 or len(base) == 7:
        return a[:7] > base[:7]
    return a > base


class Labels:
    """論点の候補の statement に書く、資料の名前と施設の名前。"""

    def __init__(self, d, shisetsu_rows):
        self.d = d
        self.facility = {r["key"]: r for r in shisetsu_rows}

    def source(self, key):
        d = self.d
        if key.startswith("sp:"):
            e = d.index.get(key[3:]) or {}
            mid = key[3:].split("_")[0]
            role = e.get("role") or ""
            who = "議員" if speaker_class(role) == "議員" else (role or "役職の無い発言者")
            return f"{(d.meetings.get(mid) or {}).get('name', '')}の{who}の発言"
        if key.startswith("bq:"):
            return f"議会だより第{(d.questions.get(key) or {}).get('issue', '')}号"
        m = records.RE_DOC_PAGE.fullmatch(key) or records.RE_DOC.fullmatch(key)
        if m:
            return f"「{(d.docs.get(m.group(1)) or {}).get('title', '')}」"
        m = records.RE_PT_PAGE.fullmatch(key)
        if m:
            return (d.plans.get(m.group(1)) or {}).get("meta", {}).get("name", "")
        m = records.RE_GI.fullmatch(key)
        if m:
            return f"{(d.meetings.get(m.group(1)) or {}).get('name', '')}の{m.group(2)}"
        return key

    def fac(self, key):
        return (self.facility.get(key) or {}).get("name", key)


def ref_of(name, r):
    x = rec_ref(name, r)
    return dict(ref=x["ref"], text=x["text"], url=x["url"], layer=x["layer"])


def q_ref(L, name, q):
    return dict(ref=f"records/{name}/{q['question']}", text=f"{q['date']} {q['meeting']}",
                url=L.d.key_url("sp:" + q["question"][3:]), layer=group_layer(q["rows"]))


def issue(type_, statement, refs, scope="テーマ", program=""):
    if any(r["layer"] == UNCONFIRMED for r in refs):
        statement = "記録（未確認）による。" + statement
    return dict(type=type_, scope=scope, program=program, statement=statement, refs=refs, layer=ISSUE)


def changed_rows(rows):
    """予定と変更の行（資料の日付の順）のうち、前の予定の行と元号・年の数が違う予定の行と、変更の行。最初の予定の行も含める。
    候補にならなければ空。"""
    rows = sorted((r for r in rows if r["kind"] in ("予定", "変更")), key=lambda r: (r["source_date"], r["source"]))
    picked, prev, hit = [], None, False
    for r in rows:
        if r["kind"] == "変更":
            picked.append(r)
            hit = True
            continue
        y = era_years(r["target"])
        if not y:
            continue
        if prev is None:
            picked.append(r)
        elif y != prev:
            picked.append(r)
            hit = True
        prev = y
    return (picked, rows) if hit else ([], rows)


def issues_yotei(L, R):
    out = []
    groups = {}
    for r in R["kotogara"]:
        groups.setdefault(("kotogara", r["point"]), []).append(r)
    for r in R["shisetsu"]:
        groups.setdefault(("shisetsu", (r["facility"], r["aspect"], r["value"])), []).append(r)
    for (name, k), rows in sorted(groups.items(), key=lambda x: (x[0][0], str(x[0][1]))):
        picked, considered = changed_rows(rows)
        if not picked:
            continue
        parts = [f"{r['source_date']}の{L.source(r['source'])}では{r['target'] or '時期の記載なし'}（{r['kind']}）" for r in picked]
        subject = k if name == "kotogara" else f"{L.fac(k[0])}の「{k[2]}」"
        s = f"{subject}は、" + "、".join(parts)
        reasons = [r["reason"] for r in picked if r.get("reason")]
        if reasons:
            s += "。理由として「" + "」「".join(reasons) + "」"
        programs = {r.get("program") for r in rows} if name == "kotogara" else {""}
        program = programs.pop() if len(programs) == 1 else ""
        out.append(issue("予定の変更", s, [ref_of(name, r) for r in considered],
                         scope="事業" if program else "テーマ", program=program))
    return out


def points_of(q, side=None):
    return {r["point"] for r in q["rows"] if r["point"] and (side is None or r["side"] == side)}


def issues_ryuho(L, R):
    out = []
    groups = {}
    for name in ("yaritori", "shitsugi"):
        for q in R[name]:
            for r in q["rows"]:
                if r["side"] == "答え" and r["kind"] == "留保" and r["point"]:
                    groups.setdefault((q["date"], q["question"], r["point"]), (name, q, []))[2].append(r)
    for (date, question, point), (name, q, rows) in sorted(groups.items()):
        later = []
        for n2 in ("yaritori", "shitsugi"):
            for q2 in R[n2]:
                if is_after(q2["date"], date) and point in points_of(q2):
                    later.append((q2["date"], f"{q2['meeting']}の一般質問" if n2 == "yaritori" else f"{q2['meeting']}の議案の質疑",
                                  q_ref(L, n2, q2)))
        for r in R["kotogara"]:
            if r["point"] == point and is_after(r["source_date"], date):
                later.append((r["source_date"], L.source(r["source"]), ref_of("kotogara", r)))
        later.sort(key=lambda x: (x[0], x[2]["ref"]))
        roles = "・".join(dict.fromkeys(r["speaker"] for r in rows))
        s = f"{date}の答え（{roles}）は、{point}について時期や中身を後に回した。"
        if later:
            s += f"そのあと、{later[0][0]}の{later[0][1]}がある" + (f"（ほか{len(later) - 1}件）" if len(later) > 1 else "")
        else:
            s += "そのあとの記録は無い"
        out.append(issue("留保のその後", s, [ref_of(name, r) for r in rows] + [x[2] for x in later]))
    return out


def asked_groups(R):
    return [("yaritori", q) for q in R["yaritori"]] + [("shitsugi", q) for q in R["shitsugi"]]


def issues_kurikaeshi(L, R):
    out = []
    by = {}
    for name, q in asked_groups(R):
        for p in points_of(q, "問い"):
            by.setdefault(p, []).append((name, q))
    for p, qs in sorted(by.items()):
        meetings = {}
        for name, q in sorted(qs, key=lambda x: (x[1]["date"], x[1]["question"])):
            meetings.setdefault(q["meeting_id"], q["meeting"])
        if len(meetings) < 2:
            continue
        out.append(issue("繰り返し問われている点", f"「{p}」は、{'・'.join(meetings.values())}の問いで問われた",
                         [q_ref(L, name, q) for name, q in qs]))
    return out


def scope_text(R, tk):
    qs = asked_groups(R)
    if not qs:
        return "記録したやりとりは無い", []
    qs.sort(key=lambda x: (x[1]["date"], x[1]["question"]))
    s = (f"記録したやりとり（一般質問{len(R['yaritori'])}問・質疑{len(R['shitsugi'])}まとまり、"
         f"{qs[0][1]['meeting']}〜{qs[-1][1]['meeting']}）")
    return s, qs


def missing_text(R, tk):
    recorded = {q["question"] for q in R["yaritori"]}
    n = len(tk["問い"] - recorded)
    return f"。テーマの問い{len(tk['問い'])}問のうち{n}問は、やりとりの記録が無い" if n else ""


def issues_kubun(L, R, tk):
    rng, qs = scope_text(R, tk)
    if not qs:
        return []
    parts = []
    for name, label in (("yaritori", "一般質問"), ("shitsugi", "質疑")):
        c = stage_counts([r for q in R[name] for r in q["rows"]])
        parts.append(f"{label}は" + "・".join(f"{k}{v}件" for k, v in c.items()) + f"（全{sum(c.values())}件）")
    s = f"{rng}の問いの行を区分ごとに数えると、" + "、".join(parts) + missing_text(R, tk)
    return [issue("問われていない区分", s, [q_ref(L, name, q) for name, q in qs])]


def issues_toware(L, R, tk, themes_rows, theme):
    rng, qs = scope_text(R, tk)
    asked = set()
    for name, q in qs:
        asked |= points_of(q, "問い")
    out = []
    values = [r["value"] for r in themes_rows if r["theme"] == theme and r["kind"] in ("事柄", "記載")]
    for v in values:
        if v in asked:
            continue
        rows = [("kisai", r) for r in R["kisai"] if r["about"] == v] + \
            [("kotogara", r) for r in R["kotogara"] if r["point"] == v] + \
            [("tsunagari", r) for r in R["tsunagari"] if v in (r["upper"], r["lower"])]
        rows.sort(key=lambda x: (x[1]["source_date"], x[1]["source"]))
        srcs = list(dict.fromkeys(L.source(r["source"]) for _, r in rows))
        s = f"「{v}」は、{rng}の問いの行の点に無い。この値の記載がある資料：" + ("・".join(srcs) if srcs else NOT_RECORDED)
        s += missing_text(R, tk)
        out.append(issue("問われていない点", s, [ref_of(n, r) for n, r in rows]))
    return out


def issues_mokuteki(R):
    rows = [r for r in R["tsunagari"] if r["link"] == "目的と手段"]
    lower = {r["lower"] for r in rows}
    out = []
    for up in sorted({r["upper"] for r in rows} - lower):
        out.append(issue("つながりの記録に無い目的", f"「{up}」を手段とする目的の記載は、つながりの記録に無い",
                         [ref_of("tsunagari", r) for r in rows if r["upper"] == up]))
    return out


def issues_yakuwari(L, R):
    rows = R["shisetsu"]
    out = []
    roles = {}
    for r in rows:
        if r["aspect"] == "役割":
            roles.setdefault((r["facility"], r["value"]), []).append(r)
    for (fa, value), rr in sorted(roles.items()):
        rr.sort(key=lambda r: (r["source_date"], r["source"]))
        first = rr[0]
        states = sorted((r for r in rows if r["facility"] == fa and r["aspect"] == "状態"
                         and is_after(r["source_date"], first["source_date"])), key=lambda r: (r["source_date"], r["source"]))
        if not states:
            continue
        st = states[0]
        district = (L.facility.get(fa) or {}).get("district", "")
        later = sorted((r for r in rows if r["aspect"] == "役割" and r["value"] == value
                        and (r["facility"] == fa or district and (L.facility.get(r["facility"]) or {}).get("district") == district)
                        and is_after(r["source_date"], st["source_date"])), key=lambda r: (r["source_date"], r["source"]))
        s = (f"{L.fac(fa)}は、{first['source_date']}の{L.source(first['source'])}で{value}。"
             f"{st['source_date']}の{L.source(st['source'])}では{st['value']}（{st['kind']}）。")
        if later:
            r0 = later[0]
            s += f"そのあと、{r0['source_date']}の{L.source(r0['source'])}がある（{L.fac(r0['facility'])}の{value}）" + \
                (f"（ほか{len(later) - 1}件）" if len(later) > 1 else "")
        else:
            s += "そのあとの記録は無い"
        out.append(issue("役割のその後", s, [ref_of("shisetsu", r) for r in rr + states + later]))
    return out


def issues_yosan(data, fuhyo_years):
    """テーマの事業のうち、附表のある年度（lock の版）が実施年度にあるのに、その年度の附表に当たる事業が無いもの。"""
    out = []
    for p in data["programs"]:
        for fy in fuhyo_years:
            if f"R{fy}" not in p["years"]:
                continue
            if any(b["program"] == p["key"] and b["key"].startswith(f"fh:fuhyo-r{fy}/") for b in data["budget"]):
                continue
            out.append(issue("計画と予算", f"{p['name']}は実施年度に令和{fy}年度があるが、令和{fy}年度の附表に当たる事業が無い",
                             [dict(ref=f"programs/{p['key']}", text=p["name"], url=p["url"], layer=p["layer"])],
                             scope="事業", program=p["key"]))
    return out


def build_issues(d, data, tk, themes_rows, theme, shisetsu_rows):
    L = Labels(d, shisetsu_rows)
    R = data["records"]
    fuhyo_years = sorted(int(k[len("fuhyo-r"):]) for k in d.fuhyo)
    return (issues_yotei(L, R) + issues_ryuho(L, R) + issues_kurikaeshi(L, R) + issues_kubun(L, R, tk)
            + issues_toware(L, R, tk, themes_rows, theme) + issues_mokuteki(R) + issues_yakuwari(L, R)
            + issues_yosan(data, fuhyo_years))


# ---- 全体 ----

def theme_keys(themes_rows, theme):
    k = {}
    for r in themes_rows:
        if r["theme"] == theme:
            k.setdefault(r["kind"], set()).add(r["value"])
    return k


def read_refs():
    """build が読む台帳と参照表（作業ツリーの版）。relink は無ければ0行。"""
    links = []
    for f in ("mention", "relink"):
        path = os.path.join(gm.ROOT, "links", f"{f}.tsv")
        if os.path.exists(path):
            links += read_tsv_rows(path)
    return {"lineage": read_tsv_rows(gm.LINEAGE), "fuhyo": read_tsv_rows(os.path.join(gm.ROOT, "links", "fuhyo.tsv")),
            "links": links}


def ledger_hashes():
    return {p: sha256_file(os.path.join(gm.ROOT, p)) for p in LEDGERS if os.path.exists(os.path.join(gm.ROOT, p))}


def build(theme, themes_rows, ledgers, d, lock, refs, hashes, shisetsu_rows=()):
    tk = theme_keys(themes_rows, theme)
    for kind in ("名前",):
        if len(tk.get(kind, ())) != 1:
            raise BuildError(f"テーマ {theme} の {kind} が1行でない")
    for kind in records.THEME_KINDS:
        tk.setdefault(kind, set())
    plans = build_plans(d, tk["系列"], refs["lineage"])
    plan_keys = {p["key"] for p in plans}
    council = build_council(d, plan_keys, refs["links"])
    exchanges = build_exchanges(d, council, tk["問い"])
    words = Words(tk["語"], tk["除外の語"])
    data = {
        "theme": theme,
        "name": next(iter(tk["名前"])),
        "lock": {repo: lock[repo]["sha"] for repo in sorted(lock)},
        "ledgers": hashes,
        "plans": plans,
        "policies": build_policies(d, tk["施策"]),
        "programs": build_programs(d, tk["事業"]),
        "budget": build_budget(d, tk["事業"], refs["fuhyo"]),
        "council": council,
        "exchanges": exchanges,
        "bills": build_bills(d, tk["議案"]),
        "docs": build_docs(d, tk["資料"]),
        "records": build_records(d, ledgers, theme, tk),
        "hits": {"council": build_hits_council(d, words, council, exchanges, tk), "docs": build_hits_docs(d, words)},
    }
    data["sheets"] = build_sheets(d, data, themes_rows, theme)
    data["issues"] = build_issues(d, data, tk, themes_rows, theme, shisetsu_rows)
    return data


def check_no_empty_url(data):
    """出典の無い項目は作らない（§13）。url の空の項目を数える。"""
    bad = []
    for item in ("plans", "policies", "programs", "budget", "council", "exchanges", "bills", "docs"):
        for x in data[item]:
            if item != "exchanges" and not x.get("url"):
                bad.append(f"{item}：{x.get('key') or x.get('id') or x.get('from')}")
    for name, rows in data["records"].items():
        for x in rows:
            for r in (x["rows"] if "rows" in x else [x]):
                if not r["url"]:
                    bad.append(f"records/{name}：{'/'.join(r[c] for c in records.KEYS[name])}")
    for name in ("council", "docs"):
        for x in data["hits"][name]:
            if not x["url"]:
                bad.append(f"hits/{name}：{x.get('question') or x.get('doc')}")
    for sh in data["sheets"]:
        for col in SHEET_COLUMNS:
            for x in sh[col]:
                if not x["url"]:
                    bad.append(f"sheets/{sh['program']}/{col}：{x['ref']}")
    for i in data["issues"]:
        for x in i["refs"]:
            if not x["url"]:
                bad.append(f"issues/{i['type']}：{x['ref']}")
    return bad


def main(argv):
    try:
        lock = gm.load_lock(gm.LOCK_PATH)
        gi = gm.GitInputs(gm.INPUTS_ROOT, lock)
        gi.verify()
        inp = check_records.read_inputs(gi)
        ledgers = {n: check_records.read_file(os.path.join(check_records.RECORDS_DIR, f"{n}.tsv"), records.COLUMNS[n],
                                              n in records.OPTIONAL) for n in records.LEDGERS}
        themes_rows = check_records.read_file(check_records.THEMES, records.THEME_COLUMNS)
        shisetsu = check_records.read_file(check_records.SHISETSU, records.SHISETSU_COLUMNS)
    except (gm.GenError, records.RecordsError, mention.RefError) as e:
        print(f"停止：{e}", file=sys.stderr)
        return 1
    rep = records.check_all(ledgers, themes_rows, shisetsu, inp)
    if rep.errors:
        print(f"停止：記録の台帳の検査で誤りが {len(rep.errors)} 件ある（tools/check_records.py で確かめる）", file=sys.stderr)
        return 1
    d = Data(gi, inp)
    refs, hashes = read_refs(), ledger_hashes()
    themes = argv or sorted({r["theme"] for r in themes_rows})
    os.makedirs(OUT_DIR, exist_ok=True)
    for theme in themes:
        try:
            data = build(theme, themes_rows, ledgers, d, lock, refs, hashes, shisetsu)
        except BuildError as e:
            print(f"停止：{e}", file=sys.stderr)
            return 1
        bad = check_no_empty_url(data)
        if bad:
            print(f"停止：出典の url の無い項目が {len(bad)} 件ある", file=sys.stderr)
            for b in bad[:20]:
                print(f"  {b}", file=sys.stderr)
            return 1
        path = os.path.join(OUT_DIR, f"{theme}.json")
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
            f.write("\n")
        n = {k: len(v) for k, v in data.items() if isinstance(v, list)}
        r = {k: sum(len(x["rows"]) if "rows" in x else 1 for x in v) for k, v in data["records"].items()}
        print(f"{os.path.relpath(path, gm.ROOT)}：" + "・".join(f"{k} {v}" for k, v in n.items()))
        print("  records：" + "・".join(f"{k} {v}" for k, v in r.items()))
        print("  hits：" + "・".join(f"{k} {len(v)}" for k, v in data["hits"].items()))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
