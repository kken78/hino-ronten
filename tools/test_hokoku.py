"""審査報告の記録（records/hokoku.tsv）の検査（LINK_SCHEMA.md §11・§12・§15.9・§15.10、DESIGN.md ADR-34 の7）。

実行: python3 -B tools/test_hokoku.py -v
tools/test_records.py の見本の入力に、委員長の報告の区切り（kind が report）を1つ足し、テーマの定義に kind 報告の行を足す。
決まりに合う例が通ることと、決まりに合わない例で止まる（誤りになる）か一覧に出ることを確かめる。
"""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import records as rc  # noqa: E402
import test_records as tr  # noqa: E402

RM = "0000000002"                       # 報告の会議（議案の会議 tr.M と違う。決算は9月に提案し12月に報告する）
RS = f"{RM}_20251201_0008"              # 委員長の報告の発言
RS2 = f"{RM}_20251201_0009"             # 区切りの外の発言
RP = f"rp:{RS}"
REPORT_TEXT = ("議第１号、令和６年度日野町介護保険特別会計歳入歳出決算については、"
               "要介護認定率の推移、成年後見人制度などについて、３人が質問をしました。"
               "答弁として、認定率は下がっている。"
               "委員より、介護現場にデジタル機器、シニア世代の活用は。との質問に、長寿福祉課より、検討しているとの答弁でした。"
               "12時、介護保険特別会計の質疑を終了しました。"
               "道路の補修について質問がありました。")
REPORT = {"kind": "report", "from": RS, "to": RS, "member": "髙橋源三郎", "seat": "9番", "committee": "予算決算特別委員会",
          "bills": ["議第1号"], "meetingId": RM}
BILL = f"gi:{tr.M}/議第1号"


def inputs():
    inp = tr.inputs()
    inp.statements[RS] = {"text": REPORT_TEXT, "role": "9番", "meetingId": RM}
    inp.statements[RS2] = {"text": "次に移ります。", "role": "議長", "meetingId": RM}
    inp.order += [RS, RS2]
    inp.pos = {s: i for i, s in enumerate(inp.order)}
    inp.reports = {RS: REPORT}
    return inp


def theme_rows(extra=()):
    base = dict(tr.theme_rows()[0], views="")
    rows = tr.theme_rows() + [
        dict(base, kind="報告", value=RP, source="令和7年12月定例会議 2025-12-01 9番 髙橋源三郎 予算決算特別委員会", note=""),
        dict(base, kind="語", value="介護", source="見本", note=""),
        dict(base, kind="事柄", value="要介護認定率", source="見本", note=""),
        dict(base, kind="記載", value="成年後見制度の利用支援", source="見本", note="")] + list(extra)
    return sorted(rows, key=lambda r: (r["theme"], r["kind"], r["value"]))


def hrow(**kw):
    r = tr.row("hokoku", question=RP, bill=BILL, sid=f"sp:{RS}")
    r.update(kw)
    return r


def hokoku_rows():
    return [
        hrow(row="1", side="問い", quote="要介護認定率の推移", speaker="委員", kind="事実の確認", point="要介護認定率"),
        hrow(row="2", side="問い", quote="成年後見人制度", speaker="委員", kind="事実の確認", point="成年後見制度の利用支援"),
        hrow(row="3", side="答え", quote="認定率は下がっている。", speaker="", kind="事実・数字", answers="1",
             point="要介護認定率", note="下書き：見本。報告に答えた人の字が無い。判定：見本"),
        hrow(row="4", side="問い", quote="介護現場にデジタル機器、シニア世代の活用は。", speaker="委員", kind="方針・考え"),
        hrow(row="5", side="答え", quote="検討している", speaker="長寿福祉課より", kind="方針・考え", answers="4"),
    ]


def nozoki_row(**kw):
    r = tr.row("nozoki", question=RP, n="", sid=f"sp:{RS}", quote="12時、介護保険特別会計の質疑を終了しました。",
               reason="見本の理由")
    r.update(kw)
    return r


def run(hok=None, themes=None, nozoki=None, inp=None):
    led = tr.ledgers()
    led["hokoku"] = hokoku_rows() if hok is None else hok
    led["nozoki"] = [nozoki_row()] if nozoki is None else nozoki
    return rc.check_all(led, themes if themes is not None else theme_rows(), tr.shisetsu_ref(), inp or inputs(),
                        tr.chiku_ref(), tr.soshiki_ref())


def replace(rows, n, **kw):
    out = [dict(r) for r in rows]
    out[n].update(kw)
    return out


class HokokuOkTest(tr.RecordsTestCase):
    def test_columns(self):
        self.assertIn("hokoku", rc.LEDGERS)
        self.assertIn("hokoku", rc.OPTIONAL)        # 無ければ0行
        self.assertIn("hokoku", rc.NOT_IN_THEME)    # テーマのノートのデータにはまだ出さない
        self.assertIn("hokoku", rc.TARGET_LEDGERS)
        self.assertIn("報告", rc.THEME_KINDS)
        self.assertEqual(len(rc.THEME_KINDS), 17)   # §12 の17
        self.assertEqual(rc.KEYS["hokoku"], ("question", "row"))
        self.assertEqual(rc.COLUMNS["hokoku"], ["question", "row", "bill", "side", "sid", "quote", "speaker", "kind",
                                                "answers", "target", "target_text", "point", "origin", "status",
                                                "reviewer", "date", "note"])

    def test_passes(self):
        rep = run()
        self.assertEqual(rep.errors, [])
        self.assertEqual(rep.counts["hokoku"], 5)
        self.assertEqual(rep.counts["nozoki"], 1)

    def test_segment_of(self):
        self.assertEqual(inputs().segment_of(RP), REPORT)
        self.assertIsNone(inputs().segment_of(f"rp:{RS2}"))

    def test_bill_from_other_meeting(self):
        # bill は報告の会議でなく提案の会議の議案。報告の区切りの bills とは照らさない（§15.10）
        rep = run(hok=replace(hokoku_rows(), 0, bill=f"gi:{tr.M}/議第1号"))
        self.assertEqual(rep.errors, [])

    def test_empty_ledger(self):
        rep = run(hok=[], nozoki=[])
        self.assertEqual(rep.errors, [])
        self.assertEqual(rep.counts["hokoku"], 0)

    def test_torikoboshi_words_only(self):
        # 報告の区切りの全部の発言を見て、テーマの語（介護）を含み、引用と重ならない文だけを一覧に出す（§11）。
        # 記録しない文は出さない
        rep = run(nozoki=[])
        got = [(x["ledger"], x["question"], x["n"], x["quote"]) for x in rep.torikoboshi if x["ledger"] == "hokoku"]
        self.assertEqual(got, [("hokoku", RP, "", "12時、介護保険特別会計の質疑を終了しました。")])
        rep = run()
        got = [x["quote"] for x in rep.torikoboshi if x["ledger"] == "hokoku"]
        self.assertNotIn("12時、介護保険特別会計の質疑を終了しました。", got)
        self.assertFalse(any("道路" in q for q in got))   # テーマの語の無い文は見ない

    def test_quote_context_not_error(self):
        # 文の途中で切った引用（「との質問に」の前）は、一覧に出すが止めない（§15.10）
        rep = run()
        self.assertEqual(rep.errors, [])
        self.assertTrue(any(x["ledger"] == "hokoku" and x["kind"] == "文の途中で終わる" for x in rep.quote_context))

    def test_target(self):
        rows = replace(hokoku_rows(), 0, target_text="名:要介護認定率の推移")
        self.assertEqual(run(hok=rows).errors, [])


class HokokuErrorTest(tr.RecordsTestCase):
    def test_question_not_rp(self):
        rows = [dict(r, question=f"sq:{RS}") for r in hokoku_rows()]
        self.assertErr(run(hok=rows, nozoki=[]), "審議の記録の報告の区切り")

    def test_question_not_report(self):
        rows = [dict(r, question=f"rp:{RS2}") for r in hokoku_rows()]
        self.assertErr(run(hok=rows, nozoki=[]), "審議の記録の報告の区切り")

    def test_question_not_in_theme(self):
        themes = [r for r in theme_rows() if r["kind"] != "報告"]
        rep = run(themes=themes)
        self.assertErr(rep, "question がテーマの定義の kind 報告に無い")

    def test_theme_report_value(self):
        themes = theme_rows([dict(theme_rows()[0], kind="報告", value=f"rp:{RS2}", note="")])
        self.assertErr(run(themes=themes), "value が kind の形に合わないか")
        themes = theme_rows([dict(theme_rows()[0], kind="報告", value=f"sq:{RS}", note="")])
        self.assertErr(run(themes=themes), "value が kind の形に合わないか")

    def test_duplicate_key(self):
        rows = hokoku_rows() + [hokoku_rows()[-1]]
        self.assertErr(run(hok=rows), "行のキーが重なっている")

    def test_order(self):
        rows = hokoku_rows()
        rows = [rows[1], rows[0]] + rows[2:]
        self.assertErr(run(hok=rows), "行がキーの順でない")

    def test_sid_outside(self):
        self.assertErr(run(hok=replace(hokoku_rows(), 0, sid=f"sp:{RS2}")), "この報告の区切りの発言でない")

    def test_quote_not_in_text(self):
        rep = run(hok=replace(hokoku_rows(), 0, quote="認定率の数"))
        self.assertErr(rep, "confirmed の引用が資料の本文に無い")
        self.assertEqual(len(rep.quote_mismatch), 1)

    def test_bill(self):
        self.assertErr(run(hok=replace(hokoku_rows(), 0, bill=f"gi:{tr.M}/議第9号")), "bill が §2 の gi の形でないか")
        self.assertErr(run(hok=replace(hokoku_rows(), 0, bill="議第1号")), "bill が §2 の gi の形でないか")

    def test_side_kind_values(self):
        self.assertErr(run(hok=replace(hokoku_rows(), 0, side="意見")), "side が")
        self.assertErr(run(hok=replace(hokoku_rows(), 0, kind="事実・数字")), "問いの行の kind が §15.2 の値でない")
        self.assertErr(run(hok=replace(hokoku_rows(), 2, kind="事実の確認")), "答えの行の kind が §15.2 の値でない")

    def test_question_speaker(self):
        self.assertErr(run(hok=replace(hokoku_rows(), 0, speaker="議員")), "問いの行の speaker が「委員」でない")
        self.assertErr(run(hok=replace(hokoku_rows(), 4, speaker="委員")), "答えの行の speaker が「委員」")

    def test_empty_speaker_needs_note(self):
        rows = replace(hokoku_rows(), 2, note="下書き：見本。判定：見本")
        self.assertErr(run(hok=rows), "speaker が空の答えの行の note に「報告に答えた人の字が無い」が無い")
        rows = replace(hokoku_rows(), 4, speaker="")
        self.assertErr(run(hok=rows), "speaker が空の答えの行の note")

    def test_answers(self):
        self.assertErr(run(hok=replace(hokoku_rows(), 4, answers="3")), "answers の 3 が、同じ報告の問いの行でない")
        self.assertErr(run(hok=replace(hokoku_rows(), 4, answers="")), "答えの行に answers が無い")
        self.assertErr(run(hok=replace(hokoku_rows(), 0, answers="2")), "問いの行に answers がある")

    def test_point(self):
        self.assertErr(run(hok=replace(hokoku_rows(), 0, point="新しい点")), "point がテーマの kind 事柄か記載の値でない")

    def test_origin(self):
        self.assertErr(run(hok=replace(hokoku_rows(), 0, origin=f"sp:{RS}")), "origin が空でない")

    def test_common(self):
        self.assertErr(run(hok=replace(hokoku_rows(), 0, note="見本")), "note の頭が「下書き：」でない")
        self.assertErr(run(hok=replace(hokoku_rows(), 0, date="2026-11-15", note="下書き：見本")),
                       "confirmed の note に「判定：」の出どころが無い")
        self.assertErr(run(hok=replace(hokoku_rows(), 0, status="ok")), "status が")

    def test_target_form(self):
        self.assertErr(run(hok=replace(hokoku_rows(), 0, target_text="事業:要介護認定率の推移")),
                       "target_text が「種類:字」を「;」で区切ったもの")
        self.assertErr(run(hok=replace(hokoku_rows(), 0, target="node:jisshi/e110", target_text="名:要介護認定率の推移")),
                       "target が §2 の fh・hs・hj・hk・hz の形のキー")
        self.assertErr(run(hok=replace(hokoku_rows(), 0, target_text="名:福祉バス")),
                       "その行の sid の発言の本文に無い")


class HokokuNozokiTest(tr.RecordsTestCase):
    """記録しない文の question が rp の行（§15.9。n は空）。"""

    def test_n_must_be_empty(self):
        self.assertErr(run(nozoki=[nozoki_row(n="1")]), "question が rp の行の n が空でない")

    def test_report_must_be_recorded(self):
        self.assertErr(run(hok=[], nozoki=[nozoki_row()]), "審査報告の記録に無い")

    def test_sid_outside(self):
        self.assertErr(run(nozoki=[nozoki_row(sid=f"sp:{RS2}", quote="次に移ります。")]),
                       "sid がその問いの場面の発言でない")

    def test_quote(self):
        rep = run(nozoki=[nozoki_row(quote="13時に再開しました。")])
        self.assertErr(rep, "confirmed の引用が資料の本文に無い")


if __name__ == "__main__":
    unittest.main()
