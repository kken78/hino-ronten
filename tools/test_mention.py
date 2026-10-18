"""tools/mention.py の検査（LINK_SCHEMA.md §4・§7〜§9、DESIGN.md §5 工程3のゲート）。

実行: python3 -B tools/test_mention.py -v
参照表の場所は、環境変数 HINO_RONTEN_LINEAGE・HINO_RONTEN_ALIASES で変えられる（sentinel 用）。
指定が無ければ ref/lineage.tsv・ref/aliases.tsv を読む。
"""
import os
import sys
import tempfile
import unittest
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import mention  # noqa: E402

LINEAGE = os.environ.get("HINO_RONTEN_LINEAGE", os.path.join(ROOT, "ref", "lineage.tsv"))
ALIASES = os.environ.get("HINO_RONTEN_ALIASES", os.path.join(ROOT, "ref", "aliases.tsv"))


class MentionTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.refs = mention.load_refs(LINEAGE, ALIASES)

    def find(self, text, day):
        return mention.find_mentions(text, day, self.refs)

    def tos(self, result):
        return [m.to for m in result.rows]

    def all_series(self, result):
        """行・期の行なし・期間外のすべてに出てくる series。"""
        return ([m.series for m in result.rows]
                + [x.series for x in result.no_edition]
                + [x.series for x in result.out_of_period])


class TestGates(MentionTestCase):
    """DESIGN.md §5 工程3のゲート。"""

    def test_gate1_bunkazai_not_chiiki_nogyo(self):
        # ゲート1：「文化財保存活用地域計画」の言及は bunkazai に入り、chiiki-nogyo には1件も入らない
        for text in ["日野町文化財保存活用地域計画の策定", "文化財保存活用地域計画の策定"]:
            with self.subTest(text=text):
                r = self.find(text, "2025-06-15")
                self.assertEqual(self.tos(r), ["plan:bunkazai"])
                self.assertNotIn("chiiki-nogyo", self.all_series(r))

    def test_gate1_before_period_is_candidate_not_chiiki_nogyo(self):
        # 策定前（2023年度）の言及は bunkazai の計画期間の前の candidate になる（§7）。chiiki-nogyo には入らない
        r = self.find("策定中の文化財保存活用地域計画について", "2023-06-15")
        self.assertEqual(self.tos(r), ["plan:bunkazai"])
        self.assertTrue(r.rows[0].note.startswith("計画期間の前（2年前）。"))
        self.assertEqual(r.out_of_period, [])
        self.assertNotIn("chiiki-nogyo", self.all_series(r))

    def test_gate2_kyoiku_by_fiscal_year(self):
        # ゲート2：期の明記がない「教育振興基本計画」は、発言日の年度で kyoiku3・kyoiku4・計画期間の前・期間外に分かれる
        r = self.find("教育振興基本計画について伺う", "2022-06-15")
        self.assertEqual(self.tos(r), ["plan:kyoiku3"])
        r = self.find("教育振興基本計画について伺う", "2025-06-15")
        self.assertEqual(self.tos(r), ["plan:kyoiku4"])
        r = self.find("教育振興基本計画について伺う", "2018-06-15")
        self.assertEqual(self.tos(r), ["plan:kyoiku3"])
        self.assertTrue(r.rows[0].note.startswith("計画期間の前（2年前）。"))
        self.assertEqual(r.out_of_period, [])
        r = self.find("教育振興基本計画について伺う", "2016-06-15")
        self.assertEqual(r.rows, [])
        self.assertEqual([(x.series, x.fiscal_year) for x in r.out_of_period], [("kyoiku", 2016)])


class TestFiscalYear(MentionTestCase):
    def test_march_belongs_to_previous_fiscal_year(self):
        r = self.find("教育振興基本計画", "2026-03-05")
        self.assertEqual(self.tos(r), ["plan:kyoiku4"])
        self.assertIn("2026-03-05 は令和7年度", r.rows[0].note)
        self.assertIn("2025〜2029年度", r.rows[0].note)

    def test_boundary(self):
        self.assertEqual(self.tos(self.find("教育振興基本計画", "2025-03-31")), ["plan:kyoiku3"])
        self.assertEqual(self.tos(self.find("教育振興基本計画", "2025-04-01")), ["plan:kyoiku4"])

    def test_date_object(self):
        self.assertEqual(self.tos(self.find("教育振興基本計画", date(2022, 6, 15))), ["plan:kyoiku3"])

    def test_invalid_date(self):
        for bad in [None, "2026/03/05", "2026-13-01", ""]:
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    self.find("教育振興基本計画", bad)


class TestEdition(MentionTestCase):
    def test_explicit_before_overrides_date(self):
        r = self.find("第3期日野町教育振興基本計画の評価", "2026-06-15")
        self.assertEqual(self.tos(r), ["plan:kyoiku3"])
        self.assertIn("期の明記（第3期）", r.rows[0].note)

    def test_explicit_after(self):
        r = self.find("日野町地域福祉計画（第4期）では", "2022-06-15")
        self.assertEqual(self.tos(r), ["plan:chiiki-fukushi4"])
        self.assertIn("期の明記（第4期）", r.rows[0].note)

    def test_kanji_numeral(self):
        r = self.find("第五次日野町総合計画", "2019-06-15")
        self.assertEqual(self.tos(r), ["lin:sogo/5"])
        self.assertIn("期の明記（第5次）", r.rows[0].note)

    def test_kanji_numeral_over_ten(self):
        r = self.find("第十一期日野町分別収集計画", "2026-06-15")
        self.assertEqual(self.tos(r), ["plan:bunbetsu"])

    def test_before_and_after_differ(self):
        r = self.find("第3期日野町教育振興基本計画（第4期）", "2026-06-15")
        self.assertEqual(self.tos(r), ["plan:kyoiku3"])
        self.assertIn("期の明記が前後で違う（第3期・第4期）", r.rows[0].note)

    def test_edition_without_row(self):
        r = self.find("第1期子ども・子育て支援事業計画では", "2016-06-15")
        self.assertEqual(r.rows, [])
        self.assertEqual([(x.series, x.edition) for x in r.no_edition], [("kodomo", "1")])

    def test_no_or_kagikakko_between(self):
        # 2026-10-11 の決定（§7）：「の」か「「」のどちらか1つと「日野町」を挟む形も期の明記として読む
        cases = [
            ("第6次の総合計画を策定する", "2019-06-14", "plan:sogo6", "期の明記（第6次）"),
            ("第3期「子ども・子育て支援事業計画」", "2024-06-14", "plan:kodomo", "期の明記（第3期）"),
            ("第4期の日野町教育振興基本計画", "2025-03-11", "plan:kyoiku4", "期の明記（第4期）"),
            ("第6期の総合計画", "2020-03-12", "plan:sogo6", "期の明記（第6期）"),
        ]
        for text, day, to, note in cases:
            with self.subTest(text=text):
                r = self.find(text, day)
                self.assertEqual(self.tos(r), [to])
                self.assertTrue(r.rows[0].note.startswith(note))

    def test_two_chars_between_not_edition(self):
        r = self.find("第6次となる総合計画", "2019-06-14")
        self.assertEqual(self.tos(r), ["lin:sogo/5"])
        self.assertNotIn("期の明記", r.rows[0].note)

    def test_no_between_without_row(self):
        r = self.find("第3次の総合計画", "2018-06-13")
        self.assertEqual(r.rows, [])
        self.assertEqual([(x.series, x.edition) for x in r.no_edition], [("sogo", "3")])

    def test_jisshi_not_read_as_sogo_edition(self):
        r = self.find("第6次日野町総合計画実施計画に記載", "2026-06-15")
        self.assertEqual(self.tos(r), ["plan:jisshi"])
        self.assertNotIn("sogo", self.all_series(r))


class TestSameTextEdition(MentionTestCase):
    """2026-10-11 の決定（§7）：同じ本文の明記の無い言及は発言日で判別し、note に本文の期の明記を書く。"""
    MARK = "同じ本文に期の明記がある"

    def test_dated_row_gets_note(self):
        r = self.find("第6次日野町総合計画ではダブルケアの位置づけ。現在の総合計画では育児と介護", "2019-03-14")
        self.assertEqual(self.tos(r), ["plan:sogo6", "lin:sogo/5"])
        self.assertTrue(r.rows[1].note.endswith("。同じ本文に期の明記がある（第6次）"))
        self.assertNotIn(self.MARK, r.rows[0].note)

    def test_forms_in_order_including_no_edition(self):
        r = self.find("第2次日野町総合計画と第6次日野町総合計画、そして総合計画", "2019-03-14")
        self.assertEqual(self.tos(r), ["plan:sogo6", "lin:sogo/5"])
        self.assertTrue(r.rows[1].note.endswith("（第2次・第6次）"))
        self.assertEqual([(x.series, x.edition) for x in r.no_edition], [("sogo", "2")])

    def test_edition_after_dated_mention(self):
        r = self.find("総合計画の策定。第6次総合計画", "2019-06-14")
        self.assertEqual(self.tos(r), ["lin:sogo/5", "plan:sogo6"])
        self.assertIn("同じ本文に期の明記がある（第6次）", r.rows[0].note)

    def test_same_to_no_note(self):
        r = self.find("第5次総合計画と総合計画", "2019-06-14")
        self.assertEqual(self.tos(r), ["lin:sogo/5"])
        self.assertNotIn(self.MARK, r.rows[0].note)

    def test_unknown_period_no_note(self):
        r = self.find("第5次国土利用計画と国土利用計画", "2019-06-14")
        self.assertEqual(self.tos(r), ["plan:kokudoriyou"])
        self.assertEqual(r.rows[0].note, "期間不明")
        self.assertEqual([(x.series, x.edition) for x in r.no_edition], [("kokudoriyou", "5")])


class TestLongestMatch(MentionTestCase):
    def test_bunkazai_variants(self):
        # 2026-10-11 の決定：文化財保存活用地域計画の書き方の違い4つは bunkazai の略称。chiiki-nogyo には入らない
        for text in ["文化財の保存活用地域計画", "文化財保護活用地域計画", "文化財地域計画", "文化財保存活動地域計画"]:
            with self.subTest(text=text):
                r = self.find(text, "2025-06-15")
                self.assertEqual(self.tos(r), ["plan:bunkazai"])
                self.assertNotIn("chiiki-nogyo", self.all_series(r))
        r = self.find("文化財の保存活用地域計画", "2023-06-15")  # 計画期間の前（§7）
        self.assertEqual(self.tos(r), ["plan:bunkazai"])
        self.assertEqual(r.out_of_period, [])
        self.assertNotIn("chiiki-nogyo", self.all_series(r))

    def test_national_sixth_environment_plan_excluded(self):
        # 2026-10-11 の決定：国の第6次環境基本計画は除外の語。kankyo の候補も一覧も出ない
        r = self.find("国においては第6次環境基本計画・第7次エネルギー基本計画など", "2024-12-02")
        self.assertEqual((r.rows, r.no_edition, r.out_of_period), ([], [], []))

    def test_kyojin_not_chiiki_nogyo(self):
        r = self.find("国土強靱化日野町地域計画のほうを策定", "2025-06-15")
        self.assertEqual(self.tos(r), ["plan:kyojin"])
        self.assertNotIn("chiiki-nogyo", self.all_series(r))

    def test_kyojin_variant_character(self):
        r = self.find("日野町国土強靱化地域計画", "2025-06-15")
        self.assertEqual(self.tos(r), ["plan:kyojin"])

    def test_exclusion(self):
        r = self.find("滋賀県地域防災計画や流域下水道", "2025-03-10")
        self.assertEqual((r.rows, r.no_edition, r.out_of_period), ([], [], []))

    def test_exclusion_mixed(self):
        r = self.find("滋賀県地域防災計画と日野町地域防災計画", "2025-06-15")
        self.assertEqual(self.tos(r), ["plan:bosai"])

    def test_national_strategy_excluded(self):
        r = self.find("まち・ひと・しごと創生総合戦略が定められ", "2022-06-15")
        self.assertEqual((r.rows, r.no_edition, r.out_of_period), ([], [], []))
        r = self.find("総合戦略に掲げる施策", "2022-06-15")
        self.assertEqual(self.tos(r), ["plan:senryaku2"])


class TestContextAbbrev(MentionTestCase):
    """2026-10-15 の決定（§7 文脈で決める略称・§9 文脈語）。"""
    GROUP = "文脈で決まらない（組：chiiki-nogyo・bunkazai・kyojin）"

    def find(self, text, day, before=()):
        return mention.find_mentions(text, day, self.refs, before)

    def test_ambiguous_terms(self):
        self.assertEqual({k: a.group for k, a in self.refs.ambiguous.items()}, {
            "地域計画": ("chiiki-nogyo", "bunkazai", "kyojin"),
            "日野町地域計画": ("chiiki-nogyo", "kyojin")})
        for a in self.refs.ambiguous.values():
            self.assertFalse({"地域計画", "日野町地域計画"} & {c.term for c in a.clues})

    def test_bunkazai_from_before(self):
        r = self.find("地域計画の進捗はどうか", "2025-06-15", ["文化財保存活用地域計画の策定について伺う"])
        self.assertEqual(self.tos(r), ["plan:bunkazai"])
        self.assertEqual(r.rows[0].evidence, "地域計画")
        self.assertTrue(r.rows[0].note.startswith("文脈で決めた（手がかり：文化財保存活用地域計画）。2025-06-15 は令和7年度"))

    def test_chiiki_nogyo_from_before(self):
        r = self.find("地域計画の策定", "2025-06-15", ["農地の集積について"])
        self.assertEqual(self.tos(r), ["plan:chiiki-nogyo"])
        self.assertEqual(r.rows[0].note, "文脈で決めた（手がかり：農地）。期間不明")

    def test_nearest_of_two(self):
        r = self.find("文化財の保護と農業の振興について、地域計画は", "2025-06-15")
        self.assertEqual(self.tos(r), ["plan:chiiki-nogyo"])
        r = self.find("農業の振興と文化財の保護について、地域計画は", "2025-06-15")
        self.assertEqual(self.tos(r), ["plan:bunkazai"])
        # 同じ本文の言及より前は、before より近い
        r = self.find("文化財について。地域計画", "2025-06-15", ["農地の話"])
        self.assertEqual(self.tos(r), ["plan:bunkazai"])
        # before は後ろの本文ほど近い
        r = self.find("地域計画", "2025-06-15", ["農地の話", "文化財の話"])
        self.assertEqual(self.tos(r), ["plan:bunkazai"])

    def test_same_end_longer_wins(self):
        # 「保存活用地域計画」と「文化財保存活用地域計画」は終わりの位置が同じ。長い方を手がかりにする
        r = self.find("地域計画", "2025-06-15", ["文化財保存活用地域計画"])
        self.assertIn("手がかり：文化財保存活用地域計画）", r.rows[0].note)

    def test_after_in_same_text(self):
        r = self.find("地域計画は農地の集約を進める", "2025-06-15")
        self.assertEqual(self.tos(r), ["plan:chiiki-nogyo"])
        self.assertTrue(r.rows[0].note.startswith("文脈で決めた（手がかり：農地）"))
        # 後ろでは、始まりの位置がいちばん前のもの
        r = self.find("地域計画は文化財と農地", "2025-06-15")
        self.assertEqual(self.tos(r), ["plan:bunkazai"])

    def test_undetermined(self):
        r = self.find("地域計画について伺う", "2025-06-15")
        self.assertEqual((r.rows, r.out_of_period, r.no_edition), ([], [], []))
        self.assertEqual([(x.series, x.evidence, x.note, x.fiscal_year) for x in r.undetermined],
                         [("chiiki-nogyo", "地域計画", self.GROUP, 2025)])

    def test_ambiguous_term_itself_not_clue(self):
        for before in [["地域計画の話"], ["日野町地域計画の話"]]:
            with self.subTest(before=before):
                r = self.find("地域計画", "2025-06-15", before)
                self.assertEqual(r.rows, [])
                self.assertEqual(len(r.undetermined), 1)
        r = self.find("地域計画の話。地域計画", "2025-06-15")
        self.assertEqual(r.rows, [])
        self.assertEqual(len(r.undetermined), 1)

    def test_hino_chiiki_keikaku_group(self):
        r = self.find("強靭化の取り組みと日野町地域計画", "2025-06-15")
        self.assertEqual(self.tos(r), ["plan:kyojin"])
        # 文化財は「日野町地域計画」の組（chiiki-nogyo・kyojin）の手がかりではない
        r = self.find("文化財と日野町地域計画", "2025-06-15")
        self.assertEqual(r.rows, [])
        self.assertEqual([x.note for x in r.undetermined], ["文脈で決まらない（組：chiiki-nogyo・kyojin）"])

    def test_out_of_period_after_context(self):
        # 決まった bunkazai の発言日が計画期間（2025〜2034年度）の4年以上前なら、期間外の一覧に出る
        r = self.find("地域計画の策定", "2021-06-15", ["文化財の保護について"])
        self.assertEqual((r.rows, r.undetermined), ([], []))
        self.assertEqual([x.series for x in r.out_of_period], ["bunkazai"])
        self.assertEqual(r.out_of_period[0].note,
                         "文脈で決めた（手がかり：文化財）。2021-06-15 は令和3年度。bunkazai のどの期の期間にも入らない")

    def test_explicit_edition_after_context(self):
        r = self.find("農地の集積。第2期地域計画", "2025-06-15")
        self.assertEqual(r.rows, [])
        self.assertEqual([(x.series, x.edition) for x in r.no_edition], [("chiiki-nogyo", "2")])
        self.assertTrue(r.no_edition[0].note.startswith("文脈で決めた（手がかり：農地）。期の明記（第2期）"))

    def test_merged_with_direct_mention(self):
        # 同じ本文で同じ to になる一致は1行にまとめる（evidence は先に出た一致）
        r = self.find("文化財保存活用地域計画と、その地域計画", "2025-06-15")
        self.assertEqual(self.tos(r), ["plan:bunkazai"])
        self.assertEqual(r.rows[0].evidence, "文化財保存活用地域計画")
        self.assertFalse(r.rows[0].note.startswith("文脈で決めた"))
        self.assertTrue(r.rows[0].note.endswith("。ほかに一致した語：地域計画"))

    def test_context_words_are_not_mentions(self):
        r = self.find("農地と農業と文化財と強靭化と強靱化", "2025-06-15", ["地域計画"])
        self.assertEqual((r.rows, r.no_edition, r.out_of_period, r.undetermined), ([], [], [], []))


class TestGrouping(MentionTestCase):
    def test_same_plan_merged(self):
        r = self.find("第7期障がい福祉計画・第3期障がい児福祉計画", "2024-06-15")
        self.assertEqual(self.tos(r), ["plan:shogai-fukushi7"])
        self.assertEqual(r.rows[0].evidence, "障がい福祉計画")
        self.assertIn("ほかに一致した語：障がい児福祉計画", r.rows[0].note)

    def test_repeated_term_one_row(self):
        r = self.find("教育振興基本計画と、教育振興基本計画と、教育振興基本計画", "2022-06-15")
        self.assertEqual(self.tos(r), ["plan:kyoiku3"])

    def test_different_plans_in_order(self):
        r = self.find("日野町総合計画と日野町環境基本計画", "2025-06-15")
        self.assertEqual(self.tos(r), ["plan:sogo6", "plan:kankyo"])

    def test_unknown_period(self):
        r = self.find("日野町地域防災計画に基づき", "2025-06-15")
        self.assertEqual(self.tos(r), ["plan:bosai"])
        self.assertIn("期間不明", r.rows[0].note)

    def test_partner_whole_period(self):
        r = self.find("ひのパートナープラン2019の後期計画", "2019-06-15")
        self.assertEqual(self.tos(r), ["plan:partner"])
        self.assertIn("令和元年度", r.rows[0].note)
        r = self.find("ひのパートナープラン2019の後期計画", "2015-06-15")  # 計画期間（2019〜）の4年前
        self.assertEqual(r.rows, [])
        self.assertEqual([x.series for x in r.out_of_period], ["partner"])


class TestContext(MentionTestCase):
    def test_fifteen_each_side(self):
        text = "あ" * 20 + "日野町総合計画" + "い" * 20
        r = self.find(text, "2025-06-15")
        self.assertEqual(r.rows[0].evidence, "日野町総合計画")
        self.assertEqual(r.rows[0].context, "あ" * 15 + "日野町総合計画" + "い" * 15)

    def test_short_at_edges(self):
        r = self.find("日野町総合計画", "2025-06-15")
        self.assertEqual(r.rows[0].context, "日野町総合計画")
        r = self.find("あい日野町総合計画う", "2025-06-15")
        self.assertEqual(r.rows[0].context, "あい日野町総合計画う")

    def test_context_is_normalized(self):
        r = self.find("第６次　日野町\n総合計画　を", "2025-06-15")
        self.assertEqual(self.tos(r), ["plan:sogo6"])
        self.assertEqual(r.rows[0].context, "第6次日野町総合計画を")


class TestNormalize(unittest.TestCase):
    def test_nfkc_and_spaces(self):
        self.assertEqual(mention.normalize("第６次　日野町 総合\t計画\r\n"), "第6次日野町総合計画")

    def test_page_numbers(self):
        self.assertEqual(mention.normalize("総合\n2-34計画"), "総合計画")
        self.assertEqual(mention.normalize("総合-19-計画"), "総合計画")

    def test_js_whitespace_set(self):
        self.assertEqual(mention.normalize("a﻿b c d"), "abcd")
        # Python の \s は \x1c〜\x1f を含むが、JavaScript の \s は含まない
        self.assertEqual(mention.normalize("a\x1cb"), "a\x1cb")


class TestLoadRefs(unittest.TestCase):
    LIN_HEAD = "series\tedition\tplan\tname\tstart_fy\tend_fy\tsource\tnote\n"
    ALI_HEAD = "series\tterm\tkind\tnote\n"
    LIN_OK = LIN_HEAD + "kyoiku\t4\tkyoiku4\t第4期 日野町教育振興基本計画\t2025\t2029\tmanifest\t\n"
    ALI_OK = ALI_HEAD + "kyoiku\t日野町教育振興基本計画\t正式名\t\n"

    def load(self, lin, ali):
        with tempfile.TemporaryDirectory() as d:
            lp, ap = os.path.join(d, "l.tsv"), os.path.join(d, "a.tsv")
            with open(lp, "w", encoding="utf-8") as f:
                f.write(lin)
            with open(ap, "w", encoding="utf-8") as f:
                f.write(ali)
            return mention.load_refs(lp, ap)

    def test_minimal_ok(self):
        self.load(self.LIN_OK, self.ALI_OK)

    def test_bad_header(self):
        with self.assertRaises(mention.RefError):
            self.load(self.LIN_OK.replace("start_fy", "start"), self.ALI_OK)

    def test_bad_kind(self):
        with self.assertRaises(mention.RefError):
            self.load(self.LIN_OK, self.ALI_OK.replace("正式名", "別名"))

    def test_unnormalized_term(self):
        with self.assertRaises(mention.RefError):
            self.load(self.LIN_OK, self.ALI_OK.replace("日野町教育", "日野町 教育"))

    LIN_CTX = (LIN_OK + "chiiki-nogyo\t\tchiiki-nogyo\t地域計画\t\t\t\t\n"
               + "bunkazai\t\tbunkazai\t日野町文化財保存活用地域計画\t2025\t2034\tmanifest\t\n")
    ALI_CTX = (ALI_OK + "chiiki-nogyo\t地域計画\t略称\t\n"
               + "chiiki-nogyo\t地域計画(農業)\t正式名\t\n"
               + "bunkazai\t文化財保存活用地域計画\t正式名\t\n")

    def test_context_word_loaded(self):
        refs = self.load(self.LIN_CTX, self.ALI_CTX + "chiiki-nogyo\t農地\t文脈語\t\nbunkazai\t文化財\t文脈語\t\n")
        self.assertEqual([(t.series, t.term) for t in refs.terms if t.kind == mention.CONTEXT],
                         [("chiiki-nogyo", "農地"), ("bunkazai", "文化財")])
        self.assertNotIn("農地", [t.term for t in refs.match_terms])
        self.assertEqual(refs.ambiguous["地域計画"].group, ("chiiki-nogyo", "bunkazai"))
        r = mention.find_mentions("農地と文化財", "2025-06-15", refs)
        self.assertEqual((r.rows, r.out_of_period, r.undetermined), ([], [], []))
        r = mention.find_mentions("地域計画", "2025-06-15", refs, ["農地"])
        self.assertEqual([m.to for m in r.rows], ["plan:chiiki-nogyo"])

    def test_context_word_outside_group(self):
        # kyoiku は文脈で決める略称の組に入らない
        with self.assertRaises(mention.RefError) as cm:
            self.load(self.LIN_CTX, self.ALI_CTX + "kyoiku\t学校\t文脈語\t\n")
        self.assertIn("組に入らない", str(cm.exception))

    def test_context_word_same_as_plan_term(self):
        for row in ["bunkazai\t地域計画\t文脈語\t\n", "chiiki-nogyo\t文化財保存活用地域計画\t文脈語\t\n"]:
            with self.subTest(row=row):
                with self.assertRaises(mention.RefError) as cm:
                    self.load(self.LIN_CTX, self.ALI_CTX + row)
                self.assertIn("文脈語が日野町の計画の語と同じ", str(cm.exception))

    def test_context_word_in_two_series(self):
        with self.assertRaises(mention.RefError) as cm:
            self.load(self.LIN_CTX, self.ALI_CTX + "chiiki-nogyo\t保存\t文脈語\t\nbunkazai\t保存\t文脈語\t\n")
        self.assertIn("同じ文脈語が2つの series", str(cm.exception))

    def test_real_refs(self):
        refs = mention.load_refs(LINEAGE, ALIASES)
        self.assertTrue(refs)



# 計画期間の前（§7）：最初の期の初年度より前の3年以内は、最初の期の candidate にする
class TestBeforePeriod(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.refs = mention.load_refs(LINEAGE, ALIASES)

    def find(self, text, day, before=()):
        return mention.find_mentions(text, day, self.refs, before)

    def test_one_and_three_years_before(self):
        for day, wareki, n in (("2024-06-15", "令和6年度", 1), ("2025-03-31", "令和6年度", 1), ("2022-04-01", "令和4年度", 3)):
            with self.subTest(day=day):
                r = self.find("文化財保存活用地域計画について", day)
                self.assertEqual([m.to for m in r.rows], ["plan:bunkazai"])
                self.assertEqual(r.rows[0].note,
                                 f"計画期間の前（{n}年前）。{day} は{wareki}。日野町文化財保存活用地域計画（2025〜2034年度）")
                self.assertEqual(r.out_of_period, [])

    def test_first_edition_of_series(self):
        # 期のある series は、start_fy が最も小さい期（kyoiku3、2020〜2024年度）の行を作る
        r = self.find("教育振興基本計画について", "2017-06-15")
        self.assertEqual([m.to for m in r.rows], ["plan:kyoiku3"])
        self.assertEqual(r.rows[0].note,
                         "計画期間の前（3年前）。2017-06-15 は平成29年度。第3期 日野町教育振興基本計画（2020〜2024年度）")

    def test_four_years_before_is_out_of_period(self):
        for day in ("2021-06-15", "2022-03-31"):
            with self.subTest(day=day):
                r = self.find("文化財保存活用地域計画について", day)
                self.assertEqual(r.rows, [])
                self.assertEqual([(x.series, x.fiscal_year) for x in r.out_of_period], [("bunkazai", 2021)])

    def test_blank_period_series_stays_unknown(self):
        # 計画期間が空欄の期がある series は、これまでどおり「期間不明」
        r = self.find("日野町緑の基本計画について", "2010-06-15")
        self.assertEqual([(m.to, m.note) for m in r.rows], [("plan:midori", "期間不明")])
        self.assertEqual(r.out_of_period, [])

    def test_context_prefix(self):
        r = self.find("地域計画の策定", "2023-06-15", ["文化財の保護について"])
        self.assertEqual([m.to for m in r.rows], ["plan:bunkazai"])
        self.assertEqual(r.rows[0].note, "文脈で決めた（手がかり：文化財）。計画期間の前（2年前）。2023-06-15 は令和5年度。"
                                         "日野町文化財保存活用地域計画（2025〜2034年度）")

    def test_dated_row_gets_explicit_note(self):
        # 計画期間の前の行も発言日で決めた行として、同じ本文の期の明記を note に書く
        r = self.find("第4期教育振興基本計画と、教育振興基本計画", "2018-06-15")
        self.assertEqual([(m.to, m.note) for m in r.rows], [
            ("plan:kyoiku4", "期の明記（第4期）"),
            ("plan:kyoiku3", "計画期間の前（2年前）。2018-06-15 は平成30年度。第3期 日野町教育振興基本計画（2020〜2024年度）。"
                             "同じ本文に期の明記がある（第4期）")])


if __name__ == "__main__":
    unittest.main()
