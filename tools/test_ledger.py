"""tools/ledger.py・tools/update_links.py・tools/check_links.py の検査（LINK_SCHEMA.md §1〜§3・§5・§6・§11、
DESIGN.md §5 工程4-3・4-4）。

実行: python3 -B tools/test_ledger.py -v
入力のデータは小さな見本を使い、候補は tools/gen_mentions.py の build で作る。参照表は実物（ref/lineage.tsv・
ref/aliases.tsv）を読む。参照表の場所は、環境変数 HINO_RONTEN_LINEAGE・HINO_RONTEN_ALIASES で変えられる。
"""
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import check_links  # noqa: E402
import gen_mentions as gm  # noqa: E402
import ledger  # noqa: E402
import mention  # noqa: E402
import update_links  # noqa: E402

LINEAGE = os.environ.get("HINO_RONTEN_LINEAGE", os.path.join(ROOT, "ref", "lineage.tsv"))
ALIASES = os.environ.get("HINO_RONTEN_ALIASES", os.path.join(ROOT, "ref", "aliases.tsv"))

M = "0000000001"  # 見本の会議（2025-06-12。令和7年度）
MEETINGS = [{"id": M, "name": "令和7年6月定例会議", "date": "2025-06-12", "dateFrom": "pdf",
             "pdfs": [{"label": "第1日", "date": "2025-06-12", "url": "u1"}]}]
PLAN_NAMES = {"kyoiku4": "第4期 日野町教育振興基本計画", "kodomo": "第3期 日野町子ども・子育て支援事業計画",
              "sogo6": "第6次日野町総合計画"}

# 見本の発言（連番の順）。計画名を含むのは 1〜4 だけ
TEXTS = [
    "教育振興基本計画の進み具合を伺います",        # 1 → plan:kyoiku4
    "子ども・子育て支援事業計画について質問します",  # 2 → plan:kodomo
    "日野町総合計画に沿って進めてまいります",        # 3 → plan:sogo6
    "第2期子ども・子育て支援事業計画を振り返ります",  # 4 → lin:kodomo/2
    "ありがとうございました", "次の質問に移ります", "以上で終わります", "答弁を求めます",
    "お答えいたします", "再質問をします", "よろしくお願いします", "休憩します",
]
FILLER = "本日の会議を開きます"  # 計画名を含まない発言


def sid(n):
    return f"{M}_20250612_{n:04d}"


def index_of(texts):
    """連番1から順に発言を並べた索引。"""
    return [{"sid": sid(i), "meetingId": M, "role": "1番", "name": "見本", "text": t, "date": "2025-06-12"}
            for i, t in enumerate(texts, start=1)]


def question(answers):
    return {"issue": 35, "member": "中西 佳子", "q_num": 1, "title": "子育ての支援",
            "question_text": "子育ての支援を伺う", "answer_title": "", "answers": answers, "other": []}


ANSWERS = [{"label": "町長", "text": "検討します"}, {"label": "教育長", "text": "教育振興基本計画に基づき進めます"}]
BQ = "bq:35/中西佳子/1"


class LedgerTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.refs = mention.load_refs(LINEAGE, ALIASES)
        plans, seen = [], set()
        for r in cls.refs.lineage:
            if r.plan and r.plan not in seen:
                seen.add(r.plan)
                plans.append({"id": r.plan, "name": PLAN_NAMES.get(r.plan, f"見本の名称 {r.plan}")})
        cls.manifest = {"schema": 1, "plans": plans}

    def inputs(self, texts=TEXTS, answers=ANSWERS):
        return gm.Inputs(
            lock={"council-dashboard": {"sha": "a" * 40, "files": []},
                  "hino-council-search": {"sha": "b" * 40, "files": []},
                  "shiga-hino-plans": {"sha": "c" * 40, "files": []}},
            questions=[question(answers)], minutes_links={"35": {"中西 佳子": {"meeting_id": M}}},
            meetings=MEETINGS, index=index_of(texts), proceedings={}, manifest=self.manifest,
            plan_listing=[], ref_hashes={})

    def built(self, **kw):
        return gm.build(self.inputs(**kw), self.refs)

    def gen_and_corpus(self, **kw):
        b = self.built(**kw)
        return ledger.generated_rows(b), ledger.make_corpus(b.inputs, b.refs)

    def base(self):
        """見本の入力で、空の台帳から作った台帳（すべて candidate）。"""
        gen, corpus = self.gen_and_corpus()
        return ledger.merge([], gen, corpus).rows

    @staticmethod
    def row(rows, frm, to):
        hits = [r for r in rows if r["from"] == frm and r["to"] == to]
        assert len(hits) == 1, (frm, to, hits)
        return hits[0]

    def decide(self, rows, frm, to, status, note="見本の判断"):
        """人の確定・却下（status・reviewer・date・note を書く）。"""
        out = [dict(r) for r in rows]
        r = self.row(out, frm, to)
        r.update(status=status, reviewer="見本", date="2026-10-11", note=note)
        return out


# 0. 見本の前提（生成の結果）
class TestSample(LedgerTestCase):
    def test_generated(self):
        keys = sorted((r["from"], r["to"], r["where"]) for r in self.base())
        self.assertEqual(keys, [(BQ, "plan:kyoiku4", "answers"),
                                (f"sp:{sid(1)}", "plan:kyoiku4", "text"),
                                (f"sp:{sid(2)}", "plan:kodomo", "text"),
                                (f"sp:{sid(3)}", "plan:sogo6", "text"),
                                (f"sp:{sid(4)}", "lin:kodomo/2", "text")])


# 1. 台帳の形（§1・§3・§11）
class TestFormat(LedgerTestCase):
    def test_round_trip_and_order(self):
        rows = self.base()
        data = ledger.format_ledger(rows)
        self.assertTrue(data.startswith("\t".join(ledger.LEDGER_COLUMNS).encode("utf-8") + b"\n"))
        self.assertEqual(ledger.parse_ledger(data, "mention"), rows)
        # bq: の行が sp: の行より先（文字コード順）
        self.assertEqual([r["from"][:3] for r in rows], ["bq:", "sp:", "sp:", "sp:", "sp:"])

    def test_unsorted_stops(self):
        lines = ledger.format_ledger(self.base()).decode("utf-8").split("\n")
        lines[2], lines[3] = lines[3], lines[2]
        with self.assertRaises(ledger.LedgerError) as cm:
            ledger.parse_ledger("\n".join(lines).encode("utf-8"), "mention")
        self.assertIn("文字コード順", str(cm.exception))

    def test_file_level_errors_stop(self):
        good = ledger.format_ledger(self.base())
        cases = {"BOM": b"\xef\xbb\xbf" + good, "CR": good.replace(b"\n", b"\r\n"),
                 "最後の改行なし": good[:-1], "ヘッダ": good.replace(b"from\tto", b"to\tfrom", 1),
                 "列の数": good.replace(b"\tcandidate\t", b"\tcandidate\t\t", 1)}
        for name, data in cases.items():
            with self.subTest(name=name):
                with self.assertRaises(ledger.LedgerError):
                    ledger.parse_ledger(data, "mention")

    def test_row_errors_stop(self):
        sp = f"sp:{sid(2)}"
        cases = {
            "from の形": {"from": "sp:12345_x_0001"},
            "from に plan": {"from": "plan:kodomo"},
            "to の形": {"to": "plan:Kodomo"},
            "mention の to に node": {"to": "node:kodomo/第1節/(1)/①"},
            "method がファイルと違う": {"method": "program"},
            "crosswalk": {"method": "crosswalk"},
            "status": {"status": "保留"},
            "confirmed に reviewer なし": {"status": "confirmed", "date": "2026-10-11"},
            "confirmed の date": {"status": "confirmed", "reviewer": "見本", "date": "2026/10/11"},
            "candidate に reviewer": {"reviewer": "見本"},
            "rejected の note が空": {"status": "rejected", "reviewer": "見本", "date": "2026-10-11", "note": ""},
            "sp の where": {"where": "title"},
            "evidence が正規化されていない": {"evidence": "子ども・子育て 支援事業計画"},
            "context に evidence が無い": {"context": "について質問します"},
        }
        for name, change in cases.items():
            with self.subTest(name=name):
                rows = [dict(r) for r in self.base()]
                self.row(rows, sp, "plan:kodomo").update(change)
                rows.sort(key=lambda r: (r["from"], r["to"], r["method"]))
                with self.assertRaises(ledger.LedgerError):
                    ledger.parse_ledger(ledger.format_ledger(rows), "mention")

    def test_duplicate_key_stops(self):
        rows = self.base()
        dup = dict(self.row(rows, f"sp:{sid(2)}", "plan:kodomo"), note="別の行")
        data = ledger.format_ledger(rows + [dup])
        with self.assertRaises(ledger.LedgerError) as cm:
            ledger.parse_ledger(data, "mention")
        self.assertIn("重なっている", str(cm.exception))


# 2. sp の照合（§5）：一致・移動・停止
class TestMatchSp(LedgerTestCase):
    def test_match(self):
        gen, corpus = self.gen_and_corpus()
        ck = ledger.check_rows(self.base(), corpus)
        self.assertEqual((ck.counts[ledger.MATCH], ck.moved, ck.stopped), (5, [], []))

    def test_context_renormalized(self):
        # 台帳の context に §4 をかけ直してから比べる（全角の数字・空白は正規化で消える）
        _, corpus = self.gen_and_corpus()
        r = dict(self.row(self.base(), f"sp:{sid(4)}", "lin:kodomo/2"), context="第２期子ども・子育て 支援事業計画")
        self.assertEqual(ledger.match_row(r, corpus).result, ledger.MATCH)

    def test_moved(self):
        # 連番1の前に発言が1つ入り、連番が1つずつずれた
        _, corpus = self.gen_and_corpus(texts=[FILLER] + TEXTS)
        m = ledger.match_row(self.row(self.base(), f"sp:{sid(1)}", "plan:kyoiku4"), corpus)
        self.assertEqual((m.result, m.moved_to), (ledger.MOVED, f"sp:{sid(2)}"))

    def test_stopped_zero(self):
        _, corpus = self.gen_and_corpus(texts=[FILLER] + TEXTS[1:])
        m = ledger.match_row(self.row(self.base(), f"sp:{sid(1)}", "plan:kyoiku4"), corpus)
        self.assertEqual(m.result, ledger.STOPPED)
        self.assertIn("0 件", m.reason)

    def test_stopped_two(self):
        # 前後5件の2つの発言が context を含む
        _, corpus = self.gen_and_corpus(texts=[FILLER, TEXTS[0], TEXTS[0]] + TEXTS[1:])
        m = ledger.match_row(self.row(self.base(), f"sp:{sid(1)}", "plan:kyoiku4"), corpus)
        self.assertEqual(m.result, ledger.STOPPED)
        self.assertIn("2 件", m.reason)

    def test_beyond_five_stops(self):
        _, corpus = self.gen_and_corpus(texts=[FILLER] * 6 + TEXTS)
        m = ledger.match_row(self.row(self.base(), f"sp:{sid(1)}", "plan:kyoiku4"), corpus)
        self.assertEqual(m.result, ledger.STOPPED)

    def test_sid_missing(self):
        _, corpus = self.gen_and_corpus()
        r = dict(self.row(self.base(), f"sp:{sid(1)}", "plan:kyoiku4"), **{"from": f"sp:{sid(30)}"})
        m = ledger.match_row(r, corpus)
        self.assertEqual(m.result, ledger.STOPPED)
        self.assertIn("sid が無く", m.reason)


# 3. bq の照合（§5）：answers は要素のいずれかに含まれれば一致
class TestMatchBq(LedgerTestCase):
    def test_answers_element(self):
        r = self.row(self.base(), BQ, "plan:kyoiku4")
        self.assertEqual(r["where"], "answers")
        _, corpus = self.gen_and_corpus(answers=list(reversed(ANSWERS)))  # 要素の順が変わっても一致
        self.assertEqual(ledger.match_row(r, corpus).result, ledger.MATCH)

    def test_answers_changed_stops(self):
        r = self.row(self.base(), BQ, "plan:kyoiku4")
        _, corpus = self.gen_and_corpus(answers=[ANSWERS[0], {"label": "教育長", "text": "教育振興基本計画で進めます"}])
        m = ledger.match_row(r, corpus)
        self.assertEqual(m.result, ledger.STOPPED)
        self.assertIn("answers", m.reason)

    def test_other_field_not_used(self):
        # where が answers の行は、ほかの欄に context があっても一致にしない
        r = self.row(self.base(), BQ, "plan:kyoiku4")
        _, corpus = self.gen_and_corpus(answers=[ANSWERS[0]])
        self.assertEqual(ledger.match_row(r, corpus).result, ledger.STOPPED)


# 4. plan・lin の名称の照合（§5）
class TestMatchLabel(LedgerTestCase):
    def test_label_changed_stops(self):
        _, corpus = self.gen_and_corpus()
        rows = self.decide(self.base(), f"sp:{sid(3)}", "plan:sogo6", "confirmed")
        self.row(rows, f"sp:{sid(3)}", "plan:sogo6")["to_label"] = "第6次 日野町総合計画（旧）"
        ck = ledger.check_rows(rows, corpus)
        self.assertEqual([(r["from"], r["status"]) for r in ck.stopped], [(f"sp:{sid(3)}", "confirmed")])
        self.assertIn("いまの名称", ck.stopped[0]["reason"])
        gen, _ = self.gen_and_corpus()
        self.assertEqual(ledger.check_ledger(rows, gen, corpus).exit_code, 1)

    def test_lin_label(self):
        _, corpus = self.gen_and_corpus()
        r = self.row(self.base(), f"sp:{sid(4)}", "lin:kodomo/2")
        self.assertEqual(r["to_label"], self.refs.edition_row("kodomo", 2).name)
        self.assertEqual(ledger.match_label(r, corpus).result, ledger.MATCH)


# 5. 併合（§6）：candidate は機械が持つ行、confirmed・rejected は11列を変えない
class TestMerge(LedgerTestCase):
    def test_from_empty_all_candidate(self):
        gen, corpus = self.gen_and_corpus()
        m = ledger.merge([], gen, corpus)
        self.assertEqual(len(m.added), 5)
        self.assertEqual({(r["status"], r["reviewer"], r["date"]) for r in m.rows}, {("candidate", "", "")})

    def test_note_changed(self):
        # 人が candidate の行の note に書いても、再生成で置き換わり、note_changed に出る
        gen, corpus = self.gen_and_corpus()
        rows = [dict(r) for r in self.base()]
        r = self.row(rows, f"sp:{sid(2)}", "plan:kodomo")
        new_note = r["note"]
        r["note"] = "人のメモ"
        m = ledger.merge(rows, gen, corpus)
        self.assertEqual(self.row(m.rows, f"sp:{sid(2)}", "plan:kodomo")["note"], new_note)
        self.assertEqual(m.note_changed, [{"from": f"sp:{sid(2)}", "to": "plan:kodomo", "method": "mention",
                                           "old_note": "人のメモ", "new_note": new_note}])

    def test_candidate_all_columns_replaced(self):
        # 本文が変わると、candidate の evidence 以外の欄（context）も新しい値になる
        texts = list(TEXTS)
        texts[1] = "改めて子ども・子育て支援事業計画について質問します"
        gen, corpus = self.gen_and_corpus(texts=texts)
        m = ledger.merge(self.base(), gen, corpus)
        new = self.row(m.rows, f"sp:{sid(2)}", "plan:kodomo")
        self.assertEqual(new, self.row(ledger.merge([], gen, corpus).rows, f"sp:{sid(2)}", "plan:kodomo"))
        self.assertIn("改めて", new["context"])
        self.assertEqual(len(m.updated), 1)

    def test_decided_rows_unchanged(self):
        texts = list(TEXTS)
        texts[1] = "改めて子ども・子育て支援事業計画について質問します"
        gen, corpus = self.gen_and_corpus(texts=texts)
        for status in ("confirmed", "rejected"):
            with self.subTest(status=status):
                rows = self.decide(self.base(), f"sp:{sid(2)}", "plan:kodomo", status)
                before = self.row(rows, f"sp:{sid(2)}", "plan:kodomo")
                after = self.row(ledger.merge(rows, gen, corpus).rows, f"sp:{sid(2)}", "plan:kodomo")
                self.assertEqual(after, before)

    def test_vanished(self):
        # 発言から計画名が消えた：candidate は削除、confirmed・rejected は残して vanished に出す
        texts = list(TEXTS)
        texts[1] = FILLER
        gen, corpus = self.gen_and_corpus(texts=texts)
        m = ledger.merge(self.base(), gen, corpus)
        self.assertEqual([(r["from"], r["to"]) for r in m.removed], [(f"sp:{sid(2)}", "plan:kodomo")])
        self.assertEqual(m.vanished, [])
        for status in ("confirmed", "rejected"):
            with self.subTest(status=status):
                rows = self.decide(self.base(), f"sp:{sid(2)}", "plan:kodomo", status)
                m = ledger.merge(rows, gen, corpus)
                self.assertIn(self.row(rows, f"sp:{sid(2)}", "plan:kodomo"), m.rows)
                self.assertEqual([(r["from"], r["status"], r["check"]) for r in m.vanished],
                                 [(f"sp:{sid(2)}", status, ledger.STOPPED)])
                self.assertEqual(len(m.vanished_confirmed), 1 if status == "confirmed" else 0)
                # 根拠の消失：confirmed なら終了コード1。rejected は一覧に出すだけ
                self.assertEqual(ledger.check_ledger(m.rows, gen, corpus).exit_code, 1 if status == "confirmed" else 0)

    def test_generated_must_be_candidate(self):
        gen, corpus = self.gen_and_corpus()
        gen[0] = dict(gen[0], status="confirmed")
        with self.assertRaises(ledger.LedgerError):
            ledger.merge([], gen, corpus)


# 6. 移動した confirmed・rejected（§5・§6）：移動先に candidate を作らず、出なくなった行に数えない
class TestMovedDecided(LedgerTestCase):
    def test_confirmed_and_rejected_moved(self):
        rows = self.decide(self.base(), f"sp:{sid(1)}", "plan:kyoiku4", "confirmed")
        rows = self.decide(rows, f"sp:{sid(2)}", "plan:kodomo", "rejected", note="見本の却下の理由")
        gen, corpus = self.gen_and_corpus(texts=[FILLER] + TEXTS)
        m = ledger.merge(rows, gen, corpus)
        keys = {(r["from"], r["to"]) for r in m.rows}
        self.assertNotIn((f"sp:{sid(2)}", "plan:kyoiku4"), keys)   # 移動先に candidate を作らない
        self.assertNotIn((f"sp:{sid(3)}", "plan:kodomo"), keys)
        self.assertEqual(sorted((r["from"], r["to"]) for r in m.suppressed),
                         [(f"sp:{sid(2)}", "plan:kyoiku4"), (f"sp:{sid(3)}", "plan:kodomo")])
        self.assertEqual(m.vanished, [])
        ck = ledger.check_rows(m.rows, corpus)
        self.assertEqual(sorted((r["from"], r["status"], r["moved_to"]) for r in ck.moved),
                         [(f"sp:{sid(1)}", "confirmed", f"sp:{sid(2)}"), (f"sp:{sid(2)}", "rejected", f"sp:{sid(3)}")])
        self.assertEqual((ck.stopped, ck.rejected_unmatched), ([], []))

    def test_candidate_at_destination_dropped(self):
        # 続く発言も同じ計画に触れていた：移動先の組の candidate が台帳にあっても candidate にしない
        texts = [TEXTS[0], "教育振興基本計画の評価を伺います"] + TEXTS[2:]
        gen, corpus = self.gen_and_corpus(texts=texts)
        rows = self.decide(ledger.merge([], gen, corpus).rows, f"sp:{sid(1)}", "plan:kyoiku4", "confirmed")
        self.assertEqual(self.row(rows, f"sp:{sid(2)}", "plan:kyoiku4")["status"], "candidate")
        gen, corpus = self.gen_and_corpus(texts=[FILLER] + texts)
        m = ledger.merge(rows, gen, corpus)
        kyoiku = sorted((r["from"], r["status"]) for r in m.rows if r["to"] == "plan:kyoiku4" and r["from"].startswith("sp:"))
        self.assertEqual(kyoiku, [(f"sp:{sid(1)}", "confirmed"), (f"sp:{sid(3)}", "candidate")])
        self.assertEqual([r["from"] for r in m.suppressed], [f"sp:{sid(2)}"])
        self.assertEqual([r for r in m.removed if r["to"] == "plan:kyoiku4"], [])  # ほかの計画の行は連番がずれて付け替わる
        self.assertEqual(m.vanished, [])
        rep = ledger.check_ledger(m.rows, gen, corpus)  # 作り直しても同じ（台帳と lock の版が食い違わない）
        self.assertEqual((rep.stale, rep.exit_code), ([], 0))

    def test_moved_but_destination_not_generated(self):
        # 移動先は見つかるが、生成の結果に移動先の組が無い（別の発言に同じ context）→ 出なくなった confirmed
        texts = [FILLER, "教育振興基本計画の進み具合を伺います"] + TEXTS[1:]
        rows = self.decide(self.base(), f"sp:{sid(1)}", "plan:kyoiku4", "confirmed")
        gen, corpus = self.gen_and_corpus(texts=texts)
        gen = [g for g in gen if g["to"] != "plan:kyoiku4"]
        m = ledger.merge(rows, gen, corpus)
        self.assertEqual([(r["from"], r["check"]) for r in m.vanished_confirmed], [(f"sp:{sid(1)}", ledger.MOVED)])

    def test_rejected_unmatched_does_not_stop(self):
        rows = self.decide(self.base(), f"sp:{sid(2)}", "plan:kodomo", "rejected", note="見本の却下の理由")
        texts = list(TEXTS)
        texts[1] = FILLER
        gen, corpus = self.gen_and_corpus(texts=texts)
        rep = ledger.check_ledger(rows, gen, corpus)
        self.assertEqual([(r["from"], r["status"]) for r in rep.checked.rejected_unmatched],
                         [(f"sp:{sid(2)}", "rejected")])
        self.assertEqual(rep.checked.stopped, [])
        self.assertEqual(rep.exit_code, 0)

    def test_rejected_bq_not_checked(self):
        rows = self.decide(self.base(), BQ, "plan:kyoiku4", "rejected", note="見本の却下の理由")
        gen, corpus = self.gen_and_corpus(answers=[ANSWERS[0]])
        ck = ledger.check_rows(rows, corpus)
        self.assertEqual((ck.moved, ck.stopped, ck.rejected_unmatched), ([], [], []))


# 7. sentinel（§11）：confirmed・candidate の全行で、1文字替えると移動か停止になる
class TestSentinel(LedgerTestCase):
    def test_mutate(self):
        self.assertEqual(ledger.mutate_context("教育振興基本計画"), "教育振興〓本計画")
        self.assertEqual(ledger.mutate_context("教育〓興基本計画"), "教育〓興※本計画")
        self.assertEqual(ledger.mutate_context("計画"), "計〓")

    def test_all_rows_pass(self):
        _, corpus = self.gen_and_corpus()
        rows = self.decide(self.base(), f"sp:{sid(1)}", "plan:kyoiku4", "confirmed")
        self.assertEqual(ledger.sentinel(rows, corpus), [])

    def test_moved_counts_as_pass(self):
        # 1文字替えた context を前後の発言が含む → 移動（一致でないので合格）
        texts = list(TEXTS)
        texts[4] = "教育振興〓本計画の進み具合を伺います"
        _, corpus = self.gen_and_corpus(texts=texts)
        r = self.row(self.base(), f"sp:{sid(1)}", "plan:kyoiku4")
        r = dict(r, context="教育振興基本計画")
        m = ledger.match_row(r, corpus, context=ledger.mutate_context(r["context"]))
        self.assertEqual(m.result, ledger.MOVED)
        self.assertEqual(ledger.sentinel([r], corpus), [])

    def test_failure_detected(self):
        # 本文が、元の context と1文字替えた context の両方を含む → 一致になり、sentinel が止める
        texts = list(TEXTS)
        texts[0] = "教育振興基本計画と教育振興〓本計画"
        _, corpus = self.gen_and_corpus(texts=texts)
        r = dict(self.row(self.base(), f"sp:{sid(1)}", "plan:kyoiku4"), context="教育振興基本計画")
        self.assertEqual(ledger.sentinel([r], corpus),
                         [{"from": f"sp:{sid(1)}", "to": "plan:kyoiku4", "method": "mention", "context": "教育振興〓本計画"}])

    def test_rejected_not_target(self):
        # 本文が元の context と1文字替えた context の両方を含む行でも、rejected なら sentinel の対象外
        ctx = self.row(self.base(), f"sp:{sid(2)}", "plan:kodomo")["context"]
        texts = list(TEXTS)
        texts[1] = ctx + ledger.mutate_context(ctx)
        _, corpus = self.gen_and_corpus(texts=texts)
        rows = [dict(self.row(self.base(), f"sp:{sid(2)}", "plan:kodomo"))]
        self.assertEqual(len(ledger.sentinel(rows, corpus)), 1)  # candidate なら止まる
        rows = self.decide(rows, f"sp:{sid(2)}", "plan:kodomo", "rejected", note="見本の却下の理由")
        self.assertEqual(ledger.sentinel(rows, corpus), [])


# 8. 台帳と lock の版（§6・§11）
class TestStale(LedgerTestCase):
    def test_up_to_date(self):
        gen, corpus = self.gen_and_corpus()
        rep = ledger.check_ledger(self.base(), gen, corpus)
        self.assertEqual((rep.stale, rep.exit_code), ([], 0))

    def test_new_candidate_not_in_ledger(self):
        gen, corpus = self.gen_and_corpus(texts=TEXTS + ["日野町総合計画を見直します"])
        rep = ledger.check_ledger(self.base(), gen, corpus)
        self.assertEqual(rep.stale, [(f"sp:{sid(13)}", "plan:sogo6", "mention")])
        self.assertEqual(rep.exit_code, 1)

    def test_candidate_note_edited(self):
        gen, corpus = self.gen_and_corpus()
        rows = [dict(r) for r in self.base()]
        self.row(rows, f"sp:{sid(2)}", "plan:kodomo")["note"] = "人のメモ"
        rep = ledger.check_ledger(rows, gen, corpus)
        self.assertEqual(rep.stale, [(f"sp:{sid(2)}", "plan:kodomo", "mention")])

    def test_decided_rows_are_not_stale(self):
        gen, corpus = self.gen_and_corpus()
        rows = self.decide(self.base(), f"sp:{sid(2)}", "plan:kodomo", "confirmed")
        self.assertEqual(ledger.check_ledger(rows, gen, corpus).stale, [])


# 9. 道具（update_links.run・check_links.run）：書くもの・終了コード・決定性
class TestTools(LedgerTestCase):
    def files(self, d):
        out = {}
        for base, _, names in os.walk(d):
            for n in names:
                with open(os.path.join(base, n), "rb") as f:
                    out[os.path.relpath(os.path.join(base, n), d)] = f.read()
        return out

    def test_update_then_check(self):
        with tempfile.TemporaryDirectory() as d:
            path, out = os.path.join(d, "links", "mention.tsv"), os.path.join(d, "build")
            code, merged, _ = update_links.run(self.built(), path, out)
            self.assertEqual((code, len(merged.added)), (0, 5))
            self.assertEqual(sorted(os.listdir(out)), ["moved.tsv", "note_changed.tsv", "rejected_unmatched.tsv",
                                                       "removed.tsv", "stopped.tsv", "update.md", "vanished.tsv"])
            code, rows, rep = check_links.run(self.built(), path, out)
            self.assertEqual((code, len(rows)), (0, 5))
            with open(os.path.join(out, "check.md"), encoding="utf-8") as f:
                self.assertIn("判定：合格", f.read())

    def test_twice_identical(self):
        outs = []
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "links", "mention.tsv")
            for n in range(2):
                out = os.path.join(d, f"build{n}")
                code, merged, _ = update_links.run(self.built(), path, out)
                self.assertEqual(code, 0)
                outs.append((self.files(out), open(path, "rb").read()))
            self.assertEqual(len(merged.added), 0)  # 2回目は台帳が変わらない
        self.assertEqual(outs[0][1], outs[1][1])
        self.assertEqual({k: v for k, v in outs[0][0].items() if k != "update.md"},
                         {k: v for k, v in outs[1][0].items() if k != "update.md"})

    def test_update_stops_without_writing(self):
        # confirmed の行が出なくなった（移動先も無い）→ 終了コード1、台帳は書かない
        with tempfile.TemporaryDirectory() as d:
            path, out = os.path.join(d, "mention.tsv"), os.path.join(d, "build")
            ledger.write_ledger(path, self.decide(self.base(), f"sp:{sid(2)}", "plan:kodomo", "confirmed"))
            before = open(path, "rb").read()
            texts = list(TEXTS)
            texts[1] = FILLER
            code, merged, checked = update_links.run(self.built(texts=texts), path, out)
            self.assertEqual(code, 1)
            self.assertEqual(open(path, "rb").read(), before)
            self.assertEqual(len(merged.vanished_confirmed), 1)
            with open(os.path.join(out, "vanished.tsv"), encoding="utf-8") as f:
                self.assertIn(f"sp:{sid(2)}", f.read())

    def test_unsorted_ledger_stops(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "mention.tsv")
            lines = ledger.format_ledger(self.base()).decode("utf-8").split("\n")
            lines[2], lines[3] = lines[3], lines[2]
            with open(path, "wb") as f:
                f.write("\n".join(lines).encode("utf-8"))
            before = open(path, "rb").read()
            for run in (update_links.run, check_links.run):
                with self.subTest(run=run.__module__):
                    with self.assertRaises(ledger.LedgerError):
                        run(self.built(), path, os.path.join(d, "build"))
                    self.assertEqual(open(path, "rb").read(), before)  # 並べ直さない

    def test_check_stale_stops(self):
        with tempfile.TemporaryDirectory() as d:
            path, out = os.path.join(d, "mention.tsv"), os.path.join(d, "build")
            ledger.write_ledger(path, self.base())
            code, _, rep = check_links.run(self.built(texts=TEXTS + ["日野町総合計画を見直します"]), path, out)
            self.assertEqual((code, len(rep.stale)), (1, 1))
            with open(os.path.join(out, "check.md"), encoding="utf-8") as f:
                self.assertIn("tools/update_links.py を先に動かす", f.read())

    def test_check_moved_continues(self):
        # 確定した行の移動は一覧に出すだけで、終了コード0
        with tempfile.TemporaryDirectory() as d:
            path, out = os.path.join(d, "mention.tsv"), os.path.join(d, "build")
            rows = self.decide(self.base(), f"sp:{sid(1)}", "plan:kyoiku4", "confirmed")
            built = self.built(texts=[FILLER] + TEXTS)
            gen = ledger.generated_rows(built)
            ledger.write_ledger(path, ledger.merge(rows, gen, ledger.make_corpus(built.inputs, built.refs)).rows)
            code, _, rep = check_links.run(built, path, out)
            self.assertEqual(code, 0)
            with open(os.path.join(out, "moved.tsv"), encoding="utf-8") as f:
                self.assertIn(f"sp:{sid(1)}\tplan:kyoiku4\tmention\tconfirmed\tsp:{sid(2)}", f.read())

    def test_check_missing_ledger_stops(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ledger.LedgerError):
                check_links.run(self.built(), os.path.join(d, "mention.tsv"), os.path.join(d, "build"))


if __name__ == "__main__":
    unittest.main()
