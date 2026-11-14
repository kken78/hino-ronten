"""tools/build_rag.py の検査（LINK_SCHEMA §17）。"""
import io
import json
import os
import re
import sys
import tempfile
import unittest
import zipfile
from xml.etree import ElementTree

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import build_rag as br  # noqa: E402

P = "node:jisshi/e008"
U = "https://example.jp/"


def q(question, date, meeting, name, rows):
    return {"question": question, "meeting_id": "m", "meeting": meeting, "date": date,
            "member": {"key": "k", "name": name, "seat": 1}, "rows": rows}


def qrow(row, side, quote, layer="確定", **kw):
    r = {"row": str(row), "side": side, "quote": quote, "speaker": "町長" if side == "答え" else "", "round": "1",
         "stage": "結果" if side == "問い" else "", "kind": "留保" if side == "答え" else "事実の確認",
         "point": "開園時期", "url": U + f"q{row}", "layer": layer}
    r.update(kw)
    return r


KOT = [("doc:a/1", "令和10年度の開設を目指します。"), ("doc:b/1", "開園時期を見直しました。"), ("sp:1", "令和10年度の開園をめどに")]
KADAI = [{"ref": "plan:youho/hoshin/challenges/1/1", "text": "① 出生数の減少", "source": "youho/honpen p.18-19",
          "url": U + "youho.pdf#page=20"}]


def sheet(view, kind, name, **kw):
    s = {"view": view, "view_kind": kind, "name": name,
         "vision": [{"text": "めざす姿:どの子も育つまち", "source": U + "sogo.pdf"}], "kadai": KADAI,
         "cost": [], "desc": [], "tsunagari": [], "kotogara": [], "shisetsu": [], "katei": [], "asked": []}
    s.update(kw)
    return s


def data(**kw):
    d = {
        "theme": "hoiku", "name": "幼児教育・保育施設の再編",
        "lock": {"hino-council-search": "1af9baa0", "shiga-hino-plans": "807b1680"},
        "programs": [{"key": P, "name": "認定こども園整備事業", "desc": "新こども園を整備する。", "field_no": "分野①",
                      "field_name": "子ども・子育て", "years": ["R8", "R9"], "source": U + "jisshi.pdf",
                      "cost": {"label": "概算事業費", "amount": 3000000, "unit": "千円"}, "layer": "確定",
                      "policy": "node:sogo6/e047"}],
        "budget": [{"key": "fh:fuhyo-r8/b010", "program": P, "name": "認定こども園整備事業", "kubun": ["新規"],
                    "amount": 228421, "unit": "千円", "dept": ["子ども支援課"], "url": U + "fuhyo.pdf#page=1"}],
        "policies": [{"key": "node:sogo6/e011", "kind": "分野", "no": "①", "name": "子ども・子育て", "source": U + "sogo.pdf"},
                     {"key": "node:sogo6/e047", "kind": "基本施策", "no": "(3)", "name": "幼児教育・保育の充実", "source": U + "sogo.pdf"}],
        "plans": [{"key": "plan:youho", "name": "再編整備計画", "start_fy": "2024", "end_fy": "2029", "posted": "",
                   "url": U + "youho"}],
        "docs": [{"category": "koho", "title": "広報ひの", "date": "2026-07", "fiscal_year": "2026", "url": U + "koho.pdf"},
                 {"category": "jigyo", "title": "基本構想", "date": "", "fiscal_year": "2025", "url": "https://web.archive.org/web/20250830131330id_/" + U + "k.pdf",
                  "original_url": U + "k.pdf", "archived": "2025-08-30"}],
        "sheets": [sheet(P, "事業", "認定こども園整備事業",
                         kotogara=[{"ref": f"records/kotogara/開園時期/{s}/{q}"} for s, q in KOT]),
                   sheet("plan:youho", "期の計画", "再編整備計画"),
                   sheet("fa:f1", "施設", "日野幼稚園"),
                   sheet("hoiku", "テーマ", "幼児教育・保育施設の再編",
                         kotogara=[{"ref": f"records/kotogara/開園時期/{s}/{q}"} for s, q in KOT])],
        "chushin": P,
        "exchanges": [{"meeting_id": "m", "meeting": "令和7年3月定例会", "date": "2025-03-10", "n": 1, "question": "iq:1",
                       "member": {"key": "k", "name": "日野花子", "seat": 1}, "titles": [{"title": "新こども園について", "n": 1}],
                       "titles_chosen": True,
                       "turns": [{"url": U + "t1"}]}],
        "bills": [{"key": "b", "meeting": "令和8年3月定例会議", "date": "2026-03-23", "no": "議案第1号", "title": "予算",
                   "result": "原案可決", "method": "起立", "debates": [], "url": U + "bill"}],
        "issues": [{"type": "予定の変更", "statement": "開園時期は、令和10年度から令和11年度", "layer": "論点の候補",
                    "refs": [{"ref": "records/kotogara/開園時期/doc:a/1/令和10年度の開設を目指します。", "text": "x",
                              "url": U + "a.pdf#page=1", "layer": "確定"},
                             {"ref": "records/yaritori/iq:1/2", "text": "y", "url": U + "q2", "layer": "確定"},
                             {"ref": "どこにも無い", "text": "z", "url": U + "z", "layer": "論点の候補"}]},
                   {"type": "問われていない点", "statement": "「懇話会の設置目的」は、取り上げられていない", "layer": "論点の候補",
                    "refs": [{"ref": "records/kisai/懇話会の設置目的/doc:c/2", "text": "在り方を検討する。",
                              "url": U + "c2", "layer": "確定"},
                             {"ref": "records/kotogara/開園時期/doc:a/1/令和10年度の開設を目指します。", "text": "x",
                              "url": U + "a.pdf#page=1", "layer": "確定"},
                             {"ref": "records/kotogara/開園時期/doc:b/1/開園時期を見直しました。", "text": "x2",
                              "url": U + "b.pdf#page=1", "layer": "確定"},
                             {"ref": "records/tsunagari/目的と手段/持続可能な環境/こども園の新設/doc:a/3", "text": "t",
                              "url": U + "a3", "layer": "確定"},
                             {"ref": "どこにも無い2", "text": "w", "url": U + "w", "layer": "確定"}]}],
        "records": {
            "kotogara": [
                {"point": "開園時期", "source": "doc:a/1", "source_date": "2025-03",
                 "quote": "令和10年度の開設を目指します。", "value": "", "target": "令和10年度", "kind": "予定",
                 "prev": "", "reason": "", "url": U + "a.pdf#page=1", "layer": "確定"},
                {"point": "開園時期", "source": "doc:b/1", "source_date": "2026-07",
                 "quote": "開園時期を見直しました。", "value": "", "target": "令和11年4月", "kind": "変更",
                 "prev": "令和10年4月", "reason": "安全性を優先する", "url": U + "b.pdf#page=1", "layer": "確定"},
                {"point": "開園時期", "source": "sp:1", "source_date": "2025-06-13",
                 "quote": "令和10年度の開園をめどに", "value": "", "target": "令和10年度", "kind": "予定",
                 "prev": "", "reason": "", "url": U + "sp1", "layer": "論点の候補"}],
            "shisetsu": [{"facility": "fa:f1", "aspect": "状態", "value": "閉園", "source": "doc:a/2", "source_date": "2025-03",
                          "quote": "閉園します。", "target": "令和10年度", "kind": "予定", "prev": "", "url": U + "a2",
                          "layer": "確定"}],
            "yaritori": [q("iq:1", "2025-03-10", "令和7年3月定例会", "日野花子",
                           [qrow(1, "問い", "開園はいつか"), qrow(2, "答え", "今後検討します")])],
            "shitsugi": [],
            "tsunagari": [{"link": "目的と手段", "upper": "持続可能な環境", "lower": "こども園の新設",
                           "source": "doc:a/3", "source_date": "2025-03", "quote": "新設を進めます。", "url": U + "a3",
                           "layer": "確定"}],
            "katei": [{"theme": "hoiku", "step": "1", "name": "懇話会", "from": "2022-07-12", "to": "2024-01-12",
                       "sources": "doc:c/1", "quote": "令和４年７月１２日", "url": U + "c1", "layer": "確定",
                       "date": "2026-10-28"}],
            "kisai": [{"title": "懇話会の設置目的", "about": "懇話会の設置目的", "source": "doc:c/2",
                       "source_date": "2022-07", "quote": "在り方を検討する。", "url": U + "c2", "layer": "確定",
                       "date": "2026-10-28"}],
        },
        "names": {"sources": {"doc:a/1": "再編整備計画", "doc:b/1": "「広報ひの」", "sp:1": "令和7年6月定例会議の課長の発言",
                              "doc:a/2": "再編整備計画", "doc:a/3": "再編整備計画", "doc:c/2": "懇話会の資料",
                              "doc:c/1": "懇話会の資料（第1回）"},
                  "facilities": {"fa:f1": {"name": "日野幼稚園", "district": "日野"}}},
        "theme_questions": 16,
        "hits": {"council": [{"excerpt": "キーワードの一致"}], "docs": []},
    }
    d.update(kw)
    return json.dumps(d, ensure_ascii=False).encode("utf-8")


def area_data():
    """地区・組織の見方の見本（DESIGN.md ADR-32）：dist:hino「日野」と org:kucho-kai「日野町区長会」のシートと names.views。
    日野地区の施設は fa:f1 と fa:f2。fa:f3 は別の地区。施設の記録に面「規模」の行を1つ足す。"""
    d = json.loads(data())
    d["sheets"][-1:-1] = [sheet("dist:hino", "地区", "日野"), sheet("org:kucho-kai", "組織", "日野町区長会")]
    d["names"]["views"] = {"dist:hino": {"name": "日野", "aliases": []},
                           "fa:f1": {"name": "日野幼稚園", "district": "日野"},
                           "fa:f2": {"name": "保育所あおぞら園", "district": "日野"},
                           "fa:f3": {"name": "必佐幼稚園", "district": "必佐"},
                           "node:jisshi/e008": {"name": "認定こども園整備事業"},
                           "org:kucho-kai": {"name": "日野町区長会", "aliases": ["区長会", "区長連絡会"]}}
    d["records"]["shisetsu"].append({"facility": "fa:f1", "aspect": "規模", "value": "1,278㎡", "source": "doc:a/2",
                                     "source_date": "2025-03", "quote": "延床面積1,278㎡", "target": "", "kind": "いまのこと",
                                     "prev": "", "url": U + "a2", "layer": "確定"})
    return json.dumps(d, ensure_ascii=False).encode("utf-8")


def docx_bytes(md):
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "a.docx")
        br.write_docx(path, md)
        with open(path, "rb") as f:
            return f.read()


def built(**kw):
    return br.build(data(**kw), P)


def frame_data():
    """枠・資料の種類・筋のある見本（LINK_SCHEMA §17.1〜§17.3。DESIGN.md ADR-37）。開園時期の事柄の行と、about 開園時期と
    about 空の記載の行を、資料 doc:a の筋1 にする。"""
    d = json.loads(data())
    k = d["records"]["kotogara"][0]
    k.update(suji="1", suji_key="suji:a/1", shurui="定期監査の報告")
    d["records"]["kisai"] += [
        {"title": "要望の文", "about": "開園時期", "source": "doc:a/1", "source_date": "2025-03", "quote": "留意されたい。",
         "kind": "要望", "target": "", "suji": "1", "suji_key": "suji:a/1", "shurui": "定期監査の報告", "url": U + "a.pdf#page=1",
         "layer": "論点の候補"},
        {"title": "計画の期", "about": "", "source": "doc:a/1", "source_date": "2025-03", "quote": "計画は３年毎に見直す。",
         "kind": "事実", "target": "", "suji": "1", "suji_key": "suji:a/1", "shurui": "定期監査の報告", "url": U + "a.pdf#page=1",
         "layer": "論点の候補"}]
    rows = [("kisai", "records/kisai/計画の期/doc:a/1", "", "事実", "計画は３年毎に見直す。"),
            ("kotogara", "records/kotogara/開園時期/doc:a/1/令和10年度の開設を目指します。", "開園時期", "事実", "令和10年度の開設を目指します。"),
            ("kisai", "records/kisai/要望の文/doc:a/1", "開園時期", "要望", "留意されたい。")]
    d["suji"] = [{"key": "suji:a/1", "doc": "doc:a", "n": 1, "shurui": "定期監査の報告", "url": U + "a.pdf", "layer": "記録（未確認）",
                  "rows": [{"ledger": l, "ref": r, "point": p, "kind": k2, "target": "", "quote": q, "source": "doc:a/1",
                            "source_date": "2025-03", "page": 1, "pos": i, "layer": "記録（未確認）"} for i, (l, r, p, k2, q) in enumerate(rows)]}]
    d["suji"][0]["bun"] = [{"quote": q, "kind": k2, "refs": [r], "points": [{"point": p, "kind": k2}], "layer": "記録（未確認）" if l == "kisai" else "確定"}
                           for l, r, p, k2, q in rows]
    d["waku"] = [{"key": "waku:w", "name": "流れ", "source": "pt:x/honpen/49", "url": U + "x.pdf#page=49", "note": "", "layer": "確定", "nendo": [],
                  "elements": [{"view": "waku:w/1", "n": 1, "name": "開園の推計", "note": "", "points": ["開園時期"],
                                "rec": {"定期監査の報告": ["2025"]}, "gikai": 2},
                               {"view": "waku:w/2", "n": 2, "name": "単価の設定", "note": "図の注「※改定反映」", "points": [], "rec": {},
                                "gikai": 0}]}]
    d["shiryo"] = [{"shurui": "定期監査の報告", "match": "a", "tsukuru": "監査委員（合議）", "konkyo": "地方自治法199条",
                    "atesaki": "議会・町長", "outou": "措置の通知と公表", "source": "見本", "note": ""}]
    d["names"]["sources"]["pt:x/honpen/49"] = "第9期計画"
    return json.dumps(d, ensure_ascii=False).encode("utf-8")


def kessan_bill():
    """提案の説明の記録の行（paras）と質疑の記録の行（rows）のある決算の議案（LINK_SCHEMA §13.4・§16.1・§17。2026-11-15）。
    paras の段落16 は同じ文を2行に記録（記載の種類が違う）、段落18 は記録（未確認）。rows は、問いの2行が同じ事項、
    答えの3行は事項が変わり最後の行は事項なし、再質問は記録（未確認）。tools/test_build_pages.py・test_mcp_ronten.py も使う。"""
    C, N = "確定", "記録（未確認）"
    pr = lambda ledger, point, kind, quote, layer=C: {"ledger": ledger, "ref": f"records/{ledger}/{quote}", "point": point,
                                                     "kind": kind, "quote": quote, "layer": layer}
    sr = lambda row, side, sid, speaker, rnd, quote, point, layer=C: {"row": row, "side": side, "sid": sid, "speaker": speaker,
                                                                      "round": rnd, "quote": quote, "point": point, "layer": layer}
    member = {"key": "mb:松田洋子", "name": "松田洋子", "seat": "4番"}
    return {"key": "gi:0000008116/議第64号", "meeting_id": "0000008116", "meeting": "令和6年9月定例会議", "date": "2024-12-02",
            "no": "議第64号", "kind": "決算", "title": "決算について", "committee": "", "result": "認定", "method": "起立多数",
            "debates": [], "url": U + "m.html", "layer": C,
            "kessan": {"fiscal_year": "2023", "decided_meeting_id": "0000008211", "decided_meeting": "令和6年12月定例会",
                       "vote_date": "2024-12-02",
                       "proposals": [{"date": "2024-09-02", "role": "町長", "sid": "sp:p0", "url": "p0", "paras": []},
                                     {"date": "2024-09-02", "role": "代表監査委員", "sid": "sp:p1", "url": "p1", "paras": [
                                         {"p": 16, "rows": [pr("kisai", "", "事実", "３年目にあたります。"),
                                                            pr("kotogara", "給付費の計画と実績", "事実", "計画比率は81.6パーセントにとどまりました。"),
                                                            pr("kisai", "要介護認定率", "要望", "計画比率は81.6パーセントにとどまりました。")]},
                                         {"p": 18, "rows": [pr("kisai", "介護予防の取り組み", "要望", "連携をお願いします。", N)]}]}],
                       "steps": [{"kind": "質疑", "date": "2024-09-12", "member": member, "committee": "", "nbills": 1, "stance": "",
                                  "sid": "sp:q1", "url": "u1", "rows": [
                                      sr("1", "問い", "sp:q1", "議員", "最初の問い", "問1。", "給付費の計画と実績"),
                                      sr("2", "問い", "sp:q1", "議員", "最初の問い", "問2。", "給付費の計画と実績"),
                                      sr("3", "答え", "sp:a1", "厚生主監", "最初の問い", "答1。", "給付費の計画と実績"),
                                      sr("4", "答え", "sp:a1", "厚生主監", "最初の問い", "答2。", "第8期の計画の指標"),
                                      sr("5", "答え", "sp:a1", "厚生主監", "最初の問い", "答3。", ""),
                                      sr("6", "問い", "sp:q2", "議員", "再質問1", "再1。", "介護予防の取り組み", N)]},
                                 {"kind": "委員長の報告", "date": "2024-12-02", "member": {"key": "", "name": "x", "seat": ""},
                                  "committee": "決算特別委員会", "nbills": 7, "stance": "", "sid": "sp:r1", "url": "u2"}]}}


class FrameTest(unittest.TestCase):
    def test_honpen(self):
        honpen, kiroku = br.build(frame_data(), P)
        # 主な事項の記載の推移に、about がその事柄の記載の行も入り、項目の欄を書く
        self.assertIn("- 【未確認】［2025年3月］再編整備計画：資料の種類：定期監査の報告。見出し：要望の文。記載の種類：要望。"
                      "項目：再編整備計画の項目1（3件のうち3件目。suji:a/1）。「留意されたい。」", honpen)
        self.assertIn("資料の種類：定期監査の報告。対象の時期：令和10年度。書き方：予定。項目：再編整備計画の項目1（3件のうち2件目。suji:a/1）。", honpen)
        # 枠組みの表と資料の種類（表を使わない）。要素の note は出さない
        self.assertIn("## 認定こども園整備事業：流れと、資料の記載状況", honpen)
        self.assertIn("- 要素1：開園の推計。該当する事項：開園時期。資料別の記載年：定期監査の報告：2025。議会での質問・答弁の記録数：2", honpen)
        self.assertIn("- 要素2：単価の設定。該当する事項：該当する事項なし。資料別の記載年：未記録\n", honpen)
        self.assertNotIn("※改定反映", honpen)
        self.assertIn(br.WAKU_NOTE, honpen)
        self.assertIn("## 認定こども園整備事業：資料の種類と根拠法令", honpen)
        self.assertIn("- 資料の種類：定期監査の報告。作成者：監査委員（合議）。根拠法令：地方自治法199条。", honpen)
        # 事項ごとの質問・答弁にも記載の行
        part = honpen[honpen.index("事項ごとの質問・答弁：開園時期"):]
        self.assertIn("見出し：要望の文。", part[:part.index("照合結果")])

    def test_items(self):
        # 枠組みの要素に当たらない資料の種類の項目は、本編の節「<資料の種類>」に項目の段落で（LINK_SCHEMA §16.1・§17.1・§17.2）。
        # 記録編には章「同じ項目の記載」を置かない（DESIGN.md ADR-37 の経過、2026-11-14）
        honpen, kiroku = br.build(frame_data(), P)
        self.assertNotIn("同じ項目の記載", kiroku)
        self.assertIn("## 認定こども園整備事業：定期監査の報告", honpen)
        self.assertIn("### 認定こども園整備事業：定期監査の報告：再編整備計画（2025年3月）", honpen)
        self.assertIn("資料ごとに、記録した項目を段落で示します。地方自治法199条による定期監査の報告です。\n", honpen)
        self.assertIn("- ［2025年3月］再編整備計画の項目1（suji:a/1）：【未確認】［事実］「計画は３年毎に見直す。」"
                      "［事実］「令和10年度の開設を目指します。」（事項：開園時期）【未確認】［要望］「留意されたい。」（事項：開園時期）（出典：", honpen)
        self.assertNotIn("：定期監査の報告：", built()[0])

    def test_law_article(self):
        # 法令の条（LINK_SCHEMA §16.4）：最初の条項から法令の名前と条
        self.assertEqual([br.law_article(t) for t in ("地方自治法（昭和二十二年法律第六十七号）第233条（e-Gov 法令検索）", "地方自治法199条1項・2項・9項",
                                                      "地方公共団体の財政の健全化に関する法律3条1項", "設置要綱", "", "pt:x/honpen/49")],
                         ["地方自治法233条", "地方自治法199条", "地方公共団体の財政の健全化に関する法律3条", "", "", ""])
        self.assertEqual(br.flow_lead({"name": "流れ", "source": "pt:x/honpen/49"}), "流れの要素の順に、資料と議案を示します。")
        self.assertEqual(br.section_lead({"konkyo": "地方自治法199条1項"}, "定期監査の報告", [{"name": "決算の認定までの流れ"}]),
                         "地方自治法199条による定期監査の報告です。決算の認定までの流れとは別のものです。")
        self.assertEqual(br.section_lead({"konkyo": "設置要綱"}, "提言", []), "")

    def test_bill_lines(self):
        # 議案を置く枠組みの要素（LINK_SCHEMA §16.1・§17.2）：提出・審議・議決。無いものは決まった文
        b = {"meeting": "令和7年9月定例会議", "no": "議第70号", "title": "決算について", "url": U + "m.html", "result": "認定",
             "method": "起立多数", "kessan": {"decided_meeting": "令和7年12月定例会議", "vote_date": "2025-12-01", "proposals": [],
             "steps": [{"kind": "質疑", "date": "2025-09-11", "member": {"name": "松田洋子", "seat": "4番"}, "nbills": 2, "stance": "", "url": "u1"},
                       {"kind": "委員長の報告", "date": "2025-12-01", "member": {"name": "x", "seat": ""}, "committee": "予算決算特別委員会",
                        "nbills": 7, "stance": "", "url": "u2"},
                       {"kind": "討論", "date": "2025-12-01", "member": {"name": "加藤和幸", "seat": "10番"}, "nbills": 3, "stance": "反対", "url": "u3"}]}}
        self.assertEqual(br.Rag.bill_lines(0, b), ["議案：令和7年9月定例会議の議第70号「決算について」（出典：" + U + "m.html）", br.NO_PROPOSAL])
        self.assertEqual(br.Rag.bill_lines(1, b), ["［2025年9月11日］質疑：4番 松田洋子 議員（2議案について）（出典：u1）",
                                                   "［2025年12月1日］委員長の報告：予算決算特別委員会（7議案について）（出典：u2）",
                                                   "［2025年12月1日］討論：10番 加藤和幸 議員。賛否：反対（出典：u3）", br.NO_IINKAI])
        self.assertEqual(br.Rag.bill_lines(2, b), ["議決：認定。採決の方法：起立多数。採決の日付：2025年12月1日。議決の会議：令和7年12月定例会議（出典：" + U + "m.html）"])
        b["kessan"]["steps"] = []
        self.assertEqual(br.Rag.bill_lines(1, b), [br.NO_STEPS, br.NO_IINKAI])

    def test_bill_lines_records(self):
        # 提案の説明の記録の行（paras）と、質疑の記録の行（rows）の箇条（LINK_SCHEMA §17、2026-11-15）
        b = kessan_bill()
        self.assertEqual(br.Rag.bill_lines(0, b), [
            "議案：令和6年9月定例会議の議第64号「決算について」（出典：" + U + "m.html）",
            "［2024年9月2日］提案の説明：町長（出典：p0）",
            "［2024年9月2日］提案の説明：代表監査委員（出典：p1）",
            "提案の説明の記載（代表監査委員。段落16）：［事実］「３年目にあたります。」"
            "［事実］「計画比率は81.6パーセントにとどまりました。」（事項：給付費の計画と実績、要介護認定率（要望））",
            "提案の説明の記載（代表監査委員。段落18）：【未確認】［要望］「連携をお願いします。」（事項：介護予防の取り組み）"])
        self.assertEqual(br.Rag.bill_lines(1, b), [
            "［2024年9月12日］質疑：4番 松田洋子 議員（1議案について）（出典：u1）",
            "問い　4番 松田洋子 議員：「問1。」「問2。」（事項：給付費の計画と実績）",
            "答え　厚生主監：「答1。」（事項：給付費の計画と実績）「答2。」（事項：第8期の計画の指標）「答3。」",
            "再質問1　4番 松田洋子 議員：【未確認】「再1。」（事項：介護予防の取り組み）",
            "［2024年12月2日］委員長の報告：決算特別委員会（7議案について）（出典：u2）", br.NO_IINKAI])

    def test_flow(self):
        # 要素に資料の種類が当たる枠組みは、年度ごとの節目の<枠組みの名前>（年度）に要素を番号の順に全部
        d = json.loads(frame_data())
        d["waku"].append({"key": "waku:k", "name": "決算の流れ", "source": "地方自治法（昭和二十二年法律第六十七号）第233条", "url": "",
                          "note": "", "layer": "確定",
                          "elements": [{"view": "waku:k/1", "n": 1, "name": "調製", "note": "", "source": "地方自治法233条1項",
                                        "shiryo": [], "points": [], "rec": {}, "gikai": 0},
                                       {"view": "waku:k/2", "n": 2, "name": "審査", "note": "", "source": "地方自治法233条2項",
                                        "shiryo": ["定期監査の報告"], "points": [], "rec": {"定期監査の報告": ["2025"]}, "gikai": 0}],
                          "nendo": [{"fiscal_year": "2024", "elements": [
                              {"n": 1, "docs": []},
                              {"n": 2, "docs": [{"doc": "doc:a", "date": "2025-03", "suji": ["suji:a/1"], "nosuji": 2}]}]}]})
        honpen, _ = br.build(json.dumps(d, ensure_ascii=False).encode("utf-8"), P)
        self.assertIn("### 認定こども園整備事業：年度ごとの節目：決算の流れ（令和6年度）", honpen)
        self.assertIn("要素1：調製（地方自治法233条1項）。" + br.NO_SHURUI, honpen)
        self.assertIn("要素2：審査（地方自治法233条2項）。資料：再編整備計画（2025年3月）", honpen)
        self.assertIn("この資料には、ここに出していない記載が2件あります（事項の所に出ます）。", honpen)
        self.assertIn("地方自治法233条の手続きの順に、資料と議案を示します。資料の記載は項目ごとの段落です。", honpen)
        self.assertIn("枠組み：決算の流れ。出典：地方自治法（昭和二十二年法律第六十七号）第233条\n", honpen)
        self.assertIn("- 要素1：調製（地方自治法233条1項）。該当する事項：該当する事項なし。", honpen)
        # 流れに置いた項目は、資料の種類の節に重ねない
        self.assertNotIn("：定期監査の報告：再編整備計画", honpen)


class BuildTest(unittest.TestCase):
    def test_same_input_same_output(self):
        self.assertEqual(built(), built())
        honpen = built()[0]
        self.assertEqual(docx_bytes(honpen), docx_bytes(honpen))

    def test_guide(self):
        for md, part in zip(built(), ("本編", "記録編")):
            self.assertTrue(md.startswith(f"# 認定こども園整備事業（{part}）：この資料の読み方\n"))
            self.assertIn("テーマ「幼児教育・保育施設の再編」", md)
            self.assertRegex(md, r"sha256 [0-9a-f]{12}")
            self.assertIn("hino-council-search 1af9baa、shiga-hino-plans 807b168", md)
            # いちばん新しい資料の日付（記録の date＝人が確かめた日は使わない）
            self.assertIn("いちばん新しい記載の資料の日付は 2026年7月 です", md)

    def test_headings_have_program_name_and_depth(self):
        for md in built():
            hs = [h for h in md.split("\n") if h.startswith("#")]
            self.assertTrue(hs)
            for h in hs:
                m = re.match(r"(#{1,3}) (.*)", h)
                self.assertIsNotNone(m, h)      # 見出しは1〜3
                self.assertTrue(m.group(2).startswith("認定こども園整備事業"), h)

    def test_entries_have_source_and_no_tables(self):
        for md in built():
            for line in md.split("\n"):
                self.assertFalse(line.startswith("|"), line)
                if "「" in line and not line.startswith(("#", "- 記載は", "- 日野町の公開資料", "- 「【未確認】」の段落", "- 欄「資料の種類」", "- 欄「記載の種類」", "- 欄「項目」",
                                                                 "【未確認】", "比べた記載：記録編の")):
                    self.assertIn("出典：", line, line)

    def test_kisai_kind_and_target(self):
        # 構造にしていない記載の行は、見出しのあとに記載の種類と対象の時期を書く。空なら書かない（§17.1。ADR-36）
        honpen, kiroku = built()
        self.assertIn("見出し：懇話会の設置目的。「在り方を検討する。」", kiroku)
        self.assertNotIn("記載の種類：", kiroku)
        d = json.loads(data())
        d["records"]["kisai"][0].update(kind="要望", target="令和６年度")
        honpen, kiroku = br.build(json.dumps(d, ensure_ascii=False).encode("utf-8"), P)
        self.assertIn("見出し：懇話会の設置目的。記載の種類：要望。対象の時期：令和６年度。「在り方を検討する。」", kiroku)
        # 読み方に、記載の種類の意味を書く（ADR-36 の7）
        self.assertIn("欄「記載の種類」の事実・見通し・評価・要望は、資料の作成者（監査委員など）が記した内容の種類です。"
                      "評価・要望・見通しの区分は論点ノートによる評価ではありません", honpen)

    def test_entry_form(self):
        honpen, kiroku = built()
        self.assertIn("- ［2025年3月］再編整備計画：資料の種類：町の資料。対象の時期：令和10年度。書き方：予定。"
                      "「令和10年度の開設を目指します。」（出典：https://example.jp/a.pdf#page=1）", honpen)
        # 記録（未確認）の行
        self.assertIn("- 【未確認】［2025年6月13日］令和7年6月定例会議の課長の発言：", honpen)
        # 答弁の種類は表示の言葉（§16.3）
        self.assertIn("発言：答弁。発言者：町長。回：1。種類：今後検討。「今後検討します」", honpen)
        self.assertIn("発言：質問。発言者：日野花子 議員。回：1。区分：結果（施設・定員等）。種類：事実の確認。", kiroku)
        self.assertIn("面：状況。値：閉園。", kiroku)

    def test_honpen_chapters(self):
        honpen = built()[0]
        heads = [h for h in honpen.split("\n") if h.startswith("# ")]
        self.assertEqual(heads, ["# 認定こども園整備事業（本編）：この資料の読み方", "# 認定こども園整備事業（本編）：1 事業の要点",
                                 "# 認定こども園整備事業（本編）：2 概要", "# 認定こども園整備事業（本編）：3 論点整理",
                                 "# 認定こども園整備事業（本編）：4 事業の運営"])
        self.assertIn("当初予算額 228,421千円", honpen)
        self.assertIn("基本施策(3) 幼児教育・保育の充実（出典：https://example.jp/sogo.pdf）", honpen)
        # 主な事項：町の資料の最新の記載（会議録の発言は使わない）と変更
        self.assertIn("町の資料の最新の記載（2026年7月、「広報ひの」）：令和11年4月", honpen)
        self.assertIn("当初：令和10年4月　→　2026年7月に変更。変更理由：「安全性を優先する」", honpen)
        self.assertIn("再編整備計画 18〜19ページに掲げる課題：「① 出生数の減少」", honpen)
        self.assertIn("### 認定こども園整備事業：施設の再編：日野幼稚園（日野地区）", honpen)
        self.assertIn("### 認定こども園整備事業：年度ごとの節目：令和7年度", honpen)
        self.assertIn("一般質問：令和7年3月定例会　質問者：日野花子 議員　議会だよりの見出し：問1「新こども園について」", honpen)
        self.assertIn("出典の url のうち web.archive.org のものは、町のサイトに載らなくなった資料の、Webアーカイブの保存版です", honpen)
        self.assertIn("事業資料：基本構想（出典：https://web.archive.org/web/20250830131330id_/" + U + "k.pdf）。町のサイトに載らなくなったため、"
                      "Webアーカイブの保存版（2025年8月30日保存）を示す。町の元の url：" + U + "k.pdf", honpen)

    def test_bulletin_titles(self):
        # 議会だよりの見出し（LINK_SCHEMA §17.1、DESIGN.md ADR-28）
        t1, t2 = {"title": "通園制度", "n": 1}, {"title": "新こども園の大きさは", "n": 2}
        for x, want in (({"titles": [], "titles_chosen": False}, ""),
                        ({"titles": [t2], "titles_chosen": True}, "　議会だよりの見出し：問2「新こども園の大きさは」"),
                        ({"titles": [t1], "titles_chosen": False}, "　議会だよりの見出し：問1「通園制度」"),
                        ({"titles": [t1, t2], "titles_chosen": True}, "　議会だよりの見出し：問1「通園制度」、問2「新こども園の大きさは」"),
                        ({"titles": [t1, t2], "titles_chosen": False},
                         "　議会だよりの見出し（どの問いに当たるかは確かめていない）：問1「通園制度」、問2「新こども園の大きさは」")):
            with self.subTest(x=x):
                self.assertEqual(br.bulletin_titles(x), want)

    def test_issues(self):
        honpen = built()[0]
        self.assertIn("## 認定こども園整備事業：照合結果（未確認）", honpen)
        # 文の後ろに、比べた記載の出典を資料の日付の順に付ける。日付の分からないもの（記録の行に当たらない）は最後（§17.1）
        self.assertIn("【未確認】開園時期は、令和10年度から令和11年度（比べた記載の出典：https://example.jp/a.pdf#page=1、"
                      "https://example.jp/q2、https://example.jp/z）\n", honpen)
        # 比べた記載は、記録の行が分かれば資料の日付と名前を添える
        self.assertIn("- 比べた記載：［2025年3月］再編整備計画：資料の種類：町の資料。対象の時期：令和10年度。", honpen)
        self.assertIn("- 比べた記載：［2025年3月10日］令和7年3月定例会の一般質問：発言：答弁。", honpen)
        self.assertIn("- 比べた記載：【未確認】z（出典：https://example.jp/z）", honpen)
        # 問われていない点は、記録編のどの節にあるかを書き、記録の行に当たらないものだけ並べる（§17.1）
        s = honpen[honpen.index("：照合結果（未確認）：問われていない点"):]
        s = s[:s.index("\n## ")]
        self.assertIn("【未確認】「懇話会の設置目的」は、取り上げられていない\n\n比べた記載：記録編の「構造にしていない記載：懇話会の設置目的」に1件、"
                      "「事柄：開園時期」に2件、「つながり」に1件\n\n- 比べた記載：w（出典：https://example.jp/w）\n", s)
        self.assertNotIn("在り方を検討する。", s)

    def test_katei_form(self):
        honpen, kiroku = built()
        # 過程の記録は資料の日付が無いので［ ］を付けず、期間と1つめの資料の名前を書く（§17.1）
        line = ("- 検討の段階：段階：懇話会。期間：2022年7月12日〜2024年1月12日。資料：懇話会の資料（第1回）。資料の種類：町の資料。"
                "「令和４年７月１２日」（出典：https://example.jp/c1）")
        self.assertIn(line + "\n", kiroku)
        self.assertIn(line + "\n", honpen)        # 経過
        self.assertIn("- 検討の段階：懇話会。期間：2022年7月12日〜2024年1月12日（出典：https://example.jp/c1）", honpen)   # 年度ごとの節目
        for md in (honpen, kiroku):
            self.assertNotIn("］検討の段階", md)
        span = br.Rag.katei_span
        self.assertEqual(span({"from": "2026-04", "to": ""}), "2026年4月〜（継続中）")
        self.assertEqual(span({"from": "2026-01-14", "to": "2026-01-14"}), "2026年1月14日")
        self.assertEqual(span({"from": "", "to": ""}), br.jd(""))

    def test_katei_cycle(self):
        # 期のある過程の行は、段階の名前の前に期を書く（§15.5、DESIGN.md ADR-30）
        d = json.loads(data())
        d["records"]["katei"][0]["cycle"] = "第9期"
        honpen, kiroku = br.build(json.dumps(d, ensure_ascii=False).encode("utf-8"), P)
        self.assertIn("- 検討の段階：期：第9期。段階：懇話会。期間：2022年7月12日〜2024年1月12日。", kiroku)
        self.assertIn("- 検討の段階：期：第9期。懇話会。期間：2022年7月12日〜2024年1月12日（出典：", honpen)

    def test_latest_all_and_katei_order(self):
        d = json.loads(data())
        # 同じ最新の日付に value・target のある行がもう1つ：値は「／」でつなぐ（§16.2・§17.2）
        d["records"]["kotogara"].append(dict(d["records"]["kotogara"][1], quote="もう1つの文。", target="令和12年4月"))
        # from の無い段階：1つ前の段階（懇話会 2022-07-12）の直後。年度ごとの節目では「年度不明」
        d["records"]["katei"].append({"theme": "hoiku", "step": "2", "name": "検討会", "from": "", "to": "",
                                      "sources": "doc:c/1", "quote": "検討会を置く。", "url": U + "c1", "layer": "確定"})
        d["records"]["katei"].append({"theme": "hoiku", "step": "3", "name": "策定", "from": "2025-03", "to": "2025-03",
                                      "sources": "doc:a/1", "quote": "策定した。", "url": U + "a1", "layer": "確定"})
        honpen, kiroku = br.build(json.dumps(d, ensure_ascii=False).encode("utf-8"), P)
        self.assertIn("町の資料の最新の記載（2026年7月、「広報ひの」）：令和11年4月／令和12年4月", honpen)
        i, j, k = (honpen.index(x) for x in ("段階：懇話会。", "段階：検討会。期間：日付不明。", "段階：策定。"))
        self.assertLess(i, j)
        self.assertLess(j, k)
        self.assertIn("年度ごとの節目：年度不明", honpen)
        self.assertGreater(honpen.index("年度ごとの節目：年度不明"), honpen.index("年度ごとの節目：令和7年度"))

    def test_round_and_source_date(self):
        d = json.loads(data())
        sid = "sp:0000008397_20250310_0291"
        d["records"]["yaritori"][0]["rows"][1].update(sid=sid, round="再質問1")
        d["records"]["kotogara"].append({"point": "開園時期", "source": sid,
                                         "source_date": "2025-03-10", "quote": "答えの文。", "value": "", "target": "",
                                         "kind": "いまのこと", "prev": "", "reason": "", "url": U + "sp291", "layer": "確定"})
        d["names"]["sources"][sid] = "令和7年3月定例会の課長の発言"
        d["records"]["katei"].append({"theme": "hoiku", "step": "2", "name": "設計者の選定", "from": "2026-01-14",
                                      "to": "2026-01-14", "sources": "sp:0000008942_20260309_0233,doc:b/1",
                                      "quote": "契約を結んだ。", "url": U + "sp233", "layer": "確定"})
        d["records"]["katei"].append({"theme": "hoiku", "step": "3", "name": "予算", "from": "2026-04", "to": "",
                                      "sources": "doc:koho-no790-05/1", "quote": "取り組みます。", "url": U + "k790",
                                      "layer": "確定"})
        d["docs"].append({"id": "koho-no790-05", "category": "koho", "title": "予算のあらまし", "date": "2026-05", "url": U + "k790"})
        d["names"]["sources"]["sp:0000008942_20260309_0233"] = "令和8年3月定例会議の子ども支援課長の発言"
        d["names"]["sources"]["doc:koho-no790-05/1"] = "「予算のあらまし」"
        honpen, kiroku = br.build(json.dumps(d, ensure_ascii=False).encode("utf-8"), P)
        # 回：やりとりの記録の確定した行の round。無ければ未記録（§17.1）
        self.assertIn("［2025年3月10日］令和7年3月定例会の課長の発言：資料の種類：会議録。回：再質問1。書き方：いまのこと。「答えの文。」", kiroku)
        self.assertIn("［2025年6月13日］令和7年6月定例会議の課長の発言：資料の種類：会議録。回：未記録。", kiroku)
        self.assertNotIn("資料の種類：町の資料。回：", kiroku)          # 町の資料には回を付けない
        # 検討の段階：資料のキーから分かる資料の日付を添える（sp は発言の日、doc は台帳の date）。
        # 1つめの資料の種類と、会議録の発言なら回も書く（§17.1）
        self.assertIn("期間：2026年1月14日。資料：令和8年3月定例会議の子ども支援課長の発言（2026年3月9日）。資料の種類：会議録。回：未記録。"
                      "「契約を結んだ。」", kiroku)
        self.assertIn("期間：2026年4月〜（継続中）。資料：「予算のあらまし」（2026年5月）。資料の種類：広報ひの。「取り組みます。」", kiroku)
        self.assertIn("資料：懇話会の資料（第1回）。資料の種類：町の資料。「令和４年７月１２日」", kiroku)   # 台帳の date が無い doc は書かない
        # 検討の段階の資料の発言が、やりとりの記録の確定した行にあれば、その回
        d["records"]["yaritori"][0]["rows"][1].update(sid="sp:0000008942_20260309_0233", round="再質問2")
        kiroku = br.build(json.dumps(d, ensure_ascii=False).encode("utf-8"), P)[1]
        self.assertIn("（2026年3月9日）。資料の種類：会議録。回：再質問2。「契約を結んだ。」", kiroku)
        self.assertEqual([br.Rag.kind_of(k) for k in ("sp:1", "doc:koho-no790-05/1", "doc:a/1", "pt:x", "")],
                         ["会議録", "広報ひの", "町の資料", "町の資料", "町の資料"])

    def test_plan_dates(self):
        # 計画の posted の最後の年月を資料の日付にする（§17.1）
        self.assertEqual([br.posted_date(x) for x in ("令和8年4月", "令和7年3月策定・令和8年6月一部改正", "2021年3月発行",
                                                       "平成30年3月", "令和元年5月", "令和7年度", "")],
                         ["2026-04", "2026-06", "2021-03", "2018-03", "2019-05", "", ""])
        d = json.loads(data())
        d["programs"][0]["posted"] = "令和8年4月"
        for x in d["policies"]:
            x["posted"] = "2021年3月発行"
        d["sheets"][0]["vision"] = [dict(d["sheets"][0]["vision"][0], ref="policies/node:sogo6/e011")]
        d["plans"][0]["posted"] = "令和7年3月策定・令和8年6月一部改正"
        honpen = br.build(json.dumps(d, ensure_ascii=False).encode("utf-8"), P)[0]
        self.assertIn("［2026年4月］実施計画：事業名：認定こども園整備事業。", honpen)
        self.assertIn("［2026年4月］実施計画：概算事業費（令和8〜9年度）：3,000,000千円", honpen)
        self.assertIn("［2021年3月］総合計画：分野① 子ども・子育て／基本施策(3)", honpen)
        self.assertIn("- ［2021年3月］総合計画のめざす姿：「どの子も育つまち」", honpen)
        self.assertIn("- ［2026年6月］再編整備計画 18〜19ページに掲げる課題：「① 出生数の減少」（出典：https://example.jp/youho.pdf#page=20）", honpen)
        # posted が無ければ［ ］を付けない
        honpen = br.build(data(), P)[0]
        self.assertIn("\n実施計画：事業名：認定こども園整備事業。", honpen)
        self.assertIn("- 再編整備計画 18〜19ページに掲げる課題：「① 出生数の減少」", honpen)

    def test_none_text(self):
        d = json.loads(data())
        d["records"]["kotogara"] = [r for r in d["records"]["kotogara"] if r["source"].startswith("sp:")]
        honpen = br.build(json.dumps(d, ensure_ascii=False).encode("utf-8"), P)[0]
        self.assertIn("町の資料に記載なし（会議録の発言 1 件）。会議録の発言を日付順に示します。", honpen)

    def test_no_hits(self):
        for md in built():
            self.assertNotIn("キーワードの一致", md)
            self.assertNotIn("キーワード検索", md)

    def test_kiroku_all_rows(self):
        kiroku = built()[1]
        heads = [h for h in kiroku.split("\n") if h.startswith("# ")]
        self.assertEqual([h.split("：", 1)[1] for h in heads[1:]],
                         ["事柄", "施設", "やりとり（一般質問）", "質疑（議案）", "つながり", "過程", "構造にしていない記載"])
        for quote in ("令和10年度の開設を目指します。", "開園時期を見直しました。", "令和10年度の開園をめどに", "閉園します。",
                      "開園はいつか", "今後検討します", "新設を進めます。", "令和４年７月１２日", "在り方を検討する。"):
            self.assertIn(f"「{quote}」", kiroku)
        self.assertIn("関係：目的と手段。上位の記載：持続可能な環境。下位の記載：こども園の新設。", kiroku)
        self.assertIn("期間：2022年7月12日〜2024年1月12日", kiroku)

    def test_stops(self):
        with self.assertRaises(br.RagError):
            br.build(data(), "node:jisshi/e999")
        with self.assertRaises(br.RagError):
            built(sheets=[])
        with self.assertRaises(br.RagError):
            built(programs=[])        # 見方が事業なのに programs に無い
        for k in ("names", "chushin"):
            d = json.loads(data())
            del d[k]
            with self.assertRaises(br.RagError):
                br.build(json.dumps(d).encode("utf-8"), P)

    def test_basic_policy_of_program(self):
        # 基本施策は programs の policy で引く（テーマの最初の1つを出さない。§17.2、DESIGN.md ADR-31 の6）
        d = json.loads(data())
        d["policies"].insert(0, {"key": "node:sogo6/e040", "kind": "基本施策", "no": "(1)", "name": "別の施策", "source": U + "s.pdf"})
        honpen = br.build(json.dumps(d, ensure_ascii=False).encode("utf-8"), P)[0]
        self.assertIn("基本施策(3) 幼児教育・保育の充実", honpen)
        self.assertNotIn("別の施策", honpen)
        d["programs"][0]["policy"] = ""
        honpen = br.build(json.dumps(d, ensure_ascii=False).encode("utf-8"), P)[0]
        self.assertNotIn("総合計画：分野①", honpen)

    def test_other_views(self):
        # 期の計画・施設・テーマ自体の見方（§17.2 の1）。止まらず、要点の章に名前が出る
        d = json.loads(data())
        d["plans"][0]["posted"] = "令和7年3月策定"
        raw = json.dumps(d, ensure_ascii=False).encode("utf-8")
        honpen, kiroku = br.build(raw, "plan:youho")
        self.assertIn("# 再編整備計画（本編）：1 見方の要点", honpen)
        self.assertIn("［2025年3月］計画：再編整備計画。計画期間：2024〜2029年度。策定・改正：令和7年3月策定（出典：https://example.jp/youho）", honpen)
        self.assertIn("［2025年3月］再編整備計画 18〜19ページに掲げる課題：「① 出生数の減少」", honpen)
        self.assertNotIn("当初予算額", honpen)
        self.assertTrue(kiroku.startswith("# 再編整備計画（記録編）：この資料の読み方"))
        honpen = br.build(raw, "fa:f1")[0]
        self.assertIn("# 日野幼稚園（本編）：1 見方の要点", honpen)
        self.assertIn("施設：日野幼稚園。地区：日野", honpen)
        self.assertIn("いまの状態：［2025年3月］再編整備計画：資料の種類：町の資料。面：状況。値：閉園。", honpen)
        honpen = br.build(raw, "hoiku")[0]
        self.assertIn("# 幼児教育・保育施設の再編（本編）：1 見方の要点", honpen)
        self.assertIn("系列の計画：再編整備計画（出典：https://example.jp/youho）", honpen)
        self.assertIn("中心の見方：認定こども園整備事業（node:jisshi/e008）", honpen)
        d["chushin"] = ""
        honpen = br.build(json.dumps(d, ensure_ascii=False).encode("utf-8"), "hoiku")[0]
        self.assertIn("中心の見方：未記録", honpen)

    def test_area_views(self):
        # 地区・組織の見方（§14・§17.2 の1。ADR-32）：地区は名前とその地区の施設、組織は名前とほかの表記。事業の要点は出さない
        raw = area_data()
        honpen, kiroku = br.build(raw, "dist:hino")
        self.assertIn("# 日野（本編）：1 見方の要点", honpen)
        self.assertIn("地区：日野。施設：日野幼稚園、保育所あおぞら園\n", honpen)
        self.assertNotIn("必佐幼稚園", honpen)
        self.assertTrue(kiroku.startswith("# 日野（記録編）：この資料の読み方"))
        honpen = br.build(raw, "org:kucho-kai")[0]
        self.assertIn("# 日野町区長会（本編）：1 見方の要点", honpen)
        self.assertIn("組織：日野町区長会。ほかの表記：区長会、区長連絡会\n", honpen)
        for h in (br.build(raw, "dist:hino")[0], honpen):
            self.assertNotIn("当初予算額", h)
            self.assertNotIn("概算事業費", h)
            self.assertNotIn("1 事業の要点", h)
        # 施設の無い地区・ほかの表記の無い組織は「未記録」
        d = json.loads(raw)
        d["names"]["views"]["org:kucho-kai"]["aliases"] = []
        for k in ("fa:f1", "fa:f2"):
            d["names"]["views"][k]["district"] = ""
        raw2 = json.dumps(d, ensure_ascii=False).encode("utf-8")
        self.assertIn("地区：日野。施設：未記録\n", br.build(raw2, "dist:hino")[0])
        self.assertIn("組織：日野町区長会。ほかの表記：未記録\n", br.build(raw2, "org:kucho-kai")[0])

    def test_aspect_kibo(self):
        # 施設の記録の面「規模」（§15.8）は、表示の言葉を替えずにそのまま書く
        kiroku = br.build(area_data(), P)[1]
        self.assertIn("面：規模。値：1,278㎡。", kiroku)

    def test_point_scope(self):
        # 主な事項：その見方の事柄 → テーマ全体の事柄。ほかの見方だけの点は出さない（§16.2・§17.2）。記録編は全行（§17.3）
        d = json.loads(data())
        extra = [{"point": "用地", "source": "doc:a/4", "source_date": "2025-04", "quote": "用地を決めた。", "value": "",
                  "target": "", "kind": "済んだこと", "prev": "", "reason": "", "url": U + "a4", "layer": "確定"},
                 {"point": "定員", "source": "doc:a/5", "source_date": "2025-05", "quote": "定員は285人。", "value": "285人",
                  "target": "", "kind": "いまのこと", "prev": "", "reason": "", "url": U + "a5", "layer": "確定"}]
        d["records"]["kotogara"] += extra
        d["names"]["sources"].update({"doc:a/4": "再編整備計画", "doc:a/5": "再編整備計画"})
        # 定員は期の計画の見方だけの点。用地はどの見方にも無い（テーマ全体の点）
        plan = next(x for x in d["sheets"] if x["view"] == "plan:youho")
        plan["kotogara"] = [{"ref": "records/kotogara/定員/doc:a/5/定員は285人。"}]
        next(x for x in d["sheets"] if x["view"] == "hoiku")["kotogara"] += [
            {"ref": "records/kotogara/用地/doc:a/4/用地を決めた。"}, {"ref": "records/kotogara/定員/doc:a/5/定員は285人。"}]
        raw = json.dumps(d, ensure_ascii=False).encode("utf-8")
        honpen, kiroku = br.build(raw, P)
        heads = [h for h in honpen.split("\n") if h.startswith("### 認定こども園整備事業：主な事項：")]
        self.assertEqual([h.rsplit("：", 1)[1] for h in heads], ["開園時期", "用地"])
        self.assertIn("### 認定こども園整備事業：記録：事柄：定員", kiroku.replace("## ", "### "))
        honpen = br.build(raw, "plan:youho")[0]
        heads = [h for h in honpen.split("\n") if h.startswith("### 再編整備計画：主な事項：")]
        self.assertEqual([h.rsplit("：", 1)[1] for h in heads], ["定員", "用地"])
        self.assertNotIn("予定の変更：開園時期", honpen)      # 経過の予定の変更も同じ範囲
        honpen = br.build(raw, "hoiku")[0]
        heads = [h for h in honpen.split("\n") if h.startswith("### 幼児教育・保育施設の再編：主な事項：")]
        self.assertEqual(sorted(h.rsplit("：", 1)[1] for h in heads), ["定員", "用地", "開園時期"])

    def test_docx(self):
        honpen = built()[0]
        buf = io.BytesIO(docx_bytes(honpen))
        with zipfile.ZipFile(buf) as z:
            self.assertEqual(sorted(z.namelist()), sorted(["[Content_Types].xml", "_rels/.rels",
                                                            "word/_rels/document.xml.rels", "word/styles.xml",
                                                            "word/document.xml"]))
            for i in z.infolist():
                self.assertEqual(i.date_time, br.ZIP_TIME)
                self.assertEqual(i.compress_type, zipfile.ZIP_STORED)   # 圧縮しない（zlib の実装で変わらない）
            for n in z.namelist():
                ElementTree.fromstring(z.read(n))      # XML として読める
            doc = z.read("word/document.xml").decode("utf-8")
        ns = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
        root = ElementTree.fromstring(doc)
        paras = root.iter(ns + "p")
        texts = []
        for p in paras:
            st = p.find(f"{ns}pPr/{ns}pStyle")
            texts.append((st.get(ns + "val") if st is not None else "", "".join(t.text or "" for t in p.iter(ns + "t"))))
        self.assertEqual(texts[0], ("Heading1", "認定こども園整備事業（本編）：この資料の読み方"))
        self.assertIn(("", "・［2025年3月］再編整備計画：資料の種類：町の資料。対象の時期：令和10年度。書き方：予定。"
                           "「令和10年度の開設を目指します。」（出典：https://example.jp/a.pdf#page=1）"), texts)
        self.assertEqual({s for s, _ in texts if s}, {"Heading1", "Heading2", "Heading3"})
        # Markdown の段落と同じ数
        md_paras = [x for x in honpen.split("\n") if x.strip()]
        self.assertEqual(len(texts), len(md_paras))

    def test_prompt(self):
        t = br.prompt_text()
        self.assertTrue(t.startswith("## 共通の指示"))
        self.assertNotIn("この指示は、持ち込み用の資料", t)

    def test_jd(self):
        self.assertEqual(br.jd("2025-03-10"), "2025年3月10日")
        self.assertEqual(br.jd("2025-03"), "2025年3月")
        self.assertEqual(br.fy_name(2019), "令和元年度")
        self.assertEqual(br.fiscal_year("2026-03-23"), 2025)


if __name__ == "__main__":
    unittest.main()
