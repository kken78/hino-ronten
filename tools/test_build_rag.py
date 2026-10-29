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


def data(**kw):
    d = {
        "theme": "hoiku", "name": "幼児教育・保育施設の再編",
        "lock": {"hino-council-search": "1af9baa0", "shiga-hino-plans": "807b1680"},
        "programs": [{"key": P, "name": "認定こども園整備事業", "desc": "新こども園を整備する。", "field_no": "分野①",
                      "field_name": "子ども・子育て", "years": ["R8", "R9"], "source": U + "jisshi.pdf",
                      "cost": {"label": "概算事業費", "amount": 3000000, "unit": "千円"}, "layer": "確定"}],
        "budget": [{"key": "fh:fuhyo-r8/b010", "program": P, "name": "認定こども園整備事業", "kubun": ["新規"],
                    "amount": 228421, "unit": "千円", "dept": ["子ども支援課"], "url": U + "fuhyo.pdf#page=1"}],
        "policies": [{"kind": "基本施策", "no": "(3)", "name": "幼児教育・保育の充実", "source": U + "sogo.pdf"}],
        "plans": [{"key": "plan:youho", "name": "再編整備計画", "start_fy": "2024", "end_fy": "2029", "posted": "",
                   "url": U + "youho"}],
        "docs": [{"category": "koho", "title": "広報ひの", "date": "2026-07", "fiscal_year": "2026", "url": U + "koho.pdf"}],
        "sheets": [{"program": P, "vision": [{"text": "めざす姿:どの子も育つまち", "source": U + "sogo.pdf"}],
                    "kadai": [{"ref": "plan:youho/hoshin/challenges/1/1", "text": "① 出生数の減少",
                               "source": "youho/honpen p.18-19", "url": U + "youho.pdf#page=20"}]}],
        "exchanges": [{"meeting_id": "m", "meeting": "令和7年3月定例会", "date": "2025-03-10", "n": 1, "question": "iq:1",
                       "member": {"key": "k", "name": "日野花子", "seat": 1}, "titles": [{"title": "新こども園について"}],
                       "turns": [{"url": U + "t1"}]}],
        "bills": [{"key": "b", "meeting": "令和8年3月定例会議", "date": "2026-03-23", "no": "議案第1号", "title": "予算",
                   "result": "原案可決", "method": "起立", "debates": [], "url": U + "bill"}],
        "issues": [{"type": "予定の変更", "statement": "開園時期は、令和10年度から令和11年度", "layer": "論点の候補",
                    "refs": [{"ref": "records/kotogara/hoiku/開園時期/doc:a/1/令和10年度の開設を目指します。", "text": "x",
                              "url": U + "a.pdf#page=1", "layer": "確定"},
                             {"ref": "records/yaritori/iq:1/2", "text": "y", "url": U + "q2", "layer": "確定"},
                             {"ref": "どこにも無い", "text": "z", "url": U + "z", "layer": "論点の候補"}]},
                   {"type": "問われていない点", "statement": "「懇話会の設置目的」は、取り上げられていない", "layer": "論点の候補",
                    "refs": [{"ref": "records/kisai/hoiku/懇話会の設置目的/doc:c/2", "text": "在り方を検討する。",
                              "url": U + "c2", "layer": "確定"},
                             {"ref": "records/kotogara/hoiku/開園時期/doc:a/1/令和10年度の開設を目指します。", "text": "x",
                              "url": U + "a.pdf#page=1", "layer": "確定"},
                             {"ref": "records/kotogara/hoiku/開園時期/doc:b/1/開園時期を見直しました。", "text": "x2",
                              "url": U + "b.pdf#page=1", "layer": "確定"},
                             {"ref": "records/tsunagari/hoiku/目的と手段/持続可能な環境/こども園の新設/doc:a/3", "text": "t",
                              "url": U + "a3", "layer": "確定"},
                             {"ref": "どこにも無い2", "text": "w", "url": U + "w", "layer": "確定"}]}],
        "records": {
            "kotogara": [
                {"theme": "hoiku", "point": "開園時期", "program": P, "source": "doc:a/1", "source_date": "2025-03",
                 "quote": "令和10年度の開設を目指します。", "value": "", "target": "令和10年度", "kind": "予定",
                 "prev": "", "reason": "", "url": U + "a.pdf#page=1", "layer": "確定"},
                {"theme": "hoiku", "point": "開園時期", "program": P, "source": "doc:b/1", "source_date": "2026-07",
                 "quote": "開園時期を見直しました。", "value": "", "target": "令和11年4月", "kind": "変更",
                 "prev": "令和10年4月", "reason": "安全性を優先する", "url": U + "b.pdf#page=1", "layer": "確定"},
                {"theme": "hoiku", "point": "開園時期", "program": P, "source": "sp:1", "source_date": "2025-06-13",
                 "quote": "令和10年度の開園をめどに", "value": "", "target": "令和10年度", "kind": "予定",
                 "prev": "", "reason": "", "url": U + "sp1", "layer": "論点の候補"}],
            "shisetsu": [{"facility": "f1", "aspect": "状態", "value": "閉園", "source": "doc:a/2", "source_date": "2025-03",
                          "quote": "閉園します。", "target": "令和10年度", "kind": "予定", "prev": "", "url": U + "a2",
                          "layer": "確定"}],
            "yaritori": [q("iq:1", "2025-03-10", "令和7年3月定例会", "日野花子",
                           [qrow(1, "問い", "開園はいつか"), qrow(2, "答え", "今後検討します")])],
            "shitsugi": [],
            "tsunagari": [{"theme": "hoiku", "link": "目的と手段", "upper": "持続可能な環境", "lower": "こども園の新設",
                           "source": "doc:a/3", "source_date": "2025-03", "quote": "新設を進めます。", "url": U + "a3",
                           "layer": "確定"}],
            "katei": [{"theme": "hoiku", "step": "1", "name": "懇話会", "from": "2022-07-12", "to": "2024-01-12",
                       "sources": "doc:c/1", "quote": "令和４年７月１２日", "url": U + "c1", "layer": "確定",
                       "date": "2026-10-28"}],
            "kisai": [{"theme": "hoiku", "title": "懇話会の設置目的", "about": "懇話会の設置目的", "source": "doc:c/2",
                       "source_date": "2022-07", "quote": "在り方を検討する。", "url": U + "c2", "layer": "確定",
                       "date": "2026-10-28"}],
        },
        "names": {"sources": {"doc:a/1": "再編整備計画", "doc:b/1": "「広報ひの」", "sp:1": "令和7年6月定例会議の課長の発言",
                              "doc:a/2": "再編整備計画", "doc:a/3": "再編整備計画", "doc:c/2": "懇話会の資料"},
                  "facilities": {"f1": {"name": "日野幼稚園", "district": "日野"}}},
        "theme_questions": 16,
        "hits": {"council": [{"excerpt": "キーワードの一致"}], "docs": []},
    }
    d.update(kw)
    return json.dumps(d, ensure_ascii=False).encode("utf-8")


def docx_bytes(md):
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "a.docx")
        br.write_docx(path, md)
        with open(path, "rb") as f:
            return f.read()


def built(**kw):
    return br.build(data(**kw), P)


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
                if "「" in line and not line.startswith(("#", "- 記載は", "- 日野町の公開資料", "- 「【未確認】」の段落",
                                                                 "【未確認】", "比べた記載：記録編の")):
                    self.assertIn("出典：", line, line)

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
        self.assertIn("一般質問：令和7年3月定例会　質問者：日野花子 議員　議会だよりの見出し「新こども園について」", honpen)

    def test_issues(self):
        honpen = built()[0]
        self.assertIn("## 認定こども園整備事業：照合結果（未確認）", honpen)
        self.assertIn("【未確認】開園時期は、令和10年度から令和11年度", honpen)
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
        d = json.loads(data())
        del d["names"]
        with self.assertRaises(br.RagError):
            br.build(json.dumps(d).encode("utf-8"), P)

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
