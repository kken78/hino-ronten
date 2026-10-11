"""tools/gen_mentions.py の検査（LINK_SCHEMA.md §1〜§3・§7・§8・§10、DESIGN.md §5 工程4）。

実行: python3 -B tools/test_gen_mentions.py -v
入力のデータは小さな見本を使う。参照表は実物（ref/lineage.tsv・ref/aliases.tsv）を読む。
参照表の場所は、環境変数 HINO_RONTEN_LINEAGE・HINO_RONTEN_ALIASES で変えられる（test_mention.py と同じ）。
"""
import json
import os
import sys
import tempfile
import unittest
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import gen_mentions as gm  # noqa: E402
import mention  # noqa: E402

LINEAGE = os.environ.get("HINO_RONTEN_LINEAGE", os.path.join(ROOT, "ref", "lineage.tsv"))
ALIASES = os.environ.get("HINO_RONTEN_ALIASES", os.path.join(ROOT, "ref", "aliases.tsv"))

M_JUNE = "0000000001"    # 日付が複数ある会議（初日 2025-06-02）
M_NODATE = "0000000002"  # meetings.json の date が null の会議
M_SPAN = "0000000003"    # 日付が2つの年度にまたがる会議
M_2018 = "0000000004"    # 2018年度の会議
M_NAME = "0000000005"    # 日付のある PDF が無く、date を会議名から求めた会議（dateFrom が name）

MEETINGS = [
    {"id": M_JUNE, "name": "令和7年6月定例会議", "date": "2025-06-02", "dateFrom": "pdf", "pdfs": [
        {"label": "目次", "date": None, "url": "u0"},
        {"label": "第2日", "date": "2025-06-12", "url": "u2"},
        {"label": "第1日", "date": "2025-06-02", "url": "u1"}]},
    {"id": M_NODATE, "name": "見本（会議名に日付なし）臨時会", "date": None, "dateFrom": None, "pdfs": [
        {"label": "本文", "date": None, "url": "u3"}]},
    {"id": M_SPAN, "name": "見本", "date": "2025-03-30", "dateFrom": "pdf", "pdfs": [
        {"label": "a", "date": "2025-03-30", "url": "u4"},
        {"label": "b", "date": "2025-04-02", "url": "u5"}]},
    {"id": M_2018, "name": "平成30年第3回（6月）定例会会議録", "date": "2018-06-13", "dateFrom": "pdf", "pdfs": [
        {"label": "第2日", "date": "2018-06-13", "url": "u6"}]},
    {"id": M_NAME, "name": "令和3年第1回（2月10日）臨時会会議録", "date": "2021-02-10", "dateFrom": "name", "pdfs": [
        {"label": "目次", "date": None, "url": "u7"},
        {"label": "本文", "date": None, "url": "u8"}]},
]

PLAN_NAMES = {
    "sogo6": "第6次日野町総合計画",
    "kyoiku4": "第4期 日野町教育振興基本計画",
    "shogai-fukushi7": "第7期 障がい福祉計画・第3期 障がい児福祉計画",
}


def speech(sid, text, role="1番", day=None):
    return {"sid": sid, "meetingId": sid.split("_")[0], "role": role, "name": "見本", "text": text, "date": day}


def question(issue, member, q_num, title, question_text=None, answer_title=None, answers=None, other=None):
    q = {"issue": issue, "member": member, "q_num": q_num, "title": title}
    if question_text is not None:
        q.update({"question_text": question_text, "answer_title": answer_title or "",
                  "answers": answers or [], "other": other or []})
    return q


class GenTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.refs = mention.load_refs(LINEAGE, ALIASES)
        plans, seen = [], set()
        for r in cls.refs.lineage:
            if r.plan and r.plan not in seen:
                seen.add(r.plan)
                plans.append({"id": r.plan, "name": PLAN_NAMES.get(r.plan, f"見本の名称 {r.plan}")})
        cls.manifest = {"schema": 1, "plans": plans}
        cls.names = gm.plan_names(cls.manifest, cls.refs)
        cls.mdates = gm.meeting_dates(MEETINGS)


# 1. bq のキー
class TestBqKey(GenTestCase):
    def test_spaces_removed_and_nfkc(self):
        for member in ["中西 佳子", "中西　佳子", "中西佳子"]:
            with self.subTest(member=member):
                self.assertEqual(gm.bq_key({"issue": 36, "member": member, "q_num": 2}), "bq:36/中西佳子/2")
        self.assertEqual(gm.bq_key({"issue": 24, "member": "Ｈｉｎｏ　太郎", "q_num": 1}), "bq:24/Hino太郎/1")

    def test_duplicate_key_stops(self):
        qs = [question(35, "中西 佳子", 2, "題名"), question(35, "中西　佳子", 2, "題名")]
        ml = {"35": {"中西 佳子": {"meeting_id": M_JUNE}}}
        with self.assertRaises(gm.GenError):
            gm.gen_bulletin(qs, ml, self.mdates, self.refs, self.names)


# 2. 会議の日付（meetings.json の date 項目。§8・D1）
class TestMeetingDates(GenTestCase):
    def test_earliest_date_and_toc_ignored(self):
        self.assertEqual(self.mdates[M_JUNE], (date(2025, 6, 2), ""))

    def test_date_from_name(self):
        self.assertEqual(self.mdates[M_NAME], (date(2021, 2, 10), ""))

    def _with(self, mid, **kw):
        return [dict(m, **kw) if m["id"] == mid else m for m in MEETINGS]

    def test_pdf_mismatch_stops(self):
        # dateFrom が pdf で、date が日付のある PDF のうち最も早い日（2025-06-02）と違う
        with self.assertRaises(gm.GenError) as cm:
            gm.meeting_dates(self._with(M_JUNE, date="2025-06-12"))
        self.assertIn(M_JUNE, str(cm.exception))

    def test_name_with_dated_pdf_stops(self):
        # dateFrom が name なのに、日付のある PDF がある
        with self.assertRaises(gm.GenError) as cm:
            gm.meeting_dates(self._with(M_2018, dateFrom="name"))
        self.assertIn(M_2018, str(cm.exception))

    def test_missing_field_stops(self):
        for field in ["date", "dateFrom"]:
            with self.subTest(field=field):
                old = [{k: v for k, v in m.items() if k != field} if m["id"] == M_JUNE else m for m in MEETINGS]
                with self.assertRaises(gm.GenError) as cm:
                    gm.meeting_dates(old)
                self.assertIn(M_JUNE, str(cm.exception))

    def test_inconsistent_null_or_unknown_from_stops(self):
        for kw in [{"date": None, "dateFrom": "pdf"}, {"date": None, "dateFrom": None}, {"dateFrom": "index"}]:
            with self.subTest(**kw):
                with self.assertRaises(gm.GenError):
                    gm.meeting_dates(self._with(M_JUNE, **kw))

    def test_no_date(self):
        d, reason = self.mdates[M_NODATE]
        self.assertIsNone(d)
        self.assertIn("日付が無い", reason)

    def test_span_fiscal_years(self):
        d, reason = self.mdates[M_SPAN]
        self.assertIsNone(d)
        self.assertIn("年度", reason)


# 3. 発言日（sid の日付 → 会議の日付 → 日付なし）
class TestSpeechDate(GenTestCase):
    def test_sid_date(self):
        self.assertEqual(gm.sid_date(f"{M_JUNE}_20250612_0003"), date(2025, 6, 12))
        for sid in [f"{M_NODATE}_kaigiroku-honbun_0003", f"{M_JUNE}_H29.5.15_0001",
                    f"{M_JUNE}_9_kaigiroku_0001", f"{M_JUNE}_8.5rmokuji_0000"]:
            with self.subTest(sid=sid):
                self.assertIsNone(gm.sid_date(sid))

    def test_invalid_eight_digits_stop(self):
        with self.assertRaises(gm.GenError):
            gm.sid_date(f"{M_JUNE}_20251301_0001")

    def test_order(self):
        self.assertEqual(gm.speech_date(speech(f"{M_JUNE}_20250612_0003", ""), self.mdates), (date(2025, 6, 12), ""))
        self.assertEqual(gm.speech_date(speech(f"{M_JUNE}_8.5rmokuji_0000", ""), self.mdates), (date(2025, 6, 2), ""))
        self.assertEqual(gm.speech_date(speech(f"{M_NAME}_2gijiroku_0003", ""), self.mdates), (date(2021, 2, 10), ""))
        d, reason = gm.speech_date(speech(f"{M_NODATE}_kaigiroku-honbun_0003", ""), self.mdates)
        self.assertIsNone(d)
        self.assertIn(M_NODATE, reason)

    def test_meeting_id_mismatch_stops(self):
        e = speech(f"{M_JUNE}_20250612_0003", "")
        e["meetingId"] = M_NODATE
        with self.assertRaises(gm.GenError):
            gm.speech_date(e, self.mdates)

    def test_unknown_meeting_stops(self):
        with self.assertRaises(gm.GenError):
            gm.speech_date(speech("0000009999_kaigiroku_0001", ""), self.mdates)

    def test_toc(self):
        self.assertTrue(gm.is_toc(f"{M_JUNE}_8.5rmokuji_0000"))
        self.assertTrue(gm.is_toc(f"{M_JUNE}_kaigiroku-mokuji_0000"))
        self.assertFalse(gm.is_toc(f"{M_JUNE}_20250612_0003"))


# 4. 議会だよりの発言日（minutes_links の meeting_id → 会議の日付）
class TestQuestionDate(GenTestCase):
    ML = {"35": {"中西 佳子": {"meeting_id": M_JUNE}}, "34": {"日野 一郎": {"meeting_id": M_NODATE}}}

    def test_meeting_first_day(self):
        q = question(35, "中西　佳子", 2, "題名")
        self.assertEqual(gm.question_date(q, self.ML, self.mdates), (M_JUNE, date(2025, 6, 2), ""))

    def test_no_meeting(self):
        mid, d, reason = gm.question_date(question(36, "中西 佳子", 1, "題名"), self.ML, self.mdates)
        self.assertEqual((mid, d), ("", None))
        self.assertIn("minutes_links.json", reason)

    def test_meeting_without_date(self):
        mid, d, reason = gm.question_date(question(34, "日野 一郎", 1, "題名"), self.ML, self.mdates)
        self.assertEqual((mid, d), (M_NODATE, None))
        self.assertIn("日付が無い", reason)

    def test_no_date_not_matched(self):
        qs = [question(36, "中西 佳子", 1, "教育振興基本計画と滋賀県地域防災計画と日野町総合計画")]
        g = gm.gen_bulletin(qs, self.ML, self.mdates, self.refs, self.names)
        self.assertEqual((g.candidates, g.out_of_period, g.no_edition), ([], [], []))
        self.assertEqual(len(g.no_date), 1)
        row = g.no_date[0]
        self.assertEqual(sorted(row), sorted(gm.NO_DATE_COLUMNS))
        self.assertEqual(row["from"], "bq:36/中西佳子/1")
        self.assertEqual((row["meeting_id"], row["scene"], row["index_date"]), ("", "", ""))
        self.assertEqual(row["matched_series"], "kyoiku、sogo")

    def test_matched_series_in_name_order(self):
        # matched_series は series の名前順（コードポイント順）。文中で出てくる順ではない
        qs = [question(36, "中西 佳子", 2, "日野町総合計画と教育振興基本計画")]
        g = gm.gen_bulletin(qs, self.ML, self.mdates, self.refs, self.names)
        self.assertEqual([r["matched_series"] for r in g.no_date], ["kyoiku、sogo"])


# 5. 議長の除外（§7：role が「議長」と完全に一致するものだけ）
class TestChair(GenTestCase):
    def test_chair_excluded_vice_chair_kept(self):
        index = [speech(f"{M_JUNE}_20250612_0001", "教育振興基本計画", role="議長"),
                 speech(f"{M_JUNE}_20250612_0002", "教育振興基本計画", role="副議長"),
                 speech(f"{M_NODATE}_kaigiroku_0001", "教育振興基本計画", role="議長")]
        g = gm.gen_minutes(index, self.mdates, {}, self.refs, self.names)
        self.assertEqual([r["from"] for r in g.candidates], [f"sp:{M_JUNE}_20250612_0002"])
        self.assertEqual(g.no_date, [])


# 5-2. 目次の除外（§7：sid の真ん中に mokuji を含む項目は発言ではないため対象から除く）
class TestTocExcluded(GenTestCase):
    def test_toc_gives_no_rows(self):
        index = [speech(f"{M_JUNE}_8.5rmokuji_0000", "目次 教育振興基本計画 第1期子ども・子育て支援事業計画", role=""),
                 speech(f"{M_NODATE}_kaigiroku-mokuji_0000", "目次 教育振興基本計画", role=""),
                 speech(f"{M_JUNE}_20250612_0001", "教育振興基本計画")]
        g = gm.gen_minutes(index, self.mdates, {}, self.refs, self.names)
        self.assertEqual([r["from"] for r in g.candidates], [f"sp:{M_JUNE}_20250612_0001"])
        self.assertEqual((g.out_of_period, g.no_edition, g.no_date), ([], [], []))


# 6. 場面（索引の並びで from〜to の両端を含む。採決は sid）
class TestScene(GenTestCase):
    SIDS = [f"{M_JUNE}_20250612_{n:04d}" for n in range(1, 7)]

    def index(self):
        return [speech(s, "") for s in self.SIDS]

    def test_ranges(self):
        s = self.SIDS
        proc = {M_JUNE: {"segments": [
            {"kind": "ippan", "from": s[1], "to": s[2]},
            {"kind": "vote", "sid": s[4]}]}}
        scenes = gm.scene_of(self.index(), proc)
        self.assertEqual({k: scenes.get(k, gm.OUTSIDE) for k in s}, {
            s[0]: "範囲外", s[1]: "一般質問", s[2]: "一般質問", s[3]: "範囲外", s[4]: "採決", s[5]: "範囲外"})

    def test_labels(self):
        s = self.SIDS
        kinds = ["shitsugi", "report", "debate", "proposal"]
        proc = {M_JUNE: {"segments": [{"kind": k, "from": s[i], "to": s[i]} for i, k in enumerate(kinds)]}}
        scenes = gm.scene_of(self.index(), proc)
        self.assertEqual([scenes[s[i]] for i in range(4)], ["議案質疑", "委員長報告", "討論", "提案説明"])

    def test_scene_in_candidates(self):
        s = self.SIDS
        index = [speech(s[1], "教育振興基本計画"), speech(s[3], "教育振興基本計画")]
        proc = {M_JUNE: {"segments": [{"kind": "ippan", "from": s[1], "to": s[1]}]}}
        g = gm.gen_minutes(index, self.mdates, gm.scene_of(index, proc), self.refs, self.names)
        self.assertEqual([(r["from"], r["scene"]) for r in g.candidates],
                         [(f"sp:{s[1]}", "一般質問"), (f"sp:{s[3]}", "範囲外")])

    def test_errors_stop(self):
        s = self.SIDS
        bad = {
            "重なり": [{"kind": "ippan", "from": s[0], "to": s[2]}, {"kind": "shitsugi", "from": s[2], "to": s[3]}],
            "端の欠落": [{"kind": "ippan", "from": s[0], "to": f"{M_JUNE}_20250612_0099"}],
            "逆順": [{"kind": "ippan", "from": s[3], "to": s[1]}],
            "未知の場面": [{"kind": "unknown", "from": s[0], "to": s[0]}],
        }
        for name, segs in bad.items():
            with self.subTest(name=name):
                with self.assertRaises(gm.GenError):
                    gm.scene_of(self.index(), {M_JUNE: {"segments": segs}})


# 7. 計画：manifest に載っているものだけ（_charttest.json を読まない）
class TestPlans(GenTestCase):
    def test_charttest_not_listed(self):
        manifest = {"plans": [{"id": "kodomo", "name": "a"}, {"id": "koutsu", "name": "b"}, {"id": "sogo6", "name": "c"}]}
        listed = ["data/plans/_charttest.json", "data/plans/kodomo.json", "data/plans/koutsu.json"]
        self.assertEqual(gm.manifest_plan_paths(manifest, listed), ["data/plans/kodomo.json", "data/plans/koutsu.json"])

    def test_lineage_plan_missing_in_manifest_stops(self):
        manifest = {"plans": [p for p in self.manifest["plans"] if p["id"] != "kyoiku4"]}
        with self.assertRaises(gm.GenError):
            gm.plan_names(manifest, self.refs)


# 8. where：最初に一致した欄。同じ to の後の欄は note。other と answers の label は照合しない
class TestBulletinWhere(GenTestCase):
    ML = {"35": {"中西 佳子": {"meeting_id": M_JUNE}}}

    def gen(self, q):
        return gm.gen_bulletin([q], self.ML, self.mdates, self.refs, self.names)

    def test_first_field_and_note(self):
        q = question(35, "中西 佳子", 2, "子育ての質問",
                     question_text="日野町総合計画について",
                     answers=[{"label": "教育振興基本計画", "text": "総合計画に基づき進める"},
                              {"label": "町長", "text": "教育振興基本計画を見直す"}],
                     other=[{"label": "要望", "text": "地域防災計画を見直されたい"}])
        rows = self.gen(q).candidates
        self.assertEqual([(r["to"], r["where"], r["evidence"]) for r in rows], [
            ("plan:kyoiku4", "answers", "教育振興基本計画"),
            ("plan:sogo6", "question_text", "日野町総合計画")])
        self.assertIn("ほかに一致した欄：answers", rows[1]["note"])
        self.assertNotIn("ほかに一致した欄", rows[0]["note"])
        for r in rows:
            self.assertEqual(r["from"], "bq:35/中西佳子/2")
            self.assertEqual(r["speech_date"], "2025-06-02")
            self.assertEqual(r["scene"], "")

    def test_answers_element_where_is_answers(self):
        # D4：answers の要素から出た行の where は、§3 の値「answers」（要素の番号は付けない）
        q = question(35, "中西 佳子", 1, "題名", question_text="質問",
                     answers=[{"label": "町長", "text": "答弁"}, {"label": "教育長", "text": "第4期日野町教育振興基本計画で"}])
        rows = self.gen(q).candidates
        self.assertEqual([(r["to"], r["where"]) for r in rows], [("plan:kyoiku4", "answers")])

    def test_other_field_listed_once(self):
        # answers の2つの要素がどちらも同じ to に一致しても、「ほかに一致した欄」の answers は1回だけ
        q = question(35, "中西 佳子", 4, "題名", question_text="日野町総合計画について",
                     answers=[{"label": "町長", "text": "総合計画に基づく"}, {"label": "課長", "text": "総合計画の施策"}])
        rows = self.gen(q).candidates
        self.assertEqual([(r["to"], r["where"]) for r in rows], [("plan:sogo6", "question_text")])
        self.assertTrue(rows[0]["note"].endswith("ほかに一致した欄：answers"))
        self.assertEqual(rows[0]["note"].count("answers"), 1)

    def test_unpublished_title_only(self):
        rows = self.gen(question(35, "中西 佳子", 3, "総合計画の見直しについて")).candidates
        self.assertEqual([(r["to"], r["where"]) for r in rows], [("plan:sogo6", "title")])


# 9. to_label：plan は manifest の name、lin は系譜表の name
class TestToLabel(GenTestCase):
    def test_plan_and_lin(self):
        self.assertEqual(gm.to_label("plan:shogai-fukushi7", self.names, self.refs),
                         "第7期 障がい福祉計画・第3期 障がい児福祉計画")
        self.assertEqual(gm.to_label("lin:sogo/5", self.names, self.refs), "第5次日野町総合計画")
        with self.assertRaises(gm.GenError):
            gm.to_label("lin:sogo/9", self.names, self.refs)

    def test_in_candidates(self):
        index = [speech(f"{M_JUNE}_20250612_0001", "第7期障がい福祉計画・第3期障がい児福祉計画と第五次日野町総合計画")]
        g = gm.gen_minutes(index, self.mdates, {}, self.refs, self.names)
        self.assertEqual([(r["to"], r["to_label"]) for r in g.candidates], [
            ("lin:sogo/5", "第5次日野町総合計画"),
            ("plan:shogai-fukushi7", "第7期 障がい福祉計画・第3期 障がい児福祉計画")])


# 10. 一覧の1件化（同じ質問の複数の欄に同じ言及があっても1件）
class TestListedOnce(GenTestCase):
    def test_out_of_period_once(self):
        ml = {"30": {"日野 一郎": {"meeting_id": M_2018}}}
        q = question(30, "日野 一郎", 1, "教育振興基本計画", question_text="教育振興基本計画の評価",
                     answers=[{"label": "教育長", "text": "第1期子ども・子育て支援事業計画と教育振興基本計画"}])
        g = gm.gen_bulletin([q], ml, self.mdates, self.refs, self.names)
        self.assertEqual(g.candidates, [])
        self.assertEqual([(r["series"], r["where"], r["fiscal_year"]) for r in g.out_of_period], [("kyoiku", "title", "2018")])
        self.assertEqual([(r["series"], r["edition"], r["where"]) for r in g.no_edition], [("kodomo", "1", "answers")])


# 11. TSV の形（§1）と candidate の列（§3）
class TestTsv(GenTestCase):
    def test_format_and_sort(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "x.tsv")
            gm.write_tsv(p, ["from", "to"], [{"from": "sp:b", "to": "plan:a"}, {"from": "bq:1/a/1", "to": "plan:z"},
                                            {"from": "bq:1/a/1", "to": "plan:b"}])
            with open(p, "rb") as f:
                raw = f.read()
        self.assertFalse(raw.startswith(b"\xef\xbb\xbf"))
        self.assertNotIn(b"\r", raw)
        self.assertEqual(raw.decode("utf-8"), "from\tto\nbq:1/a/1\tplan:b\nbq:1/a/1\tplan:z\nsp:b\tplan:a\n")

    def test_tab_or_newline_in_cell_stops(self):
        with tempfile.TemporaryDirectory() as d:
            for bad in ["a\tb", "a\nb"]:
                with self.subTest(bad=bad):
                    with self.assertRaises(gm.GenError):
                        gm.write_tsv(os.path.join(d, "x.tsv"), ["from"], [{"from": bad}])

    def test_candidate_columns(self):
        g = gm.gen_minutes([speech(f"{M_JUNE}_20250612_0001", "教育振興基本計画")], self.mdates, {}, self.refs, self.names)
        r = g.candidates[0]
        self.assertEqual(gm.CANDIDATE_COLUMNS, ["from", "to", "method", "evidence", "where", "context", "to_label",
                                                "status", "reviewer", "date", "note", "speech_date", "scene"])
        self.assertEqual(sorted(r), sorted(gm.CANDIDATE_COLUMNS))
        self.assertEqual((r["method"], r["where"], r["status"], r["reviewer"], r["date"]),
                         ("mention", "text", "candidate", "", ""))


# 12. lock の読み込みの制限（§10）
class TestLock(unittest.TestCase):
    LOCK = {
        "council-dashboard": {"sha": "a" * 40, "files": ["docs/data/questions.json"]},
        "hino-council-search": {"sha": "b" * 40, "files": ["public/data/index/*.json"]},
        "shiga-hino-plans": {"sha": "c" * 40, "files": ["data/manifest.json"]},
    }

    def test_match(self):
        self.assertTrue(gm.match_lock("public/data/index/*.json", "public/data/index/2025.json"))
        self.assertFalse(gm.match_lock("public/data/index/*.json", "public/data/index/sub/2025.json"))
        self.assertFalse(gm.match_lock("public/data/index/*.json", "public/data/index/2025.txt"))
        self.assertTrue(gm.match_lock("data/manifest.json", "data/manifest.json"))
        self.assertFalse(gm.match_lock("data/manifest.json", "data/manifest.json.bak"))

    def test_read_outside_lock_stops_before_git(self):
        inputs = gm.GitInputs("/nonexistent", self.LOCK)
        for repo, path in [("council-dashboard", "README.md"), ("shiga-hino-plans", "data/plans/_charttest.json"),
                           ("unknown-repo", "data/manifest.json")]:
            with self.subTest(path=path):
                with self.assertRaises(gm.GenError):
                    inputs.read_bytes(repo, path)

    def test_load_lock(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "inputs.lock.json")
            for lock in [self.LOCK,
                         {**self.LOCK, "council-dashboard": {"sha": "a" * 39, "files": ["x"]}},
                         {k: v for k, v in self.LOCK.items() if k != "shiga-hino-plans"}]:
                with open(p, "w", encoding="utf-8") as f:
                    json.dump(lock, f)
                if lock is self.LOCK:
                    self.assertEqual(gm.load_lock(p), self.LOCK)
                else:
                    with self.assertRaises(gm.GenError):
                        gm.load_lock(p)


# 13. D2：date が null の会議の発言は、索引の date 項目に値があっても no_date に出る。
#     date を会議名から求めた会議（dateFrom が name）の発言は、その日付で照合する
class TestNoDateIgnoresIndexDate(GenTestCase):
    def test_null_date_meeting_goes_to_no_date(self):
        sid = f"{M_NODATE}_kaigiroku-honbun_0004"
        g = gm.gen_minutes([speech(sid, "教育振興基本計画")], self.mdates, {}, self.refs, self.names)
        self.assertEqual((g.candidates, g.out_of_period, g.no_edition), ([], [], []))
        self.assertEqual([(r["from"], r["meeting_id"]) for r in g.no_date], [(f"sp:{sid}", M_NODATE)])
        self.assertIn("date が null", g.no_date[0]["reason"])

    def test_name_date_meeting_matched(self):
        sid = f"{M_NAME}_2gijiroku_0003"
        g = gm.gen_minutes([speech(sid, "教育振興基本計画")], self.mdates, {}, self.refs, self.names)
        self.assertEqual(g.no_date, [])
        self.assertEqual([(r["from"], r["to"], r["speech_date"]) for r in g.candidates],
                         [(f"sp:{sid}", "plan:kyoiku3", "2021-02-10")])

    def test_index_date_not_used(self):
        sid = f"{M_NODATE}_kaigiroku-honbun_0003"
        index = [speech(sid, "教育振興基本計画と滋賀県地域防災計画と日野町総合計画", day="2021-02-10")]
        g = gm.gen_minutes(index, self.mdates, {}, self.refs, self.names)
        self.assertEqual((g.candidates, g.out_of_period, g.no_edition), ([], [], []))
        self.assertEqual(len(g.no_date), 1)
        row = g.no_date[0]
        self.assertEqual((row["from"], row["meeting_id"], row["scene"]), (f"sp:{sid}", M_NODATE, "範囲外"))
        self.assertEqual(row["matched_series"], "kyoiku、sogo")  # 除外の語（滋賀県地域防災計画）は数えない
        self.assertEqual(row["index_date"], "2021-02-10")       # 参考。照合には使わない


# 14. 同じ入力から2回作った出力が、バイト単位で同じ
class TestDeterministic(GenTestCase):
    def sample_inputs(self):
        s = [f"{M_JUNE}_20250612_{n:04d}" for n in range(1, 5)]
        return gm.Inputs(
            lock={"council-dashboard": {"sha": "a" * 40, "files": []},
                  "hino-council-search": {"sha": "b" * 40, "files": []},
                  "shiga-hino-plans": {"sha": "c" * 40, "files": []}},
            questions=[question(35, "中西 佳子", 1, "総合計画", question_text="第3期子ども・子育て支援事業計画「の」",
                                answers=[{"label": "町長", "text": "教育振興基本計画"}]),
                       question(36, "日野 一郎", 1, "地域防災計画")],
            minutes_links={"35": {"中西 佳子": {"meeting_id": M_JUNE}}},
            meetings=MEETINGS,
            index=[speech(s[0], "第3期「子ども・子育て支援事業計画」と教育振興基本計画", role="町長"),
                   speech(s[1], "議長の発言 教育振興基本計画", role="議長"),
                   speech(s[2], "日野町総合計画と第1期子ども・子育て支援事業計画", role="副議長"),
                   speech(f"{M_JUNE}_8.5rmokuji_0000", "目次 日野町地域防災計画", role=""),
                   speech(f"{M_2018}_20180613_0001", "教育振興基本計画"),
                   speech(f"{M_NODATE}_kaigiroku_0001", "教育振興基本計画", day="2021-02-10")],
            proceedings={M_JUNE: {"segments": [{"kind": "ippan", "from": s[0], "to": s[2]}]}},
            manifest=self.manifest,
            plan_listing=["data/plans/_charttest.json", "data/plans/kodomo.json"],
            ref_hashes={"ref/lineage.tsv": "0" * 64, "ref/aliases.tsv": "1" * 64, "tools/mention.py": "2" * 64},
        )

    def test_twice_identical(self):
        outs = []
        for _ in range(2):
            built = gm.build(self.sample_inputs(), self.refs)
            with tempfile.TemporaryDirectory() as d:
                names = gm.write_outputs(d, built)
                files = {}
                for n in names:
                    with open(os.path.join(d, n), "rb") as f:
                        files[n] = f.read()
                outs.append(files)
        self.assertEqual(sorted(outs[0]), ["candidates.tsv", "no_date.tsv", "no_edition.tsv",
                                           "out_of_period.tsv", "report.md"])
        self.assertEqual(outs[0], outs[1])
        report = outs[0]["report.md"].decode("utf-8")
        self.assertNotIn(f"sp:{M_JUNE}_8.5rmokuji_0000", outs[0]["candidates.tsv"].decode("utf-8"))
        for needle in ["a" * 40, "b" * 40, "c" * 40, "0" * 64, "会議の初日", "副議長", "_charttest.json",
                       "- 除いた目次の項目 1 件\n"]:
            with self.subTest(needle=needle):
                self.assertIn(needle, report)


if __name__ == "__main__":
    unittest.main()
