"""tools/records.py・tools/check_records.py の検査（LINK_SCHEMA.md §1・§11・§12・§15、DESIGN.md ADR-24）。

実行: python3 -B tools/test_records.py -v
見本の小さな入力（発言・場面・議会だより・資料のページ・計画）と、§15 の形に合う見本の台帳を作り、
検査ごとに、通る場合と止まる・一覧に出る場合を確かめる。
"""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import check_records  # noqa: E402
import records as rc  # noqa: E402

M = "0000000001"


def sid(n):
    return f"{M}_20250101_{n:04d}"


# 見本の発言。議長の進行（奇数）をはさみ、一般質問（0002〜0012）と議案の質疑（0013〜0015）の場面にする
TEXTS = {
    1: ("議長", "松田議員。"),
    2: ("議員", "新こども園の定員を伺います。前置きです。"),
    3: ("議長", "子ども支援課長。"),
    4: ("子ども支援課長", "定員は285人です。お答えします。"),
    5: ("議長", "松田議員。"),
    6: ("議員", "面積はどうか。要望します。"),
    7: ("議長", "子ども支援課長。"),
    8: ("子ども支援課長", "約3,000平方メートルです。"),
    9: ("議長", "松田議員。"),
    10: ("議員", "締めくくりに要望します。次に用地を伺います。"),
    11: ("議長", "町長。"),
    12: ("町長", "用地は選定中です。"),
    13: ("議員", "予算について。こども園の土地はどうか。道路はどうか。"),
    14: ("議長", "総務課長。"),
    15: ("総務課長", "土地は買います。道路は直します。"),
}
IPPAN = {"kind": "ippan", "from": sid(2), "to": sid(12), "member": "松田 洋子", "meetingId": M,
         "turns": [[0, "q", 1], [2, "a", 1], [4, "rq", 1], [6, "a", 1], [8, "q", 2], [10, "a", 2]]}
SHITSUGI = {"kind": "shitsugi", "from": sid(13), "to": sid(15), "member": "山本秀喜", "meetingId": M,
            "bills": ["議第1号"], "turns": [[0, "q", 1], [2, "a", 1]]}
DOCS = {("teigen", "text"): "一頁目の文。\f二頁目に再編の方針がある。"}
PTS = {("youho", "honpen", "text"): "計画期間は令和6年からです。"}
IQ = f"iq:{sid(2)}"
SQ = f"sq:{sid(13)}"
OK = {"status": "confirmed", "reviewer": "kken78", "date": "2026-10-27", "note": "下書き：見本"}


def inputs():
    return rc.Inputs(
        statements={sid(n): {"text": t, "role": r, "meetingId": M} for n, (r, t) in TEXTS.items()},
        order=[sid(n) for n in sorted(TEXTS)],
        segments={sid(2): IPPAN, sid(13): SHITSUGI},
        gian={M: {"議第1号"}},
        bulletin={"bq:30/松田洋子/1": ["新こども園の定員は", "定員を伺う"]},
        docs={"teigen"},
        doc_text=lambda did, layer: DOCS.get((did, layer)),
        pt_text=lambda pid, name, layer: PTS.get((pid, name, layer)),
        plans={"youho", "jisshi"},
        nodes={"node:jisshi/e008"},
        series={"youho"})


def theme_rows():
    rows = [("名前", "幼児教育・保育施設の再編", ""), ("系列", "youho", ""), ("事業", "node:jisshi/e008", ""),
            ("議案", f"gi:{M}/議第1号", ""), ("語", "こども園", ""), ("除外の語", "学童保育", ""),
            ("問い", IQ, "令和7年 2025-01-01 4番 松田洋子 問1「新こども園」"),
            ("質疑", SQ, "令和7年 2025-01-01 8番 山本秀喜 議第1号 新こども園の用地"),
            ("資料", "doc:teigen", ""), ("事柄", "新こども園の定員", ""), ("事柄", "新こども園の用地", ""),
            ("記載", "再編の方針", ""), ("記載", "提言", ""), ("施設", "fa:a", "")]
    out = [{"theme": "hoiku", "kind": k, "value": v, "source": s or "見本", "reviewer": "kken78",
            "date": "2026-10-27", "note": ""} for k, v, s in rows]
    return sorted(out, key=lambda r: (r["theme"], r["kind"], r["value"]))


def shisetsu_ref():
    return [{"key": "fa:a", "name": "見本園", "aliases": "", "district": "日野", "source": "見本",
             "reviewer": "kken78", "date": "2026-10-27", "note": ""}]


def row(ledger, **kw):
    r = {c: "" for c in rc.COLUMNS[ledger]}
    r.update(OK)
    r.update(kw)
    return r


def ledgers():
    y = [
        row("yaritori", question=IQ, n="1", row="1", side="問い", sid=f"sp:{sid(2)}", quote="新こども園の定員を伺います。",
            speaker="議員", round="最初の問い", stage="結果", kind="数字・見込み", point="新こども園の定員",
            bq="bq:30/松田洋子/1", bulletin="載っている"),
        row("yaritori", question=IQ, n="1", row="2", side="答え", sid=f"sp:{sid(4)}", quote="定員は285人です。",
            speaker="子ども支援課長", round="最初の問い", kind="事実・数字", answers="1", point="新こども園の定員",
            bulletin="載っている"),
        row("yaritori", question=IQ, n="1", row="3", side="問い", sid=f"sp:{sid(6)}", quote="面積はどうか。",
            speaker="議員", round="再質問1", stage="結果", kind="事実の確認", point="新こども園の定員",
            bulletin="載っていない"),
        row("yaritori", question=IQ, n="1", row="4", side="答え", sid=f"sp:{sid(8)}", quote="約3,000平方メートルです。",
            speaker="子ども支援課長", round="再質問1", kind="事実・数字", answers="3", point="新こども園の定員",
            bulletin="載っていない"),
    ]
    s = [row("shitsugi", question=SQ, n="1", row="1", bills=f"gi:{M}/議第1号", side="問い", sid=f"sp:{sid(13)}",
             quote="こども園の土地はどうか。", speaker="議員", round="最初の問い", stage="投入", kind="事実の確認",
             point="新こども園の用地")]
    k = [row("kotogara", theme="hoiku", point="新こども園の定員", program="node:jisshi/e008", source=f"sp:{sid(4)}",
             source_date="2025-01-01", quote="定員は285人です。", kind="いまのこと", yaritori=f"{IQ}/2")]
    t = [row("tsunagari", theme="hoiku", link="もとにした", upper="提言", upper_ref="doc:teigen/1", lower="再編の方針",
             lower_ref="plan:youho", source="doc:teigen/2", source_date="2024-02", quote="再編の方針がある")]
    p = [row("katei", theme="hoiku", step="1", name="懇話会", **{"from": "2022-07", "to": "2024-01"},
             sources="doc:teigen/1", quote="一頁目の文")]
    ki = [row("kisai", theme="hoiku", title="計画期間", source="pt:youho/honpen/1", source_date="2025-03",
              quote="計画期間は令和6年からです。")]
    sh = [row("shisetsu", facility="fa:a", aspect="役割", value="指定避難所", source="doc:teigen/1",
              source_date="2018-04", quote="一頁目の文。", kind="いまのこと")]
    return {"yaritori": y, "shitsugi": s, "kotogara": k, "tsunagari": t, "katei": p, "kisai": ki, "shisetsu": sh}


def run(led=None, themes=None, ref=None, inp=None):
    return rc.check_all(led if led is not None else ledgers(), themes if themes is not None else theme_rows(),
                        ref if ref is not None else shisetsu_ref(), inp or inputs())


class RecordsTestCase(unittest.TestCase):
    def assertErr(self, rep, text):
        self.assertTrue(any(text in e for e in rep.errors), f"「{text}」の誤りが無い：{rep.errors}")


class BaseTest(RecordsTestCase):
    def test_baseline_passes(self):
        rep = run()
        self.assertEqual(rep.errors, [])
        self.assertEqual(rep.counts["yaritori"], 4)
        self.assertEqual(rep.counts["nozoki"], 0)   # 記録しない文の台帳が無ければ0行（LINK_SCHEMA §11）
        self.assertEqual(rep.round_diff, [])
        self.assertEqual(rep.quote_mismatch, [])

    def test_inputs_qturns(self):
        inp = inputs()
        self.assertEqual(inp.segment_of(f"iq:{sid(2)}"), IPPAN)
        self.assertEqual(inp.segment_of(f"iq:{sid(10)}"), IPPAN)   # 問2 の q の最初の発言も iq（§2）
        self.assertIsNone(inp.segment_of(f"iq:{sid(4)}"))           # 答えの発言は iq でない
        self.assertEqual(inp.segment_of(SQ), SHITSUGI)
        self.assertIsNone(inp.segment_of(f"sq:{sid(2)}"))


class FormTest(RecordsTestCase):
    COLS = ["a", "b"]

    def test_parse_ok(self):
        self.assertEqual(rc.parse_tsv("a\tb\n1\t2\n".encode(), self.COLS, "x"), [{"a": "1", "b": "2"}])

    def test_parse_errors(self):
        for data, msg in ((b"\xef\xbb\xbfa\tb\n", "BOM"), (b"a\tb\r\n", "LF"), (b"a\tb\n1\t2", "改行で終わって"),
                          (b"a\tc\n", "ヘッダ"), (b"a\tb\n1\n", "列の数"), (b"a\tb\n\xff\t1\n", "UTF-8")):
            with self.subTest(msg=msg), self.assertRaises(rc.RecordsError) as cm:
                rc.parse_tsv(data, self.COLS, "x")
            self.assertIn(msg, str(cm.exception))

    def test_row_numeric_order(self):
        led = ledgers()
        base = led["yaritori"][3]
        led["yaritori"] += [dict(base, row=str(n), answers="3") for n in range(5, 12)]   # 9 の後に 10・11
        rep = run(led)
        self.assertFalse([e for e in rep.errors if "キーの順" in e], rep.errors)
        led["yaritori"][-1], led["yaritori"][-2] = led["yaritori"][-2], led["yaritori"][-1]
        self.assertErr(run(led), "キーの順でない")

    def test_char_order_and_duplicate(self):
        led = ledgers()
        led["kisai"].append(dict(led["kisai"][0], title="あ"))   # 「計画期間」より前の字が後ろにある
        self.assertErr(run(led), "キーの順でない")
        led = ledgers()
        led["kisai"].append(dict(led["kisai"][0]))
        self.assertErr(run(led), "行のキーが重なっている")


class CommonTest(RecordsTestCase):
    def test_status_columns(self):
        cases = [(dict(status="candidate"), "candidate に reviewer"),
                 (dict(status="confirmed", date=""), "reviewer か date"),
                 (dict(status="rejected", note=""), "rejected の note が空"),
                 (dict(note="見本"), "下書き："),
                 (dict(status="ok"), "status が")]
        for kw, msg in cases:
            with self.subTest(msg=msg):
                led = ledgers()
                led["kisai"][0].update(kw)
                self.assertErr(run(led), msg)


class QuoteTest(RecordsTestCase):
    def test_mismatch_confirmed_stops(self):
        led = ledgers()
        led["kisai"][0]["quote"] = "計画期間は令和7年からです。"
        rep = run(led)
        self.assertErr(rep, "confirmed の引用が資料の本文に無い")
        self.assertEqual([r["ledger"] for r in rep.quote_mismatch], ["kisai"])

    def test_mismatch_candidate_listed_only(self):
        led = ledgers()
        led["kisai"][0].update(quote="計画期間は令和7年からです。", status="candidate", reviewer="", date="")
        rep = run(led)
        self.assertEqual(rep.errors, [])
        self.assertEqual(len(rep.quote_mismatch), 1)

    def test_normalized_match_and_length(self):
        led = ledgers()
        led["kotogara"][0]["quote"] = "定員は２８５人です。"   # 全角の数字も §4 の正規化で一致する
        self.assertEqual(run(led).errors, [])
        led["kisai"][0]["quote"] = "計" * 201
        self.assertErr(run(led), "200字を超える")

    def test_source_kinds(self):
        led = ledgers()
        led["kisai"][0]["source"] = f"gi:{M}/議第1号"
        self.assertErr(run(led), "source が gi の行は")
        led = ledgers()
        led["kisai"][0]["source"] = "doc:nai/1"
        self.assertErr(run(led), "資料が入力に無い")
        led = ledgers()
        led["kisai"][0]["source_date"] = "2025/03"
        self.assertErr(run(led), "source_date")


class ExchangeTest(RecordsTestCase):
    def test_round_diff_listed_not_error(self):
        led = ledgers()
        led["yaritori"][2]["round"] = "最初の問い"   # turns では再質問1
        rep = run(led)
        self.assertEqual(rep.errors, [])
        self.assertEqual([(r["row"], r["round"], r["turns_round"]) for r in rep.round_diff],
                         [("3", "最初の問い", "再質問1")])

    def test_values(self):
        cases = [(1, dict(answers="9"), "answers の 9"),
                 (1, dict(answers=""), "answers が無い"),
                 (0, dict(stage=""), "stage が"),
                 (0, dict(kind="事実・数字"), "問いの行の kind"),
                 (1, dict(kind="要望"), "答えの行の kind"),
                 (0, dict(round="再質問"), "round が"),
                 (0, dict(point="知らない点"), "point が"),
                 (0, dict(bq="bq:99/松田洋子/1"), "bq が議会だよりに無い"),
                 (1, dict(bq="bq:30/松田洋子/1"), "答えの行に bq"),
                 (0, dict(bulletin="載った"), "bulletin が"),
                 (0, dict(sid=f"sp:{sid(13)}"), "sid が、この問いの場面の発言でない"),
                 (0, dict(n="0"), "n か row が"),
                 (0, dict(speaker="町長"), "speaker が「議員」でない")]
        for i, kw, msg in cases:
            with self.subTest(msg=msg):
                led = ledgers()
                led["yaritori"][i].update(kw)
                self.assertErr(run(led), msg)

    def test_empty_point_allowed(self):
        led = ledgers()
        led["yaritori"][2]["point"] = ""   # 当たる名前が無ければ空（§15.2）
        self.assertEqual(run(led).errors, [])

    def test_question_not_in_theme(self):
        themes = [r for r in theme_rows() if r["kind"] != "問い"]
        self.assertErr(run(themes=themes), "テーマの定義の kind 問い に無い")

    def test_shitsugi_bills(self):
        led = ledgers()
        led["shitsugi"][0]["bills"] = f"gi:{M}/議第2号"
        self.assertErr(run(led), "bills が審議の記録")


class ThemeTest(RecordsTestCase):
    def edit(self, kind, **kw):
        rows = theme_rows()
        for r in rows:
            if r["kind"] == kind:
                r.update(kw)
                break
        return sorted(rows, key=lambda r: (r["theme"], r["kind"], r["value"]))

    def test_values(self):
        cases = [("問い", dict(value=f"iq:{sid(4)}"), "value が kind の形に合わない"),
                 ("問い", dict(source="2025-01-01 4番 中西佳子 問1"), "議員の名前"),
                 ("質疑", dict(source="山本"), "議員の名前"),
                 ("系列", dict(value="nai"), "value が"),
                 ("事業", dict(value="node:jisshi/e999"), "value が"),
                 ("議案", dict(value=f"gi:{M}/議第9号"), "value が"),
                 ("資料", dict(value="doc:teigen/1"), "value が"),
                 ("施設", dict(value="fa:b"), "value が"),
                 ("語", dict(value="こども 園"), "value が"),
                 ("記載", dict(reviewer=""), "reviewer か date")]
        for kind, kw, msg in cases:
            with self.subTest(kind=kind, msg=msg):
                self.assertErr(run(themes=self.edit(kind, **kw)), msg)

    def test_q2_turn_is_iq(self):
        rows = self.edit("問い", value=f"iq:{sid(10)}")
        rep = run(led={**ledgers(), "yaritori": []}, themes=rows)
        self.assertFalse([e for e in rep.errors if "ref/themes.tsv" in e], rep.errors)

    def test_kind_and_name(self):
        rows = theme_rows() + [dict(theme_rows()[0], kind="名前", value="別の名前")]
        rows.sort(key=lambda r: (r["theme"], r["kind"], r["value"]))
        self.assertErr(run(themes=rows), "名前 の行が1行でない")
        rows = theme_rows() + [dict(theme_rows()[0], kind="地区", value="日野")]
        rows.sort(key=lambda r: (r["theme"], r["kind"], r["value"]))
        self.assertErr(run(themes=rows), "kind が §12 の13")

    def test_shisetsu_ref(self):
        self.assertErr(run(ref=[dict(shisetsu_ref()[0], key="fa:A")]), "fa の形でない")


class OtherLedgersTest(RecordsTestCase):
    def test_kotogara(self):
        led = ledgers()
        led["kotogara"][0]["prev"] = "250人"
        self.assertErr(run(led), "変更でない行に prev")
        led = ledgers()
        led["kotogara"][0]["yaritori"] = f"{IQ}/9"
        self.assertErr(run(led), "yaritori の参照")
        led = ledgers()
        led["kotogara"].append(dict(led["kotogara"][0], source=f"sp:{sid(4)}", quote="お答えします。",
                                    program="node:jisshi/e009"))
        led["kotogara"].sort(key=lambda r: rc.sort_key(r, rc.KEYS["kotogara"]))
        rep = run(led)
        self.assertErr(rep, "program が計画の事業に無い")
        self.assertErr(rep, "program が違う")

    def test_tsunagari(self):
        led = ledgers()
        led["tsunagari"][0]["upper"] = "知らない記載"
        self.assertErr(run(led), "upper がそのテーマの kind 記載")
        led = ledgers()
        led["tsunagari"][0]["lower_ref"] = "plan:nai/hoshin/bullets/3/1"
        self.assertErr(run(led), "lower_ref が入力に無い")
        led = ledgers()
        led["tsunagari"][0]["lower_ref"] = "plan:youho/hoshin/bullets/3/1"
        self.assertEqual(run(led).errors, [])

    def test_katei(self):
        led = ledgers()
        led["katei"].append(dict(led["katei"][0], step="3"))
        self.assertErr(run(led), "step が1からの続いた番号でない")
        led = ledgers()
        led["katei"][0]["sources"] = "doc:teigen/1,doc:nai/1"
        self.assertErr(run(led), "sources の資料が入力に無い")

    def test_kisai_about(self):
        led = ledgers()
        led["kisai"][0]["about"] = "提言"
        self.assertEqual(run(led).errors, [])
        led["kisai"][0]["about"] = "知らない"
        self.assertErr(run(led), "about が")

    def test_shisetsu(self):
        led = ledgers()
        led["shisetsu"][0]["facility"] = "fa:b"
        self.assertErr(run(led), "ref/shisetsu.tsv に無い")
        ref = shisetsu_ref() + [dict(shisetsu_ref()[0], key="fa:b")]
        self.assertErr(run(led, ref=ref), "kind 施設に無い")
        led = ledgers()
        led["shisetsu"][0]["aspect"] = "面積"
        self.assertErr(run(led), "aspect が")


class TorikoboshiTest(RecordsTestCase):
    def quotes(self, rep, ledger="yaritori"):
        return [r["quote"] for r in rep.torikoboshi if r["ledger"] == ledger]

    def test_range_and_closing(self):
        # 最後の行が答え（0008）なので、次の議員の発言（0010。締めくくりと次の問い）も見る
        self.assertEqual(self.quotes(run()),
                         ["前置きです。", "お答えします。", "要望します。", "締めくくりに要望します。", "次に用地を伺います。"])

    def test_last_row_member(self):
        led = ledgers()
        del led["yaritori"][3]
        self.assertEqual(self.quotes(run(led)), ["前置きです。", "お答えします。", "要望します。"])

    def test_nozoki_removes(self):
        led = ledgers()
        led["nozoki"] = [row("nozoki", question=IQ, n="1", sid=f"sp:{sid(2)}", quote="前置きです。", reason="前置き")]
        rep = run(led)
        self.assertEqual(rep.errors, [])
        self.assertNotIn("前置きです。", self.quotes(rep))

    def test_nozoki_checks(self):
        led = ledgers()
        led["nozoki"] = [row("nozoki", question=IQ, n="2", sid=f"sp:{sid(2)}", quote="前置きです。", reason="前置き")]
        self.assertErr(run(led), "question と n")
        led["nozoki"] = [row("nozoki", question=IQ, n="1", sid=f"sp:{sid(2)}", quote="無い文。", reason="前置き")]
        self.assertErr(run(led), "confirmed の引用")
        led["nozoki"] = [row("nozoki", question=IQ, n="1", sid=f"sp:{sid(2)}", quote="前置きです。")]
        self.assertErr(run(led), "reason が空")

    def test_shitsugi_theme_words_only(self):
        self.assertEqual(self.quotes(run(), "shitsugi"), [])
        led = ledgers()
        led["shitsugi"][0]["quote"] = "道路はどうか。"
        led["shitsugi"][0]["point"] = ""
        self.assertEqual(self.quotes(run(led), "shitsugi"), ["こども園の土地はどうか。"])

    def test_rejected_rows_do_not_cover(self):
        led = ledgers()
        led["yaritori"][2].update(status="rejected", note="下書き：見本。記録しない")
        self.assertIn("面積はどうか。", self.quotes(run(led)))


class QuoteContextTest(RecordsTestCase):
    def test_baseline_and_mid_sentence(self):
        # 見本の引用は、どれも文の終わりで終わるか、本文で「。」の直前で終わる（つながりの記録の「再編の方針がある」）
        self.assertEqual(run().quote_context, [])
        led = ledgers()
        led["kisai"][0]["quote"] = "計画期間は令和6年から"
        rep = run(led)
        self.assertEqual([(r["ledger"], r["kind"]) for r in rep.quote_context], [("kisai", "文の途中で終わる")])

    def test_demonstrative(self):
        inp = inputs()
        inp.statements[sid(4)]["text"] = "その定員は285人です。"
        led = ledgers()
        led["yaritori"][1]["quote"] = "その定員は285人です。"
        led["kotogara"][0]["quote"] = "その定員は285人です。"
        rep = run(led, inp=inp)
        self.assertEqual(sorted(r["ledger"] for r in rep.quote_context if r["kind"] == "指示語で始まる"),
                         ["kotogara", "yaritori"])


class CheckRecordsTest(unittest.TestCase):
    def test_bulletin_texts(self):
        q = {"issue": "30", "member": "松田 洋子", "q_num": "1", "title": "題", "question_text": "問い",
             "answer_title": "答えの題", "answers": [{"label": "町長", "text": "答え"}]}
        self.assertEqual(check_records.bulletin_texts([q]), {"bq:30/松田洋子/1": ["題", "問い", "答えの題", "答え"]})

    def test_format_tsv(self):
        self.assertEqual(rc.format_tsv(["a", "b"], [{"a": "x\ty", "b": 1}]), "a\tb\nx y\t1\n")

    def test_report_lines(self):
        rep = run()
        lines = check_records.report_lines(rep)
        self.assertIn("- 誤り：0", lines)


if __name__ == "__main__":
    unittest.main()
