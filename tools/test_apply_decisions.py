"""tools/apply_decisions.py の検査（LINK_SCHEMA.md §1・§3・§6、DESIGN.md §5 工程4-5）。

実行: python3 -B tools/test_apply_decisions.py -v
見本の入力と台帳は tools/test_ledger.py と同じもの（LedgerTestCase）を使う。
"""
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import apply_decisions as ad  # noqa: E402
import ledger  # noqa: E402
from test_ledger import BQ, FILLER, TEXTS, LedgerTestCase, sid  # noqa: E402

S1, S2, S4 = f"sp:{sid(1)}", f"sp:{sid(2)}", f"sp:{sid(4)}"


class ApplyTestCase(LedgerTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ledger_path = os.path.join(self.tmp.name, "mention.tsv")
        self.decisions_path = os.path.join(self.tmp.name, "decisions.tsv")
        self.out = os.path.join(self.tmp.name, "build")
        ledger.write_ledger(self.ledger_path, self.base())

    def tearDown(self):
        self.tmp.cleanup()

    def ledger_bytes(self):
        with open(self.ledger_path, "rb") as f:
            return f.read()

    def dec(self, frm, to, status, note="", **kw):
        """判定の一覧の1行。context は台帳の行のもの。"""
        r = self.row(self.base(), frm, to)
        d = {"from": frm, "to": to, "method": "mention", "context": r["context"], "status": status,
             "reviewer": "kken78", "date": "2026-10-11", "note": note}
        d.update(kw)
        return d

    def write_decisions(self, rows, raw=None):
        data = raw if raw is not None else (
            "\n".join(["\t".join(ad.DECISION_COLUMNS)] + ["\t".join(d[c] for c in ad.DECISION_COLUMNS) for d in rows])
            + "\n").encode("utf-8")
        with open(self.decisions_path, "wb") as f:
            f.write(data)

    def assert_stops_without_writing(self, rows=None, raw=None, needle=None):
        before = self.ledger_bytes()
        self.write_decisions(rows, raw)
        with self.assertRaises(ad.DecisionError) as cm:
            ad.write(self.decisions_path, self.ledger_path)
        self.assertEqual(self.ledger_bytes(), before)  # 1件も書かない
        if needle:
            self.assertIn(needle, str(cm.exception))
        return str(cm.exception)


# 1. 確定・却下の書き写しと note の作り方
class TestApply(ApplyTestCase):
    def test_confirm_and_reject(self):
        base = self.base()
        self.write_decisions([self.dec(S1, "plan:kyoiku4", "confirmed"),
                              self.dec(S2, "plan:kodomo", "confirmed", note="見本のメモ"),
                              self.dec(S4, "lin:kodomo/2", "rejected", note="見本の却下の理由")])
        applied = ad.write(self.decisions_path, self.ledger_path)
        self.assertEqual((applied["confirmed"], applied["rejected"]), (2, 1))
        after = ledger.read_ledger(self.ledger_path, "mention")
        expect = {
            (S1, "plan:kyoiku4"): ("confirmed", self.row(base, S1, "plan:kyoiku4")["note"]),
            (S2, "plan:kodomo"): ("confirmed", self.row(base, S2, "plan:kodomo")["note"] + "。メモ：見本のメモ"),
            (S4, "lin:kodomo/2"): ("rejected", "却下：見本の却下の理由。判別の根拠：" + self.row(base, S4, "lin:kodomo/2")["note"]),
        }
        for b, a in zip(base, after):
            k = (a["from"], a["to"])
            with self.subTest(row=k):
                self.assertEqual((a["from"], a["to"], a["method"]), (b["from"], b["to"], b["method"]))
                if k in expect:
                    self.assertEqual((a["status"], a["reviewer"], a["date"], a["note"]),
                                     (expect[k][0], "kken78", "2026-10-11", expect[k][1]))
                    # status・reviewer・date・note のほかは変えない
                    for c in ledger.LEDGER_COLUMNS:
                        if c not in ("status", "reviewer", "date", "note"):
                            self.assertEqual(a[c], b[c])
                else:
                    self.assertEqual(a, b)

    def test_decided_note(self):
        self.assertEqual(ad.decided_note("confirmed", "根拠", ""), "根拠")
        self.assertEqual(ad.decided_note("confirmed", "根拠", "メモ1"), "根拠。メモ：メモ1")
        self.assertEqual(ad.decided_note("confirmed", "", "メモ1"), "メモ：メモ1")
        self.assertEqual(ad.decided_note("rejected", "根拠", "理由"), "却下：理由。判別の根拠：根拠")

    def test_bq_row(self):
        self.write_decisions([self.dec(BQ, "plan:kyoiku4", "confirmed")])
        ad.write(self.decisions_path, self.ledger_path)
        self.assertEqual(self.row(ledger.read_ledger(self.ledger_path, "mention"), BQ, "plan:kyoiku4")["status"],
                         "confirmed")


# 2. 合わない行があれば、台帳に1件も書かない
class TestRejectRows(ApplyTestCase):
    def test_bad_rows(self):
        good = self.dec(S1, "plan:kyoiku4", "confirmed")
        cases = {
            "台帳に無い": (self.dec(S1, "plan:kyoiku4", "confirmed", **{"from": f"sp:{sid(9)}"}), "台帳に同じ"),
            "context が違う": (self.dec(S2, "plan:kodomo", "confirmed", context="について質問します"), "context が台帳の行と違う"),
            "理由の無い却下": (self.dec(S2, "plan:kodomo", "rejected"), "却下の理由"),
            "date の形": (self.dec(S2, "plan:kodomo", "confirmed", date="2026/10/11"), "YYYY-MM-DD"),
            "date が日付でない": (self.dec(S2, "plan:kodomo", "confirmed", date="2026-02-30"), "日付として正しくない"),
            "status": (self.dec(S2, "plan:kodomo", "candidate"), "confirmed・rejected でない"),
            "reviewer が空": (self.dec(S2, "plan:kodomo", "confirmed", reviewer=""), "reviewer が空"),
        }
        for name, (bad, needle) in cases.items():
            with self.subTest(name=name):
                # 正しい行と一緒でも、1件も書かない
                self.assert_stops_without_writing([good, bad], needle=needle)

    def test_duplicate(self):
        d = self.dec(S2, "plan:kodomo", "confirmed")
        self.assert_stops_without_writing([d, dict(d, note="2回目")], needle="一覧に 2 回")

    def test_not_candidate(self):
        ledger.write_ledger(self.ledger_path, self.decide(self.base(), S2, "plan:kodomo", "confirmed"))
        self.assert_stops_without_writing([self.dec(S2, "plan:kodomo", "rejected", note="理由")],
                                          needle="candidate でない（confirmed）")

    def test_all_bad_rows_listed(self):
        msg = self.assert_stops_without_writing([self.dec(S1, "plan:kyoiku4", "rejected"),
                                                 self.dec(S2, "plan:kodomo", "confirmed", date="")])
        self.assertIn("2 件", msg)
        self.assertIn("2行目", msg)
        self.assertIn("3行目", msg)

    def test_format(self):
        good = ("\t".join(ad.DECISION_COLUMNS) + "\n" + "\t".join(
            self.dec(S2, "plan:kodomo", "confirmed")[c] for c in ad.DECISION_COLUMNS) + "\n").encode("utf-8")
        cases = {"BOM": b"\xef\xbb\xbf" + good, "CR": good.replace(b"\n", b"\r\n"), "最後の改行なし": good[:-1],
                 "ヘッダ": good.replace(b"from\tto", b"to\tfrom", 1),
                 "note にタブ": good[:-1] + b"\t\xe8\xbf\xbd\xe5\x8a\xa0\n",
                 "行が0件": ("\t".join(ad.DECISION_COLUMNS) + "\n").encode("utf-8")}
        for name, raw in cases.items():
            with self.subTest(name=name):
                self.assert_stops_without_writing(raw=raw)
        self.write_decisions(None, raw=good)  # 形の正しい一覧は書き写せる
        ad.write(self.decisions_path, self.ledger_path)


# 3. 同じ一覧を2回当てると「candidate でない」で止まる
class TestTwice(ApplyTestCase):
    def test_second_time_stops(self):
        rows = [self.dec(S1, "plan:kyoiku4", "confirmed"), self.dec(S4, "lin:kodomo/2", "rejected", note="理由")]
        self.write_decisions(rows)
        ad.write(self.decisions_path, self.ledger_path)
        after_first = self.ledger_bytes()
        msg = self.assert_stops_without_writing(rows, needle="candidate でない")
        self.assertIn("2 件", msg)
        self.assertEqual(self.ledger_bytes(), after_first)


# 4. 書いたあとに check_links.run で確かめる
class TestRun(ApplyTestCase):
    def test_check_passes(self):
        self.write_decisions([self.dec(S1, "plan:kyoiku4", "confirmed"),
                              self.dec(S4, "lin:kodomo/2", "rejected", note="理由")])
        code, applied, rows, rep = ad.run(self.decisions_path, self.ledger_path, self.built(), self.out)
        self.assertEqual(code, 0)
        self.assertEqual([r["status"] for r in rows].count("confirmed"), 1)
        self.assertEqual((rep.checked.counts[ledger.MATCH], rep.stale, rep.sentinel_failures), (4, [], []))

    def test_check_fails_after_writing(self):
        # 確定した行が、lock の版の入力では再生成で出ない → 書いたうえで、確かめが終了コード1
        self.write_decisions([self.dec(S2, "plan:kodomo", "confirmed")])
        texts = list(TEXTS)
        texts[1] = FILLER
        code, _, rows, rep = ad.run(self.decisions_path, self.ledger_path, self.built(texts=texts), self.out)
        self.assertEqual(code, 1)
        self.assertEqual(self.row(rows, S2, "plan:kodomo")["status"], "confirmed")
        self.assertEqual(len(rep.merged.vanished_confirmed), 1)


if __name__ == "__main__":
    unittest.main()
