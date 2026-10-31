"""MCP の道具：テーマのノートのデータ（build/theme/<theme>.json）を生成AIに読ませる、読み取り専用の stdio サーバー
（LINK_SCHEMA §14、DESIGN.md ADR-27）。

読むものは、テーマのノートのデータ（§13）、ref/themes.tsv（テーマの語）、lock の版の hino-council-search の
public/data/index/<年>.json（会議録の本文）だけ。ネットワークを使わない。標準ライブラリだけ。
記載の書き方は持ち込み用の資料（§17.1、tools/build_rag.py）と同じ。

実行: python3 -B tools/mcp_ronten.py <theme> <node キー> [--log <jsonl>]（例 hoiku node:jisshi/e008）
"""
import csv
import json
import os
import re
import sys
import time
import unicodedata

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_rag as br  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
THEME_DIR = os.path.join(ROOT, "build", "theme")
THEMES_TSV = os.path.join(ROOT, "ref", "themes.tsv")
HS = "hino-council-search"
INDEX = "public/data/index/{}.json"
KOHO = "doc:koho-"
NOTE = ("記載の頭に【未確認】がある行と、照合結果は、人による確認が済んでいない。"
        "記載の形は「［資料の日付］資料の名前：欄：値。「引用」（出典：url）」。検討の段階（政策の過程）の記載は、資料の日付ではなく期間を書くため［ ］が無い。"
        "欄「資料の種類」は、会議録（会議録の発言）・広報ひの・町の資料の別。引用は資料の原文のまま。")
SPEECH_NOTE = ("会議録の本文（資料そのもの。項目ごとに記録したものではない。テーマの語のある発言だけ）。"
               "引用するときは、この本文から原文のまま引く。")
SEARCH_LIMIT = 20
SNIPPET = 160


class McpError(ValueError):
    pass


def norm(s):
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", s or "")).lower()


def theme_words(path, theme):
    """ref/themes.tsv の、そのテーマの kind 語の値。"""
    with open(path, encoding="utf-8", newline="") as f:
        return [r["value"] for r in csv.DictReader(f, delimiter="\t") if r["theme"] == theme and r["kind"] == "語"]


class Server:
    def __init__(self, data_bytes, program, words=(), speeches=None, log=None):
        self.d = json.loads(data_bytes.decode("utf-8"))
        self.r = br.Rag(self.d, data_bytes, program)
        self.log = log
        self.items = {}
        self.questions = {}
        self.speech_of = {}
        self._index(words, speeches or {})

    # ---- 記載の一覧（id → 種類・日付・本文） ----
    def _add(self, i, kind, date, text, key=""):
        self.items[i] = {"id": i, "kind": kind, "date": date or "", "text": text, "key": key, "n": norm(text + " " + key)}

    def _index(self, words, speeches):
        d, r, R = self.d, self.r, self.d["records"]
        for n, x in enumerate(R.get("kotogara") or [], 1):
            self._add(f"kotogara:{n}", f"事柄：{x['point']}", x["source_date"], r.kot_entry(x), x["point"])
        for n, x in enumerate(R.get("shisetsu") or [], 1):
            fname = self.facility(x["facility"])
            self._add(f"shisetsu:{n}", f"施設：{fname}", x["source_date"], r.shisetsu_entry(x), fname)
        for n, x in enumerate(R.get("tsunagari") or [], 1):
            self._add(f"tsunagari:{n}", "つながり", x["source_date"], r.tsunagari_entry(x), f"{x['upper']} {x['lower']}")
        for n, k in enumerate(R.get("katei") or [], 1):
            self._add(f"katei:{n}", "過程", k.get("from"), r.katei_entry(k), k.get("name"))
        for n, x in enumerate(R.get("kisai") or [], 1):
            self._add(f"kisai:{n}", f"記載：{x.get('about') or ''}", x["source_date"],
                      r.kisai_entry(x),
                      x.get("about") or "")
        for name in ("yaritori", "shitsugi"):
            for q in R.get(name) or []:
                self.questions[f"{name}:{q['question']}"] = (name, q)
                for row in q["rows"]:
                    self._add(f"{name}:{q['question']}/{row['row']}", "一般質問" if name == "yaritori" else "議案質疑", q["date"],
                              r.qa_entry(name, q, row) + (f"　事項：{row['point']}" if row.get("point") else ""), row.get("point") or "")
        for n, x in enumerate(d.get("exchanges") or [], 1):
            self._add(f"exchange:{n}", "一般質問の一覧", x["date"], r.exchange_line(x))
            for t in x.get("turns") or []:
                sp = speeches.get((t.get("sid") or "").replace("sp:", ""))
                if not sp or not any(w in sp.get("text", "") for w in words):
                    continue
                who = f"{x['member']['name']} 議員" if t["side"] == "問い" else (sp.get("role") or t.get("role") or "")
                i = f"speech:{t['sid'].replace('sp:', '')}"
                self.speech_of.setdefault(n, []).append(i)
                self._add(i, "会議録の本文", x["date"],
                          f"［{br.jd(x['date'])}］{x['meeting']}の一般質問（質問者：{x['member']['name']} 議員）："
                          f"{'質問' if t['side'] == '問い' else '答弁'}。発言者：{who}。会議録の本文：「{sp['text'].strip()}」（出典：{t['url']}）",
                          who)
        for n, b in enumerate(d.get("bills") or [], 1):
            deb = "・".join(f"{x.get('stance')}（{x['member'].get('name')} 議員）" for x in b.get("debates") or []) or "なし"
            self._add(f"bill:{n}", "議案", b["date"], f"［{br.jd(b['date'])}］{b.get('meeting')}の{b.get('no')} {b.get('title')}。"
                      f"議決結果：{b.get('result')}。採決方法：{b.get('method')}。討論：{deb}（出典：{b.get('url')}）")
        for n, x in enumerate(d.get("issues") or [], 1):
            self._add(f"issue:{n}", f"照合結果（未確認）：{x['type']}", "", r.issue_statement(x))

    def facility(self, key):
        return (self.r.fac.get(key) or {}).get("name") or key

    def by_key(self, prefix, key):
        return sorted((i for i, it in self.items.items() if i.startswith(prefix) and it["key"] == key),
                      key=lambda i: (self.items[i]["date"], i))

    def line(self, i):
        return f"- [{i}] {self.items[i]['text']}"

    def issue_text(self, n):
        x = self.d["issues"][n - 1]
        out = [f"[issue:{n}] 照合結果（未確認）：{x['type']}", self.r.issue_statement(x)]
        refs = x.get("refs") or []
        if x["type"] == br.UNASKED:
            where, refs = self.r.kiroku_sections(refs)
            if where:
                out.append("比べた記載のある記録：" + "、".join(f"{k}（{v}件）" for k, v in where))
        out += ["- 比べた記載：" + self.r.ref_entry(ref) for ref in refs]
        return "\n".join(out)

    # ---- 道具 ----
    def t_overview(self, _):
        d, r = self.d, self.r
        out = [f"{r.pname}（テーマ「{d.get('name')}」）の資料。{NOTE}",
               f"取り込んだ資料のうち、いちばん新しい記載の資料の日付：{br.jd(r.latest_date())}。それより後のことは資料に無い。", "",
               "## 事業の要点"]
        md = r.honpen().markdown()
        s = md.index("：1 事業の要点")
        out.append(md[s:md.index("\n# ", s)].split("\n", 1)[1].strip())
        T = d["records"].get("tsunagari") or []
        names = [r.pname]
        for x in [p.get("name") for p in d.get("plans") or []] + [t[k] for t in T for k in ("upper", "lower")]:
            if x and re.search(r"(計画|構想|提言)$", x) and x not in names:
                names.append(x)
        out += ["", "## 正式な名前（答弁や文書では略さずに使う）"] + [f"- {x}" for x in names]
        out += ["", "## 目的（つながりの記録の上位の記載と、その原文。答弁で目的を述べるときはこの原文を使う）"]
        seen = []
        for t in sorted(T, key=lambda t: t["source_date"], reverse=True):
            if t["link"] == "目的と手段" and t["upper"] not in seen:
                seen.append(t["upper"])
                out.append(f"- 目的「{t['upper']}」→ 手段「{t['lower']}」：{r.tsunagari_entry(t)}")
        K = sorted(d["records"].get("katei") or [], key=lambda k: k.get("from") or "")
        out += ["", "## いまの段階（政策の過程のうち新しいもの。原文）"] + [f"- {r.katei_entry(k)}" for k in K[-3:]]
        out += ["", "## 事項（topic で取る。事項ごとに「いまの町の説明」の原文を返す）"]
        out += [f"- {p}（{len(r.kot[p])}件）" for p in r.ordered_points()]
        fs = {}
        for x in d["records"].get("shisetsu") or []:
            fs[self.facility(x["facility"])] = fs.get(self.facility(x["facility"]), 0) + 1
        out += ["", "## 施設（topic で取る）"] + [f"- {k}（{v}件）" for k, v in sorted(fs.items(), key=lambda x: (-x[1], x[0]))]
        ab = {}
        for x in d["records"].get("kisai") or []:
            ab[x.get("about") or br.KISAI_NONE] = ab.get(x.get("about") or br.KISAI_NONE, 0) + 1
        out += ["", "## 記載の見出し（topic で取る）"] + [f"- {k}（{v}件）" for k, v in sorted(ab.items())]
        ts = {}
        for x in d.get("issues") or []:
            ts[x["type"]] = ts.get(x["type"], 0) + 1
        out += ["", "## 照合結果（未確認）（issues で取る）"] + [f"- {k}（{v}件）" for k, v in ts.items()]
        out += ["", f"## 議会（council で取る）：一般質問 {len(d.get('exchanges') or [])}問（うち質問・答弁を項目ごとに記録したもの "
                f"{len(d['records'].get('yaritori') or [])}問。ほかの問いの答弁は speeches で会議録の本文を読む）、"
                f"議案質疑 {len(d['records'].get('shitsugi') or [])}件、関係議案 {len(d.get('bills') or [])}件"]
        return "\n".join(out)

    def t_search(self, a):
        terms = [norm(t) for t in re.split(r"[\s　、,]+", a.get("query") or "") if norm(t)]
        if not terms:
            raise McpError("query が空")
        kind = a.get("kind") or ""
        hits = []
        for it in self.items.values():
            if kind and not it["kind"].startswith(kind):
                continue
            m = sum(1 for t in terms if t in it["n"])
            if m:
                hits.append((-m, it["date"], it["id"]))
        hits.sort()
        lim = int(a.get("limit") or SEARCH_LIMIT)
        out = [f"{len(hits)}件（{min(lim, len(hits))}件を表示。合う語の多い順、同じなら資料の日付順）。全文は fetch で取る。{NOTE}"]
        for _, _, i in hits[:lim]:
            t = self.items[i]["text"]
            out.append(f"[{i}] {self.items[i]['kind']}：{t[:SNIPPET]}{'…' if len(t) > SNIPPET else ''}")
        return "\n".join(out)

    def t_fetch(self, a):
        ids = a.get("ids") or []
        if isinstance(ids, str):
            ids = [ids]
        if not ids:
            raise McpError("ids が空")
        out = []
        for i in ids:
            if i.startswith("issue:"):
                n = i.split(":", 1)[1]
                if not n.isdigit() or not 1 <= int(n) <= len(self.d.get("issues") or []):
                    out.append(f"[{i}] 無い id")
                else:
                    out.append(self.issue_text(int(n)))
            elif i in self.questions:
                name, q = self.questions[i]
                out.append(f"[{i}] {'一般質問' if name == 'yaritori' else '議案質疑'}：{br.jd(q['date'])} {q['meeting']}　"
                           f"質問者：{q['member']['name']} 議員")
                out += [self.line(f"{name}:{q['question']}/{row['row']}") for row in sorted(q["rows"], key=lambda x: int(x["row"]))]
            elif i in self.items:
                out.append(f"[{i}] {self.items[i]['kind']}：{self.items[i]['text']}")
            else:
                out.append(f"[{i}] 無い id")
        return "\n".join(out)

    def t_topic(self, a):
        name = (a.get("name") or "").strip()
        r, out = self.r, []
        if name in r.kot:
            c = r.latest(name)
            out.append(f"## 事柄：{name}")
            if c:
                v = c.get("value") or c.get("target") or ""
                out.append(f"町の資料の最新の記載（{br.jd(c['source_date'])}、{r.name(c['source'])}）：{v}（出典：{c.get('url')}）")
                out.append(f"いまの町の説明（原文。答弁や文書ではこの言い回しを使う）：{r.kot_entry(c)}")
                if c["source"].startswith(KOHO):
                    base = [x for x in r.kot[name] if not x["source"].startswith(("sp:", KOHO))]
                    if base:
                        out.append("上は広報ひのの記載のため、数字や時期の出典には、次の計画などの記載（広報ひの以外でいちばん新しいもの）を使う："
                                   + r.kot_entry(base[-1]))
            else:
                out.append(f"{r.none_text(name)}。")
            ans = [i for i in self.by_key(("yaritori:", "shitsugi:"), name) if "発言：答弁" in self.items[i]["text"]]
            if ans:
                out.append("当局の答弁のうち新しいもの（原文。これまでの答弁と食い違わないように確かめる）：")
                out += [self.line(i) for i in ans[-3:]]
            out.append("記載の推移（資料の日付順）：")
            out += [self.line(i) for i in self.by_key("kotogara:", name)]
            qa = self.by_key(("yaritori:", "shitsugi:"), name)
            if qa:
                out.append("この事項についての質問・答弁（記録したもの）：")
                out += [self.line(i) for i in qa]
        fs = self.by_key("shisetsu:", name)
        if fs:
            out += [f"## 施設：{name}"] + [self.line(i) for i in fs]
        ks = self.by_key("kisai:", name)
        if ks:
            out += [f"## 記載の見出し：{name}"] + [self.line(i) for i in ks]
        if not out:
            raise McpError(f"「{name}」という事項・施設・記載の見出しは無い。overview の一覧の名前を使うか、search で探す")
        return "\n".join(out)

    def t_council(self, a):
        f, t = a.get("from_date") or "", a.get("to_date") or "9999"
        rows = sorted((it["date"], i) for i, it in self.items.items() if i.startswith(("exchange:", "bill:")) and f <= it["date"] <= t)
        out = ["一般質問と関係議案（日付順）。一般質問の会議録の本文は speeches で、項目ごとに記録した質問は fetch で取る。"]
        out += [self.line(i) for _, i in rows]
        out.append("項目ごとに記録した質問・質疑：")
        for k, (name, q) in self.questions.items():
            if f <= q["date"] <= t:
                out.append(f"- [{k}] {br.jd(q['date'])} {q['meeting']}　質問者：{q['member']['name']} 議員（{len(q['rows'])}行）")
        return "\n".join(out)

    def t_speeches(self, a):
        x = (a.get("exchange") or "").strip()
        n = x.split(":", 1)[1] if x.startswith("exchange:") else x
        if not n.isdigit() or not 1 <= int(n) <= len(self.d.get("exchanges") or []):
            raise McpError("exchange は council が返す exchange:<番号> で指定する")
        ids = self.speech_of.get(int(n))
        if not ids:
            return f"exchange:{n} には、テーマの語のある発言の本文が無い"
        return "\n".join([SPEECH_NOTE] + [self.line(i) for i in ids])

    def t_issues(self, a):
        ty = a.get("type")
        issues = self.d.get("issues") or []
        out = ["照合結果（未確認）：機械による照合の結果で、人による確認は済んでいない。"]
        if not ty:
            out[0] += "type を指定すると、比べた記載とあわせて返す。fetch で issue:<番号> を取ってもよい。"
            out += [f"[issue:{n}] {x['type']}：{self.r.issue_statement(x)}" for n, x in enumerate(issues, 1)]
            return "\n".join(out)
        hit = [n for n, x in enumerate(issues, 1) if x["type"] == ty]
        if not hit:
            raise McpError(f"比べ方「{ty}」の照合結果は無い")
        return "\n\n".join(out + [self.issue_text(n) for n in hit])

    def t_links(self, _):
        r = self.r
        out = ["## 目的と手段・もとにした資料（つながりの記録。ここに無い関係は記録に無い）"]
        out += [self.line(i) for i in self.items if i.startswith("tsunagari:")]
        out += ["", "## 政策の過程（検討の段階）"]
        out += [self.line(i) for i in sorted((i for i in self.items if i.startswith("katei:")), key=lambda i: (self.items[i]["date"], i))]
        out += ["", "## 総合計画のめざす姿と、計画に掲げる課題"]
        for v in r.sheet.get("vision") or []:
            out.append(f"- 総合計画のめざす姿：「{re.sub(r'^めざす姿:', '', v.get('text', ''))}」（出典：{v.get('source') or v.get('url')}）")
        for k in r.sheet.get("kadai") or []:
            out.append(f"- 計画に掲げる課題：「{k.get('text')}」（出典：{k.get('url')}）")
        return "\n".join(out)

    TOOLS = [
        ("overview", "最初に呼ぶ。事業の要点（事業名・概算事業費・当初予算額・総合計画の位置）、資料の時点、正式な名前、目的の原文、"
         "いまの段階、事項・施設・記載の見出し・照合結果の一覧を返す。", {}, "t_overview"),
        ("search", "記載を語で探す。語は空白で区切る（例「開園時期 令和11年」）。kind で種類を絞れる（事柄・施設・つながり・過程・記載・"
         "一般質問・議案質疑・一般質問の一覧・会議録の本文・議案・照合結果）。返すのは id と抜粋。全文は fetch で取る。",
         {"query": {"type": "string"}, "kind": {"type": "string"}, "limit": {"type": "integer"}}, "t_search"),
        ("fetch", "id を指定して記載の全文を取る（search・topic・council・speeches・issues が返す id）。"
         "yaritori:<問いのキー> で、記録した一般質問の全行を取る。",
         {"ids": {"type": "array", "items": {"type": "string"}}}, "t_fetch"),
        ("topic", "事項（事柄）・施設・記載の見出しの名前を指定して、その記載を資料の日付順に取る。事柄は、いまの町の説明の原文と、"
         "当局の新しい答弁の原文を先に返す。名前は overview の一覧のとおり。", {"name": {"type": "string"}}, "t_topic"),
        ("council", "関連する一般質問と関係議案の一覧（日付・質問者・議決結果）。from_date・to_date（YYYY-MM-DD）で絞れる。",
         {"from_date": {"type": "string"}, "to_date": {"type": "string"}}, "t_council"),
        ("speeches", "一般質問1問の会議録の本文（質問と答弁の全文）を取る。exchange に council が返す exchange:<番号> を渡す。"
         "項目ごとに記録していない一般質問の答弁も、ここで読める。", {"exchange": {"type": "string"}}, "t_speeches"),
        ("issues", "照合結果（未確認）の一覧を取る。type を指定すると、その比べ方の照合結果を、比べた記載とあわせて取る"
         "（予定の変更・問われていない点・繰り返し問われている点・留保のその後・役割のその後・つながりの記録に無い目的・問われていない区分）。",
         {"type": {"type": "string"}}, "t_issues"),
        ("links", "目的と手段・もとにした資料のつながりの記録、政策の過程、総合計画のめざす姿と計画の課題を取る。", {}, "t_links"),
    ]

    def call(self, name, args):
        fn = {n: f for n, _, _, f in self.TOOLS}.get(name)
        if fn is None:
            raise McpError(f"無い道具：{name}")
        return getattr(self, fn)(args or {})

    def handle(self, msg):
        m, mid = msg.get("method"), msg.get("id")
        if m == "initialize":
            return {"jsonrpc": "2.0", "id": mid, "result": {
                "protocolVersion": (msg.get("params") or {}).get("protocolVersion", "2025-06-18"),
                "capabilities": {"tools": {}}, "serverInfo": {"name": "ronten", "version": "1"}}}
        if m == "tools/list":
            return {"jsonrpc": "2.0", "id": mid, "result": {"tools": [
                {"name": n, "description": d, "inputSchema": {"type": "object", "properties": p}} for n, d, p, _ in self.TOOLS]}}
        if m == "tools/call":
            p = msg.get("params") or {}
            try:
                text, err = self.call(p.get("name"), p.get("arguments")), False
            except McpError as e:
                text, err = f"エラー：{e}", True
            if self.log:
                with open(self.log, "a", encoding="utf-8") as f:
                    f.write(json.dumps({"time": time.strftime("%Y-%m-%dT%H:%M:%S"), "tool": p.get("name"),
                                        "arguments": p.get("arguments"), "chars": len(text)}, ensure_ascii=False) + "\n")
            return {"jsonrpc": "2.0", "id": mid, "result": {"content": [{"type": "text", "text": text}], "isError": err}}
        if m == "ping":
            return {"jsonrpc": "2.0", "id": mid, "result": {}}
        if mid is None:
            return None
        return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"無いメソッド：{m}"}}

    def serve(self, stdin, stdout):
        for line in stdin:
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except ValueError:
                continue
            res = self.handle(msg)
            if res is not None:
                stdout.write(json.dumps(res, ensure_ascii=False) + "\n")
                stdout.flush()


def load_speeches(data):
    """lock の版の hino-council-search から、テーマの一般質問の年の会議録の本文を読む。"""
    import gen_mentions as gm
    lock = gm.load_lock(gm.LOCK_PATH)
    gi = gm.GitInputs(gm.INPUTS_ROOT, lock)
    out = {}
    for y in sorted({x["date"][:4] for x in data.get("exchanges") or []}):
        for s in gi.read_json(HS, INDEX.format(y)):
            out[s["sid"]] = s
    return out


def main(argv):
    args = [a for a in argv[1:]]
    log = None
    if "--log" in args:
        i = args.index("--log")
        log = args[i + 1]
        del args[i:i + 2]
    if len(args) != 2:
        print("使い方: python3 -B tools/mcp_ronten.py <theme> <node キー> [--log <jsonl>]", file=sys.stderr)
        return 1
    theme, program = args
    try:
        with open(os.path.join(THEME_DIR, f"{theme}.json"), "rb") as f:
            raw = f.read()
        server = Server(raw, program, theme_words(THEMES_TSV, theme), load_speeches(json.loads(raw)), log)
    except (OSError, br.RagError, ValueError) as e:
        print(f"止めた：{e}", file=sys.stderr)
        return 1
    server.serve(sys.stdin, sys.stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
