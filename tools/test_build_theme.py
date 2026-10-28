"""tools/build_theme.py の検査（LINK_SCHEMA.md §13・§13.3・§13.4）と、tools/records.py・tools/check_records.py の
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
PLAN_YOUHO = {"id": "youho", "meta": {"posted": "令和7年3月策定"}, "sources": [{"url": "https://example.jp/youho.pdf"}], "tabs": []}


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
    d.questions = {"bq:30/松田洋子/1": {"pub_date": "2025-05-15", "minutes_exchange": "https://example.jp/ex",
                                    "bulletin": "https://example.jp/b.pdf"}}
    d.manifest = {}
    d.plans = {"jisshi": PLAN_JISSHI, "sogo6": PLAN_SOGO6, "youho": PLAN_YOUHO}
    d.sources_index = [{"id": "kodomo", "file": "honpen.pdf", "url": "https://example.jp/kodomo.pdf"},
                       {"id": "youho", "file": "honpen.pdf", "url": "https://example.jp/youho.pdf"},
                       {"id": "fuhyo-r8", "file": "r8jigyou.pdf", "url": "https://example.jp/fuhyo.pdf"}]
    d.fuhyo = {"fuhyo-r8": {"id": "fuhyo-r8", "source": {"id": "fuhyo-r8", "file": "r8jigyou.pdf"}, "pillars": [
        {"items": [{"key": "b010", "kubun": ["新規"], "kan": "民生費", "name": "認定こども園整備事業", "desc": "",
                    "amount": 228421, "dept": ["子ども支援課"], "page": 1}]}]}}
    d.docs = {"teigen": {"id": "teigen", "category": "shingi", "title": "提言", "fiscal_year": "2023", "date": "",
                         "pages": "2", "check": "ok", "url": "https://example.jp/teigen.pdf"}}
    d.doc_files = {"data/text/teigen.txt", "data/ocr/teigen.txt"}
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


def build(led=None, rf=None):
    d = make_data()
    d.inp.nodes |= {"node:sogo6/e011", "node:sogo6/e047"}
    d.inp.series |= {"kodomo"}
    return bt.build("hoiku", theme_rows(), led or tr.ledgers(), d, {"hino-council-search": {"sha": "a" * 40}},
                    rf or refs(), {"ref/themes.tsv": "x"})


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
        self.assertEqual(d["hits"], {"council": [], "docs": []})
        self.assertEqual((d["sheets"], d["issues"]), ([], []))
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
