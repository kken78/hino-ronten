"""テーマのノートのデータ build/theme/<theme>.json を作る（LINK_SCHEMA.md §13・§13.3、DESIGN.md ADR-12・ADR-19・ADR-24）。

いまは確定の層の9つの項目（plans・policies・programs・budget・council・exchanges・bills・docs・records）を作る。
hits・sheets・issues は空の配列のまま置く（S4-3b で作る）。

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


def build(theme, themes_rows, ledgers, d, lock, refs, hashes):
    tk = theme_keys(themes_rows, theme)
    for kind in ("名前",):
        if len(tk.get(kind, ())) != 1:
            raise BuildError(f"テーマ {theme} の {kind} が1行でない")
    for kind in records.THEME_KINDS:
        tk.setdefault(kind, set())
    plans = build_plans(d, tk["系列"], refs["lineage"])
    plan_keys = {p["key"] for p in plans}
    council = build_council(d, plan_keys, refs["links"])
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
        "exchanges": build_exchanges(d, council, tk["問い"]),
        "bills": build_bills(d, tk["議案"]),
        "docs": build_docs(d, tk["資料"]),
        "records": build_records(d, ledgers, theme, tk),
        "hits": {"council": [], "docs": []},
        "sheets": [],
        "issues": [],
    }
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
            data = build(theme, themes_rows, ledgers, d, lock, refs, hashes)
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
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
