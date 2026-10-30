"""tools/eval_words.py の検査（docs/eval-shisaku1.md §7）。"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import eval_words as ew  # noqa: E402

DOC = """# 試作1

### 7.1 場面と外せない語

| 場面 | 依頼文 | 外せない語 |
| --- | --- | --- |
| T1 | 答弁の案を書いてください。 | W1・W2 |
| T2 | 再質問。 | W1〜W3 |

| 番号 | 原文 | 語の骨 |
| --- | --- | --- |
| W1 | 令和１１年度での開設を目指します | 令和11年度 |
| W2 | 効率的な施設管理／連続性のある保育・幼児教育 | 効率的な施設管理／連続性のある保育 |
| W3 | 3,000,000千円 | 3,000,000 |

### 7.2 数え方
| W9 | 表の外 | 外 |
"""


class EvalWordsTest(unittest.TestCase):
    def test_expand(self):
        self.assertEqual(ew.expand("W1〜W3・W19"), ["W1", "W2", "W3", "W19"])
        with self.assertRaises(ew.WordsError):
            ew.expand("W1・X")

    def test_read_tables(self):
        scenes, words = ew.read_tables(DOC)
        self.assertEqual(scenes, {"T1": ["W1", "W2"], "T2": ["W1", "W2", "W3"]})
        self.assertEqual(words["W2"], (["効率的な施設管理", "連続性のある保育・幼児教育"], ["効率的な施設管理", "連続性のある保育"]))
        self.assertNotIn("W9", words)          # §7.1 の外の表は読まない
        with self.assertRaises(ew.WordsError):
            ew.read_tables(DOC.replace("| W3 | 3,000,000千円 | 3,000,000 |\n", ""))

    def test_real_doc(self):
        with open(ew.DOC, encoding="utf-8") as f:
            scenes, words = ew.read_tables(f.read())
        self.assertEqual(sorted(scenes), ["T1", "T2", "T3"])
        self.assertEqual(len(words), 19)
        self.assertEqual(words["W18"][0], ["3,000,000千円", "228,421千円"])

    def test_count(self):
        scenes, words = ew.read_tables(DOC)
        with tempfile.TemporaryDirectory() as tmp:
            for name, text in (("r-T1-haiku-1.md", "令和11年度での開設を 目指します。効率的な施設管理と連続性のある保育・幼児教育"),
                               ("r-T1-haiku-2.md", "令和11年度の開設。効率的な施設管理、連続性のある保育"),
                               ("r-T1-haiku-2-check.md", "数えない"), ("x-T1-haiku-1.md", "別の回")):
                with open(os.path.join(tmp, name), "w", encoding="utf-8") as f:
                    f.write(text)
            rows = ew.count("r", scenes, words, tmp)
        self.assertEqual(len(rows), 1)
        r = rows[0]
        self.assertEqual((r["scene"], r["model"], r["n"]), ("T1", "haiku", 2))
        self.assertEqual((r["mean"], r["min"], r["loose"]), (0.5, 0.0, 1.0))   # 1回めは2つとも原文のまま、2回めは語の骨だけ
        self.assertEqual(r["per"], {"W1": [1, 2], "W2": [1, 2]})
        text = ew.report("r", rows)
        self.assertIn("| T1 | haiku | 2 | 50% | 50% | 0% | 100% | W1:1/2 W2:1/2 |", text)


if __name__ == "__main__":
    unittest.main()
