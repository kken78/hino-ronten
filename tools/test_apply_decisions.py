"""tools/apply_decisions.py の検査（LINK_SCHEMA.md §1・§3・§6・§7 fuhyo・§11、DESIGN.md §5 工程4-5・工程5）。

実行: python3 -B tools/test_apply_decisions.py -v
見本の入力と台帳は tools/test_ledger.py と同じもの（LedgerTestCase）を使う。附表の台帳の見本は
tools/test_gen_fuhyo.py の FuhyoTestCase を使う。
"""
import contextlib
import io
import os
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import apply_decisions as ad  # noqa: E402
import gen_fuhyo as gf  # noqa: E402
import gen_mentions as gm  # noqa: E402
import ledger  # noqa: E402
from test_gen_fuhyo import NONE, FuhyoTestCase, fh, node  # noqa: E402
from test_ledger import BQ, FILLER, TEXTS, TEXTS_TWO, LedgerTestCase, sid  # noqa: E402

S1, S2, S4 = f"sp:{sid(1)}", f"sp:{sid(2)}", f"sp:{sid(4)}"
COLUMNS_9 = ad.DECISION_COLUMNS + [ad.RELINK_TO]


class ApplyTestCase(LedgerTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ledger_path = os.path.join(self.tmp.name, "mention.tsv")
        self.relink_path = os.path.join(self.tmp.name, "relink.tsv")
        self.decisions_path = os.path.join(self.tmp.name, "decisions.tsv")
        self.keys_path = os.path.join(self.tmp.name, "keys.tsv")
        self.out = os.path.join(self.tmp.name, "build")
        self.printed = io.StringIO()  # 書き写す前の件数の表示
        ledger.write_ledger(self.ledger_path, self.base())

    def tearDown(self):
        self.tmp.cleanup()

    def ledger_bytes(self):
        with open(self.ledger_path, "rb") as f:
            return f.read()

    def relink_bytes(self):
        """relink の台帳のバイト列（無ければ None）。"""
        if not os.path.exists(self.relink_path):
            return None
        with open(self.relink_path, "rb") as f:
            return f.read()

    def dec(self, frm, to, status, note="", rows=None, **kw):
        """判定の一覧の1行。context は台帳の行（rows を省くと self.base()）のもの。"""
        r = self.row(rows or self.base(), frm, to)
        d = {"from": frm, "to": to, "method": "mention", "context": r["context"], "status": status,
             "reviewer": "kken78", "date": "2026-10-11", "note": note, ad.RELINK_TO: ""}
        d.update(kw)
        return d

    def write_decisions(self, rows, raw=None, columns=ad.DECISION_COLUMNS, keys=None):
        """判定の一覧を書く。範囲の一覧も書く（keys を省くと、rows の (from, to, method) を重ねずに並べたもの）。"""
        data = raw if raw is not None else (
            "\n".join(["\t".join(columns)] + ["\t".join(d[c] for c in columns) for d in rows]) + "\n").encode("utf-8")
        with open(self.decisions_path, "wb") as f:
            f.write(data)
        if keys is None:
            keys = list(dict.fromkeys((d["from"], d["to"], d["method"]) for d in rows or []))
        self.write_keys(keys)

    def write_keys(self, keys, raw=None):
        data = raw if raw is not None else (
            "\n".join(["\t".join(ad.KEY_COLUMNS)] + ["\t".join(k) for k in keys]) + "\n").encode("utf-8")
        with open(self.keys_path, "wb") as f:
            f.write(data)

    def write(self, texts=TEXTS):
        return ad.write(self.decisions_path, self.keys_path, self.ledger_path, self.built(texts=texts),
                        self.relink_path, self.printed)

    def run_apply(self, texts=TEXTS):
        return ad.run(self.decisions_path, self.keys_path, self.ledger_path, self.built(texts=texts), self.out,
                      self.relink_path, out=self.printed)

    def assert_stops_without_writing(self, rows=None, raw=None, needle=None, columns=ad.DECISION_COLUMNS, keys=None,
                                     keys_raw=None):
        before, before_relink = self.ledger_bytes(), self.relink_bytes()
        self.write_decisions(rows, raw, columns, keys)
        if keys_raw is not None:
            self.write_keys(None, keys_raw)
        self.printed = io.StringIO()
        with self.assertRaises(ad.DecisionError) as cm:
            self.write()
        self.assertEqual(self.ledger_bytes(), before)  # 1件も書かない
        self.assertEqual(self.relink_bytes(), before_relink)
        self.assertEqual(self.printed.getvalue(), "")  # 止めたときは件数も表示しない
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
        applied = self.write()
        self.assertEqual((applied["confirmed"], applied["rejected"], applied["relink"]), (2, 1, 0))
        self.assertIsNone(self.relink_bytes())  # 付け替えが無ければ relink の台帳を作らない
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
        self.write()
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
        keys = [(S2, "plan:kodomo", "mention")]
        for name, raw in cases.items():
            with self.subTest(name=name):
                self.assert_stops_without_writing(raw=raw, keys=keys, needle="判定の一覧")
        self.write_decisions(None, raw=good, keys=keys)  # 形の正しい一覧は書き写せる
        self.write()


# 3. 同じ一覧を2回当てると「candidate でない」で止まる
class TestTwice(ApplyTestCase):
    def test_second_time_stops(self):
        rows = [self.dec(S1, "plan:kyoiku4", "confirmed"), self.dec(S4, "lin:kodomo/2", "rejected", note="理由")]
        self.write_decisions(rows)
        self.write()
        after_first = self.ledger_bytes()
        msg = self.assert_stops_without_writing(rows, needle="candidate でない")
        self.assertIn("2 件", msg)
        self.assertEqual(self.ledger_bytes(), after_first)


# 4. 書いたあとに check_links.run で確かめる
class TestRun(ApplyTestCase):
    def test_check_passes(self):
        self.write_decisions([self.dec(S1, "plan:kyoiku4", "confirmed"),
                              self.dec(S4, "lin:kodomo/2", "rejected", note="理由")])
        code, applied, rows, rep = self.run_apply()
        self.assertEqual(code, 0)
        self.assertEqual([r["status"] for r in rows].count("confirmed"), 1)
        self.assertEqual((rep.checked.counts[ledger.MATCH], rep.stale, rep.sentinel_failures), (4, [], []))

    def test_check_fails_after_writing(self):
        # 確定した行が、lock の版の入力では再生成で出ない → 書いたうえで、確かめが終了コード1
        self.write_decisions([self.dec(S2, "plan:kodomo", "confirmed")])
        texts = list(TEXTS)
        texts[1] = FILLER
        code, _, rows, rep = self.run_apply(texts=texts)
        self.assertEqual(code, 1)
        self.assertEqual(self.row(rows, S2, "plan:kodomo")["status"], "confirmed")
        self.assertEqual(len(rep.merged.vanished_confirmed), 1)


# 5. 付け替え（§6）：relink_to のある rejected の行は、links/relink.tsv にも1行足す
class TestRelink(ApplyTestCase):
    REASON_NOTE = "却下：前の理由。判別の根拠：期の明記（第2期）"

    def expected_relink(self, base_row, to, note, date="2026-10-11"):
        label = gm.to_label(to, gm.plan_names(self.manifest, self.refs), self.refs)
        return {"from": base_row["from"], "to": to, "method": "relink", "evidence": base_row["evidence"],
                "where": base_row["where"], "context": base_row["context"], "to_label": label,
                "status": "confirmed", "reviewer": "kken78", "date": date, "note": note}

    def test_candidate_rejected_and_relinked(self):
        base = self.base()
        self.write_decisions([self.dec(S1, "plan:kyoiku4", "confirmed"),
                              self.dec(S4, "lin:kodomo/2", "rejected", note="第3期の話", relink_to="plan:kodomo")],
                             columns=COLUMNS_9)
        code, applied, rows, rep = self.run_apply()
        self.assertEqual(code, 0)
        self.assertEqual((applied["confirmed"], applied["rejected"], applied["relink"]), (1, 1, 1))
        self.assertEqual(self.printed.getvalue().splitlines(),
                         ["書き写す前の件数：lin:kodomo/2 confirmed 0・rejected 1",
                          "書き写す前の件数：plan:kyoiku4 confirmed 1・rejected 0",
                          "書き写す前の件数：付け替え 1"])
        b4 = self.row(base, S4, "lin:kodomo/2")
        self.assertEqual(self.row(rows, S4, "lin:kodomo/2"),
                         dict(b4, status="rejected", reviewer="kken78", date="2026-10-11",
                              note=f"却下：第3期の話。判別の根拠：{b4['note']}"))
        relink = ledger.read_ledger(self.relink_path, "relink")
        self.assertEqual(relink, [self.expected_relink(b4, "plan:kodomo", "付け替え：lin:kodomo/2 の却下から。第3期の話")])
        self.assertTrue(self.relink_bytes().startswith("\t".join(ledger.LEDGER_COLUMNS).encode("utf-8") + b"\n"))
        self.assertEqual((len(rep.relink.rows), rep.relink.checked.counts[ledger.MATCH], rep.relink.exit_code), (1, 1, 0))

    def already_rejected(self):
        rows = self.decide(self.base(), S4, "lin:kodomo/2", "rejected", note=self.REASON_NOTE)
        ledger.write_ledger(self.ledger_path, rows)
        return rows

    def test_relink_already_rejected(self):
        # 判定の note が空なら、mention の行の却下の理由（「却下：」から「。判別の根拠：」の前まで）を使う
        for note, reason in (("", "前の理由"), ("第3期の話", "第3期の話")):
            with self.subTest(note=note):
                rows = self.already_rejected()
                if os.path.exists(self.relink_path):
                    os.remove(self.relink_path)
                before = self.ledger_bytes()
                self.write_decisions([self.dec(S4, "lin:kodomo/2", "rejected", note=note, relink_to="plan:kodomo",
                                               date="2026-10-18")], columns=COLUMNS_9)
                applied = self.write()
                self.assertEqual(self.ledger_bytes(), before)  # mention の行は変えない
                self.assertEqual((applied["confirmed"], applied["rejected"], applied["relink"]), (0, 0, 1))
                self.assertEqual(ledger.read_ledger(self.relink_path, "relink"),
                                 [self.expected_relink(self.row(rows, S4, "lin:kodomo/2"), "plan:kodomo",
                                                       f"付け替え：lin:kodomo/2 の却下から。{reason}", date="2026-10-18")])

    def test_relink_appended_in_order(self):
        # relink の台帳にある行は残し、足した行と合わせて from → to → method の順に書く
        rows = self.decide(self.already_rejected(), S2, "plan:kodomo", "rejected", note=self.REASON_NOTE)
        ledger.write_ledger(self.ledger_path, rows)
        self.write_decisions([self.dec(S4, "lin:kodomo/2", "rejected", relink_to="plan:kodomo")], columns=COLUMNS_9)
        self.write()
        self.write_decisions([self.dec(S2, "plan:kodomo", "rejected", relink_to="plan:kyoiku4")], columns=COLUMNS_9)
        applied = self.write()
        self.assertEqual(applied["relink"], 1)
        self.assertEqual([(r["from"], r["to"]) for r in ledger.read_ledger(self.relink_path, "relink")],
                         [(S2, "plan:kyoiku4"), (S4, "plan:kodomo")])

    def test_eight_columns_still_accepted(self):
        self.write_decisions([self.dec(S1, "plan:kyoiku4", "confirmed")])
        self.assertEqual(self.write()["confirmed"], 1)


# 6. 付け替えの誤り：どちらの台帳にも書かない
class TestRelinkErrors(ApplyTestCase):
    def test_bad_relink_to(self):
        cases = {
            "confirmed に relink_to": (self.dec(S2, "plan:kodomo", "confirmed", relink_to="plan:kyoiku4"),
                                     "rejected の行にだけ"),
            "存在しない plan": (self.dec(S4, "lin:kodomo/2", "rejected", note="理由", relink_to="plan:nothing"),
                            "manifest にも系譜表にも無い"),
            "存在しない lin": (self.dec(S4, "lin:kodomo/2", "rejected", note="理由", relink_to="lin:kodomo/9"),
                           "manifest にも系譜表にも無い"),
            "manifest にある版の lin": (self.dec(S4, "lin:kodomo/2", "rejected", note="理由", relink_to="lin:kodomo/3"),
                                   "manifest にも系譜表にも無い"),
            "node": (self.dec(S4, "lin:kodomo/2", "rejected", note="理由", relink_to="node:kodomo/e001"),
                     "plan・lin のキーでない"),
            "元の to と同じ": (self.dec(S4, "lin:kodomo/2", "rejected", note="理由", relink_to="lin:kodomo/2"),
                          "元の行の to と同じ"),
            "candidate の却下に理由が無い": (self.dec(S4, "lin:kodomo/2", "rejected", relink_to="plan:kodomo"),
                                     "却下の理由）が空"),
        }
        good = self.dec(S1, "plan:kyoiku4", "confirmed")
        for name, (bad, needle) in cases.items():
            with self.subTest(name=name):
                self.assert_stops_without_writing([good, bad], needle=needle, columns=COLUMNS_9)

    def test_duplicate_in_relink_ledger(self):
        rows = self.decide(self.base(), S4, "lin:kodomo/2", "rejected", note="却下：理由。判別の根拠：根拠")
        ledger.write_ledger(self.ledger_path, rows)
        self.write_decisions([self.dec(S4, "lin:kodomo/2", "rejected", relink_to="plan:kodomo")], columns=COLUMNS_9)
        self.write()
        self.assert_stops_without_writing([self.dec(S4, "lin:kodomo/2", "rejected", relink_to="plan:kodomo")],
                                          needle="relink の台帳に同じ (from, to, method) の行がある", columns=COLUMNS_9)

    def test_duplicate_in_decisions(self):
        # 同じ発言の2行を、同じ計画に付け替える
        gen, corpus = self.gen_and_corpus(texts=TEXTS_TWO)
        rows = ledger.merge([], gen, corpus).rows
        ledger.write_ledger(self.ledger_path, rows)
        before = self.ledger_bytes()
        self.write_decisions([self.dec(S4, "lin:kodomo/2", "rejected", note="理由", rows=rows, relink_to="plan:kodomo"),
                              self.dec(S4, "plan:kyoiku4", "rejected", note="理由", rows=rows, relink_to="plan:kodomo")],
                             columns=COLUMNS_9)
        with self.assertRaises(ad.DecisionError) as cm:
            self.write(texts=TEXTS_TWO)
        self.assertIn("一覧に 2 回", str(cm.exception))
        self.assertEqual((self.ledger_bytes(), self.relink_bytes()), (before, None))

    def test_conflict_not_written(self):
        # 付け替え先の (from, to) の mention の行が candidate のまま → 書く前に止める
        gen, corpus = self.gen_and_corpus(texts=TEXTS_TWO)
        rows = ledger.merge([], gen, corpus).rows
        ledger.write_ledger(self.ledger_path, rows)
        before = self.ledger_bytes()
        self.write_decisions([self.dec(S4, "lin:kodomo/2", "rejected", note="理由", rows=rows, relink_to="plan:kyoiku4")],
                             columns=COLUMNS_9)
        with self.assertRaises(ad.DecisionError) as cm:
            self.write(texts=TEXTS_TWO)
        self.assertIn("付け替えの重なり", str(cm.exception))
        self.assertEqual((self.ledger_bytes(), self.relink_bytes()), (before, None))

    def test_already_rejected_without_relink_to(self):
        ledger.write_ledger(self.ledger_path, self.decide(self.base(), S4, "lin:kodomo/2", "rejected",
                                                          note="却下：理由。判別の根拠：根拠"))
        self.assert_stops_without_writing([self.dec(S4, "lin:kodomo/2", "rejected", note="理由")],
                                          needle="candidate でない（rejected）", columns=COLUMNS_9)

    def test_headers(self):
        row = self.dec(S2, "plan:kodomo", "confirmed")
        line = "\t".join(row[c] for c in ad.DECISION_COLUMNS)
        cases = {"9列目の名前が違う": ("\t".join(ad.DECISION_COLUMNS + ["relink"]), line + "\t"),
                 "10列": ("\t".join(COLUMNS_9 + ["memo"]), line + "\t\t"),
                 "relink_to が途中": ("\t".join(ad.DECISION_COLUMNS[:-1] + [ad.RELINK_TO, "note"]), line + "\t"),
                 "9列のヘッダに8列の行": ("\t".join(COLUMNS_9), line)}
        for name, (head, body) in cases.items():
            with self.subTest(name=name):
                self.assert_stops_without_writing(raw=(head + "\n" + body + "\n").encode("utf-8"),
                                                  keys=[(S2, "plan:kodomo", "mention")], needle="判定の一覧")


# 7. 判定の範囲（§11、CLAUDE.md 不変の制約11）：--keys の一覧と判定の一覧が同じでなければ、どちらの台帳にも書かない
class TestScope(ApplyTestCase):
    def test_usage(self):
        # --keys が無い・引数の数が違う → 使い方を表示して終了コード1。入力を読まず、台帳は変わらない
        self.write_decisions([self.dec(S1, "plan:kyoiku4", "confirmed")])
        before = self.ledger_bytes()
        cases = {"引数なし": [], "--keys が無い（前の形）": [self.decisions_path],
                 "--keys が無い（2つ）": [self.keys_path, self.decisions_path],
                 "判定の一覧が無い": ["--keys", self.keys_path],
                 "引数が多い": ["--keys", self.keys_path, self.decisions_path, self.decisions_path],
                 "--keys の位置が違う": [self.decisions_path, "--keys", self.keys_path]}
        for name, args in cases.items():
            with self.subTest(name=name):
                err, out = io.StringIO(), io.StringIO()
                with mock.patch.object(ad.check_links, "LEDGER_PATH", self.ledger_path), \
                        mock.patch.object(ad.check_links, "RELINK_PATH", self.relink_path), \
                        mock.patch.object(ad.check_links, "OUT_DIR", self.out), \
                        mock.patch.object(ad.check_links, "RELINK_OUT_DIR", self.out), \
                        mock.patch.object(ad.gm, "load_lock", side_effect=AssertionError("使い方の誤りで入力を読んだ")), \
                        contextlib.redirect_stderr(err), contextlib.redirect_stdout(out):
                    code = ad.main(["apply_decisions.py"] + args)
                self.assertEqual(code, 1)
                self.assertIn(ad.USAGE, err.getvalue())
                self.assertEqual(out.getvalue(), "")
                self.assertEqual((self.ledger_bytes(), self.relink_bytes()), (before, None))

    def test_keys_format(self):
        d = self.dec(S2, "plan:kodomo", "confirmed")
        head = "\t".join(ad.KEY_COLUMNS) + "\n"
        line = f"{S2}\tplan:kodomo\tmention\n"
        good = (head + line).encode("utf-8")
        cases = {"ヘッダの順": (good.replace(b"from\tto", b"to\tfrom", 1), "ヘッダ"),
                 "ヘッダに列を足す": (("from\tto\tmethod\tcontext\n" + line[:-1] + "\t" + d["context"] + "\n").encode("utf-8"),
                               "ヘッダ"),
                 "ヘッダが2列": (("from\tto\n" + f"{S2}\tplan:kodomo\n").encode("utf-8"), "ヘッダ"),
                 "行が0件": (head.encode("utf-8"), "範囲の行が0件"),
                 "列の数の違い": ((head + line + f"{S1}\tplan:kyoiku4\n").encode("utf-8"), "3行目：列の数が 2"),
                 "重複": ((head + line + line).encode("utf-8"), "範囲の一覧に 2 回"),
                 "BOM": (b"\xef\xbb\xbf" + good, "BOM"),
                 "CR": (good.replace(b"\n", b"\r\n"), "CR"),
                 "最後の改行なし": (good[:-1], "改行で終わっていない")}
        for name, (raw, needle) in cases.items():
            with self.subTest(name=name):
                msg = self.assert_stops_without_writing([d], keys_raw=raw, needle=needle)
                self.assertIn("範囲の一覧", msg)
        self.write_decisions([d])
        self.write_keys(None, good)  # 形の正しい範囲の一覧なら書き写せる
        self.assertEqual(self.write()["confirmed"], 1)

    def test_duplicates_all_listed(self):
        line = (S2, "plan:kodomo", "mention")
        msg = self.assert_stops_without_writing([self.dec(S2, "plan:kodomo", "confirmed")], keys=[line, line, line])
        self.assertIn("3 件", msg)
        for n in (2, 3, 4):
            self.assertIn(f"{n}行目 {S2} plan:kodomo mention：同じ (from, to, method) が範囲の一覧に 3 回ある", msg)

    def test_out_of_scope(self):
        msg = self.assert_stops_without_writing(
            [self.dec(S1, "plan:kyoiku4", "confirmed"), self.dec(S2, "plan:kodomo", "confirmed")],
            keys=[(S1, "plan:kyoiku4", "mention")])
        self.assertIn(f"判定の一覧 3行目 {S2} plan:kodomo mention：範囲の外の行", msg)
        self.assertIn("1 件", msg)

    def test_no_decision(self):
        msg = self.assert_stops_without_writing(
            [self.dec(S1, "plan:kyoiku4", "confirmed")],
            keys=[(S1, "plan:kyoiku4", "mention"), (S4, "lin:kodomo/2", "mention")])
        self.assertIn(f"範囲の一覧 3行目 {S4} lin:kodomo/2 mention：判定が無い", msg)
        self.assertIn("1 件", msg)

    def test_both_listed_before_ledger_check(self):
        # 範囲の外の行と判定の無い行をすべて示す。台帳との照合（apply）より前に止める
        outside = self.dec(S1, "plan:kyoiku4", "confirmed", **{"from": f"sp:{sid(9)}"})  # 台帳にも無い行
        msg = self.assert_stops_without_writing(
            [self.dec(S2, "plan:kodomo", "confirmed"), outside],
            keys=[(S2, "plan:kodomo", "mention"), (S4, "lin:kodomo/2", "mention")])
        self.assertIn("2 件", msg)
        self.assertIn(f"判定の一覧 3行目 sp:{sid(9)} plan:kyoiku4 mention：範囲の外の行", msg)
        self.assertIn(f"範囲の一覧 3行目 {S4} lin:kodomo/2 mention：判定が無い", msg)
        self.assertNotIn("台帳に同じ", msg)

    def test_same_scope(self):
        # 範囲と判定の一覧が同じ（並びは違ってよい）→ いまと同じに書き写し、書く前に件数を to の文字コード順に表示する
        rows = [self.dec(S1, "plan:kyoiku4", "confirmed"), self.dec(S2, "plan:kodomo", "confirmed"),
                self.dec(S4, "lin:kodomo/2", "rejected", note="理由")]
        self.write_decisions(rows, keys=[(d["from"], d["to"], d["method"]) for d in reversed(rows)])
        with open(self.decisions_path, "rb") as f:
            expect, _ = ad.apply(self.base(), ad.parse_decisions(f.read()))
        applied = self.write()
        self.assertEqual((applied["confirmed"], applied["rejected"], applied["relink"]), (2, 1, 0))
        self.assertEqual(ledger.read_ledger(self.ledger_path, "mention"), expect)
        self.assertIsNone(self.relink_bytes())
        self.assertEqual(self.printed.getvalue().splitlines(),
                         ["書き写す前の件数：lin:kodomo/2 confirmed 0・rejected 1",
                          "書き写す前の件数：plan:kodomo confirmed 1・rejected 0",
                          "書き写す前の件数：plan:kyoiku4 confirmed 1・rejected 0",
                          "書き写す前の件数：付け替え 0"])


# 8. 附表の台帳（--ledger fuhyo。§6・§7 fuhyo・§11）
class TestFuhyo(FuhyoTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ledger_path = os.path.join(self.tmp.name, "fuhyo.tsv")
        self.decisions_path = os.path.join(self.tmp.name, "decisions.tsv")
        self.keys_path = os.path.join(self.tmp.name, "keys.tsv")
        self.out = os.path.join(self.tmp.name, "build")
        self.printed = io.StringIO()
        ledger.write_ledger(self.ledger_path, self.fuhyo_base())

    def tearDown(self):
        self.tmp.cleanup()

    def ledger_bytes(self):
        with open(self.ledger_path, "rb") as f:
            return f.read()

    def dec(self, frm, to, status, note=""):
        r = self.row(self.fuhyo_base(), frm, to)
        return {"from": frm, "to": to, "method": "fuhyo", "context": r["context"], "status": status,
                "reviewer": "kken78", "date": "2026-10-20", "note": note, ad.RELINK_TO: ""}

    def write_files(self, rows, columns=ad.DECISION_COLUMNS, keys=None):
        data = "\n".join(["\t".join(columns)] + ["\t".join(d[c] for c in columns) for d in rows]) + "\n"
        with open(self.decisions_path, "wb") as f:
            f.write(data.encode("utf-8"))
        keys = keys if keys is not None else [(d["from"], d["to"], d["method"]) for d in rows]
        with open(self.keys_path, "wb") as f:
            f.write(("\n".join(["\t".join(ad.KEY_COLUMNS)] + ["\t".join(k) for k in keys]) + "\n").encode("utf-8"))

    def write(self):
        return ad.write_fuhyo(self.decisions_path, self.keys_path, self.ledger_path, self.built(), self.printed)

    def assert_stops_without_writing(self, rows, needle, **kw):
        before = self.ledger_bytes()
        self.write_files(rows, **kw)
        with self.assertRaises(ad.DecisionError) as cm:
            self.write()
        self.assertEqual(self.ledger_bytes(), before)  # 1件も書かない
        self.assertEqual(self.printed.getvalue(), "")
        self.assertIn(needle, str(cm.exception))
        return str(cm.exception)

    def test_apply_and_counts(self):
        rows = [self.dec(fh("b001"), node("e001"), "confirmed", note="区分：一致"),
                self.dec(fh("b002"), node("e002"), "rejected", note="事業の中身が違う"),
                self.dec(fh("b002"), NONE, "confirmed", note="区分：一部。見本のメモ")]
        self.write_files(rows)
        code, applied, after, rep = ad.run_fuhyo(self.decisions_path, self.keys_path, self.ledger_path, self.built(),
                                                 self.out, out=self.printed)
        self.assertEqual((code, applied["confirmed"], applied["rejected"]), (0, 2, 1))
        # 書き写す前の件数は、to の種類（node・none）と status ごと。付け替えの行は無い
        self.assertEqual(self.printed.getvalue().splitlines(),
                         ["書き写す前の件数：node confirmed 1・rejected 1",
                          "書き写す前の件数：none confirmed 1・rejected 0"])
        base = self.fuhyo_base()
        self.assertEqual(self.row(after, fh("b002"), node("e002")),
                         dict(self.row(base, fh("b002"), node("e002")), status="rejected", reviewer="kken78",
                              date="2026-10-20",
                              note=f"却下：事業の中身が違う。判別の根拠：{self.row(base, fh('b002'), node('e002'))['note']}"))
        self.assertEqual((rep.classification.classified, len(rep.classification.pending)), ([fh("b001"), fh("b002")], 6))
        self.assertEqual(ledger.read_ledger(self.ledger_path, "fuhyo"), after)

    def test_confirmed_without_kubun_stops(self):
        # 確定の判定のメモに §7 fuhyo の区分が無い、または to の種類に合わない区分なら、書き写さない
        for note, needle in (("見本のメモ", "区分が無い"), ("区分：一部", "区分「一部」は node の確定に使えない")):
            with self.subTest(note=note):
                self.assert_stops_without_writing([self.dec(fh("b001"), node("e001"), "confirmed", note=note)], needle)

    def test_relink_to_refused(self):
        rows = [self.dec(fh("b001"), node("e001"), "confirmed")]
        self.assert_stops_without_writing(rows, "relink_to の列を使わない", columns=ad.DECISION_COLUMNS + [ad.RELINK_TO])

    def test_scope_must_hold_all_candidates_of_a_project(self):
        # b002 の候補は node と none の2行。node だけを判定した範囲は止める
        msg = self.assert_stops_without_writing([self.dec(fh("b002"), node("e002"), "confirmed")],
                                                "candidate の行が欠けている")
        self.assertIn(f"{fh('b002')} {NONE} fuhyo", msg)

    def test_scope_mismatch(self):
        rows = [self.dec(fh("b001"), node("e001"), "confirmed")]
        msg = self.assert_stops_without_writing(rows, "範囲の外の行", keys=[(fh("b003"), node("e012"), "fuhyo")])
        self.assertIn("判定が無い", msg)

    def test_classification_errors(self):
        both = [self.dec(fh("b002"), node("e002"), "confirmed"), self.dec(fh("b002"), NONE, "confirmed")]
        self.assert_stops_without_writing(both, "confirmed の none と confirmed の node が両方ある")
        all_rejected = [self.dec(fh("b002"), node("e002"), "rejected", note="理由"),
                        self.dec(fh("b002"), NONE, "rejected", note="理由")]
        self.assert_stops_without_writing(all_rejected, "候補をすべて却下した")

    def test_mention_rules_still_apply(self):
        # 理由の無い却下・context の違いは、附表の台帳でも止める（apply の検査を通す）
        self.assert_stops_without_writing([self.dec(fh("b001"), node("e001"), "rejected")], "却下の理由")
        bad = dict(self.dec(fh("b001"), node("e001"), "confirmed"), context="別の事業")
        self.assert_stops_without_writing([bad], "context が台帳の行と違う")

    def test_usage(self):
        cases = {"--keys が無い": ["--ledger", "fuhyo", self.decisions_path],
                 "判定の一覧が無い": ["--ledger", "fuhyo", "--keys", self.keys_path],
                 "台帳の名前が違う": ["--ledger", "relink", "--keys", self.keys_path, self.decisions_path],
                 "--ledger の位置が違う": ["--keys", self.keys_path, self.decisions_path, "--ledger", "fuhyo"]}
        before = self.ledger_bytes()
        for name, args in cases.items():
            with self.subTest(name=name):
                err, out = io.StringIO(), io.StringIO()
                with mock.patch.object(gm, "load_lock", side_effect=AssertionError("使い方の誤りで入力を読んだ")), \
                        mock.patch.object(gf, "load_built", side_effect=AssertionError("使い方の誤りで入力を読んだ")), \
                        contextlib.redirect_stderr(err), contextlib.redirect_stdout(out):
                    self.assertEqual(ad.main(["apply_decisions.py"] + args), 1)
                self.assertIn(ad.USAGE, err.getvalue())
                self.assertEqual((out.getvalue(), self.ledger_bytes()), ("", before))


if __name__ == "__main__":
    unittest.main()
