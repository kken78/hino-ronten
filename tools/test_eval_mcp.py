"""tools/eval_mcp.py の検査（docs/eval-shisaku1.md §8.2）。"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import eval_mcp as em  # noqa: E402
import test_mcp_ronten as tm  # noqa: E402

MD = """# opus-A（会話A）

## 依頼1

依頼文：答弁の案を書いてください。

### 答え

答弁案の本文。

## 依頼2

依頼文：点検してください。

### 答え

点検の本文。
"""


class EvalMcpTest(unittest.TestCase):
    def setUp(self):
        self.corpus = em.Corpus(em.collect(tm.server()))

    def test_collect(self):
        self.assertIn("https://example.jp/a.pdf#page=1", self.corpus.urls)
        self.assertIn(em.ws("令和10年度の開設を目指します。"), self.corpus.ws)
        self.assertIn(em.ws("新こども園の開園はいつか。"), self.corpus.ws)      # speeches の本文も入る

    def test_answers(self):
        self.assertEqual(em.answers(MD), [("依頼1", "\n答弁案の本文。\n"), ("依頼2", "\n点検の本文。\n")])

    def test_check(self):
        text = ("- 根1 「令和10年度の開設を目指します。」（出典：https://example.jp/a.pdf#page=1）\n"
                "- 根2 「令和１０年度の開設を目指します。」［出典：https://example.jp/a.pdf#page=1］**\n"
                "- 「自分で作った問い」（出典：https://example.jp/nai）\n"
                "- 「令和10年度の…目指します。」\n")
        r = em.check(text, self.corpus)
        self.assertEqual(r["urls"], 3)
        self.assertEqual(r["url_kinds"], 2)
        self.assertEqual(r["bad_urls"], ["https://example.jp/nai"])   # 末尾の ** や ］ は url に入れない
        self.assertEqual(r["quotes"], 4)
        self.assertEqual(r["width"], ["令和１０年度の開設を目指します。"])     # NFKC でだけ合う
        self.assertEqual(r["not_in"], ["自分で作った問い"])                # 略記の「…」は前後で比べる

    def test_quotes_per_line(self):
        self.assertEqual(em.quotes("「外「内」側」と「次」"), ["外「内」側", "次"])
        self.assertEqual(em.quotes("閉じない「かっこ"), [])

    def test_report(self):
        r = em.check("「自分で作った問い」", self.corpus)
        s = em.report("t", [("opus-A", "依頼1", r)])
        self.assertIn("| opus-A 依頼1 | 10 | 0（0） | 0 | 1 | 1 | 0 |", s)
        self.assertIn("- 道具の返した文に無い引用：「自分で作った問い」", s)


if __name__ == "__main__":
    unittest.main()
