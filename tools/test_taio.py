"""問いと事項の対応（records/taio.tsv）の道具の検査（LINK_SCHEMA.md §2 の段落の位置・§11・§15.12、DESIGN.md ADR-39）。

実行: python3 -B tools/test_taio.py -v
tools/test_records.py の見本の入力の発言に段落の区切り（改行）を入れ、見本の台帳（やりとり・質疑の記録）をまとめ直す。
hani の書き方、引用の段落の決め方、まとめ直しの決まり（止める条件を含む）、まとめ直しでない行の守り方、§11 の検査、
対応の無い問いの一覧、前の版との比べ方、判定の書き写し（--ledger taio）、まとめ直しの道具の引数を確かめる。
"""
import io
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import apply_decisions as ad  # noqa: E402
import check_records  # noqa: E402
import gen_mentions as gm  # noqa: E402
import gen_taio  # noqa: E402
import records as rc  # noqa: E402
import test_hokoku as th  # noqa: E402
import test_records as tr  # noqa: E402

S = tr.sid
DATE = "2026-11-16"
P1 = "新こども園の定員"
P2 = "新こども園の用地"
# 段落の区切りを入れた本文（§4 の正規化は改行を除くので、見本の台帳の引用はそのまま本文にある）
TEXTS = {2: "新こども園の定員を伺います。\n前置きです。", 4: "定員は285人です。\nお答えします。",
         6: "面積はどうか。\n要望します。", 8: "約3,000\n平方メートルです。",
         13: "予算について。\nこども園の土地はどうか。道路はどうか。"}
HANI1 = f"sp:{S(2)}/1,sp:{S(4)}/1,sp:{S(6)}/1,sp:{S(8)}/1-2"
HANI2 = f"sp:{S(13)}/2"
NOTE1 = f"まとめ直し：{DATE}（もと：records/yaritori.tsv の row 1,2,3,4）。判定：もとの行の判定（{rc.NO_HANTEI}）"


def inputs():
    inp = tr.inputs()
    for n, t in TEXTS.items():
        inp.statements[S(n)]["text"] = t
    return inp


def expected():
    return [
        {"question": tr.IQ, "point": P1, "hani": HANI1, "bills": "", "bq": "bq:30/松田洋子/1", "status": "confirmed",
         "reviewer": "kken78", "date": "2026-10-27", "note": NOTE1},
        {"question": tr.SQ, "point": P2, "hani": HANI2, "bills": f"gi:{tr.M}/議第1号", "bq": "", "status": "confirmed",
         "reviewer": "kken78", "date": "2026-10-27",
         "note": f"まとめ直し：{DATE}（もと：records/shitsugi.tsv の row 1）。判定：もとの行の判定（{rc.NO_HANTEI}）"},
    ]


def trow(**kw):
    r = {c: "" for c in rc.TAIO_COLUMNS}
    r.update(kw)
    return r


def run(taio=None, led=None, themes=None, inp=None):
    led = dict(led or tr.ledgers())
    led[rc.TAIO] = expected() if taio is None else taio
    return rc.check_all(led, themes if themes is not None else tr.theme_rows(), tr.shisetsu_ref(), inp or inputs(),
                        tr.chiku_ref(), tr.soshiki_ref())


def replace(rows, n, **kw):
    out = [dict(r) for r in rows]
    out[n].update(kw)
    return out


class HaniTest(unittest.TestCase):
    def test_format_one_way(self):
        # 発言の順・段落の順。続いた段落は1つの範囲、離れた段落は同じ sid を繰り返す。同じ段落は1回
        paras = [("b", 3), ("a", 7), ("a", 5), ("a", 6), ("a", 9), ("a", 5)]
        self.assertEqual(rc.format_hani(paras), "sp:a/5-7,sp:a/9,sp:b/3")
        self.assertEqual(rc.format_hani(reversed(paras)), "sp:a/5-7,sp:a/9,sp:b/3")

    def test_parse(self):
        h = f"sp:{S(2)}/1-3,sp:{S(2)}/5,sp:{S(4)}/2"
        paras, errs = rc.parse_hani(h)
        self.assertEqual(errs, [])
        self.assertEqual(paras, [(S(2), 1), (S(2), 2), (S(2), 3), (S(2), 5), (S(4), 2)])
        self.assertEqual(rc.format_hani(paras), h)

    def test_parse_errors(self):
        cases = [("", "空"), (f"sp:{S(2)}/0", "形でない"), (f"sp:{S(2)}", "形でない"), (f"sp:{S(2)}/1, sp:{S(4)}/1", "形でない"),
                 (f"sp:{S(2)}/3-3", "始めが終わり"), (f"sp:{S(2)}/4-2", "始めが終わり"),
                 (f"sp:{S(2)}/1-3,sp:{S(2)}/2", "2回"), (f"sp:{S(4)}/1,sp:{S(2)}/1", "順"),
                 (f"sp:{S(2)}/3,sp:{S(2)}/1", "順"), (f"sp:{S(2)}/1,sp:{S(2)}/2", "まとめていない"),
                 (f"sp:{S(2)}/1-2,sp:{S(2)}/3", "まとめていない")]
        for h, msg in cases:
            _, errs = rc.parse_hani(h)
            self.assertTrue(any(msg in e for e in errs), f"{h!r}：{errs}")

    def test_sid_with_hyphen(self):
        # sid は「-」を含むことがある。段落の位置は最後の「/」で分ける（§2）
        s = "0000000009_9_kai-giroku_0001"
        paras, errs = rc.parse_hani(f"sp:{s}/2-3")
        self.assertEqual((paras, errs), ([(s, 2), (s, 3)], []))

    def test_paragraphs(self):
        self.assertEqual(rc.paragraphs("一。\n\n　\n二。\n"), ["一。", "二。"])
        self.assertEqual(rc.paragraphs("改行の無い本文"), ["改行の無い本文"])


class QuotePlacesTest(unittest.TestCase):
    def test_places(self):
        text = "一つ目の段落です。\n二つ目の  段落です。\n三つ目。"
        self.assertEqual(rc.quote_places(text, "二つ目の段落"), [frozenset({2})])     # §4 の正規化のあとで比べる
        self.assertEqual(rc.quote_places(text, "段落です。二つ目"), [frozenset({1, 2})])   # またいだ段落を全部
        self.assertEqual(rc.quote_places(text, "無い文"), [])
        self.assertEqual(rc.quote_places(text, ""), [])
        self.assertEqual(rc.quote_places("同じ。\n同じ。", "同じ。"), [frozenset({1}), frozenset({2})])


class MatomeTest(unittest.TestCase):
    def test_baseline(self):
        made, errs = rc.matome(tr.ledgers(), inputs(), DATE)
        self.assertEqual(errs, [])
        self.assertEqual(made, expected())

    def test_skip_empty_point_and_rejected_and_candidate(self):
        led = tr.ledgers()
        led["yaritori"] = replace(led["yaritori"], 3, status="rejected", note="下書き：見本。却下：見本")
        led["yaritori"] = replace(led["yaritori"], 2, point="")
        led["yaritori"] = replace(led["yaritori"], 1, status="candidate", reviewer="", date="")
        made, errs = rc.matome(led, inputs(), DATE)
        self.assertEqual(errs, [])
        self.assertEqual(made[0]["hani"], f"sp:{S(2)}/1,sp:{S(4)}/1")
        self.assertEqual((made[0]["status"], made[0]["reviewer"], made[0]["date"]), ("candidate", "", ""))
        self.assertEqual(made[0]["note"], f"まとめ直し：{DATE}（もと：records/yaritori.tsv の row 1,2）")

    def test_hantei_and_date(self):
        led = tr.ledgers()
        led["yaritori"] = replace(led["yaritori"], 0, note="下書き：x。判定：行ごと（判定シート A）。メモ", date="2026-11-05")
        led["yaritori"] = replace(led["yaritori"], 1, note="下書き：x。判定：二者一致・抜き取り（判定シート A）")
        led["yaritori"] = replace(led["yaritori"], 2, note="下書き：x。判定：行ごと（判定シート A）", date="2026-11-07")
        made, _ = rc.matome(led, inputs(), DATE)
        self.assertEqual(made[0]["date"], "2026-11-07")   # いちばん新しい日
        self.assertTrue(made[0]["note"].endswith("。判定：もとの行の判定（行ごと（判定シート A）・二者一致・抜き取り（判定シート A））"))

    def test_hantei_parentheses(self):
        # 括弧の中の「。」では切らない。括弧の外に「。」が無ければ終わりまで。「判定：」は含めない
        n = "下書き：x。判定：行ごと（一覧 hokoku-an で確認。不変の制約11 の (1)・(2)。2026-11-15）。メモ：y。判定：z"
        self.assertEqual(rc.hantei_of(n), "行ごと（一覧 hokoku-an で確認。不変の制約11 の (1)・(2)。2026-11-15）")
        self.assertEqual(rc.hantei_of("判定：行ごと（判定シート A）"), "行ごと（判定シート A）")
        self.assertEqual(rc.hantei_of("判定：行ごと（閉じない。メモ"), "行ごと（閉じない。メモ")
        self.assertEqual(rc.hantei_of("判定：a）b。c"), "a）b")
        self.assertEqual(rc.hantei_of("下書き：x"), "")
        led = tr.ledgers()
        led["yaritori"] = replace(led["yaritori"], 0, note="下書き：x。判定：行ごと（会話で確認。2026-11-15）")
        made, _ = rc.matome(led, inputs(), DATE)
        self.assertTrue(made[0]["note"].endswith("。判定：もとの行の判定（行ごと（会話で確認。2026-11-15））"))
        self.assertEqual(made[0]["note"].count("（"), made[0]["note"].count("）"))

    def test_bills_order_and_bq(self):
        led = tr.ledgers()
        s2 = dict(led["shitsugi"][0], row="2", bills=f"gi:{tr.M}/議第2号,gi:{tr.M}/議第1号")
        led["shitsugi"] = [dict(led["shitsugi"][0], row="10"), s2]   # row の数の順に、初めて出た順
        made, errs = rc.matome(led, inputs(), DATE)
        self.assertEqual(errs, [])
        self.assertEqual(made[1]["bills"], f"gi:{tr.M}/議第2号,gi:{tr.M}/議第1号")
        self.assertIn("の row 2,10）", made[1]["note"])
        # bq は point の空の行も含めて見る
        led = tr.ledgers()
        led["yaritori"] = [dict(r, bq="") for r in led["yaritori"]]
        led["yaritori"].append(tr.row("yaritori", question=tr.IQ, n="2", row="5", side="問い", sid=f"sp:{S(10)}",
                                      quote="次に用地を伺います。", speaker="議員", round="最初の問い", stage="結果",
                                      kind="事実の確認", bq="bq:30/松田洋子/1"))
        made, errs = rc.matome(led, inputs(), DATE)
        self.assertEqual((errs, made[0]["bq"]), ([], "bq:30/松田洋子/1"))

    def test_hokoku(self):
        led = tr.ledgers()
        led["hokoku"] = th.hokoku_rows()
        inp = th.inputs()
        for n, t in TEXTS.items():
            inp.statements[S(n)]["text"] = t
        made, errs = rc.matome(led, inp, DATE)
        self.assertEqual(errs, [])
        hk = [r for r in made if r["question"] == th.RP]
        self.assertEqual([(r["point"], r["hani"], r["bills"]) for r in hk],
                         [("成年後見制度の利用支援", f"sp:{th.RS}/1", th.BILL), ("要介護認定率", f"sp:{th.RS}/1", th.BILL)])

    def test_ambiguous_paragraph(self):
        # 同じ発言の2つの段落に当たる引用：どちらも同じ組のほかの行で決まった段落なら止めない。そうでなければ止める
        inp = inputs()
        inp.statements[S(4)]["text"] = "定員は285人です。\n定員は285人です。お答えします。\n約3,000平方メートルです。"
        led = tr.ledgers()
        led["yaritori"] = [r for r in led["yaritori"] if r["row"] in ("1", "2")]
        made, errs = rc.matome(led, inp, DATE)
        self.assertEqual([r["question"] for r in made], [tr.SQ])
        self.assertTrue(any("段落が1つに決まらない" in e and "row 2" in e for e in errs), errs)
        led["yaritori"].append(dict(led["yaritori"][1], row="5", quote="定員は285人です。お答えします。"))
        led["yaritori"].append(dict(led["yaritori"][1], row="6", quote="す。定員は285"))
        made, errs = rc.matome(led, inp, DATE)
        self.assertEqual(errs, [])
        self.assertEqual(made[0]["hani"], f"sp:{S(2)}/1,sp:{S(4)}/1-2")

    def test_stops(self):
        cases = []
        led = tr.ledgers()
        led["yaritori"] = replace(led["yaritori"], 1, quote="本文に無い字")
        cases.append((led, "引用が発言の本文に無い"))
        led = tr.ledgers()
        led["yaritori"] = replace(led["yaritori"], 1, sid=f"sp:{tr.M}_20250101_0099")
        cases.append((led, "索引の発言でない"))
        led = tr.ledgers()
        led["yaritori"] = replace(led["yaritori"], 1, reviewer="someone")
        cases.append((led, "reviewer が1つでない"))
        led = tr.ledgers()
        led["yaritori"] = replace(led["yaritori"], 2, bq="bq:30/松田洋子/2")
        cases.append((led, "bq が2つ以上"))
        for led, msg in cases:
            made, errs = rc.matome(led, inputs(), DATE)
            self.assertTrue(any(msg in e for e in errs), f"{msg}：{errs}")


def written(r, note="判定：二者一致・抜き取り（判定シート K9a）", status="confirmed", **kw):
    """まとめ直した candidate の行に、--ledger taio で判定を書き写した形の行（§15.12）。"""
    head = r["note"].split("。判定：")[0]
    return dict(r, status=status, reviewer="kken78", date="2026-11-20",
                note=head + ("。" + note if status == "confirmed" else "。却下：" + note), **kw)


class MergeTest(unittest.TestCase):
    def new_row(self, **kw):
        return trow(question=tr.IQ, point="新しい事項", hani=f"sp:{S(2)}/2", status="candidate",
                    note="下書き：2026-11-17・Opus 5.5（プロンプトの版なし）", **kw)

    def test_keep_non_matome_rows(self):
        made = expected()
        cur = [self.new_row()] + [dict(made[1], hani="古い", status="candidate", reviewer="", date="",
                                       note=made[1]["note"].split("。判定：")[0])]
        rows, c, errs, diff = rc.merge_taio(cur, made, DATE)
        self.assertEqual((errs, diff), ([], []))
        self.assertEqual(rows, sorted(made + [self.new_row()], key=lambda r: (r["question"], r["point"])))
        self.assertEqual(c, {"added": 1, "changed": 1, "removed": 0, "kept": 1, "written": 0})
        # 2回目は変わらない
        rows2, c2, _, _ = rc.merge_taio(rows, made, DATE)
        self.assertEqual((rows2, c2["added"], c2["changed"]), (rows, 0, 0))

    def test_date_only_change_is_same(self):
        made = expected()
        old = [dict(r, note=r["note"].replace(DATE, "2026-11-01")) for r in made]
        rows, c, errs, _ = rc.merge_taio(old, made, DATE)
        self.assertEqual((errs, rows, c["changed"]), ([], made, 0))

    def test_collision(self):
        made = expected()
        _, _, errs, _ = rc.merge_taio([dict(made[0], note="下書き：x")], made, DATE)
        self.assertTrue(any("まとめ直しでない行と同じ" in e for e in errs), errs)

    def test_is_written(self):
        e = expected()
        cand = dict(e[0], status="candidate", reviewer="", date="", note=e[0]["note"].split("。判定：")[0])
        self.assertEqual([rc.is_written(r) for r in (e[0], cand, written(cand), written(cand, "事項が違う", "rejected"),
                                                    trow(note="下書き：x。判定：y"))],
                         [False, False, True, True, False])
        self.assertEqual([rc.as_matome(r) for r in (e[0], cand, written(cand))], [True, True, False])

    def test_written_rows_kept(self):
        # 判定を書き写した行は作り直さず、そのまま残す。もとの行が変わっていても止めない。中身が違えば数える
        made = expected()
        w = written(made[0], hani=f"sp:{S(2)}/1-2,sp:{S(4)}/1,sp:{S(6)}/1,sp:{S(8)}/1-2")   # 判定で hani を直した
        rows, c, errs, diff = rc.merge_taio([w, made[1]], made, DATE)
        self.assertEqual(errs, [])
        self.assertEqual(rows, [w, made[1]])
        self.assertEqual((c["written"], c["added"], c["changed"]), (1, 0, 0))
        self.assertEqual(diff, [(tr.IQ, P1, "中身が違う（列 hani）")])
        rows, _, errs, diff = rc.merge_taio([w, made[1]], made[1:], DATE)   # 組が無くなっても止めない
        self.assertEqual((errs, rows), ([], [w, made[1]]))
        self.assertEqual(diff, [(tr.IQ, P1, "組が無くなる")])
        # 中身が同じなら数えない。日の違う書き写した行があっても、まとめ直した日は1つに決まる
        w2 = dict(written(made[0]), note=written(made[0])["note"].replace(DATE, "2026-11-01"))
        rows, _, errs, diff = rc.merge_taio([w2, made[1]], made, DATE)
        self.assertEqual((errs, diff, rows), ([], [], [w2, made[1]]))
        self.assertEqual(rc.matome_dates(rows), {DATE})


class CheckTaioTest(tr.RecordsTestCase):
    def test_baseline(self):
        rep = run()
        self.assertEqual(rep.errors, [])
        self.assertEqual(rep.taio["rows"], 2)
        self.assertEqual(rep.taio["themes"], {"hoiku": 2})
        self.assertEqual(rep.taio_missing, [])

    def test_not_checked_without_taio(self):
        rep = tr.run(inp=inputs())
        self.assertIsNone(rep.taio)
        self.assertEqual(rep.errors, [])

    def test_broken_rows(self):
        e = expected()
        cases = [
            (replace(e, 0, hani=f"sp:{S(2)}/3,sp:{S(4)}/1,sp:{S(6)}/1,sp:{S(8)}/1-2"), "段落の数（2）を超える"),
            (replace(e, 0, hani=HANI1 + f",sp:{tr.M}_20250101_0099/1"), "索引に無い"),
            (replace(e, 1, hani=f"sp:{S(12)}/1"), "区切りの発言でない"),
            (replace(e, 0, point="無い事項"), "point が"),
            ([e[0], e[0], e[1]], "行のキーが重なっている"),
            ([e[1], e[0]], "キーの順でない"),
            (replace(e, 0, hani=f"sp:{S(2)}/1,sp:{S(2)}/1"), "2回"),
            (replace(e, 0, bills=f"gi:{tr.M}/議第1号"), "一般質問の行に bills"),
            (replace(e, 1, bills=""), "bills が空"),
            (replace(e, 1, bills=f"gi:{tr.M}/議第1号,gi:{tr.M}/議第1号"), "同じキーが2つ"),
            (replace(e, 1, bills=f"gi:{tr.M}/議第9号"), "gian.json に無い"),
            (replace(e, 0, bq="bq:30/中西佳子/1"), "議会だよりに無い"),
            (replace(e, 1, bq="bq:30/松田洋子/1"), "bq がある"),
            (replace(e, 0, question=f"iq:{S(4)}"), "question"),
            (replace(e, 0, status="candidate"), "candidate に reviewer"),
            (replace(e, 0, status="rejected", note=""), "rejected の note が空"),
            (replace(e, 0, note="メモ"), "note の頭"),
            (replace(e, 0, note="下書き：x"), "「判定：」が無い"),
            # まとめ直した組と同じキーの、まとめ直しでない行
            (replace(e, 0, note="下書き：x。判定：x"), "台帳のまとめ直した行に無い"),
        ]
        for rows, msg in cases:
            rep = run(rows)
            self.assertErr(rep, msg)

    def test_matome_check(self):
        e = expected()
        self.assertErr(run(replace(e, 0, hani=f"sp:{S(2)}/1-2,sp:{S(4)}/1,sp:{S(6)}/1,sp:{S(8)}/1-2")), "列 hani")
        self.assertErr(run(e[1:]), "台帳のまとめ直した行に無い")
        self.assertErr(run(replace(e, 1, note=e[1]["note"].replace(DATE, "2026-11-17"))), "日が2つ以上")
        # まとめ直しでない行は、まとめ直しの確かめで見ない
        extra = trow(question=tr.IQ, point=P2, hani=f"sp:{S(2)}/2", status="candidate", note="下書き：x")
        rep = run(sorted(e + [extra], key=lambda r: (r["question"], r["point"])))
        self.assertEqual(rep.errors, [])

    def test_written_rows_not_checked(self):
        # もとの行が candidate のままの組を、confirmed に書き写した行。まとめ直しの確かめで誤りにならない
        led = tr.ledgers()
        led["yaritori"] = [dict(r, status="candidate", reviewer="", date="") for r in led["yaritori"]]
        made, _ = rc.matome(led, inputs(), DATE)
        self.assertEqual(made[0]["status"], "candidate")
        w = written(made[0])
        rep = run([w, made[1]], led=led)
        self.assertEqual(rep.errors, [])
        self.assertEqual((rep.taio["written"], rep.taio["matome"], rep.taio["written_diff"]), (1, 1, []))
        # 判定で hani を直した行も誤りにならず、違いを数える（check.md に出す）
        w = written(made[0], hani=f"sp:{S(2)}/1-2,sp:{S(4)}/1,sp:{S(6)}/1,sp:{S(8)}/1-2")
        rep = run([w, made[1]], led=led)
        self.assertEqual(rep.errors, [])
        self.assertEqual(rep.taio["written_diff"], [(tr.IQ, P1, "中身が違う（列 hani）")])
        lines = check_records.report_lines(rep)
        self.assertIn("- 判定を書き写した行で、まとめ直すと別の中身になるか無くなる組：1（止めない）", lines)
        self.assertIn(f"  - {tr.IQ} × {P1}：中身が違う（列 hani）", lines)
        # 却下を書き写した行も同じ
        rep = run([written(made[0], "事項が違う", "rejected"), made[1]], led=led)
        self.assertEqual(rep.errors, [])
        # まとめ直したままの行（candidate）の hani を書き写しなしに変えたら誤り
        self.assertErr(run([dict(made[0], hani=f"sp:{S(2)}/2"), made[1]], led=led), "列 hani")

    def test_bq_member_and_sq_bills(self):
        inp = inputs()
        inp.bulletin["bq:30/中西佳子/1"] = ["見本"]
        self.assertErr(run(replace(expected(), 0, bq="bq:30/中西佳子/1"), inp=inp), "bq の議員")
        inp = inputs()
        inp.gian[tr.M].add("議第2号")
        self.assertErr(run(replace(expected(), 1, bills=f"gi:{tr.M}/議第1号,gi:{tr.M}/議第2号"), inp=inp),
                       "質疑の区切りの会議・議案に無い")

    def test_missing_list_and_rp(self):
        led = tr.ledgers()
        led["hokoku"] = th.hokoku_rows()
        inp = th.inputs()
        for n, t in TEXTS.items():
            inp.statements[S(n)]["text"] = t
        led[rc.TAIO] = expected()
        rep = rc.check_all(led, th.theme_rows(), tr.shisetsu_ref(), inp, tr.chiku_ref(), tr.soshiki_ref())
        self.assertErr(rep, "台帳のまとめ直した行に無い")   # 報告の組がまだ台帳に無い
        self.assertEqual(rep.taio_missing, [{"theme": "hoiku", "kind": "報告", "question": th.RP, "date": "2025-12-01"}])
        made, _ = rc.matome(led, inp, DATE)
        led[rc.TAIO] = made
        rep = rc.check_all(led, th.theme_rows(), tr.shisetsu_ref(), inp, tr.chiku_ref(), tr.soshiki_ref())
        self.assertEqual(rep.errors, [])
        self.assertEqual((rep.taio_missing, rep.taio["themes"]), ([], {"hoiku": 4}))
        # rp は議案の会議と報告の会議を比べない。区切りの bills が空なら止めずに数える
        th.REPORT["bills"] = []
        try:
            rep = rc.check_all(led, th.theme_rows(), tr.shisetsu_ref(), inp, tr.chiku_ref(), tr.soshiki_ref())
        finally:
            th.REPORT["bills"] = ["議第1号"]
        self.assertEqual((rep.errors, rep.taio["rp_no_bills"]), ([], 2))
        bad = replace(made, [i for i, r in enumerate(made) if r["question"] == th.RP][0], bills=f"gi:{tr.M}/議第1号,x")
        rep = rc.check_all(dict(led, taio=bad), th.theme_rows(), tr.shisetsu_ref(), inp, tr.chiku_ref(), tr.soshiki_ref())
        self.assertErr(rep, "gi の形でないか")

    def test_question_date(self):
        self.assertEqual(rc.question_date(f"iq:{S(2)}"), "2025-01-01")
        self.assertEqual(rc.question_date("rp:0000000009_9_kaigiroku_0001"), "")

    def test_report_lines(self):
        rep = run()
        lines = check_records.report_lines(rep)
        self.assertIn("- 問いと事項の対応：2行（candidate 0・confirmed 2・rejected 0。まとめ直したままの行 2・判定を書き写した行 0）",
                      lines)
        self.assertIn("- 問いと事項の対応の、題材ごとの組（題材に選んだ問い・質疑・報告を question に持つ行）：hoiku 2", lines)
        self.assertIn("- 対応の無い問い・質疑・報告：0（hoiku 0。taio_missing.tsv）", lines)
        self.assertNotIn("- 問いと事項の対応：", "\n".join(check_records.report_lines(tr.run())))

    def test_write_outputs(self):
        rep = run(replace(expected(), 0, status="rejected", note=expected()[0]["note"] + "。却下：見本",
                          reviewer="kken78", date="2026-11-16"))
        self.assertEqual(rep.taio_missing, [{"theme": "hoiku", "kind": "問い", "question": tr.IQ, "date": "2025-01-01"}])
        with tempfile.TemporaryDirectory() as d:
            check_records.write_outputs(d, rep)
            with open(os.path.join(d, "taio_missing.tsv"), encoding="utf-8") as f:
                self.assertEqual(f.read(), f"theme\tkind\tquestion\tdate\nhoiku\t問い\t{tr.IQ}\t2025-01-01\n")
            self.assertFalse(os.path.exists(os.path.join(d, "taio_changed.tsv")))


class ChangedTest(unittest.TestCase):
    def test_taio_changed(self):
        inp = inputs()
        prev = {s: v["text"] for s, v in inp.statements.items()}
        self.assertEqual(rc.taio_changed(expected(), prev, inp), [])
        prev[S(4)] = "定員は285人です。お答えします。"        # 段落の区切りだけが違っても変わったとする
        del prev[S(13)]
        out = rc.taio_changed(expected(), prev, inp)
        self.assertEqual(out, [
            {"question": tr.IQ, "point": P1, "status": "confirmed", "sid": f"sp:{S(4)}", "change": rc.CHANGED_TEXT},
            {"question": tr.SQ, "point": P2, "status": "confirmed", "sid": f"sp:{S(13)}", "change": rc.CHANGED_GONE}])
        rep = run()
        rep.taio_changed, rep.prev_sha, rep.prev_repo = out, "a" * 40, gm.HS
        self.assertIn("- lock を上げるときの比べ方（前の版の hino-council-search aaaaaaa）：範囲の発言が変わった "
                      "本文が変わった 1・前の版に発言が無い 1（行 2。taio_changed.tsv）", check_records.report_lines(rep))

    def test_repo_of_sha(self):
        with tempfile.TemporaryDirectory() as root:
            shas = {}
            for repo in (gm.TD, gm.HS):
                p = os.path.join(root, repo)
                os.makedirs(p)
                env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.invalid",
                           GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.invalid")
                subprocess.run(["git", "-C", p, "init", "-q"], check=True)
                subprocess.run(["git", "-C", p, "commit", "-q", "--allow-empty", "-m", repo], check=True, env=env)
                shas[repo] = subprocess.run(["git", "-C", p, "rev-parse", "HEAD"], check=True,
                                            capture_output=True).stdout.decode().strip()
            self.assertEqual(check_records.repo_of_sha(shas[gm.TD], root), gm.TD)
            self.assertEqual(check_records.repo_of_sha(shas[gm.HS], root), gm.HS)
            for bad in ("0" * 40, "abc"):
                with self.assertRaises(gm.GenError):
                    check_records.repo_of_sha(bad, root)

    def test_lock_with_hs_sha(self):
        lock = {gm.HS: {"sha": "x", "files": ["a"]}, gm.TD: {"sha": "y", "files": ["b"]}}
        out = check_records.lock_with_hs_sha(lock, "z")
        self.assertEqual((out[gm.HS]["sha"], out[gm.TD]["sha"], lock[gm.HS]["sha"]), ("z", "y", "x"))


class ApplyTaioTest(unittest.TestCase):
    KEYS_H = "question\tpoint\n"
    DEC_H = "question\tpoint\tstatus\treviewer\tdate\tnote\n"

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, "taio.tsv")
        rows = [dict(r, status="candidate", reviewer="", date="", note=r["note"].split("。判定：")[0]) for r in expected()]
        with open(self.path, "w", encoding="utf-8", newline="\n") as f:
            f.write(rc.format_tsv(rc.TAIO_COLUMNS, rows))

    def tearDown(self):
        self.tmp.cleanup()

    def read(self):
        with open(self.path, encoding="utf-8") as f:
            return f.read()

    def files(self, keys, decs):
        k, d = os.path.join(self.tmp.name, "k.tsv"), os.path.join(self.tmp.name, "d.tsv")
        with open(k, "w", encoding="utf-8", newline="\n") as f:
            f.write(self.KEYS_H + "".join("\t".join(x) + "\n" for x in keys))
        with open(d, "w", encoding="utf-8", newline="\n") as f:
            f.write(self.DEC_H + "".join("\t".join(x) + "\n" for x in decs))
        return k, d

    def test_apply(self):
        k1, k2 = [tr.IQ, P1], [tr.SQ, P2]
        kp, dp = self.files([k1, k2], [k1 + ["confirmed", "kken78", "2026-11-17", "判定：二者一致・抜き取り（判定シート K9a）"],
                                       k2 + ["rejected", "kken78", "2026-11-17", "事項が違う"]])
        out = io.StringIO()
        applied = ad.write_taio(dp, kp, self.path, out)
        self.assertIn("書き写す前の件数：confirmed 1・rejected 1", out.getvalue())
        self.assertEqual((applied["confirmed"], applied["rejected"]), (1, 1))
        with open(self.path, "rb") as f:
            rows = rc.parse_tsv(f.read(), rc.TAIO_COLUMNS, "taio")
        self.assertTrue(rows[0]["note"].endswith("）。判定：二者一致・抜き取り（判定シート K9a）"))
        self.assertTrue(rows[1]["note"].endswith("。却下：事項が違う"))
        self.assertEqual((rows[0]["status"], rows[0]["reviewer"], rows[0]["date"]), ("confirmed", "kken78", "2026-11-17"))
        self.assertEqual([rc.is_written(r) for r in rows], [True, True])
        # 書き写したあとも、まとめ直しの道具はその行を変えない
        led = tr.ledgers()
        led["yaritori"] = [dict(r, status="candidate", reviewer="", date="") for r in led["yaritori"]]
        led["shitsugi"] = [dict(r, status="candidate", reviewer="", date="") for r in led["shitsugi"]]
        again, c = gen_taio.build(led, rows, inputs(), DATE)
        self.assertEqual((again, c["written"], c["diff"]), (rows, 2, []))

    def test_refused(self):
        k1 = [tr.IQ, P1]
        before = self.read()
        cases = [([k1], [k1 + ["confirmed", "kken78", "2026-11-17", "メモだけ"]], "判定："),
                 ([k1], [[tr.SQ, P2, "confirmed", "k", "2026-11-17", "判定：x"]], "範囲の外"),
                 ([k1, k1], [k1 + ["confirmed", "k", "2026-11-17", "判定：x"]], "2 回ある"),
                 ([[tr.IQ, "無い事項"]], [[tr.IQ, "無い事項", "confirmed", "k", "2026-11-17", "判定：x"]], "行が無い"),
                 ([k1], [k1 + ["confirmed", "k", "2026-11-17", "判定：もとの行の判定（x）"]], "見分けられなくなる")]
        for keys, decs, msg in cases:
            kp, dp = self.files(keys, decs)
            with self.assertRaises(gm.GenError) as cm:
                ad.write_taio(dp, kp, self.path, io.StringIO())
            self.assertIn(msg, str(cm.exception))
            self.assertEqual(self.read(), before)

    def test_main_usage(self):
        self.assertEqual(ad.main(["apply_decisions.py", "--ledger", "taio", "k.tsv"]), 1)


class GenTaioTest(unittest.TestCase):
    def test_parse_args(self):
        self.assertIsNone(gen_taio.parse_args([]))
        self.assertEqual(gen_taio.parse_args(["--date", DATE]), DATE)
        for bad in (["--date"], ["--date", "2026-13-01"], ["--date", "20261116"], ["-d", DATE]):
            with self.assertRaises(gm.GenError):
                gen_taio.parse_args(bad)

    def test_decide_date(self):
        self.assertEqual(gen_taio.decide_date(DATE, []), DATE)
        self.assertEqual(gen_taio.decide_date(None, expected()), DATE)
        with self.assertRaises(gm.GenError):
            gen_taio.decide_date(None, [])
        with self.assertRaises(gm.GenError):
            gen_taio.decide_date(None, replace(expected(), 1, note=expected()[1]["note"].replace(DATE, "2026-11-17")))

    def test_build(self):
        rows, c = gen_taio.build(tr.ledgers(), [], inputs(), DATE)
        self.assertEqual((rows, c["made"], c["added"]), (expected(), 2, 2))
        led = tr.ledgers()
        led["yaritori"] = replace(led["yaritori"], 1, quote="本文に無い字")
        with self.assertRaises(gm.GenError) as cm:
            gen_taio.build(led, [], inputs(), DATE)
        self.assertIn("1 件", str(cm.exception))
        with self.assertRaises(gm.GenError) as cm:
            gen_taio.build(tr.ledgers(), [dict(expected()[0], note="下書き：x")], inputs(), DATE)
        self.assertIn("台帳に入れられない", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
