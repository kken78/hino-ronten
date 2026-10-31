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
        self.assertIn("- 目的「持続可能な環境」→ 手段「こども園の新設」：［2025年3月］再編整備計画：関係：目的と手段。", text)
        self.assertIn("- 検討の段階：段階：懇話会。期間：2022年7月12日〜2024年1月12日。資料：懇話会の資料（第1回）。", text)
        self.assertIn("- 開園時期（3件）", text)
        self.assertIn("- 日野幼稚園（1件）", text)
        self.assertIn("一般質問 1問（うち質問・答弁を項目ごとに記録したもの 1問。", text)
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
        self.assertIn("いまの町の説明（原文。答弁や文書ではこの言い回しを使う）：［2026年7月］「広報ひの」：", text)
        # 広報ひののときは、広報ひの以外でいちばん新しい町の資料を並べる（会議録は使わない）
        self.assertIn("次の計画などの記載（広報ひの以外でいちばん新しいもの）を使う：［2025年3月］再編整備計画：", text)
        self.assertIn("当局の答弁のうち新しいもの（原文。これまでの答弁と食い違わないように確かめる）：\n- [yaritori:iq:1/2]", text)
        self.assertLess(text.index("いまの町の説明"), text.index("記載の推移（資料の日付順）："))
        text, _ = call(server(), "topic", {"name": "日野幼稚園"})
        self.assertIn("## 施設：日野幼稚園\n- [shisetsu:1] ［2025年3月］再編整備計画：面：状況。値：閉園。", text)
        text, _ = call(server(), "topic", {"name": "懇話会の設置目的"})
        self.assertIn("## 記載の見出し：懇話会の設置目的", text)
        self.assertIn("- [kisai:1] ［2022年7月］懇話会の資料：見出し：懇話会の設置目的。「在り方を検討する。」", text)
        text, _ = call(server(), "topic", {"name": "開園時期"})
        self.assertIn("令和7年6月定例会議の課長の発言：資料の種類：会議録。回：未記録。", text)

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
        self.assertIn("- [tsunagari:1] ［2025年3月］再編整備計画：関係：目的と手段。上位の記載：持続可能な環境。", text)
        self.assertIn("- [katei:1] 検討の段階：段階：懇話会。期間：2022年7月12日〜2024年1月12日。資料：懇話会の資料（第1回）。"
                      "「令和４年７月１２日」（出典：https://example.jp/c1）", text)
        self.assertIn("- 総合計画のめざす姿：「どの子も育つまち」", text)

    def test_theme_words(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = os.path.join(tmp, "themes.tsv")
            with open(p, "w", encoding="utf-8") as f:
                f.write("theme\tkind\tvalue\tsource\treviewer\tdate\tnote\n"
                        "hoiku\t語\tこども園\t\t\t\t\nhoiku\t事柄\t開園時期\t\t\t\t\nother\t語\t道路\t\t\t\t\n")
            self.assertEqual(mr.theme_words(p, "hoiku"), ["こども園"])


if __name__ == "__main__":
    unittest.main()
