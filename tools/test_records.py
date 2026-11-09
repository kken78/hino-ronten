"""tools/records.py・tools/check_records.py の検査（LINK_SCHEMA.md §1・§11・§12・§12.1・§15、DESIGN.md ADR-24・ADR-31・ADR-32）。

実行: python3 -B tools/test_records.py -v
見本の小さな入力（発言・場面・議会だより・資料のページ・計画）と、§15 の形に合う見本の台帳を作り、
検査ごとに、通る場合と止まる・一覧に出る場合を確かめる。
"""
import os
import sys
import tempfile
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
DOCS = {("teigen", "text"): "一頁目の文。\f二頁目に再編の方針がある。",
        # 定例記者会見の次第（PDF）と掲載ページ（html）。掲載ページは書かない資料（§2・§11）
        ("kaiken-20250630-shidai", "text"): "令和7年6月定例記者会見次第",
        ("kaiken-20250630-page", "text"): "令和7(2025)年6月30日定例記者会見"}
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
        docs={"teigen", "kaiken-20250630-shidai", "kaiken-20250630-page"},
        doc_text=lambda did, layer: DOCS.get((did, layer)),
        pt_text=lambda pid, name, layer: PTS.get((pid, name, layer)),
        plans={"youho", "jisshi"},
        nodes={"node:jisshi/e008", "node:jisshi/e009", "node:sogo6/e047"},
        series={"youho"},
        plans_in_lineage={"youho"})


P = "node:jisshi/e008"   # 見本の中心の見方（計画の事業）
# 見本の views（§12）と、kind 名前の行の note（中心の見方）
VIEWS = {("事柄", "新こども園の定員"): P, ("事柄", "新こども園の用地"): P}
NOTES = {"名前": f"中心の見方：{P}。見本"}


def theme_rows():
    rows = [("名前", "幼児教育・保育施設の再編", ""), ("系列", "youho", ""), ("事業", "node:jisshi/e008", ""),
            ("議案", f"gi:{M}/議第1号", ""), ("語", "こども園", ""), ("除外の語", "学童保育", ""),
            ("問い", IQ, "令和7年 2025-01-01 4番 松田洋子 問1「新こども園」"),
            ("質疑", SQ, "令和7年 2025-01-01 8番 山本秀喜 議第1号 新こども園の用地"),
            ("資料", "doc:teigen", ""), ("事柄", "新こども園の定員", ""), ("事柄", "新こども園の用地", ""),
            ("記載", "再編の方針", ""), ("記載", "提言", ""), ("施設", "fa:a", "")]
    out = [{"theme": "hoiku", "kind": k, "value": v, "source": s or "見本", "views": VIEWS.get((k, v), ""),
            "reviewer": "kken78", "date": "2026-10-27", "note": NOTES.get(k, "")} for k, v, s in rows]
    return sorted(out, key=lambda r: (r["theme"], r["kind"], r["value"]))


def shisetsu_ref():
    return [{"key": "fa:a", "name": "見本園", "aliases": "", "district": "日野", "source": "見本",
             "reviewer": "kken78", "date": "2026-10-27", "note": ""}]


# 見本の地区・組織の参照表（§12.1。ADR-32）
DIST = "dist:hino"
ORG = "org:kucho-kai"


def chiku_ref():
    return [{"key": DIST, "name": "日野", "aliases": "", "source": "見本", "reviewer": "kken78", "date": "2026-11-05",
             "note": ""},
            {"key": "dist:hisa", "name": "必佐", "aliases": "", "source": "見本", "reviewer": "kken78", "date": "2026-11-05",
             "note": ""}]


def soshiki_ref():
    return [{"key": ORG, "name": "日野町区長会", "aliases": "区長会", "source": "見本", "reviewer": "kken78",
             "date": "2026-11-05", "note": ""}]


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
    k = [row("kotogara", point="新こども園の定員", source=f"sp:{sid(4)}",
             source_date="2025-01-01", quote="定員は285人です。", kind="いまのこと", yaritori=f"{IQ}/2")]
    t = [row("tsunagari", link="もとにした", upper="提言", upper_ref="doc:teigen/1", lower="再編の方針",
             lower_ref="plan:youho", source="doc:teigen/2", source_date="2024-02", quote="再編の方針がある")]
    p = [row("katei", theme="hoiku", step="1", name="懇話会", **{"from": "2022-07", "to": "2024-01"},
             sources="doc:teigen/1", quote="一頁目の文")]
    ki = [row("kisai", title="計画期間", source="pt:youho/honpen/1", source_date="2025-03",
              quote="計画期間は令和6年からです。")]
    sh = [row("shisetsu", facility="fa:a", aspect="役割", value="指定避難所", source="doc:teigen/1",
              source_date="2018-04", quote="一頁目の文。", kind="いまのこと")]
    return {"yaritori": y, "shitsugi": s, "kotogara": k, "tsunagari": t, "katei": p, "kisai": ki, "shisetsu": sh}


def run(led=None, themes=None, ref=None, inp=None, chiku=None, soshiki=None):
    return rc.check_all(led if led is not None else ledgers(), themes if themes is not None else theme_rows(),
                        ref if ref is not None else shisetsu_ref(), inp or inputs(),
                        chiku if chiku is not None else chiku_ref(), soshiki if soshiki is not None else soshiki_ref())


def with_area(rows, **views):
    """テーマの定義に kind 地区（dist:hino）と組織（org:kucho-kai）の行を足す。views は「地区」「組織」→ views の列。"""
    base = rows[0]
    rows = rows + [dict(base, kind="地区", value=DIST, views=views.get("地区", ""), note=""),
                   dict(base, kind="組織", value=ORG, views=views.get("組織", ""), note="")]
    return sorted(rows, key=lambda r: (r["theme"], r["kind"], r["value"]))


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


    def test_hantei_after_20261104(self):
        # date が 2026-11-04 より後の confirmed は、note に「判定：」の出どころが要る（§15.1）
        led = ledgers()
        led["kisai"][0]["date"] = "2026-11-05"
        self.assertErr(run(led), "「判定：」の出どころが無い")
        led["kisai"][0]["note"] = "下書き：2026-11-05・Opus 5.5（プロンプトの版なし）。判定：行ごと（判定シート K5）"
        self.assertEqual(run(led).errors, [])
        led = ledgers()
        led["kisai"][0]["date"] = "2026-11-04"   # 2026-11-04 以前は止めない
        self.assertEqual(run(led).errors, [])
        led["kisai"][0].update(date="2026-11-05", status="rejected", note="下書き：見本。記録しない")
        self.assertEqual(run(led).errors, [])   # rejected は見ない


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
        rows = theme_rows() + [dict(theme_rows()[0], kind="会計", value="一般会計")]
        rows.sort(key=lambda r: (r["theme"], r["kind"], r["value"]))
        self.assertErr(run(themes=rows), "kind が §12 の15")

    def test_shisetsu_ref(self):
        self.assertErr(run(ref=[dict(shisetsu_ref()[0], key="fa:A")]), "fa の形でない")

    def test_shisetsu_district(self):
        # district は、空か、地区の参照表の name のどれか（§11 施設の参照表・§12.1）
        self.assertFalse(run().errors)
        self.assertFalse(run(ref=[dict(shisetsu_ref()[0], district="")]).errors)
        self.assertErr(run(ref=[dict(shisetsu_ref()[0], district="東京")]), "district が地区の参照表（ref/chiku.tsv）の name に無い")
        self.assertErr(run(ref=[dict(shisetsu_ref()[0], district="hino")]), "district が地区の参照表")   # key ではなく name
        # 地区の参照表が無いか0行なら、この検査は飛ばす
        self.assertFalse(run(ref=[dict(shisetsu_ref()[0], district="東京")], chiku=[]).errors)

    def test_area_ref_ok(self):
        rep = run()
        self.assertFalse(rep.errors)
        self.assertEqual(rep.ref_counts, {"shisetsu": 1, "chiku": 2, "soshiki": 1})
        rep = run(chiku=[], soshiki=[])     # ファイルが無い（0行）ときも止めない
        self.assertFalse(rep.errors)
        self.assertEqual(rep.ref_counts, {"shisetsu": 1, "chiku": 0, "soshiki": 0})

    def test_area_ref_errors(self):
        c, o = chiku_ref(), soshiki_ref()
        cases = [(dict(chiku=list(reversed(c))), "ref/chiku.tsv：3行目：行がキーの順でない"),
                 (dict(chiku=c + [dict(c[1])]), "ref/chiku.tsv：行のキーが重なっている"),
                 (dict(chiku=[c[0], dict(c[1], key="org:hisa")]), "ref/chiku.tsv org:hisa：key が §2 の dist の形でない"),
                 (dict(chiku=[c[0], dict(c[1], key="dist:hisa_")]), "key が §2 の dist の形でない"),
                 (dict(soshiki=[dict(o[0], key="dist:kucho-kai")]), "ref/soshiki.tsv dist:kucho-kai：key が §2 の org の形でない"),
                 (dict(soshiki=[dict(o[0], reviewer="")]), "ref/soshiki.tsv org:kucho-kai：reviewer か date"),
                 (dict(chiku=[c[0], dict(c[1], date="2026/11/05")]), "ref/chiku.tsv dist:hisa：reviewer か date")]
        for kw, msg in cases:
            with self.subTest(msg=msg):
                self.assertErr(run(**kw), msg)

    def test_kind_area(self):
        # kind 地区・組織の value は dist・org のキーで、参照表にある（§11・§12）
        rep = run(themes=with_area(theme_rows()))
        self.assertFalse(rep.errors)
        rows = with_area(theme_rows())
        for r in rows:
            if r["kind"] == "地区":
                r["value"] = "日野"           # 名前ではなく dist キー
        self.assertErr(run(themes=rows), "hoiku/地区/日野：value が kind の形に合わないか")
        self.assertErr(run(themes=with_area(theme_rows()), chiku=[]), "hoiku/地区/dist:hino：value が kind の形に合わないか")
        self.assertErr(run(themes=with_area(theme_rows()), soshiki=[]), "hoiku/組織/org:kucho-kai：value が kind の形に合わないか")
        rows = with_area(theme_rows())
        for r in rows:
            if r["kind"] == "組織":
                r["value"] = DIST             # 組織の行に地区のキー
        self.assertErr(run(themes=rows), f"hoiku/組織/{DIST}：value が kind の形に合わないか")

    def test_views_area(self):
        # views に dist・org のキーを書ける。kind 地区・組織の行も views を持てる（§12）
        rep = run(themes=self.views("事柄", f"{P},{DIST},{ORG}"))
        self.assertFalse(rep.errors)
        rep = run(themes=with_area(theme_rows(), 地区=f"{P},{ORG}", 組織=f"plan:youho,{DIST}"))
        self.assertFalse(rep.errors)
        th = rc.check_themes(with_area(theme_rows(), 地区=P), inputs(), {"fa:a"}, rc.Report(), {DIST}, {ORG})
        self.assertEqual(th.views_of("地区", DIST), {P})
        self.assertErr(run(themes=with_area(theme_rows(), 組織="dist:nai")), "views のキーが入力に無い（dist:nai")
        self.assertErr(run(themes=self.views("事柄", DIST), chiku=[]), f"views のキーが入力に無い（{DIST}")

    def views(self, kind, views, value=None):
        rows = theme_rows()
        for r in rows:
            if r["kind"] == kind and (value is None or r["value"] == value):
                r["views"] = views
                break
        return rows

    def test_views_ok(self):
        for kind in ("事柄", "記載", "施設"):
            with self.subTest(kind=kind):
                rep = run(themes=self.views(kind, f"{P},plan:youho,fa:a"))
                self.assertFalse([e for e in rep.errors if "ref/themes.tsv" in e], rep.errors)

    def test_views_errors(self):
        cases = [("事業", P, "views を持てるのは"),
                 ("名前", P, "views を持てるのは"),
                 ("事柄", f"{P},", "空の要素"),
                 ("事柄", f"{P},,fa:a", "空の要素"),
                 ("事柄", f"{P},{P}", "同じキーが重なっている"),
                 ("事柄", f"{P},hoiku", "テーマの id"),
                 ("事柄", "node:jisshi/e999", "views のキーが入力に無い"),
                 ("事柄", "plan:nai", "views のキーが入力に無い"),
                 ("事柄", "plan:jisshi", "views のキーが入力に無い"),   # manifest にあっても系譜表に無い
                 ("事柄", "fa:b", "views のキーが入力に無い"),
                 ("事柄", "dist:nai", "views のキーが入力に無い"),
                 ("事柄", "org:nai", "views のキーが入力に無い"),
                 ("事柄", "lin:youho/1", "見方のキー（node・plan・fa・dist・org）の形でない"),
                 ("事柄", "kaigo", "見方のキー（node・plan・fa・dist・org）の形でない")]
        for kind, views, msg in cases:
            with self.subTest(kind=kind, views=views):
                self.assertErr(run(themes=self.views(kind, views)), msg)

    def test_views_shisaku(self):
        def rows_with(views):
            rows = theme_rows() + [dict(theme_rows()[0], kind="施策", value="node:sogo6/e047", views=views)]
            return sorted(rows, key=lambda r: (r["theme"], r["kind"], r["value"]))
        rep = run(themes=rows_with(P))
        self.assertFalse([e for e in rep.errors if "ref/themes.tsv" in e], rep.errors)
        # node:jisshi/e009 は計画の事業にあるが、テーマの kind 事業に無い
        self.assertErr(run(themes=rows_with("node:jisshi/e009")), "施策の行の views が、同じテーマの kind 事業の行に無い")
        self.assertErr(run(themes=rows_with("fa:a")), "施策の行の views が node キーでない")

    def test_views_shisaku_same_program(self):
        # 同じテーマで、同じ事業を views に持つ施策の行が2行あれば誤り（§11）。2行目に出す
        def rows_with(views2):
            base = theme_rows()
            rows = base + [dict(base[0], kind="事業", value="node:jisshi/e009", views=""),
                           dict(base[0], kind="施策", value="node:sogo6/e047", views=P),
                           dict(base[0], kind="施策", value="node:jisshi/e009", views=views2)]
            return sorted(rows, key=lambda r: (r["theme"], r["kind"], r["value"]))
        rep = run(themes=rows_with(P))
        errs = [e for e in rep.errors if "施策の行の views に同じ事業がある" in e]
        self.assertEqual(len(errs), 1, rep.errors)
        self.assertIn("hoiku/施策/node:sogo6/e047", errs[0])     # 文字コード順で2行目
        self.assertIn(f"（{P}。node:jisshi/e009）", errs[0])
        rep = run(themes=rows_with("node:jisshi/e009"))
        self.assertFalse([e for e in rep.errors if "ref/themes.tsv" in e], rep.errors)

    def test_views_of_and_chushin(self):
        rows = theme_rows() + [dict(r, theme="kaigo", views="fa:a" if r["kind"] == "事柄" else "", note="")
                               for r in theme_rows() if r["kind"] in ("名前", "事柄")]
        rows.sort(key=lambda r: (r["theme"], r["kind"], r["value"]))
        rep = run(themes=rows)
        self.assertFalse([e for e in rep.errors if "ref/themes.tsv" in e], rep.errors)
        theme = rc.check_themes(rows, inputs(), {"fa:a"}, rc.Report())
        self.assertEqual(theme.views_of("事柄", "新こども園の定員"), {P, "fa:a"})   # テーマをまたいで合わせる
        self.assertEqual(theme.views_of("記載", "提言"), set())
        self.assertEqual(theme.chushin("hoiku"), P)
        self.assertEqual(theme.chushin("kaigo"), "")


class OtherLedgersTest(RecordsTestCase):
    def test_kotogara_value(self):
        led = ledgers()
        led["kotogara"][0]["value"] = "２８５人"   # 全角の数字も §4 の正規化で引用（定員は285人です。）と照らす
        self.assertEqual(run(led).errors, [])
        led["kotogara"][0]["value"] = "300人"
        self.assertErr(run(led), "value が引用の中に無い")

    def test_kotogara(self):
        led = ledgers()
        led["kotogara"][0]["prev"] = "250人"
        self.assertErr(run(led), "変更でない行に prev")
        led = ledgers()
        led["kotogara"][0]["yaritori"] = f"{IQ}/9"
        self.assertErr(run(led), "yaritori の参照")
        led = ledgers()
        led["kotogara"][0]["point"] = "提言"   # 記載の値で、事柄の値でない
        self.assertErr(run(led), "point がどのテーマの kind 事柄の値でもない")

    def test_kotogara_point_any_theme(self):
        # point は、どれかのテーマの kind 事柄の値にあればよい（テーマは問わない。ADR-31 の2）
        rows = [r for r in theme_rows() if not (r["kind"] == "事柄" and r["value"] == "新こども園の定員")]
        rows += [dict(r, theme="kaigo") for r in theme_rows() if r["kind"] == "名前"]
        rows += [dict(r, theme="kaigo") for r in theme_rows() if r["value"] == "新こども園の定員"]
        rows.sort(key=lambda r: (r["theme"], r["kind"], r["value"]))
        led = ledgers()
        led["yaritori"] = [dict(r, point="") for r in led["yaritori"]]   # やりとりの記録はテーマ hoiku の点だけ
        self.assertEqual(run(led, themes=rows).errors, [])
        rows = [r for r in rows if r["value"] != "新こども園の定員"]
        self.assertErr(run(led, themes=rows), "point がどのテーマの kind 事柄の値でもない")

    def test_tsunagari(self):
        led = ledgers()
        led["tsunagari"][0]["upper"] = "知らない記載"
        self.assertErr(run(led), "upper がどのテーマの kind 記載の値でもない")
        led = ledgers()
        led["tsunagari"][0]["upper"] = "新こども園の定員"   # 事柄の値は記載の値でない
        self.assertErr(run(led), "upper がどのテーマの kind 記載の値でもない")
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
        led = ledgers()
        led["katei"][0]["cycle"] = "第9期"   # 期ごとに繰り返す計画の期（§15.5、DESIGN.md ADR-30）
        self.assertEqual(run(led).errors, [])
        led["katei"][0]["cycle"] = "第9期 "
        self.assertErr(run(led), "cycle の前後に空白がある")

    def test_unused_docs(self):
        # 記者会見の次第の PDF は過程の記録の資料に書ける。掲載ページは書けない（§2・§11 書かない資料）
        led = ledgers()
        led["katei"][0]["sources"] = "doc:kaiken-20250630-shidai/1"
        led["katei"][0]["quote"] = "定例記者会見次第"
        self.assertEqual(run(led).errors, [])
        led["katei"][0]["sources"] = "doc:kaiken-20250630-page/1"
        led["katei"][0]["quote"] = "定例記者会見"
        rep = run(led)
        self.assertEqual(len(rep.errors), 1, rep.errors)
        self.assertErr(rep, "sources に書かない資料がある（doc:kaiken-20250630-page/1")
        # テーマの定義の kind 資料も同じ
        rows = theme_rows() + [dict(theme_rows()[0], kind="資料", value="doc:kaiken-20250630-page", note="")]
        rows.sort(key=lambda r: (r["theme"], r["kind"], r["value"]))
        self.assertErr(run(themes=rows), "value に書かない資料がある（doc:kaiken-20250630-page")

    def test_kisai_about(self):
        led = ledgers()
        led["kisai"][0]["about"] = "提言"
        self.assertEqual(run(led).errors, [])
        led["kisai"][0]["about"] = "知らない"
        self.assertErr(run(led), "about がどのテーマの")

    def test_kisai_same_title(self):
        led = ledgers()
        led["kisai"][0]["about"] = "提言"
        led["kisai"].append(dict(led["kisai"][0], source="pt:youho/honpen/2", about="再編の方針"))
        self.assertErr(run(led), "同じ title の about が違う")
        led["kisai"][1].update(status="rejected", note="下書き：見本。記録しない")   # rejected は除く
        self.assertFalse([e for e in run(led).errors if "同じ title" in e])

    def test_shisetsu(self):
        led = ledgers()
        led["shisetsu"][0]["facility"] = "fa:b"
        self.assertErr(run(led), "ref/shisetsu.tsv に無い")
        ref = shisetsu_ref() + [dict(shisetsu_ref()[0], key="fa:b")]
        self.assertErr(run(led, ref=ref), "kind 施設に無い")
        led = ledgers()
        led["shisetsu"][0]["aspect"] = "面積"
        self.assertErr(run(led), "aspect が")
        # 面「規模」（§15.8。ADR-32）
        led = ledgers()
        led["shisetsu"][0].update(aspect="規模", value="一頁目")
        self.assertFalse(run(led).errors)


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


class SignalTest(RecordsTestCase):
    """届き先の信号（§11 届き先、DESIGN.md ADR-31 の4）。終了コードは変えない。"""

    def test_todoku(self):
        rep = run()
        self.assertEqual(rep.errors, [])
        # 見本の記載（提言・再編の方針）には views が無い。事柄（新こども園の定員）にはある。kisai の about は空
        self.assertEqual([(r["ledger"], r["point"]) for r in rep.signal_todoku],
                         [("tsunagari", "提言"), ("tsunagari", "再編の方針")])
        self.assertEqual(rep.signal_todoku[0]["key"], "もとにした/提言/再編の方針/doc:teigen/2")
        self.assertEqual(list(rep.signal_todoku[0]), rc.SIGNAL_TODOKU_COLUMNS)
        rows = theme_rows()
        for r in rows:
            if r["kind"] == "記載":
                r["views"] = P
        self.assertEqual(run(themes=rows).signal_todoku, [])
        led = ledgers()
        led["kisai"][0]["about"] = "提言"
        led["tsunagari"][0].update(status="candidate", reviewer="", date="")   # confirmed だけを数える
        self.assertEqual([(r["ledger"], r["point"]) for r in run(led).signal_todoku], [("kisai", "提言")])

    def test_point(self):
        led = ledgers()
        led["yaritori"][2]["point"] = ""
        led["yaritori"][3].update(status="candidate", reviewer="", date="")
        rep = run(led)
        self.assertEqual(rep.signal_point,
                         [{"ledger": "yaritori", "question": IQ, "rows": 3, "empty": 1, "ratio": "0.3333"},
                          {"ledger": "shitsugi", "question": SQ, "rows": 1, "empty": 0, "ratio": "0.0000"}])

    def test_chushin(self):
        rep = run()
        # 対象：kotogara（新こども園の定員。中心の見方にある）と tsunagari（提言・再編の方針。views 無し）。kisai は about が空
        self.assertEqual(rep.signal_chushin, [{"theme": "hoiku", "chushin": P, "rows": 2, "hit": 1, "ratio": "0.5000"}])
        rows = theme_rows()
        for r in rows:
            if r["kind"] == "名前":
                r["note"] = "見本"
        self.assertEqual(run(themes=rows).signal_chushin,
                         [{"theme": "hoiku", "chushin": "", "rows": 2, "hit": 0, "ratio": ""}])
        led = ledgers()
        led["kotogara"] = []
        led["tsunagari"] = []
        self.assertEqual(run(led).signal_chushin[0]["ratio"], "")   # rows が 0

    def test_chushin_note_end(self):
        rows = theme_rows()
        for r in rows:
            if r["kind"] == "名前":
                r["note"] = "前書き。中心の見方：fa:a"   # 行末まで
        self.assertEqual(run(themes=rows).signal_chushin[0]["chushin"], "fa:a")


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
        self.assertEqual(lines[8:12], ["- 届き先の信号：views の無い点の確定行 2（signal_todoku.tsv）",
                                       "- 届き先の信号：問いごとの点が空の割合（signal_point.tsv。問い 2）",
                                       "- 届き先の信号：中心の見方に出る行の割合（signal_chushin.tsv。テーマ 1）",
                                       "- 参照表の行の数：shisetsu 1・chiku 2・soshiki 1"])

    def test_read_area_refs(self):
        # ファイルが無ければ0行。あれば §1 の形と §12.1 の列で読む（列名と列の順が違えば止める）
        with tempfile.TemporaryDirectory() as d:
            old = check_records.CHIKU, check_records.SOSHIKI
            try:
                check_records.CHIKU, check_records.SOSHIKI = os.path.join(d, "chiku.tsv"), os.path.join(d, "soshiki.tsv")
                self.assertEqual(check_records.read_area_refs(), ([], []))
                head = "\t".join(rc.AREA_COLUMNS) + "\n"
                with open(check_records.CHIKU, "w", encoding="utf-8", newline="\n") as f:
                    f.write(head + "dist:hino\t日野\t\t見本\tkken78\t2026-11-05\t\n")
                chiku, soshiki = check_records.read_area_refs()
                self.assertEqual((chiku[0]["key"], chiku[0]["name"], soshiki), (DIST, "日野", []))
                cols = ["key", "aliases", "name", "source", "reviewer", "date", "note"]
                with open(check_records.SOSHIKI, "w", encoding="utf-8", newline="\n") as f:
                    f.write("\t".join(cols) + "\n")
                with self.assertRaises(rc.RecordsError):
                    check_records.read_area_refs()
            finally:
                check_records.CHIKU, check_records.SOSHIKI = old


if __name__ == "__main__":
    unittest.main()
