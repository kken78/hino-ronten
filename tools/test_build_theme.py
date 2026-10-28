"""tools/build_theme.py の検査（LINK_SCHEMA.md §13・§13.1〜§13.4）と、tools/records.py・tools/check_records.py の
文の区切り・指示語・報告の表示の検査（§11）。

実行: python3 -B tools/test_build_theme.py -v
見本の入力は tools/test_records.py の見本（発言・場面・資料・計画・台帳）を使い、build に要る欄を足す。
"""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import build_theme as bt  # noqa: E402
import check_records  # noqa: E402
import gen_mentions as gm  # noqa: E402
import records as rc  # noqa: E402
import test_records as tr  # noqa: E402

M = tr.M
sid = tr.sid

PLAN_JISSHI = {"id": "jisshi", "meta": {"posted": "令和8年4月"}, "sources": [{"url": "https://example.jp/jisshi.pdf"}],
               "tabs": [{"id": "hito", "blocks": [{"type": "programs", "groups": [
                   {"no": "分野①", "name": "子ども・子育て",
                    "items": [{"key": "e008", "name": "認定こども園整備事業", "desc": "新こども園を整備する。", "years": ["R8"],
                               "cost": {"label": "概算事業費", "amount": 3000000, "unit": "千円"}}]}]}]}]}
PLAN_SOGO6 = {"id": "sogo6", "meta": {"posted": "2021年6月"}, "sources": [{"url": "https://example.jp/sogo6.pdf"}],
              "tabs": [{"id": "kousou", "blocks": [{"type": "programs", "groups": [{"no": "", "name": "", "subgroups": [
                  {"no": "政策1", "name": "子育て", "items": [{"key": "e011", "no": "①", "name": "子ども・子育て",
                                                           "desc": "めざす姿:どの子も健やかに\n基本施策:(3)幼児教育・保育の充実"}]}]}]}]},
                       {"id": "mokuhyo", "blocks": [{"type": "programs", "groups": [{"no": "", "name": "", "subgroups": [
                           {"no": "", "name": "基本施策", "items": [{"key": "e047", "no": "(3)", "name": "幼児教育・保育の充実",
                                                                 "desc": "保育ニーズに対応する。\n主な取組:施設の充実"}]}]}]}]}]}
PLAN_YOUHO = {"id": "youho", "meta": {"name": "再編整備計画", "posted": "令和7年3月策定"},
              "sources": [{"id": "honpen", "url": "https://example.jp/youho.pdf", "pdf_page_offset": 2}],
              "tabs": [{"id": "hoshin", "blocks": [{"type": "challenges", "source": "honpen p.18-19", "items": [
                  {"title": "① 人口減少", "desc": "計画の画面のために書き直した文。"},
                  {"title": "② 保育ニーズの変化", "desc": "同じ。"}]}]}]}
DOC_TEXT = {"data/text/teigen.txt": "一頁目の文。\f二頁目に再編の方針がある。こども園の話。\f",
            "data/ocr/teigen.txt": "一頁目のこども園。\f二頁目。\f"}


def make_data():
    d = bt.Data.__new__(bt.Data)
    d.inp = tr.inputs()
    for n, role, text in ((16, "議長", "起立多数です。"), (17, "10番", "反対の討論をします。")):   # 採決と討論（ほかの場面と重ならない）
        d.inp.statements[sid(n)] = {"text": text, "role": role, "meetingId": M}
        d.inp.order.append(sid(n))
        d.inp.pos[sid(n)] = len(d.inp.order) - 1
    d.index = {s: {"sid": s, "meetingId": M, "date": "2025-01-01", "role": "4番" if st["role"] == "議員" else st["role"], "text": st["text"],
                   "pdf": "https://example.jp/minutes.pdf"} for s, st in d.inp.statements.items()}
    vote = {"kind": "vote", "date": "2025-03-24", "sid": sid(16), "bills": ["議第1号"], "result": "原案可決", "method": "起立多数"}
    debate = {"kind": "debate", "date": "2025-03-24", "member": "加藤和幸", "seat": "10番", "from": sid(17), "to": sid(17),
              "stance": "反対", "bills": ["議第1号"]}
    ippan = dict(tr.IPPAN, seat="4番", topics=[{"n": 2, "title": "用地は", "theme": "子育て", "src": "bulletin", "issue": "30"},
                                               {"n": 1, "title": "定員", "src": "minutes"}])
    d.inp.segments[sid(2)] = ippan
    d.proceedings = {M: {"segments": [ippan, tr.SHITSUGI, vote, debate]}}
    d.meetings = {M: {"id": M, "name": "令和7年3月定例会議", "date": "2025-03-03", "url": "https://example.jp/meeting.html"}}
    d.gian = {M: {"agenda": [{"no": "議第1号", "kind": "予算", "title": "一般会計予算", "committee": "予算特別委員会",
                              "result": "原案可決", "method": "起立多数"}]}}
    d.questions = {"bq:30/松田洋子/1": {"issue": "30", "pub_date": "2025-05-15", "minutes_exchange": "https://example.jp/ex",
                                    "bulletin": "https://example.jp/b.pdf", "member": "松田 洋子", "q_num": "1",
                                    "title": "こども園の定員は", "answers": [{"label": "町長", "text": "こども園です。"}]},
                   "bq:30/山本秀喜/1": {"issue": "30", "pub_date": "2025-05-15", "minutes_exchange": "",
                                    "bulletin": "https://example.jp/b.pdf", "member": "山本 秀喜", "q_num": "1",
                                    "title": "道路は", "question_text": "学童保育所はどうか",
                                    "answers": [{"label": "町長", "text": "こども園の近くです。"}]}}
    d.manifest = {}
    d.plans = {"jisshi": PLAN_JISSHI, "sogo6": PLAN_SOGO6, "youho": PLAN_YOUHO}
    d.sources_index = [{"id": "kodomo", "file": "honpen.pdf", "url": "https://example.jp/kodomo.pdf"},
                       {"id": "youho", "file": "honpen.pdf", "url": "https://example.jp/youho.pdf"},
                       {"id": "fuhyo-r8", "file": "r8jigyou.pdf", "url": "https://example.jp/fuhyo.pdf"}]
    d.fuhyo = {"fuhyo-r8": {"id": "fuhyo-r8", "source": {"id": "fuhyo-r8", "file": "r8jigyou.pdf"}, "pillars": [
        {"items": [{"key": "b010", "kubun": ["新規"], "kan": "民生費", "name": "認定こども園整備事業", "desc": "",
                    "amount": 228421, "dept": ["子ども支援課"], "page": 1}]}]}}
    d.docs = {"teigen": {"id": "teigen", "category": "shingi", "title": "提言", "fiscal_year": "2023", "date": "",
                         "pages": "2", "check": "ok", "url": "https://example.jp/teigen.pdf",
                         "note": "想定外の字のあるページ：2（3字）"}}
    d.doc_files = {"data/text/teigen.txt", "data/ocr/teigen.txt"}
    d.doc_text = dict(DOC_TEXT)
    d.scenes = gm.scene_of([d.index[s] for s in d.inp.order], d.proceedings)
    d.votes = {(M, "議第1号"): [vote]}
    d.debates = {(M, "議第1号"): [debate]}
    return d


def link(frm, to, status="confirmed", where="text", context="新こども園の定員", method="mention"):
    return {"from": frm, "to": to, "method": method, "evidence": "", "where": where, "context": context,
            "to_label": "計画", "status": status, "reviewer": "kken78", "date": "2026-10-27", "note": ""}


def refs():
    return {"lineage": [{"series": "youho", "edition": "", "plan": "youho", "name": "再編整備計画", "start_fy": "2024",
                         "end_fy": "2029", "source": "", "note": ""},
                        {"series": "kodomo", "edition": "2", "plan": "", "name": "第2期子ども・子育て支援事業計画",
                         "start_fy": "2020", "end_fy": "2024", "source": "kodomo/honpen.pdf p.9", "note": ""},
                        {"series": "sogo", "edition": "6", "plan": "sogo6", "name": "総合計画", "start_fy": "2021",
                         "end_fy": "2030", "source": "", "note": ""}],
            "fuhyo": [{"from": "fh:fuhyo-r8/b010", "to": "node:jisshi/e008", "status": "confirmed",
                       "note": "事業名が同じ。メモ：区分：一致"},
                      {"from": "fh:fuhyo-r8/b010", "to": "node:jisshi/e009", "status": "rejected", "note": "違う"}],
            "links": [link(f"sp:{sid(4)}", "plan:youho"),                                     # 問1 の答え
                      link(f"sp:{sid(10)}", "lin:kodomo/2"),                                  # 問2 の問い
                      link(f"sp:{sid(12)}", "plan:youho", status="rejected"),
                      link(f"sp:{sid(15)}", "plan:sogo6"),                                    # テーマの外の計画
                      link("bq:30/松田洋子/1", "plan:youho", where="answers")]}


def theme_rows():
    rows = tr.theme_rows() + [dict(tr.theme_rows()[0], kind="系列", value="kodomo"),
                              dict(tr.theme_rows()[0], kind="施策", value="node:sogo6/e011"),
                              dict(tr.theme_rows()[0], kind="施策", value="node:sogo6/e047")]
    return sorted(rows, key=lambda r: (r["theme"], r["kind"], r["value"]))


def build(led=None, rf=None, themes=None, d=None):
    d = d or make_data()
    d.inp.nodes |= {"node:sogo6/e011", "node:sogo6/e047"}
    d.inp.series |= {"kodomo"}
    return bt.build("hoiku", themes or theme_rows(), led or tr.ledgers(), d, {"hino-council-search": {"sha": "a" * 40}},
                    rf or refs(), {"ref/themes.tsv": "x"}, tr.shisetsu_ref())


class SpeakerTest(unittest.TestCase):
    def test_speaker_class(self):
        for role, want in (("4番", "議員"), ("１２番", "議員"), ("議長", "議長"), ("副議長", "議長"), ("町長", "当局"),
                           ("子ども支援課長", "当局"), ("", "その他"), ("予算特別委員長", "その他"), ("議会事務局長", "その他"),
                           ("選挙管理委員長", "当局")):
            with self.subTest(role=role):
                self.assertEqual(bt.speaker_class(role), want)


class ItemsTest(unittest.TestCase):
    def setUp(self):
        self.data = build()

    def test_top(self):
        d = self.data
        self.assertEqual(d["theme"], "hoiku")
        self.assertEqual(d["lock"], {"hino-council-search": "a" * 40})
        self.assertEqual(sorted(d["hits"]), ["council", "docs"])
        self.assertEqual(len(d["sheets"]), 1)
        self.assertEqual(bt.check_no_empty_url(d), [])

    def test_plans(self):
        p = {x["key"]: x for x in self.data["plans"]}
        self.assertEqual(sorted(p), ["lin:kodomo/2", "plan:youho"])   # sogo はテーマの系列でない
        self.assertEqual(p["lin:kodomo/2"]["url"], "https://example.jp/kodomo.pdf#page=9")
        self.assertEqual(p["lin:kodomo/2"]["posted"], "")
        self.assertEqual(p["plan:youho"]["posted"], "令和7年3月策定")
        self.assertEqual(p["plan:youho"]["url"], bt.PLAN_PAGE.format("youho"))

    def test_policies_programs_budget(self):
        self.assertEqual([(x["key"], x["kind"], x["no"]) for x in self.data["policies"]],
                         [("node:sogo6/e011", "分野", "①"), ("node:sogo6/e047", "基本施策", "(3)")])
        self.assertEqual(self.data["policies"][0]["source"], "https://example.jp/sogo6.pdf")
        pg = self.data["programs"][0]
        self.assertEqual((pg["key"], pg["field_no"], pg["field_name"], pg["cost"]["amount"]),
                         ("node:jisshi/e008", "分野①", "子ども・子育て", 3000000))
        b = self.data["budget"]
        self.assertEqual(len(b), 1)   # rejected の行は入れない
        self.assertEqual((b[0]["category"], b[0]["amount"], b[0]["url"]), ("一致", 228421, "https://example.jp/fuhyo.pdf#page=1"))

    def test_council(self):
        c = self.data["council"]
        self.assertEqual([x["from"] for x in c], [f"sp:{sid(4)}", f"sp:{sid(10)}", "bq:30/松田洋子/1"])   # 日付の順
        sp = c[0]
        self.assertEqual((sp["speaker"], sp["role"], sp["scene"], sp["kind"]), ("当局", "子ども支援課長", "一般質問", "sp"))
        self.assertEqual(sp["url"], bt.SEARCH.format(sid(2), sid(4)))
        self.assertEqual(c[1]["speaker"], "議員")
        bq = c[2]
        self.assertEqual((bq["date"], bq["scene"], bq["speaker"], bq["url"]), ("2025-05-15", "議会だより", "当局", "https://example.jp/ex"))

    def test_council_outside_scene(self):
        rf = refs()
        rf["links"].append(link(f"sp:{sid(1)}", "plan:youho"))
        c = {x["from"]: x for x in build(rf=rf)["council"]}
        self.assertEqual(c[f"sp:{sid(1)}"]["scene"], gm.OUTSIDE)
        self.assertEqual(c[f"sp:{sid(1)}"]["speaker"], "議長")
        self.assertEqual(c[f"sp:{sid(1)}"]["url"], "https://example.jp/minutes.pdf")   # やりとりの外は会議録の原本

    def test_exchanges(self):
        ex = {(x["question"], x["n"]): x for x in self.data["exchanges"]}
        self.assertEqual(sorted(ex), [(f"iq:{sid(2)}", 1), (f"iq:{sid(10)}", 2)])
        q1 = ex[(f"iq:{sid(2)}", 1)]
        self.assertEqual(q1["mentions"], [f"sp:{sid(4)}"])
        self.assertEqual([(t["sid"], t["side"]) for t in q1["turns"]],
                         [(f"sp:{sid(2)}", "問い"), (f"sp:{sid(4)}", "答え"), (f"sp:{sid(6)}", "問い"), (f"sp:{sid(8)}", "答え")])
        self.assertEqual(q1["member"], {"key": "mb:松田洋子", "name": "松田 洋子", "seat": "4番"})
        self.assertEqual(q1["titles"], [])
        q2 = ex[(f"iq:{sid(10)}", 2)]
        self.assertEqual(q2["titles"], [{"title": "用地は", "theme": "子育て", "issue": "30"}])

    def test_exchanges_theme_question_without_mention(self):
        rf = refs()
        rf["links"] = [x for x in rf["links"] if x["from"] != f"sp:{sid(4)}"]
        ex = {x["question"]: x for x in build(rf=rf)["exchanges"]}
        self.assertEqual(ex[f"iq:{sid(2)}"]["mentions"], [])   # テーマの問い（§13.4、DESIGN.md I3）

    def test_bills_docs(self):
        b = self.data["bills"][0]
        self.assertEqual((b["key"], b["date"], b["committee"], b["result"], b["method"]),
                         (f"gi:{M}/議第1号", "2025-03-24", "予算特別委員会", "原案可決", "起立多数"))
        self.assertEqual([(x["member"]["name"], x["stance"], x["sid"]) for x in b["debates"]], [("加藤和幸", "反対", f"sp:{sid(17)}")])
        self.assertEqual(b["url"], "https://example.jp/meeting.html")
        doc = self.data["docs"][0]
        self.assertEqual((doc["id"], doc["text_layers"]), ("teigen", ["原典の文字", "OCR の下書き"]))

    def test_records(self):
        r = self.data["records"]
        self.assertEqual(sorted(r), ["katei", "kisai", "kotogara", "shisetsu", "shitsugi", "tsunagari", "yaritori"])
        y = r["yaritori"][0]
        self.assertEqual((y["question"], y["meeting_id"], y["meeting"], y["member"]["key"], len(y["rows"])),
                         (f"iq:{sid(2)}", M, "令和7年3月定例会議", "mb:松田洋子", 4))
        self.assertEqual(y["rows"][0]["url"], bt.SEARCH.format(sid(2), sid(2)))
        self.assertEqual(y["rows"][0]["layer"], "確定")
        self.assertEqual(r["kisai"][0]["url"], "https://example.jp/youho.pdf#page=1")
        self.assertEqual(r["tsunagari"][0]["url"], "https://example.jp/teigen.pdf#page=2")

    def test_records_status(self):
        led = tr.ledgers()
        led["kisai"][0].update(status="candidate", reviewer="", date="")
        led["katei"][0].update(status="rejected", note="下書き：見本。違う")
        led["nozoki"] = [tr.row("nozoki", question=tr.IQ, n="1", sid=f"sp:{sid(2)}", quote="前置きです。", reason="前置き")]
        r = build(led=led)["records"]
        self.assertEqual(r["kisai"][0]["layer"], "記録（未確認）")
        self.assertEqual(r["katei"], [])
        self.assertNotIn("nozoki", r)

    def test_empty_url(self):
        d = build()
        d["docs"][0]["url"] = ""
        self.assertEqual(bt.check_no_empty_url(d), ["docs：teigen"])


def tk_of(themes=None):
    tk = bt.theme_keys(themes or theme_rows(), "hoiku")
    for kind in rc.THEME_KINDS:
        tk.setdefault(kind, set())
    return tk


class HitsTest(unittest.TestCase):
    def test_words_find(self):
        w = bt.Words({"こども園", "保育所"}, {"学童保育"})
        t, counts, pos, word = w.find("学童保育所と、こども 園と保育所。")
        self.assertEqual(t, "学童保育所と、こども園と保育所。")   # §4 の正規化（空白を除く）
        self.assertEqual(counts, {"こども園": 1, "保育所": 1})       # 学童保育の中の保育所は数えない
        self.assertEqual((pos, word), (7, "こども園"))
        self.assertEqual(w.find("道路です。")[1], {})

    def test_around(self):
        t = "あ" * 300 + "こども園" + "い" * 300
        ex = bt.around(t, 300, "こども園")
        self.assertEqual(len(ex), bt.EXCERPT)
        self.assertEqual(ex.index("こども園"), 98)
        self.assertEqual(bt.around("短い文", None, ""), "短い文")

    def test_council_units(self):
        d = make_data()
        h = bt.build_hits_council(d, bt.Words({"こども園"}, {"学童保育"}), [], [], tk_of())
        self.assertEqual([(x["kind"], x["question"]) for x in h],
                         [("問い", f"iq:{sid(2)}"), ("議会だより", "bq:30/山本秀喜/1"), ("議会だより", "bq:30/松田洋子/1")])
        q = h[0]
        self.assertEqual((q["from"], q["first_sid"], q["n"], q["words"]), (f"sp:{sid(2)}", f"sp:{sid(2)}", 1,
                                                                           [{"word": "こども園", "count": 1}]))
        self.assertEqual(q["titles"], [{"title": "定員", "theme": "", "issue": "", "src": "minutes"}])
        self.assertEqual(q["url"], bt.SEARCH.format(sid(2), sid(2)))
        self.assertEqual(q["layer"], "語の一致（未確認）")
        b = h[1]   # 学童保育所の欄は飛ばし、答えから抜粋する
        self.assertEqual((b["excerpt"], b["date"], b["member"]["seat"], b["url"]), ("こども園の近くです。", "2025-05-15", "",
                                                                                     "https://example.jp/b.pdf"))

    def test_council_shitsugi(self):
        d = make_data()
        tk = tk_of()
        tk["質疑"] = set()
        h = [x for x in bt.build_hits_council(d, bt.Words({"こども園"}, set()), [], [], tk) if x["kind"] == "質疑"]
        self.assertEqual([(x["question"], x["from"], x["bills"]) for x in h], [(f"sq:{sid(13)}", f"sp:{sid(13)}", [f"gi:{M}/議第1号"])])
        council = [{"from": f"sp:{sid(15)}", "kind": "sp"}]   # council の発言を含む質疑は入れない
        self.assertEqual([x for x in bt.build_hits_council(d, bt.Words({"こども園"}, set()), council, [], tk)
                          if x["kind"] == "質疑"], [])

    def test_council_excludes_confirmed(self):
        data = build()
        h = data["hits"]["council"]
        self.assertEqual([x["question"] for x in h], ["bq:30/山本秀喜/1"])   # 問1 は exchanges、質疑はテーマの質疑、松田は council

    def test_title_only(self):
        d = make_data()
        d.inp.segments[sid(2)]["topics"].append({"n": 2, "title": "こども園の用地", "src": "bulletin", "issue": "30"})
        h = {x["question"]: x for x in bt.build_hits_council(d, bt.Words({"こども園"}, set()), [], [], tk_of())}
        q2 = h[f"iq:{sid(10)}"]
        self.assertEqual((q2["from"], q2["excerpt"]), (f"sp:{sid(10)}", "締めくくりに要望します。次に用地を伺います。"))

    def test_docs(self):
        h = build()["hits"]["docs"]
        self.assertEqual([(x["page"], x["text_layer"], x["layer"], x["unexpected"]) for x in h],
                         [(1, "OCR の下書き", "OCR の下書き", False), (2, "原典の文字", "語の一致（未確認）", True)])
        self.assertEqual(h[1]["url"], "https://example.jp/teigen.pdf#page=2")
        self.assertEqual(h[1]["excerpt"], "二頁目に再編の方針がある。こども園の話。")

    def test_unexpected_pages(self):
        self.assertEqual(bt.unexpected_pages("取得元：町。想定外の字のあるページ：1（11字）・6（1字）"), {1, 6})
        self.assertEqual(bt.unexpected_pages(""), set())


class SheetsTest(unittest.TestCase):
    def test_sheet(self):
        s = build()["sheets"][0]
        self.assertEqual((s["program"], s["name"]), ("node:jisshi/e008", "認定こども園整備事業"))
        self.assertEqual([(x["ref"], x["text"], x["url"]) for x in s["kadai"]],
                         [("plan:youho/hoshin/challenges/1/1", "① 人口減少", "https://example.jp/youho.pdf#page=20"),
                          ("plan:youho/hoshin/challenges/1/2", "② 保育ニーズの変化", "https://example.jp/youho.pdf#page=20")])
        self.assertEqual([x["ref"] for x in s["cost"]], ["programs/node:jisshi/e008", "budget/fh:fuhyo-r8/b010"])
        self.assertEqual(s["desc"][0]["text"], "新こども園を整備する。")
        self.assertEqual([x["text"] for x in s["vision"]], ["めざす姿:どの子も健やかに"])
        self.assertEqual([x["ref"] for x in s["kotogara"]],
                         [f"records/kotogara/hoiku/新こども園の定員/sp:{sid(4)}/定員は285人です。"])
        self.assertEqual([x["ref"] for x in s["katei"]], ["records/katei/hoiku/1"])
        self.assertEqual(s["tsunagari"], [])   # テーマの定義の記載の source に事業の node キーが無い
        a = {x["ref"]: x["value"] for x in s["asked"]}
        self.assertEqual(a[f"records/yaritori/{tr.IQ}"]["結果"], 2)
        self.assertEqual(a[f"records/shitsugi/{tr.SQ}"]["投入"], 1)
        self.assertEqual(len(a[f"records/yaritori/{tr.IQ}"]), 7)

    def test_tsunagari_by_program(self):
        rows = [dict(r, source="node:jisshi/e008 の記載") if r["kind"] == "記載" and r["value"] == "再編の方針" else r
                for r in theme_rows()]
        s = build(themes=rows)["sheets"][0]
        self.assertEqual([x["ref"] for x in s["tsunagari"]], ["records/tsunagari/hoiku/もとにした/提言/再編の方針/doc:teigen/2"])

    def test_empty_url(self):
        d = build()
        d["sheets"][0]["kadai"][0]["url"] = ""
        self.assertEqual(bt.check_no_empty_url(d), ["sheets/node:jisshi/e008/kadai：plan:youho/hoshin/challenges/1/1"])


def issues(led=None, rf=None, themes=None):
    return build(led=led, rf=rf, themes=themes)["issues"]


class IssuesTest(unittest.TestCase):
    def test_baseline(self):
        got = issues()
        self.assertEqual([x["type"] for x in got], ["問われていない区分", "問われていない点", "問われていない点"])
        k = got[0]
        self.assertIn("記録したやりとり（一般質問1問・質疑1まとまり、令和7年3月定例会議〜令和7年3月定例会議）", k["statement"])
        self.assertIn("一般質問は課題0件・投入0件・活動0件・手続き0件・結果2件・成果0件・めざす姿0件（全2件）", k["statement"])
        self.assertNotIn("やりとりの記録が無い", k["statement"])
        self.assertEqual([x["statement"].split("」")[0] for x in got[1:]], ["「再編の方針", "「提言"])
        self.assertIn("この値の記載がある資料：「提言」", got[1]["statement"])
        self.assertEqual({x["layer"] for x in got}, {"論点の候補（未確認）"})

    def test_era_years_and_after(self):
        self.assertEqual(bt.era_years("令和１０年度"), (("令和", 10),))
        self.assertEqual(bt.era_years("令和6年から令和11年まで"), (("令和", 6), ("令和", 11)))
        self.assertEqual(bt.era_years("令和元年5月"), (("令和", 1),))
        self.assertEqual(bt.era_years("来年度"), ())
        self.assertTrue(bt.is_after("2025-04", "2025-03-10"))
        self.assertFalse(bt.is_after("2025-03", "2025-03-10"))   # 同じ月は後にしない
        self.assertTrue(bt.is_after("2025-03-11", "2025-03-10"))
        self.assertFalse(bt.is_after("", "2025-03-10"))

    def test_yotei(self):
        led = tr.ledgers()
        base = dict(led["kotogara"][0], point="新こども園の用地", yaritori="")
        led["kotogara"] += [
            dict(base, source="doc:teigen/1", source_date="2025-03", quote="令和10年度", target="令和10年度", kind="予定"),
            dict(base, source="doc:teigen/2", source_date="2025-06", quote="令和10年4月", target="令和10年4月", kind="予定"),
            dict(base, source="doc:teigen/2", source_date="2026-06", quote="令和11年度", target="令和１１年度", kind="予定"),
            dict(base, source="doc:teigen/2", source_date="2026-07", quote="見直しました", target="令和11年4月", kind="変更",
                 prev="令和10年4月", reason="品質を優先して見直しました。")]
        y = [x for x in issues(led=led) if x["type"] == "予定の変更"]
        self.assertEqual(len(y), 1)
        self.assertEqual(y[0]["statement"],
                         "新こども園の用地は、2025-03の「提言」では令和10年度（予定）、2026-06の「提言」では令和１１年度（予定）、"
                         "2026-07の「提言」では令和11年4月（変更）。理由として「品質を優先して見直しました。」")
        self.assertEqual((y[0]["scope"], y[0]["program"], len(y[0]["refs"])), ("事業", "node:jisshi/e008", 4))

    def test_yotei_same_year_is_not_change(self):
        led = tr.ledgers()
        base = dict(led["shisetsu"][0], aspect="状態", value="開設", kind="予定")
        led["shisetsu"] += [dict(base, source_date="2025-03", target="令和10年度", quote="a"),
                            dict(base, source_date="2025-06", target="令和10年4月", quote="b"),
                            dict(base, value="休園", source_date="2026-06", target="令和8年4月", quote="c")]
        self.assertEqual([x for x in issues(led=led) if x["type"] == "予定の変更"], [])

    def test_ryuho(self):
        led = tr.ledgers()
        led["yaritori"][1]["kind"] = "留保"
        k = led["kotogara"][0]
        led["kotogara"].append(dict(k, source="doc:teigen/2", source_date="2025-02", quote="定員は決まった", yaritori=""))
        r = [x for x in issues(led=led) if x["type"] == "留保のその後"]
        self.assertEqual(r[0]["statement"], "2025-01-01の答え（子ども支援課長）は、新こども園の定員について時期や中身を後に回した。"
                                            "そのあと、2025-02の「提言」がある")
        led["kotogara"].pop()
        r = [x for x in issues(led=led) if x["type"] == "留保のその後"]
        self.assertTrue(r[0]["statement"].endswith("そのあとの記録は無い"))

    def test_mokuteki(self):
        led = tr.ledgers()
        led["tsunagari"][0]["link"] = "目的と手段"
        m = [x for x in issues(led=led) if x["type"] == "つながりの記録に無い目的"]
        self.assertEqual([x["statement"] for x in m], ["「提言」を手段とする目的の記載は、つながりの記録に無い"])

    def test_yakuwari(self):
        led = tr.ledgers()
        base = led["shisetsu"][0]
        led["shisetsu"].append(dict(base, aspect="状態", value="休園", source_date="2026-03", quote="休園する", kind="予定"))
        y = [x for x in issues(led=led) if x["type"] == "役割のその後"]
        self.assertEqual(y[0]["statement"], "見本園は、2018-04の「提言」で指定避難所。2026-03の「提言」では休園（予定）。そのあとの記録は無い")
        led["shisetsu"].append(dict(base, source=f"sp:{sid(6)}", source_date="2026-05", quote="面積はどうか。"))
        y = [x for x in issues(led=led) if x["type"] == "役割のその後"]
        self.assertTrue(y[0]["statement"].endswith("そのあと、2026-05の令和7年3月定例会議の議員の発言がある（見本園の指定避難所）"))

    def test_kurikaeshi(self):
        d = make_data()
        L = bt.Labels(d, tr.shisetsu_ref())

        def q(qid, mid, name):
            return dict(question=qid, date="2025-01-01", meeting_id=mid, meeting=name,
                        rows=[dict(side="問い", point="新こども園の用地", stage="投入", layer="確定")])
        R = {"yaritori": [q(f"iq:{sid(2)}", "m1", "3月"), q(f"iq:{sid(10)}", "m2", "6月")], "shitsugi": []}
        k = bt.issues_kurikaeshi(L, R)
        self.assertEqual([x["statement"] for x in k], ["「新こども園の用地」は、3月・6月の問いで問われた"])
        R["yaritori"][1]["meeting_id"] = "m1"
        self.assertEqual(bt.issues_kurikaeshi(L, R), [])

    def test_yosan(self):
        rf = refs()
        rf["fuhyo"] = []
        y = [x for x in issues(rf=rf) if x["type"] == "計画と予算"]
        self.assertEqual([(x["statement"], x["scope"], x["program"]) for x in y],
                         [("認定こども園整備事業は実施年度に令和8年度があるが、令和8年度の附表に当たる事業が無い", "事業", "node:jisshi/e008")])

    def test_unconfirmed_prefix(self):
        led = tr.ledgers()
        led["tsunagari"][0].update(status="candidate", reviewer="", date="")
        t = [x for x in issues(led=led) if x["type"] == "問われていない点"]
        self.assertTrue(t[0]["statement"].startswith("記録（未確認）による。"))

    def test_missing_records(self):
        rows = theme_rows() + [dict(theme_rows()[0], kind="問い", value=f"iq:{sid(10)}")]
        k = [x for x in issues(themes=sorted(rows, key=lambda r: (r["theme"], r["kind"], r["value"])))
             if x["type"] == "問われていない区分"]
        self.assertTrue(k[0]["statement"].endswith("。テーマの問い2問のうち1問は、やりとりの記録が無い"))

    def test_labels(self):
        L = bt.Labels(make_data(), tr.shisetsu_ref())
        self.assertEqual(L.source(f"sp:{sid(6)}"), "令和7年3月定例会議の議員の発言")
        self.assertEqual(L.source(f"sp:{sid(4)}"), "令和7年3月定例会議の子ども支援課長の発言")
        self.assertEqual(L.source("doc:teigen/2"), "「提言」")
        self.assertEqual(L.source("bq:30/松田洋子/1"), "議会だより第30号")
        self.assertEqual(L.source("pt:youho/honpen/1"), "再編整備計画")
        self.assertEqual(L.source(f"gi:{M}/議第1号"), "令和7年3月定例会議の議第1号")
        self.assertEqual(L.fac("fa:a"), "見本園")

    def test_empty_url(self):
        d = build()
        d["issues"][0]["refs"][0]["url"] = ""
        self.assertEqual(bt.check_no_empty_url(d), [f"issues/問われていない区分：records/yaritori/{tr.IQ}"])


class RecordsFixTest(unittest.TestCase):
    def test_sentence_end_ascii(self):
        t, ss = rc.sentences("面積はどうか？　次です。")   # 全角の「？」は正規化で「?」になる
        self.assertEqual([x for _, _, x in ss], ["面積はどうか?", "次です。"])

    def test_not_demonstrative(self):
        inp = tr.inputs()
        inp.statements[sid(4)]["text"] = "それから、定員は285人です。"
        led = tr.ledgers()
        led["yaritori"][1]["quote"] = "それから、定員は285人です。"
        led["kotogara"][0]["quote"] = "それから、定員は285人です。"
        rep = tr.run(led, inp=inp)
        self.assertEqual([r for r in rep.quote_context if r["kind"] == "指示語で始まる"], [])

    def test_report_without_breakdown(self):
        lines = check_records.report_lines(tr.run())
        self.assertIn("- 発言の取りこぼし：5（yaritori 5。torikoboshi.tsv）", lines)
        self.assertIn("- 引用の前後：0（quote_context.tsv）", lines)


if __name__ == "__main__":
    unittest.main()
