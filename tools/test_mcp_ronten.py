"""tools/mcp_ronten.py の検査（LINK_SCHEMA §14）。"""
import io
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import mcp_ronten as mr  # noqa: E402
import test_build_rag as tb  # noqa: E402

P, U = tb.P, tb.U
SPEECHES = {
    "s1": {"sid": "s1", "role": "4番", "text": "新こども園の開園はいつか。"},
    "s2": {"sid": "s2", "role": "町長", "text": "新こども園は令和10年度の開設を目指します。"},
    "s3": {"sid": "s3", "role": "町長", "text": "給食費についてお答えします。"},
}
WORDS = ["こども園", "保育所"]


def data():
    d = json.loads(tb.data())
    # 広報ひのの記載（doc:koho-）がいちばん新しい事柄
    d["records"]["kotogara"][1]["source"] = "doc:koho-no792-04/1"
    d["names"]["sources"]["doc:koho-no792-04/1"] = "「広報ひの」"
    d["exchanges"][0]["turns"] = [{"sid": "sp:s1", "side": "問い", "url": U + "t1"},
                                  {"sid": "sp:s2", "side": "答え", "role": "町長", "url": U + "t2"},
                                  {"sid": "sp:s3", "side": "答え", "role": "町長", "url": U + "t3"}]
    return json.dumps(d, ensure_ascii=False).encode("utf-8")


def server(log=None):
    return mr.Server(data(), P, WORDS, SPEECHES, log)


def call(s, name, args=None):
    r = s.handle({"jsonrpc": "2.0", "id": 9, "method": "tools/call", "params": {"name": name, "arguments": args or {}}})
    return r["result"]["content"][0]["text"], r["result"]["isError"]


class ProtocolTest(unittest.TestCase):
    def test_initialize_and_list(self):
        s = server()
        r = s.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}})
        self.assertEqual(r["result"]["protocolVersion"], "2025-06-18")
        r = s.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        self.assertEqual([t["name"] for t in r["result"]["tools"]],
                         ["overview", "search", "fetch", "topic", "council", "speeches", "issues", "links"])
        self.assertIsNone(s.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}))
        self.assertEqual(s.handle({"jsonrpc": "2.0", "id": 3, "method": "x"})["error"]["code"], -32601)
        self.assertEqual(s.handle({"jsonrpc": "2.0", "id": 4, "method": "ping"})["result"], {})

    def test_serve_and_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = os.path.join(tmp, "log.jsonl")
            s = server(log)
            out = io.StringIO()
            s.serve(io.StringIO('{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"overview"}}\n\nx\n'), out)
            self.assertEqual(len(out.getvalue().strip().split("\n")), 1)
            with open(log, encoding="utf-8") as f:
                rec = json.loads(f.read())
            self.assertEqual((rec["tool"], rec["chars"] > 0), ("overview", True))
            self.assertNotIn("text", rec)

    def test_errors(self):
        s = server()
        for name, args in (("topic", {"name": "無い"}), ("search", {"query": " "}), ("speeches", {"exchange": "exchange:9"}),
                           ("issues", {"type": "無い"}), ("無い道具", {})):
            text, err = call(s, name, args)
            self.assertTrue(err, name)
            self.assertTrue(text.startswith("エラー："), name)
        text, err = call(s, "fetch", {"ids": ["kotogara:99", "issue:x"]})
        self.assertFalse(err)
        self.assertEqual(text, "[kotogara:99] 無い id\n[issue:x] 無い id")


class ToolTest(unittest.TestCase):
    def test_overview(self):
        text, _ = call(server(), "overview")
        self.assertIn("いちばん新しい記載の資料の日付：2026年7月", text)
        self.assertIn("当初予算額 228,421千円", text)
        self.assertIn("## 正式な名前（答弁や文書では略さずに使う）\n- 認定こども園整備事業\n- 再編整備計画", text)
        self.assertIn("- 目的「持続可能な環境」→ 手段「こども園の新設」：［2025年3月］再編整備計画：資料の種類：町の資料。関係：目的と手段。", text)
        self.assertIn("欄「資料の種類」は、会議録（会議録の発言）・広報ひの・町の資料の別。", text)
        self.assertIn("- 検討の段階：段階：懇話会。期間：2022年7月12日〜2024年1月12日。資料：懇話会の資料（第1回）。", text)
        self.assertIn("- 開園時期（3件）", text)
        self.assertIn("- 日野幼稚園（1件）", text)
        # 一般質問の数の言い分け（§14。2026-11-15 の MCP の確かめ）
        self.assertIn("## 議会（council で取る）：関連する一般質問 1問（系列の計画への言及を含む問い 0問と、題材に選んだ問い 16問を、"
                      "重ねずに数えた数。うち質問・答弁を項目ごとに記録した問い 1問。ほかの問いの答弁は speeches で会議録の本文を読む）、", text)
        self.assertNotIn("キーワードの一致", text)

    def test_search_and_fetch(self):
        s = server()
        text, _ = call(s, "search", {"query": "令和10年度 開園", "limit": 2})
        lines = text.split("\n")
        self.assertTrue(lines[0].startswith("9件（2件を表示。"))
        self.assertEqual(len(lines), 3)
        self.assertTrue(lines[2].startswith("[kotogara:1] 事柄：開園時期：［2025年3月］再編整備計画："))
        text, _ = call(s, "search", {"query": "開設", "kind": "会議録の本文"})
        self.assertIn("[speech:s2] 会議録の本文：", text)
        text, _ = call(s, "fetch", {"ids": ["yaritori:iq:1", "issue:1"]})
        self.assertIn("[yaritori:iq:1] 一般質問：2025年3月10日 令和7年3月定例会　質問者：日野花子 議員", text)
        self.assertIn("- [yaritori:iq:1/2] ［2025年3月10日］令和7年3月定例会の一般質問：発言：答弁。", text)
        self.assertIn("[issue:1] 照合結果（未確認）：予定の変更\n【未確認】開園時期は、令和10年度から令和11年度（比べた記載の出典：", text)

    def test_topic(self):
        text, _ = call(server(), "topic", {"name": "開園時期"})
        self.assertIn("町の資料の最新の記載（2026年7月、「広報ひの」）：令和11年4月", text)
        self.assertIn("いまの町の説明（原文。答弁や文書ではこの言い回しを使う）：［2026年7月］「広報ひの」：資料の種類：広報ひの。", text)
        # 広報ひののときは、広報ひの以外でいちばん新しい町の資料も並べる（会議録は使わない。DESIGN.md ADR-14・ADR-27）
        self.assertIn("上は広報ひのの記載。広報ひの以外でいちばん新しい町の資料の記載（時期や数字の書き方が違うときは、両方を資料の日付とともに示す）：［2025年3月］再編整備計画：", text)
        self.assertNotIn("出典には", text)
        self.assertIn("当局の答弁のうち新しいもの（原文。これまでの答弁と食い違わないように確かめる）：\n- [yaritori:iq:1/2]", text)
        self.assertLess(text.index("いまの町の説明"), text.index("記載の推移（資料の日付順）："))
        text, _ = call(server(), "topic", {"name": "日野幼稚園"})
        self.assertIn("## 施設：日野幼稚園\n- [shisetsu:1] ［2025年3月］再編整備計画：資料の種類：町の資料。面：状況。値：閉園。", text)
        text, _ = call(server(), "topic", {"name": "懇話会の設置目的"})
        self.assertIn("## 記載の見出し：懇話会の設置目的", text)
        self.assertIn("- [kisai:1] ［2022年7月］懇話会の資料：資料の種類：町の資料。見出し：懇話会の設置目的。「在り方を検討する。」", text)
        d = json.loads(data())
        d["records"]["kisai"][0].update(kind="評価", target="令和３年度")
        s2 = mr.Server(json.dumps(d, ensure_ascii=False).encode("utf-8"), P, WORDS, SPEECHES, None)
        text, _ = call(s2, "topic", {"name": "懇話会の設置目的"})
        self.assertIn("見出し：懇話会の設置目的。記載の種類：評価。対象の時期：令和３年度。「在り方を検討する。」", text)
        text, _ = call(s2, "overview")
        self.assertIn("欄「記載の種類」の事実・見通し・評価・要望は、資料の作成者（監査委員など）が記した内容の種類で", text)
        text, _ = call(server(), "topic", {"name": "開園時期"})
        self.assertIn("令和7年6月定例会議の課長の発言：資料の種類：会議録。回：未記録。", text)

    def test_frame(self):
        # 同じ項目の記載は fetch の suji: の id、枠組みと資料の種類は overview の節（LINK_SCHEMA §14。DESIGN.md ADR-37）
        s = mr.Server(tb.frame_data(), P, WORDS, SPEECHES, None)
        text, _ = call(s, "fetch", {"ids": ["suji:a/1"]})
        self.assertIn("[suji:a/1] 項目：資料の種類：定期監査の報告。置き場所：定期監査の報告\n［2025年3月］再編整備計画の項目1（suji:a/1）：", text)
        self.assertLess(text.index("「計画は３年毎に見直す。」"), text.index("「留意されたい。」（事項：開園時期）"))
        text, _ = call(s, "overview")
        self.assertIn("## 分野の枠組みと資料の種類", text)
        self.assertIn("- 要素1：開園の推計。該当する事項：開園時期。", text)
        self.assertIn("## 定期監査の報告（資料ごと。項目は fetch で suji: を取る）\n- 再編整備計画（2025年3月）：[suji:a/1]", text)
        self.assertNotIn("同じ項目の記載", text)
        # 事柄の topic の記載の推移に、about がその事柄の記載の行も入る
        text, _ = call(s, "topic", {"name": "開園時期"})
        part = text[text.index("記載の推移"):]
        self.assertIn("見出し：要望の文。記載の種類：要望。", part)
        self.assertNotIn("## 記載の見出し：開園時期", text)

    def test_frame_bill_records(self):
        # 議案を置く枠組みの要素の、提案の説明と質疑の記録の行（LINK_SCHEMA §14・§17。2026-11-15）：bill_lines と同じ文
        d = json.loads(tb.frame_data())
        b = tb.kessan_bill()
        d["bills"].append(b)
        d["waku"].append({"key": "waku:kessan-nintei", "name": "決算の認定までの流れ", "source": "地方自治法233条", "url": "", "note": "",
                          "layer": "確定",
                          "elements": [{"view": f"waku:kessan-nintei/{n}", "n": n, "name": nm, "note": "", "source": "", "shiryo": [],
                                        "points": [], "rec": {}, "gikai": 0} for n, nm in ((3, "提出"), (4, "審議"))],
                          "nendo": [{"fiscal_year": "2023", "elements": [{"n": 3, "docs": [], "gian": [b["key"]]},
                                                                          {"n": 4, "docs": [], "gian": [b["key"]]}]}]})
        s = mr.Server(json.dumps(d, ensure_ascii=False).encode("utf-8"), P, WORDS, SPEECHES, None)
        text, _ = call(s, "overview")
        self.assertIn("提案の説明の記載（代表監査委員。段落18）：【未確認】［要望］「連携をお願いします。」（事項：介護予防の取り組み）", text)
        self.assertIn("答え　厚生主監：「答1。」（事項：給付費の計画と実績）「答2。」（事項：第8期の計画の指標）「答3。」", text)
        self.assertLess(text.index("提案の説明：代表監査委員"), text.index("提案の説明の記載（代表監査委員。段落16）"))
        self.assertLess(text.index("質疑：4番 松田洋子 議員"), text.index("問い　4番 松田洋子 議員："))

    def test_hokoku(self):
        # 審査報告の記録（LINK_SCHEMA §14。2026-11-15 の5つめ）：hokoku:<報告のキー>、kind「委員長の報告」、当局の答弁には入れない
        s = mr.Server(tb.hokoku_data(), P, WORDS, SPEECHES, None)
        text, _ = call(s, "overview")
        self.assertIn("委員長の報告 1件、", text)
        text, _ = call(s, "fetch", {"ids": ["hokoku:rp:r1"]})
        self.assertTrue(text.startswith("[hokoku:rp:r1] 委員長の報告：2024年12月2日 令和6年12月定例会\n- [hokoku:rp:r1/1] "))
        self.assertIn("発言者：委員。", text)
        text, _ = call(s, "search", {"query": "問A", "kind": "委員長の報告"})
        self.assertIn("[hokoku:rp:r1/1] 委員長の報告：", text)
        text, _ = call(s, "council")
        self.assertIn("- [hokoku:rp:r1] 2024年12月2日 令和6年12月定例会（委員長の報告）（6行）", text)
        d = json.loads(tb.hokoku_data())
        d["records"]["kotogara"].append(dict(d["records"]["kotogara"][0], point="要介護認定"))
        text, _ = call(mr.Server(json.dumps(d, ensure_ascii=False).encode("utf-8"), P, WORDS, SPEECHES, None), "topic", {"name": "要介護認定"})
        self.assertIn("この事項についての質問・答弁（記録したもの）：", text)
        self.assertIn("[hokoku:rp:r1/3]", text)
        self.assertNotIn("当局の答弁のうち新しいもの", text)
        # 要素4 の委員長の報告の箇条は段落の番号 p ごと（資料と同じ文。2026-11-15 の7つめ）
        d = json.loads(tb.frame_data())
        b = tb.hokoku_bill()
        b["kessan"]["steps"][1]["rows"][1]["p"] = 9
        d["bills"].append(b)
        d["waku"].append({"key": "waku:kessan-nintei", "name": "決算の認定までの流れ", "source": "地方自治法233条", "url": "", "note": "",
                          "layer": "確定", "elements": [{"view": f"waku:kessan-nintei/{n}", "n": n, "name": nm, "note": "", "source": "",
                                                         "shiryo": [], "points": [], "rec": {}, "gikai": 0} for n, nm in ((3, "提出"), (4, "審議"))],
                          "nendo": [{"fiscal_year": "2023", "elements": [{"n": n, "docs": [], "gian": [b["key"]]} for n in (3, 4)]}]})
        text, _ = call(mr.Server(json.dumps(d, ensure_ascii=False).encode("utf-8"), P, WORDS, SPEECHES, None), "overview")
        self.assertIn("問い　委員：「問A。」（事項：要介護認定） 問い　委員：「問B。」（事項：要介護認定）", text)
        # 記録の無いテーマの overview は、いまのとおり
        text, _ = call(mr.Server(tb.data(), P, WORDS, SPEECHES, None), "overview")
        self.assertNotIn("委員長の報告", text)

    def test_topic_all_points(self):
        # テーマの定義の事項は、記録の有無にかかわらず topic で取れる（§14。2026-11-15 の MCP の確かめ）
        d = json.loads(tb.hokoku_data())
        d["names"]["bills"] = {"gi:0000008116/議第62号": "令和５年度日野町一般会計歳入歳出決算について"}
        d["chizu"] = tb.chizu()
        d["records"]["kisai"][0]["about"] = "提言"
        raw = json.dumps(d, ensure_ascii=False).encode("utf-8")
        pts = ["開園時期", "多様な生きがいと居場所づくり", "新こども園の開園時期", "提言", "要介護認定"]
        s = mr.Server(raw, P, WORDS, SPEECHES, None, pts)
        # 委員長の報告の行だけを持つ事項：その行を返す。議案の欄に議案の題
        text, err = call(s, "topic", {"name": "多様な生きがいと居場所づくり"})
        self.assertFalse(err)
        self.assertTrue(text.startswith("## 事項：多様な生きがいと居場所づくり\n事柄の記録と記載の行は無い。\nこの事項についての質問・答弁（記録したもの）：\n- [hokoku:rp:r1/6] "))
        self.assertIn("議案：令和6年9月定例会議の議第62号 令和５年度日野町一般会計歳入歳出決算について。", text)
        # 記録が1行も無い事項：「記録が無い」と地図での置き場所（枠組みと対応の案の印）
        text, err = call(s, "topic", {"name": "新こども園の開園時期"})
        self.assertFalse(err)
        self.assertEqual(text.split("\n")[0], "## 事項：新こども園の開園時期")
        self.assertIn("記録が無い（", text)
        self.assertIn("論点の地図での置き場所：再編整備計画：第１章 はじめに：１ 計画の期間（枠組み：流れ 要素1）（対応は案）", text)
        # 記載の行のある事項：記載の行と、質問・答弁（ここでは無い）
        text, _ = call(s, "topic", {"name": "提言"})
        self.assertTrue(text.startswith("## 記載の見出し：提言\n- [kisai:1] "))
        self.assertNotIn("記録が無い", text)
        # 体系の外の事項・地図の無いテーマ
        d2 = json.loads(raw)
        d2["records"]["kisai"][0]["about"] = ""
        s2 = mr.Server(json.dumps(d2, ensure_ascii=False).encode("utf-8"), P, WORDS, SPEECHES, None, pts)
        self.assertIn("論点の地図での置き場所：体系の外", call(s2, "topic", {"name": "提言"})[0])
        del d2["chizu"]
        d2["chizu"] = {}
        s3 = mr.Server(json.dumps(d2, ensure_ascii=False).encode("utf-8"), P, WORDS, SPEECHES, None, pts)
        self.assertNotIn("置き場所", call(s3, "topic", {"name": "提言"})[0])
        # テーマの定義に無い名前は、いまのとおりエラー
        self.assertTrue(call(s, "topic", {"name": "無い"})[1])
        # overview：事柄・記載の記録の無い事項の行（テーマの定義の順）
        text, _ = call(s, "overview")
        self.assertIn("- 事柄・記載の記録の無い事項（topic で取れる）：多様な生きがいと居場所づくり（質問・答弁 1件）、新こども園の開園時期（記録なし）", text)
        self.assertNotIn("事柄・記載の記録の無い事項", call(mr.Server(raw, P, WORDS, SPEECHES), "overview")[0])

    def test_topic_latest_all_and_stage_order(self):
        d = json.loads(data())
        d["records"]["kotogara"].append(dict(d["records"]["kotogara"][1], quote="もう1つの文。", target="令和12年4月"))
        d["records"]["katei"].append({"theme": "hoiku", "step": "2", "name": "検討会", "from": "", "to": "",
                                      "sources": "doc:c/1", "quote": "検討会を置く。", "url": U + "c1", "layer": "確定"})
        s = mr.Server(json.dumps(d, ensure_ascii=False).encode("utf-8"), P, WORDS, SPEECHES, None)
        text, _ = call(s, "topic", {"name": "開園時期"})
        # 最新の日付の行が複数：値は「／」、いまの町の説明は行ごと（§14 topic）
        self.assertIn("：令和11年4月／令和12年4月（出典：", text)
        self.assertEqual(text.count("いまの町の説明（原文。答弁や文書ではこの言い回しを使う）："), 2)
        # いまの段階は step の順の後ろから3つ：from の無い段階も出る。links の過程も step の順
        text, _ = call(s, "overview")
        self.assertLess(text.index("段階：懇話会。"), text.index("段階：検討会。"))
        text, _ = call(s, "links")
        self.assertLess(text.index("[katei:1]"), text.index("[katei:2]"))

    def test_council_and_speeches(self):
        s = server()
        text, _ = call(s, "council", {"from_date": "2025-01-01"})
        self.assertIn("- [exchange:1] ［2025年3月10日］一般質問：令和7年3月定例会　質問者：日野花子 議員", text)
        self.assertIn("- [bill:1] ［2026年3月23日］令和8年3月定例会議の議案第1号 予算。議決結果：原案可決。", text)
        self.assertIn("- [yaritori:iq:1] 2025年3月10日 令和7年3月定例会　質問者：日野花子 議員（2行）", text)
        text, _ = call(s, "council", {"to_date": "2024-12-31"})
        self.assertNotIn("exchange:1", text)
        text, _ = call(s, "speeches", {"exchange": "exchange:1"})
        self.assertTrue(text.startswith(mr.SPEECH_NOTE))
        self.assertIn("[speech:s1] ［2025年3月10日］令和7年3月定例会の一般質問（質問者：日野花子 議員）：質問。発言者：日野花子 議員。"
                      "会議録の本文：「新こども園の開園はいつか。」（出典：https://example.jp/t1）", text)
        self.assertIn("答弁。発言者：町長。会議録の本文：「新こども園は令和10年度の開設を目指します。」", text)
        self.assertNotIn("給食費", text)     # テーマの語の無い発言は返さない

    def test_issues_and_links(self):
        s = server()
        text, _ = call(s, "issues")
        # 照合結果の文に、比べた記載の出典を資料の日付の順に付ける（日付の無いものは最後）。問われていない点には付けない
        self.assertIn("[issue:1] 予定の変更：【未確認】開園時期は、令和10年度から令和11年度（比べた記載の出典："
                      "https://example.jp/a.pdf#page=1、https://example.jp/q2、https://example.jp/z）", text)
        self.assertTrue(text.endswith("[issue:2] 問われていない点：【未確認】「懇話会の設置目的」は、取り上げられていない"), text)
        self.assertNotIn("- 比べた記載", text)
        text, _ = call(s, "issues", {"type": "問われていない点"})
        # 記録の行に当たる比べた記載は、記録の節と件数にする（fixture では 広報ひのに変えた1行は記録の行に当たらない）
        self.assertIn("比べた記載のある記録：構造にしていない記載：懇話会の設置目的（1件）、事柄：開園時期（1件）、つながり（1件）", text)
        self.assertIn("- 比べた記載：w（出典：https://example.jp/w）", text)
        text, _ = call(s, "links")
        self.assertIn("- [tsunagari:1] ［2025年3月］再編整備計画：資料の種類：町の資料。関係：目的と手段。上位の記載：持続可能な環境。", text)
        self.assertIn("- [katei:1] 検討の段階：段階：懇話会。期間：2022年7月12日〜2024年1月12日。資料：懇話会の資料（第1回）。資料の種類：町の資料。"
                      "「令和４年７月１２日」（出典：https://example.jp/c1）", text)
        self.assertIn("- 総合計画のめざす姿：「どの子も育つまち」", text)
        self.assertIn("- 再編整備計画 18〜19ページに掲げる課題：「① 出生数の減少」（出典：https://example.jp/youho.pdf#page=20）", text)

    def test_overview_views(self):
        # 見方が事業でないときは「見方の要点」（§14）。止まらず、名前が出る
        for view, want in (("plan:youho", "計画：再編整備計画。計画期間：2024〜2029年度"), ("fa:f1", "施設：日野幼稚園。地区：日野"),
                           ("hoiku", "中心の見方：認定こども園整備事業（node:jisshi/e008）")):
            with self.subTest(view=view):
                text, err = call(mr.Server(data(), view, WORDS, SPEECHES), "overview")
                self.assertFalse(err)
                self.assertIn("## 見方の要点\n", text)
                self.assertNotIn("## 事業の要点", text)
                self.assertIn(want, text)
                self.assertNotIn("当初予算額", text)
        text, _ = call(server(), "overview")
        self.assertIn("## 事業の要点\n", text)

    def test_overview_area_views(self):
        # 地区・組織の見方の overview（§14。ADR-32）：地区は名前とその地区の施設の名前、組織は名前とほかの表記
        raw = tb.area_data()
        for view, want in (("dist:hino", "地区：日野。施設：日野幼稚園、保育所あおぞら園"),
                           ("org:kucho-kai", "組織：日野町区長会。ほかの表記：区長会、区長連絡会")):
            with self.subTest(view=view):
                text, err = call(mr.Server(raw, view, WORDS, SPEECHES), "overview")
                self.assertFalse(err)
                self.assertIn("## 見方の要点\n" + want + "\n", text)
                self.assertNotIn("## 事業の要点", text)
                self.assertNotIn("当初予算額", text)
                self.assertNotIn("必佐幼稚園", text)
                self.assertTrue(text.startswith(f"{want.split('：')[1].split('。')[0]}（テーマ「幼児教育・保育施設の再編」）の資料。"))

    def test_overview_other_points(self):
        # ほかの見方だけに属する事項の行（§14）。見本の「開園時期」は事業の見方の点で、ほかの見方だけの点は無い
        text, _ = call(server(), "overview")
        self.assertNotIn("ほかの見方の事項", text)
        d = json.loads(data())
        d["records"]["kotogara"] += [
            {"point": p, "source": s, "source_date": "2025-05", "quote": q, "value": "", "target": "", "kind": "いまのこと",
             "prev": "", "reason": "", "url": U + s, "layer": "確定"}
            for p, s, q in (("定員", "doc:a/5", "定員は285人。"), ("定員", "doc:a/6", "定員を見直す。"), ("園庭", "doc:a/7", "園庭を設ける。"))]
        plan = next(x for x in d["sheets"] if x["view"] == "plan:youho")
        plan["kotogara"] = [{"ref": "records/kotogara/定員/doc:a/5/定員は285人。"},
                            {"ref": "records/kotogara/定員/doc:a/6/定員を見直す。"}]
        fa = next(x for x in d["sheets"] if x["view"] == "fa:f1")
        fa["kotogara"] = [{"ref": "records/kotogara/園庭/doc:a/7/園庭を設ける。"}]
        raw = json.dumps(d, ensure_ascii=False).encode("utf-8")
        text, _ = call(mr.Server(raw, P, WORDS, SPEECHES), "overview")
        self.assertIn("- 開園時期（3件）\n- ほかの見方の事項（topic で取れる）：園庭（1件）、定員（2件）\n", text)
        # 期の計画の見方では、定員はその見方の点で、開園時期と園庭がほかの見方の点
        text, _ = call(mr.Server(raw, "plan:youho", WORDS, SPEECHES), "overview")
        self.assertIn("- ほかの見方の事項（topic で取れる）：園庭（1件）、開園時期（3件）\n", text)
        self.assertIn("- 定員（2件）\n", text)

    def test_tools_list_description(self):
        r = server().handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        d = r["result"]["tools"][0]["description"]
        self.assertIn("見方の要点（事業のときは事業名・概算事業費・当初予算額・総合計画の位置）", d)

    def test_theme_words(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = os.path.join(tmp, "themes.tsv")
            with open(p, "w", encoding="utf-8") as f:
                f.write("theme\tkind\tvalue\tsource\treviewer\tdate\tnote\n"
                        "hoiku\t語\tこども園\t\t\t\t\nhoiku\t事柄\t開園時期\t\t\t\t\nother\t語\t道路\t\t\t\t\n")
            self.assertEqual(mr.theme_words(p, "hoiku"), ["こども園"])
            self.assertEqual(mr.theme_points(p, "hoiku"), ["開園時期"])



class ChizuOverviewTest(unittest.TestCase):
    """overview の頭の論点の地図（LINK_SCHEMA §14。DESIGN.md ADR-38）。"""

    def test_overview(self):
        d = json.loads(data())
        d["chizu"] = tb.chizu()
        s = mr.Server(json.dumps(d, ensure_ascii=False).encode("utf-8"), P, WORDS, SPEECHES)
        t, err = call(s, "overview")
        self.assertFalse(err)
        self.assertIn("\n## 論点の地図\n分類の体系：再編整備計画", t)
        self.assertLess(t.index("## 論点の地図"), t.index("## 事業の要点"))
        self.assertIn("- 体系の外：事項 1\n  - 事項「提言」：記録なし", t)
        t0, _ = call(server(), "overview")
        self.assertNotIn("論点の地図", t0)
        self.assertTrue(t.endswith(t0[t0.index("## 事業の要点"):]))

if __name__ == "__main__":
    unittest.main()
