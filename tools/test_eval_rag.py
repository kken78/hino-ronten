"""tools/eval_rag.py の検査（docs/eval-shisaku1.md §6）。"""
import contextlib
import io
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import eval_rag as ev  # noqa: E402

HONPEN = """# 事業（本編）：この資料の読み方

- 記載は「［資料の日付］資料の名前：「引用」（出典：url）」の形

# 事業（本編）：2 概要

## 事業：主な事項

- ［2025年3月］計画：「令和10年度での開設を目指します。」（出典：https://example.jp/a.pdf#page=1）
- 【未確認】［2025年6月13日］課長の発言：「令和10年度の開園をめどに」（出典：https://example.jp/sp1）

# 事業（本編）：3 論点整理

## 事業：照合結果（未確認）

### 事業：照合結果（未確認）：予定の変更

【未確認】開園時期は、令和10年度から令和11年度

- 比べた記載：［2026年7月］広報：「開園時期を見直しました。」（出典：https://example.jp/b.pdf#page=1）

## 事業：一般質問と議案

- ［2026年7月］広報：「開園時期：令和11年４月（予定）」（出典：https://example.jp/b.pdf#page=1）
- ［2026年8月］広報：「別の記載」（出典：https://example.jp/c.pdf）

### 事業：照合結果（未確認）：問われていない点

"""
KIROKU = """# 事業（記録編）：事柄

- ［2022年7月］懇話会の資料：「在り方を 検討する。」（出典：https://example.jp/k1）
"""


def material():
    tmp = tempfile.mkdtemp()
    paths = []
    for name, text in (("h.md", HONPEN), ("k.md", KIROKU)):
        p = os.path.join(tmp, name)
        with open(p, "w", encoding="utf-8") as f:
            f.write(text)
        paths.append(p)
    return ev.Material([(paths[0], "本編"), (paths[1], "記録編")])


class SplitTest(unittest.TestCase):
    def test_sentences(self):
        out = ev.sentences("# 見出し\n\n---\n| --- | --- |\n- 一つめ。二つめは「中。の文」です。［出典：https://example.jp/a］\n1. 三つめ")
        self.assertEqual(out, [(5, "一つめ。"), (5, "二つめは「中。の文」です。［出典：https://example.jp/a］"), (6, "三つめ")])

    def test_table_row(self):
        self.assertEqual(ev.sentences("| 2025年 | 開園。［出典：https://example.jp/a］ |"),
                         [(1, "2025年 開園。［出典：https://example.jp/a］")])

    def test_quotes(self):
        self.assertEqual(ev.quotes("A「外「内」外」B「次」"), ["外「内」外", "次"])

    def test_cites(self):
        self.assertEqual(ev.cites("文［出典：https://example.jp/a、https://example.jp/b］と[出典: https://example.jp/c]"
                                  "と（出典：https://example.jp/d#page=2）"),
                         ["https://example.jp/a", "https://example.jp/b", "https://example.jp/c", "https://example.jp/d#page=2"])


class MaterialTest(unittest.TestCase):
    def test_urls(self):
        m = material()
        self.assertTrue(m.urls["https://example.jp/a.pdf#page=1"]["confirmed"])
        self.assertFalse(m.urls["https://example.jp/sp1"]["confirmed"])          # 【未確認】の段落だけ
        self.assertTrue(m.urls["https://example.jp/b.pdf#page=1"]["confirmed"])   # 照合結果の外にもある
        self.assertEqual(m.urls["https://example.jp/b.pdf#page=1"]["chapters"], ["本編：3 論点整理"])
        self.assertEqual(m.urls["https://example.jp/k1"]["chapters"], ["記録編：事柄"])

    def test_issue_section_only(self):
        m = material()
        t = HONPEN.replace("（出典：https://example.jp/c.pdf）", "（出典：https://example.jp/b2）")
        t = t.replace("比べた記載：［2026年7月］広報：「開園時期を見直しました。」（出典：https://example.jp/b.pdf#page=1）",
                      "比べた記載：「x」（出典：https://example.jp/only）")
        tmp = tempfile.mkdtemp()
        p = os.path.join(tmp, "h.md")
        with open(p, "w", encoding="utf-8") as f:
            f.write(t)
        m = ev.Material([(p, "本編")])
        self.assertFalse(m.urls["https://example.jp/only"]["confirmed"])

    def test_has_quote(self):
        m = material()
        self.assertTrue(m.has_quote("在り方を検討する。"))            # 空白は除く
        self.assertTrue(m.has_quote("開園時期：令和11年4月（予定）"))   # 全角・半角
        self.assertTrue(m.has_quote("令和10年度での…目指します"))      # 略した前と後
        self.assertFalse(m.has_quote("令和9年度での開設"))


class CheckTest(unittest.TestCase):
    def test_check(self):
        out = "\n".join([
            "# 骨子",
            "- 開園は「令和10年度での開設を目指します。」とされた［出典：https://example.jp/a.pdf#page=1］。",
            "- 課長は「令和10年度の開園をめどに」と答えた。［出典：https://example.jp/sp1］",
            "- 未確認の記録では、課長は「令和10年度の開園をめどに」と答えた［出典：https://example.jp/sp1］。",
            "- 提案：開園時期の見直しの理由を問う。",
            "- 計画は「令和9年度に開設」とする［出典：https://example.jp/zzz］。",
        ])
        r = ev.check(out, material())
        self.assertEqual(r["sentences"], 5)
        self.assertEqual(r["cited"], 4)
        self.assertEqual(r["no_cite"], [(5, "提案：開園時期の見直しの理由を問う。")])
        self.assertEqual(r["unknown_url"], [(6, "https://example.jp/zzz")])
        self.assertEqual(r["no_quote"], [(6, "令和9年度に開設")])
        self.assertEqual([n for n, _ in r["unconfirmed"]], [3])
        self.assertEqual(r["quotes"], 4)
        self.assertEqual(r["chapters"], {"本編：2 概要": 3})
        text = ev.report("x", r)
        self.assertIn("## K1 出典の無い文（1）", text)
        self.assertIn("- 6行目：令和9年度に開設", text)

    def test_main(self):
        tmp = tempfile.mkdtemp()
        paths = []
        for name, text in (("h.md", HONPEN), ("k.md", KIROKU), ("20261029-rag-S1-haiku.md", "文。")):
            p = os.path.join(tmp, name)
            with open(p, "w", encoding="utf-8") as f:
                f.write(text)
            paths.append(p)
        old = ev.OUT_DIR
        ev.OUT_DIR = tmp
        try:
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(ev.main(["x", paths[2], paths[0], paths[1]]), 0)
                self.assertTrue(os.path.exists(os.path.join(tmp, "20261029-rag-S1-haiku-check.md")))
                self.assertEqual(ev.main(["x", os.path.join(tmp, "無い.md"), paths[0], paths[1]]), 1)
        finally:
            ev.OUT_DIR = old


if __name__ == "__main__":
    unittest.main()
