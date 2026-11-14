"""tools/draft_records.py の検査（LINK_SCHEMA.md §15.1、DESIGN.md ADR-31 の3）。

実行: python3 -B tools/test_draft_records.py -v
見本の入力と台帳は tools/test_records.py の見本を使う。実データは使わない。
"""
import contextlib
import io
import os
import sys
import tempfile
import unittest
from types import SimpleNamespace

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import draft_records as dr  # noqa: E402
import records as rc  # noqa: E402
import test_records as tr  # noqa: E402

sid = tr.sid
COLS = dr.draft_columns("kotogara")


def tsv(cols, rows):
    return ("\t".join(cols) + "\n" + "".join("\t".join(r) + "\n" for r in rows)).encode("utf-8")


def k_row(point, n, quote, note="", **kw):
    r = {c: "" for c in COLS}
    r.update(point=point, source=f"sp:{sid(n)}", source_date="2025-01-01", quote=quote, kind="いまのこと", note=note)
    r.update(kw)
    return [r[c] for c in COLS]


# 見本の下書き：1 は通る行、2 は本体と同じキー、3 は引用が本文に無い（迷いあり）
DRAFT_ROWS = [
    k_row("新こども園の用地", 12, "用地は選定中です。", "答弁から引いた", value=""),
    k_row("新こども園の定員", 4, "定員は285人です。"),
    k_row("新こども園の用地", 15, "土地は売ります。"),
]


def drafts(mayoi=("", "", "迷い"), rows=DRAFT_ROWS, ledger="kotogara"):
    cols = dr.draft_columns(ledger)
    data = tsv(cols + [dr.MAYOI], [r + [m] for r, m in zip(rows, mayoi)]) if mayoi is not None else tsv(cols, rows)
    rows, my = dr.parse_draft(data, ledger)
    return dr.prepare(rows, my, ledger, "2026-11-05", "Opus 5.5", "")


def args(ledger="kotogara"):
    return SimpleNamespace(ledger=ledger, sheet="K9", date="2026-11-05", model="Opus 5.5")


def run_to(tmp, ds, my, ledger="kotogara", led=None):
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        code = dr.run(args(ledger), ds, my, led or tr.ledgers(), tr.theme_rows(), tr.shisetsu_ref(), tr.inputs(), tmp)
    return code


def read(tmp, name):
    with open(os.path.join(tmp, name), encoding="utf-8") as f:
        return f.read()


class NoteTest(unittest.TestCase):
    def test_draft_note(self):
        self.assertEqual(dr.draft_note("2026-11-05", "Opus 5.5", "", "", False), "下書き：2026-11-05・Opus 5.5（プロンプトの版なし）")
        self.assertEqual(dr.draft_note("2026-11-05", "Opus 5.5", "v3", "答弁から", True),
                         "下書き：2026-11-05・Opus 5.5（v3）。答弁から（迷い）")
        self.assertEqual(dr.draft_note("2026-11-05", "Opus 5.5", "v3", "", True), "下書き：2026-11-05・Opus 5.5（v3）（迷い）")

    def test_prepare(self):
        ds, my = drafts()
        # 行のキーの順（point → source → quote）に並び、迷いも同じ順に並ぶ
        self.assertEqual([(r["point"], r["source"]) for r in ds],
                         [("新こども園の定員", f"sp:{sid(4)}"), ("新こども園の用地", f"sp:{sid(12)}"),
                          ("新こども園の用地", f"sp:{sid(15)}")])
        self.assertEqual(my, [False, False, True])
        self.assertEqual({(r["status"], r["reviewer"], r["date"]) for r in ds}, {("candidate", "", "")})
        self.assertEqual([r["note"] for r in ds],
                         ["下書き：2026-11-05・Opus 5.5（プロンプトの版なし）",
                          "下書き：2026-11-05・Opus 5.5（プロンプトの版なし）。答弁から引いた",
                          "下書き：2026-11-05・Opus 5.5（プロンプトの版なし）（迷い）"])
        self.assertEqual(list(ds[0]), rc.COLUMNS["kotogara"])

    def test_without_mayoi_column(self):
        ds, my = drafts(mayoi=None)
        self.assertEqual(my, [False, False, False])
        self.assertFalse(any("迷い" in r["note"] for r in ds))

    def test_bad_draft(self):
        cols = dr.draft_columns("kotogara")
        for data, msg in ((tsv(cols + [dr.MAYOI], [DRAFT_ROWS[0] + ["たぶん"]]), "mayoi が"),
                          (tsv(cols + ["status"], [DRAFT_ROWS[0] + ["candidate"]]), "ヘッダ"),
                          (tsv(cols, []), "行が無い")):
            with self.subTest(msg=msg), self.assertRaises(dr.DraftError) as cm:
                dr.parse_draft(data, "kotogara")
            self.assertIn(msg, str(cm.exception))


class CheckTest(unittest.TestCase):
    def test_duplicate_key_in_body(self):
        ds, my = drafts()
        rep, _ = dr.check("kotogara", ds, tr.ledgers(), tr.theme_rows(), tr.shisetsu_ref(), tr.inputs())
        dup = [e for e in rep.errors if "本体に同じキーの行がある" in e]
        self.assertEqual(len(dup), 1)
        self.assertIn(f"新こども園の定員/sp:{sid(4)}/定員は285人です。", dup[0])
        # 写しでは置き換えるので、キーの重なりの誤りは出ない
        self.assertFalse([e for e in rep.errors if "行のキーが重なっている" in e])
        # 引用が本文に無い candidate は一覧に出るだけ
        self.assertEqual([m["key"] for m in rep.quote_mismatch], [f"新こども園の用地/sp:{sid(15)}/土地は売ります。"])
        self.assertEqual(rep.counts["kotogara"], 3)

    def test_no_errors(self):
        ds, my = drafts(mayoi=("",), rows=DRAFT_ROWS[:1])
        rep, _ = dr.check("kotogara", ds, tr.ledgers(), tr.theme_rows(), tr.shisetsu_ref(), tr.inputs())
        self.assertEqual(rep.errors, [])

    def test_area_refs(self):
        # 地区・組織の参照表を check_all に渡す（views の dist・org を照らす。§11。ADR-32）
        ds, my = drafts(mayoi=("",), rows=DRAFT_ROWS[:1])
        rows = tr.with_area(tr.theme_rows(), 地区=tr.ORG)
        rep, theme = dr.check("kotogara", ds, tr.ledgers(), rows, tr.shisetsu_ref(), tr.inputs(), tr.chiku_ref(), tr.soshiki_ref())
        self.assertEqual(rep.errors, [])
        self.assertEqual(theme.views_of("地区", tr.DIST), {tr.ORG})
        rep, _ = dr.check("kotogara", ds, tr.ledgers(), rows, tr.shisetsu_ref(), tr.inputs())
        self.assertTrue([e for e in rep.errors if "hoiku/地区/dist:hino" in e])

    def test_body_untouched(self):
        led = tr.ledgers()
        before = [dict(r) for r in led["kotogara"]]
        ds, _ = drafts()
        dr.check("kotogara", ds, led, tr.theme_rows(), tr.shisetsu_ref(), tr.inputs())
        self.assertEqual(led["kotogara"], before)


class OutputTest(unittest.TestCase):
    def test_sheet_written_with_errors(self):
        ds, my = drafts()
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(run_to(tmp, ds, my), 1)
            self.assertEqual(sorted(os.listdir(tmp)),
                             sorted(["check.md", "hantei-K9.md", "kotogara.candidate.tsv", "quote_context.tsv",
                                     "quote_mismatch.tsv", "review.md", "round_diff.tsv", "signal_chushin.tsv",
                                     "signal_point.tsv", "signal_todoku.tsv", "target_bill.tsv",
                                     "target_name.tsv", "target_unchecked.tsv", "teian_segment.tsv",
                                     "torikoboshi.tsv"]))
            cand = rc.parse_tsv(read(tmp, "kotogara.candidate.tsv").encode(), rc.COLUMNS["kotogara"], "x")
            self.assertEqual(len(cand), 3)
            sheet = read(tmp, "hantei-K9.md")
            self.assertTrue(sheet.startswith("# 判定シート K9（kotogara。下書き：2026-11-05・Opus 5.5）\n"))
            self.assertIn("- 行数：3\n", sheet)
            self.assertIn("- 迷い：1\n", sheet)
            self.assertIn("- 引用が本文に無い行：1\n", sheet)
            rows = [line for line in sheet.split("\n") if line.startswith("| ") and not line.startswith("| #")]
            self.assertEqual(len(rows), 3)
            cells = [line.split(" | ") for line in rows]
            # 出る先：新こども園の定員・用地の views は見本の事業（P）
            self.assertEqual({c[-3] for c in cells}, {tr.P})
            self.assertEqual([c[-2] for c in cells], ["", "", "迷い"])
            self.assertIn("検査：本体に同じキーの行がある", rows[0])
            self.assertIn("検査：引用が資料の本文に無い", rows[2])
            self.assertNotIn("検査：", rows[1])
            self.assertIn("- 誤り：1\n", read(tmp, "check.md"))
            review = read(tmp, "review.md")
            self.assertIn("- 引用：用地は選定中です。", review)
            self.assertIn(f"- 資料のキー：sp:{sid(12)}", review)
            self.assertNotIn("迷い", review)
            self.assertNotIn("下書き：", review)

    def test_exit_zero(self):
        ds, my = drafts(mayoi=("",), rows=DRAFT_ROWS[:1])
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(run_to(tmp, ds, my), 0)
            self.assertIn("- 検査の誤り：0", read(tmp, "hantei-K9.md"))

    def test_destinations(self):
        theme = rc.check_themes(tr.theme_rows(), tr.inputs(), {"fa:a"}, rc.Report())
        row = {c: "" for c in rc.COLUMNS["kisai"]}
        self.assertEqual(dr.destinations("kisai", dict(row, about=""), theme), "テーマ全体")
        self.assertEqual(dr.destinations("kisai", dict(row, about="新こども園の定員"), theme), tr.P)
        self.assertEqual(dr.destinations("yaritori", {}, theme), "—")
        t = {c: "" for c in rc.COLUMNS["tsunagari"]}
        self.assertEqual(dr.destinations("tsunagari", dict(t, upper="提言", lower="再編の方針"), theme), "テーマ全体")

    def test_kisai_sheet(self):
        rows = [["計画の目的", "", "pt:youho/honpen/1", "2025-03", "計画期間は令和6年からです。", "要望", "令和6年", ""]]
        ds, my = drafts(mayoi=("",), rows=rows, ledger="kisai")
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(run_to(tmp, ds, my, ledger="kisai"), 0)
            sheet = read(tmp, "hantei-K9.md")
            self.assertIn("| 1 | 計画の目的/pt:youho/honpen/1 | 計画の目的 |  | pt:youho/honpen/1 | 要望 | 令和6年 | 計画期間は令和6年からです。 | テーマ全体 |  |  |",
                          sheet)


class ArgsTest(unittest.TestCase):
    def test_args(self):
        a = dr.parse_args(["d.tsv", "--ledger", "kisai", "--model", "Opus 5.5", "--date", "2026-11-05", "--sheet", "K3e"])
        self.assertEqual((a.ledger, a.prompt, a.out), ("kisai", "", ""))
        with self.assertRaises(dr.DraftError):
            dr.parse_args(["d.tsv", "--ledger", "kisai", "--model", "x", "--date", "2026/11/05", "--sheet", "K3e"])
        with self.assertRaises(dr.DraftError):
            dr.parse_args(["d.tsv", "--ledger", "kisai", "--model", "x", "--date", "2026-11-05", "--sheet", "../a"])


if __name__ == "__main__":
    unittest.main()
