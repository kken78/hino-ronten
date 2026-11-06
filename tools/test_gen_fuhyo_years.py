"""tools/gen_fuhyo_years.py と、年度の台帳（links/fuhyo-years.tsv）の更新・検査・書き写しの検査
（LINK_SCHEMA.md §3・§5・§6・§7 fuhyo-years・§11、DESIGN.md ADR-33）。

実行: python3 -B tools/test_gen_fuhyo_years.py -v
"""
import copy
import io
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import apply_decisions as ad  # noqa: E402
import check_links  # noqa: E402
import gen_fuhyo_years as gy  # noqa: E402
import gen_mentions as gm  # noqa: E402
import ledger  # noqa: E402
import update_links  # noqa: E402
from test_gen_fuhyo import FakeInputs  # noqa: E402


def item(key, name, desc, kan="見本費", dept=("見本課",)):
    return {"key": key, "kubun": [], "kan": kan, "name": name, "desc": desc, "details": [], "amount": 1,
            "dept": list(dept), "page": 1}


def fuhyo(n, items):
    fid = f"fuhyo-r{n}"
    return {"id": fid, "fiscal_year": {"label": f"令和{n}年度", "year": 2018 + n},
            "source": {"id": fid, "file": f"r{n}.pdf", "page_id": "1"},
            "pillars": [{"no": 1, "name": "見本の柱1", "items": items}]}


# 見本の附表：令和5〜8年度。§7 fuhyo-years の決まりの各場合を1つずつ持つ
FUHYO = {
    "fuhyo-r5": fuhyo(5, [
        item("b001", "子育て支援事業", "子育てを支える。"),                    # R6 と名前が同じ。概要が大きく変わる
        item("b002", "組合負担金", "組合に負担金を出す。", "消防費", ("総務課",)),  # R6 に同じ名前が2つ。款と担当課で1つに絞れる
        item("b003", "旧名事業", "道路を直す工事を行う。"),                    # 名前が変わる（R6 b004）→ 名前の一致ではつながない
        item("b004", "消防施設整備事業", "施設を整える。"),                    # R6・R7 に無く R8 にある → 年度を飛ばす
        item("b005", "公民館　運営事業", "公民館を運営する。"),                # 全角空白。正規化しないので R6 b006 とつながらない
    ]),
    "fuhyo-r6": fuhyo(6, [
        item("b001", "子育て支援事業", "まったく別の内容。"),
        item("b002", "組合負担金", "組合に負担金を出す。", "消防費", ("総務課",)),
        item("b003", "組合負担金", "組合に負担金を出す。", "総務費", ("総務課",)),  # R7 に款の同じ事業が無い → つながない
        item("b004", "新名事業", "道路を直す工事を行う。"),
        item("b006", "公民館運営事業", "公民館を運営する。"),
    ]),
    "fuhyo-r7": fuhyo(7, [
        item("b001", "子育て支援事業", "まったく別の内容。"),
        item("b002", "組合負担金", "組合に負担金を出す。", "消防費", ("総務課",)),  # R6 b002 の候補が2つ → つながない
        item("b003", "組合負担金", "組合に負担金を出す。", "消防費", ("総務課",)),
    ]),
    "fuhyo-r8": fuhyo(8, [
        item("b001", "消防施設整備事業", "施設を整える。"),
    ]),
}
LOCK = {"council-dashboard": {"sha": "a" * 40, "files": []},
        "hino-council-search": {"sha": "b" * 40, "files": []},
        "shiga-hino-plans": {"sha": "c" * 40, "files": ["data/manifest.json", "data/plans/*.json"]
                             + [f"data/fuhyo/{fid}.json" for fid in sorted(FUHYO)]},
        "hino-town-docs": {"sha": "d" * 40, "files": []}}
JUDGE = "判定：依頼者が名前の一致の規則と一覧（{n}行）を確認して確定"


def fh(n, key):
    return f"fh:fuhyo-r{n}/{key}"


def built(fuhyo_set=None):
    return gy.build(gy.YearsInputs(LOCK, copy.deepcopy(fuhyo_set or FUHYO)))


def base_rows(b=None):
    b = b or built()
    return ledger.merge([], gy.generated_rows(b), gy.corpus(b)).rows


def confirm_all(rows, date="2026-11-06"):
    """name の候補をすべて確定した台帳（note は書き写しの道具と同じ形）。"""
    n = sum(1 for r in rows if r["method"] == gy.NAME)
    return [dict(r, status=ledger.CONFIRMED, reviewer="見本", date=date, note=f"{r['note']}。メモ：{JUDGE.format(n=n)}")
            for r in rows]


def manual(frm, to, b=None, note="概要の一致：「道路を直す工事を行う。」。判定：依頼者が会話で確認（2026-11-06）"):
    b = b or built()
    row, bad = gy.manual_row(b, frm, to, {"context": gy.item_of(b, frm)[0]["n"], "status": ledger.CONFIRMED,
                                          "reviewer": "見本", "date": "2026-11-06", "note": note})
    assert not bad, bad
    return row


# 1. 名前の一致の候補（§7 fuhyo-years）
class TestNameRows(unittest.TestCase):
    def setUp(self):
        self.b = built()
        self.rows = {(r["from"], r["to"]): r for r in self.b.rows}

    def test_pairs(self):
        self.assertEqual(sorted(self.rows), sorted([
            (fh(5, "b001"), fh(6, "b001")), (fh(5, "b002"), fh(6, "b002")), (fh(5, "b004"), fh(8, "b001")),
            (fh(6, "b001"), fh(7, "b001"))]))

    def test_notes(self):
        self.assertEqual(self.rows[(fh(5, "b001"), fh(6, "b001"))]["note"],
                         "事業名が同じ。概要の内容が大きく変わっている（Dice 0.00）")
        self.assertEqual(self.rows[(fh(5, "b002"), fh(6, "b002"))]["note"],
                         "事業名が同じ。款と担当課も同じ（同じ年度に同じ名前が複数）")
        self.assertEqual(self.rows[(fh(5, "b004"), fh(8, "b001"))]["note"], "事業名が同じ。間の年度（R6〜R7）は附表に無い")
        self.assertEqual(self.rows[(fh(6, "b001"), fh(7, "b001"))]["note"], "事業名が同じ")

    def test_gap_one_year(self):
        f = copy.deepcopy(FUHYO)
        del f["fuhyo-r7"]
        rows = {(r["from"], r["to"]): r for r in built(f).rows}
        self.assertEqual(rows[(fh(5, "b004"), fh(8, "b001"))]["note"], "事業名が同じ。間の年度（R6）は附表に無い")

    def test_ambiguous(self):
        # R6 b002 → R7 は款と担当課も同じ事業が2つ。つながず、一覧に出す
        self.assertEqual(sorted(a["to"] for a in self.b.ambiguous if a["from"] == fh(6, "b002")),
                         [fh(7, "b002"), fh(7, "b003")])
        self.assertFalse(any(r["from"] == fh(6, "b002") for r in self.b.rows))

    def test_kan_differs_no_row(self):
        # R6 b003（総務費）は R7 に款の同じ事業が無い。つながず、一覧にも出さない。それより後の年度は見ない
        self.assertFalse(any(r["from"] == fh(6, "b003") for r in self.b.rows))
        self.assertFalse(any(a["from"] == fh(6, "b003") for a in self.b.ambiguous))

    def test_raw_name(self):
        # 事業名は正規化しない（全角空白の違いでつながない）
        self.assertFalse(any(r["from"] == fh(5, "b005") for r in self.b.rows))

    def test_row_columns(self):
        r = self.rows[(fh(5, "b001"), fh(6, "b001"))]
        self.assertEqual((r["method"], r["evidence"], r["where"], r["context"], r["to_label"], r["status"]),
                         (gy.NAME, "子育て支援事業", "name", "子育て支援事業", "子育て支援事業", ledger.CANDIDATE))


# 2. 名前が変わった事業の候補の組
class TestRenames(unittest.TestCase):
    def test_order_and_values(self):
        rs = built().renames
        # 概要が同じ組が2つ（Dice 1.00）。名前の Dice の大きい b005→b006 が先
        self.assertEqual([(r["from"], r["to"], r["dice_desc"]) for r in rs[:2]],
                         [(fh(5, "b005"), fh(6, "b006"), "1.00"), (fh(5, "b003"), fh(6, "b004"), "1.00")])
        self.assertEqual([r["dice_desc"] for r in rs], sorted((r["dice_desc"] for r in rs), reverse=True))
        # 名前の一致でつながった事業は入れない
        self.assertFalse(any(r["from"] == fh(5, "b001") or r["to"] == fh(6, "b002") for r in rs))
        self.assertIn((fh(5, "b005"), fh(6, "b006")), [(r["from"], r["to"]) for r in rs])

    def test_write_keeps_dice_order(self):
        b = built()
        with tempfile.TemporaryDirectory() as d:
            gy.write_rename_lists(d, b)
            with open(os.path.join(d, "rename_candidates.tsv"), encoding="utf-8") as f:
                lines = f.read().splitlines()
        self.assertEqual(lines[0].split("\t"), gy.RENAME_COLUMNS)
        self.assertEqual(lines[1].split("\t")[:2], [fh(5, "b005"), fh(6, "b006")])


# 3. 年度の並び
class TestYears(unittest.TestCase):
    def test_stops(self):
        cases = {"year が無い": ({"year": None}, "year が無い"), "同じ year": ({"year": 2024}, "ほかの附表と同じ"),
                 "label の形": ({"label": "2023年度"}, "令和N年度")}
        for name, (values, needle) in cases.items():
            with self.subTest(name=name):
                f = copy.deepcopy(FUHYO)
                f["fuhyo-r5"]["fiscal_year"].update(values)
                with self.assertRaises(gm.GenError) as cm:
                    built(f)
                self.assertIn(needle, str(cm.exception))

    def test_read_inputs_reads_all_named(self):
        files = {f"data/fuhyo/{fid}.json": data for fid, data in FUHYO.items()}
        gi = FakeInputs(files)
        inp = gy.read_years_inputs(gi, LOCK)
        self.assertEqual(sorted(inp.fuhyo), sorted(FUHYO))
        self.assertEqual(sorted(p for _, p in gi.read), sorted(files))  # 計画は読まない


# 4. 台帳の形（§3・§11）
class TestLedgerForm(unittest.TestCase):
    def test_name_and_manual(self):
        rows = base_rows() + [manual(fh(5, "b003"), fh(6, "b004"))]
        out = ledger.parse_ledger(ledger.format_ledger(rows), gy.METHOD)
        self.assertEqual(sorted({r["method"] for r in out}), [gy.MANUAL, gy.NAME])

    def test_stops(self):
        r = base_rows()[0]
        cases = {"method が違う": (dict(r, method="fuhyo-years"), "name・manual でない"),
                 "manual の candidate": (dict(manual(fh(5, "b003"), fh(6, "b004")), status=ledger.CANDIDATE,
                                              reviewer="", date=""), "candidate は置かない"),
                 "to が node": (dict(r, to="node:jisshi/e001"), "to に node は使えない")}
        for name, (row, needle) in cases.items():
            with self.subTest(name=name):
                with self.assertRaises(ledger.LedgerError) as cm:
                    ledger.parse_ledger(ledger.format_ledger([row]), gy.METHOD)
                self.assertIn(needle, str(cm.exception))

    def test_other_ledgers_unchanged(self):
        # mention の台帳の to に fh は使えない
        row = {"from": "sp:0000000001_20250612_0004", "to": fh(5, "b001"), "method": "mention", "evidence": "語",
               "where": "text", "context": "語", "to_label": "見本", "status": ledger.CANDIDATE, "reviewer": "", "date": "",
               "note": ""}
        with self.assertRaises(ledger.LedgerError) as cm:
            ledger.parse_ledger(ledger.format_ledger([row]), "mention")
        self.assertIn("to に fh は使えない", str(cm.exception))


# 5. §5 の照合・§6 の併合
class TestMatchMerge(unittest.TestCase):
    def test_match_label_fh(self):
        b = built()
        c = gy.corpus(b)
        r = base_rows(b)[0]
        self.assertEqual(ledger.match_label(r, c).result, ledger.MATCH)
        self.assertEqual(ledger.match_label(dict(r, to_label="別の名前"), c).result, ledger.STOPPED)
        self.assertEqual(ledger.match_label(dict(r, to=fh(6, "b999")), c).result, ledger.STOPPED)

    def test_manual_kept_not_vanished(self):
        b = built()
        rows = confirm_all(base_rows(b)) + [manual(fh(5, "b003"), fh(6, "b004"), b)]
        rows.sort(key=lambda r: (r["from"], r["to"], r["method"]))
        rep = ledger.check_ledger(rows, gy.generated_rows(b), gy.corpus(b), relink_rows=None)
        self.assertEqual((rep.exit_code, rep.stale, rep.merged.vanished), (0, [], []))

    def test_sentinel(self):
        b = built()
        self.assertEqual(ledger.sentinel(base_rows(b), gy.corpus(b)), [])


# 6. 年度の対応（§11）
class TestYearsErrors(unittest.TestCase):
    def setUp(self):
        self.b = built()
        self.rows = confirm_all(base_rows(self.b))

    def errs(self, rows):
        return gy.years_errors(rows, self.b)

    def test_ok(self):
        self.assertEqual(self.errs(self.rows + [manual(fh(5, "b003"), fh(6, "b004"), self.b)]), [])

    def test_count_mismatch(self):
        rows = self.rows[1:]  # 行数 4 の note のまま 3 行
        self.assertTrue(any("note の行数 4" in e and "3" in e for e in self.errs(rows)))

    def test_counts_by_date(self):
        # 日付の違う判定は別に数える
        rows = [dict(r, date="2026-11-07", note=r["note"].replace("（4行）", "（1行）")) if n == 0 else
                dict(r, note=r["note"].replace("（4行）", "（3行）")) for n, r in enumerate(self.rows)]
        self.assertEqual(self.errs(rows), [])

    def test_judged_missing(self):
        rows = [dict(self.rows[0], note="事業名が同じ。概要の内容が大きく変わっている（Dice 0.00）")] + self.rows[1:]
        self.assertTrue(any("「判定：」が無い" in e for e in self.errs(rows)))

    def test_gap_mismatch(self):
        rows = [dict(r, note=r["note"].replace("（R6〜R7）", "（R6）")) for r in self.rows]
        self.assertTrue(any("間の年度が lock の附表の年度と合わない" in e for e in self.errs(rows)))

    def test_two_links(self):
        extra = manual(fh(5, "b003"), fh(6, "b001"), self.b)  # R6 b001 は R5 b001 ともつながっている
        self.assertTrue(any(fh(6, "b001") in e and "前の年度の事業とのつながりが 2 行" in e
                            for e in self.errs(self.rows + [extra])))

    def test_manual_rules(self):
        cases = {"年度が前でない": (dict(manual(fh(5, "b003"), fh(6, "b004"), self.b), **{"from": fh(6, "b004"),
                                                                                      "to": fh(5, "b003")}), "より前でない"),
                 "note の形": (manual(fh(5, "b003"), fh(6, "b004"), self.b, note="判定：見本"), "で始まらないか"),
                 "名前が同じ": (dict(manual(fh(5, "b003"), fh(6, "b004"), self.b), method=gy.MANUAL,
                                    **{"from": fh(6, "b002"), "to": fh(7, "b002")}), "事業名が同じ")}
        for name, (row, needle) in cases.items():
            with self.subTest(name=name):
                self.assertTrue(any(needle in e for e in self.errs([row])), self.errs([row]))

    def test_rejected_ignored(self):
        rows = self.rows + [dict(manual(fh(5, "b003"), fh(6, "b001"), self.b), status=ledger.REJECTED, note="取り消し")]
        self.assertEqual(self.errs(rows), [])

    def test_pair_counts(self):
        pairs, skipped = gy.pair_counts(self.rows, self.b)
        self.assertEqual([(a.short, b.short, n, p, q) for a, b, n, p, q in pairs],
                         [("R5", "R6", 2, 3, 3), ("R6", "R7", 1, 4, 2), ("R7", "R8", 0, 3, 1)])
        self.assertEqual(skipped, 1)


# 7. 更新・検査・書き写し（update_links・check_links・apply_decisions）
class TestTools(unittest.TestCase):
    def test_update_check_apply(self):
        b = built()
        with tempfile.TemporaryDirectory() as d:
            path, out = os.path.join(d, "links", "fuhyo-years.tsv"), os.path.join(d, "out")
            os.makedirs(os.path.join(d, "links"))
            with self.assertRaises(ledger.LedgerError):
                check_links.run_years(b, path, out)  # 台帳が無ければ止める
            code, merged, _, errors = update_links.run_years(b, path, out)
            self.assertEqual((code, len(merged.added), errors), (0, 4, []))
            self.assertEqual(check_links.run_years(b, path, out)[0], 0)
            self.assertTrue(os.path.exists(os.path.join(out, "rename_candidates.tsv")))
            # 判定：name 4行の確定と manual 1行の追加
            rows = ledger.read_ledger(path, gy.METHOD)
            dec = ["\t".join(ad.DECISION_COLUMNS)]
            dec += ["\t".join([r["from"], r["to"], r["method"], r["context"], ledger.CONFIRMED, "見本", "2026-11-06",
                               JUDGE.format(n=4)]) for r in rows]
            dec.append("\t".join([fh(5, "b003"), fh(6, "b004"), gy.MANUAL, "旧名事業", ledger.CONFIRMED, "見本",
                                  "2026-11-06", "概要の一致：「道路を直す工事を行う。」。判定：依頼者が会話で確認（2026-11-06）"]))
            keys = ["\t".join(ad.KEY_COLUMNS)] + ["\t".join(line.split("\t")[:3]) for line in dec[1:]]
            dpath, kpath = os.path.join(d, "dec.tsv"), os.path.join(d, "keys.tsv")
            for p, lines in ((dpath, dec), (kpath, keys)):
                with open(p, "wb") as f:
                    f.write(("\n".join(lines) + "\n").encode("utf-8"))
            buf = io.StringIO()
            code, applied, rows, _, errors = ad.run_years(dpath, kpath, path, b, out, out=buf)
            self.assertEqual((code, errors), (0, []))
            self.assertEqual((applied[(gy.NAME, ledger.CONFIRMED)], applied[(gy.MANUAL, ledger.CONFIRMED)]), (4, 1))
            self.assertIn("書き写す前の件数：name confirmed 4・rejected 0", buf.getvalue())
            self.assertIn("書き写す前の件数：manual confirmed 1・rejected 0", buf.getvalue())
            r = next(x for x in rows if x["from"] == fh(5, "b001"))
            self.assertEqual(r["note"], "事業名が同じ。概要の内容が大きく変わっている（Dice 0.00）。メモ：" + JUDGE.format(n=4))
            m = next(x for x in rows if x["method"] == gy.MANUAL)
            self.assertEqual((m["evidence"], m["to_label"], m["status"]), ("旧名事業", "新名事業", ledger.CONFIRMED))
            # 更新を動かしても manual の行は変わらない
            code, merged, _, _ = update_links.run_years(b, path, out)
            self.assertEqual((code, len(merged.added), len(merged.updated)), (0, 0, 0))
            # manual の取り消し（rejected）
            cancel = ["\t".join(ad.DECISION_COLUMNS), "\t".join([fh(5, "b003"), fh(6, "b004"), gy.MANUAL, "旧名事業",
                                                                 ledger.REJECTED, "見本", "2026-11-07", "見本の取り消し"])]
            with open(dpath, "wb") as f:
                f.write(("\n".join(cancel) + "\n").encode("utf-8"))
            with open(kpath, "wb") as f:
                f.write(("\n".join(["\t".join(ad.KEY_COLUMNS), "\t".join(cancel[1].split("\t")[:3])]) + "\n").encode("utf-8"))
            code, _, rows, _, _ = ad.run_years(dpath, kpath, path, b, out, out=io.StringIO())
            m = next(x for x in rows if x["method"] == gy.MANUAL)
            self.assertEqual((code, m["status"]), (0, ledger.REJECTED))
            self.assertTrue(m["note"].startswith("却下：見本の取り消し。判別の根拠：概要の一致"))

    def test_apply_stops(self):
        b = built()
        rows = base_rows(b)
        cases = {"名前が同じ manual": ([fh(6, "b002"), fh(7, "b002"), gy.MANUAL, "組合負担金", ledger.CONFIRMED], "事業名が同じ"),
                 "台帳に無い rejected": ([fh(5, "b003"), fh(6, "b004"), gy.MANUAL, "旧名事業", ledger.REJECTED], "confirmed でだけ"),
                 "附表に無い": ([fh(5, "b999"), fh(6, "b004"), gy.MANUAL, "旧名事業", ledger.CONFIRMED], "lock の附表の事業に無い"),
                 "method が違う": ([fh(5, "b003"), fh(6, "b004"), "fuhyo", "旧名事業", ledger.CONFIRMED], "name・manual でない")}
        for name, (cells, needle) in cases.items():
            with self.subTest(name=name):
                d = dict(zip(ad.DECISION_COLUMNS, cells + ["見本", "2026-11-06", "概要の一致：「見本」。判定：見本"]),
                         relink_to="")
                with self.assertRaises(ad.DecisionError) as cm:
                    ad.apply_years(rows, [(2, d)], b)
                self.assertIn(needle, str(cm.exception))


if __name__ == "__main__":
    unittest.main()
