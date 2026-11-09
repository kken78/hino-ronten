"""提案理由の記録（records/teian.tsv）の検査（LINK_SCHEMA.md §11・§15.11、DESIGN.md ADR-35）。
tools/records.py・tools/gen_teian.py・tools/apply_decisions.py の --ledger teian に足した決まりを確かめる
（提案理由の記録は財源の面だけ。DESIGN.md ADR-35 の決定）。

実行: python3 -B tools/test_teian.py -v
見本の小さな構造化の層（同じ年度の一般会計の回3つと国保の回1つ、○の行5つ）と発言を作り、通る例と通らない例を確かめる。
"""
import io
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import apply_decisions as ad  # noqa: E402
import gen_mentions as gm  # noqa: E402
import gen_teian  # noqa: E402
import hosei  # noqa: E402
import records as rc  # noqa: E402
import test_hosei as th  # noqa: E402

K = ["r6-ippan-01", "r6-ippan-02", "r6-ippan-03"]
KK = "r6-kokuho-01"
MID = "0000000010"
S1 = f"{MID}_20240601_0006"   # 町長の提案理由
S2 = f"{MID}_20240601_0007"   # 議員
S3 = f"{MID}_20240601_0008"   # 区切りに入らない町長の発言


def kai_rows(prev=None):
    prev = prev or {K[0]: "", K[1]: K[0], K[2]: K[1]}
    out = [{"id": k, "fiscal_year": "2024", "kaikei": "ippan", "gou": str(i + 1),
            "title": f"令和６年度日野町一般会計補正予算（第{'１２３'[i]}号）", "prev": prev[k], "prev_from": "号の順",
            "label_mae": "", "label_hosei": "", "note": ""} for i, k in enumerate(K)]
    out.append({"id": KK, "fiscal_year": "2024", "kaikei": "kokuho", "gou": "1", "title": "国民健康保険特別会計補正予算（第 1 号）",
                "prev": "", "prev_from": "", "label_mae": "", "label_hosei": "", "note": ""})
    return out


def maru_rows(extra=()):
    base = {"kind": "maru", "mark": "○", "unit": "千円", "line": "", "sub": "", "doc": "yosan-r6-hosei-06", "page": "2",
            "note": ""}
    rows = [dict(base, kai=K[0], key="m001", name="児童手当支給事業", amount="100", desc="児童手当の経費を新規計上します。"),
            dict(base, kai=K[0], key="m002", name="小学校管理運営事業（施設）", amount="-30",
                 desc="各経費の精算に伴い、減額補正する一方、照明の経費を新規計上します。"),
            dict(base, kai=K[1], key="m001", name="会計年度任用職員人件費（社会福祉総務費）", amount="10",
                 desc="給付金の経費を新規計上します。"),
            dict(base, kai=K[2], key="m001", name="児童手当支給事業", amount="50", desc="支給見込額の増加に伴い増額補正します。"),
            dict(base, kai=K[2], key="m002", name="会計年度任用職員人件費（社会福祉総務費）", amount="20",
                 desc="別の給付金の経費を新規計上します。"),
            dict(base, kai=KK, key="t001", kind="toku", mark="", name="国民健康保険特別会計補正予算（第 1 号）",
                 amount="809", desc="増額補正します。")]
    return rows + list(extra)


def struct(prev=None, maru=None, kai=None):
    tables = {hosei.KAI: kai or kai_rows(prev), hosei.SHIRYO: [], hosei.KAN: [], hosei.MARU: maru or maru_rows(),
              hosei.JIKO: []}
    audits = [th.audit_of(hosei.MARU, r) for r in tables[hosei.MARU]]
    return hosei.build_struct(tables, audits)


TEXT1 = ("日程第１ 議第1号、令和６年度日野町一般会計補正予算（第１号）。\n"
         "まず、歳入でございます。第15款・国庫支出金につきましては、児童手当の経費に伴い、児童手当交付金を増額補正するほか、"
         "照明の整備に伴い、学校施設整備交付金を新規計上しております。\n"
         "続きまして、歳出でございます。次に、第３款・民生費につきましては、児童手当支給事業におきまして、経費を新規計上するとともに、"
         "小学校管理運営事業（施設）におきましても、照明の経費を新規計上しております。\n"
         "次に、第３款・民生費につきましては、別の経費を計上しております。\n"
         "ご審議のほど、よろしくお願いいたします。\n"
         "日程第２ 議第2号、令和６年度日野町国民健康保険特別会計補正予算（第１号）。本案は国保です。")
Q1 = "第15款・国庫支出金につきましては、児童手当の経費に伴い、児童手当交付金を増額補正する…"
Q2 = "第15款・国庫支出金につきましては、…照明の整備に伴い、学校施設整備交付金を新規計上しております。"


def teian_inputs(proposals=None):
    st = struct()
    texts = {S1: ("町長", TEXT1), S2: ("5番", "児童手当支給事業について伺います。"),
             S3: ("町長", "児童手当支給事業におきまして、経費を新規計上しております。")}
    return rc.Inputs(
        statements={s: {"text": t, "role": r, "meetingId": MID} for s, (r, t) in texts.items()},
        order=[S1, S2, S3], segments={}, gian={MID: {"議第1号", "議第2号"}}, bulletin={}, docs=set(),
        doc_text=lambda *a: None, pt_text=lambda *a: None, plans=set(), nodes=set(), series=set(),
        struct=st, gian_hs={f"gi:{MID}/議第1号": {f"hs:{K[0]}"}},
        proposals=[(S1, S1, MID, ["議第1号", "議第2号"])] if proposals is None else proposals)


def trow(**kw):
    r = {"maru": f"hj:{K[0]}/m001", "bill": f"gi:{MID}/議第1号", "sid": f"sp:{S1}",
         "quote": Q1, "status": "candidate", "reviewer": "", "date": "",
         "note": "下書き：2026-11-09・Opus 5.5（プロンプトの版なし）"}
    r.update(kw)
    return r


def two():
    return [trow(), trow(maru=f"hj:{K[0]}/m002", quote=Q2)]


def check(rows, inp=None):
    rep = rc.Report()
    rc.check_teian(rows, inp or teian_inputs(), rep)
    return rep


class TeianTest(unittest.TestCase):
    def test_ok(self):
        # 同じ maru に財源の行が2つ（科目の名と○の行の名の字の一致は見ない）
        z = trow(quote="まず、歳入でございます。")
        rep = check(two() + [z])
        self.assertEqual(rep.errors, [])
        self.assertEqual(rep.quote_mismatch, [])
        self.assertEqual(rep.teian_segment, [])

    def test_errors(self):
        cases = [(trow(maru=f"hj:{KK}/t001"), "○の行"),
                 (trow(maru=f"hj:{K[0]}/m009"), "構造化の層に無い"),
                 (trow(bill=f"gi:{MID}/議第9号"), "gian.json に無い"),
                 (trow(bill=f"gi:{MID}/議第2号"), "対応しない"),
                 (trow(sid=f"sp:{S2}", quote="児童手当支給事業について伺います。"), "議員"),
                 (trow(sid="sp:0000000099_20240601_0001"), "索引に無い"),
                 (trow(note="見本"), "下書き："),
                 (trow(quote="…"), "「…」のほかの字が無い"),
                 (trow(quote="児童手当…に…経費"), "2字に満たない"),
                 (trow(quote="児童手当の経費……交付金"), "2字に満たない"),
                 (trow(quote="児童手当の経費に…伴い、児童手当交付金"), "続いている"),
                 # 「次に、第３款・民生費につきましては、」と「計上しております。」の組は2つの文にある
                 (trow(quote="次に、第３款・民生費につきましては、…計上しております。"), "1つに決まらない")]
        for r, msg in cases:
            rep = check([r])
            self.assertTrue(any(msg in e for e in rep.errors), (msg, rep.errors))

    def test_other_ledgers_unchanged(self):
        # 「…」は提案理由の記録だけ。ほかの台帳の照合（§15.1）は「…」を本文の字として見る
        inp = teian_inputs()
        self.assertFalse(rc.quote_in(inp, f"sp:{S1}", Q1))
        self.assertTrue(rc.quote_in(inp, f"sp:{S1}", "児童手当の経費に伴い、児童手当交付金を増額補正する"))

    def test_mismatch_and_confirmed(self):
        rep = check([trow(quote="本文に無い文。")])
        self.assertEqual(len(rep.quote_mismatch), 1)
        self.assertEqual(rep.errors, [])
        rep = check([trow(status="confirmed", reviewer="kken78", date="2026-11-10", quote="本文に無い文。")])
        self.assertTrue(any("判定：" in e for e in rep.errors))
        self.assertTrue(any("confirmed の引用" in e for e in rep.errors))

    def test_segment(self):
        inp = teian_inputs(proposals=[])
        a = trow(maru=f"hj:{K[2]}/m001", quote="児童手当支給事業におきまして、経費を新規計上しております。", sid=f"sp:{S3}")
        inp.gian_hs[f"gi:{MID}/議第1号"] = {f"hs:{K[0]}", f"hs:{K[2]}"}
        rej = trow(maru=f"hj:{K[0]}/m002", quote=Q2, status="rejected", reviewer="kken78", date="2026-11-10",
                   note="下書き：見本。却下：理由")
        rep = check([trow(), a, rej], inp)
        self.assertEqual(rep.errors, [])
        self.assertEqual([x["maru"] for x in rep.teian_segment], [f"hj:{K[0]}/m001", f"hj:{K[2]}/m001"])  # 区切りが無い
        self.assertEqual(rep.teian_segment[0]["desc"], "児童手当の経費を新規計上します。")
        self.assertEqual(list(rep.teian_segment[0]), rc.TEIAN_SEGMENT_COLUMNS)

    def test_context(self):
        rep = rc.Report()
        rows = two() + [trow(maru=f"hj:{K[0]}/m002", quote="照明の整備に伴い、学校施設整備交付金")]
        rc.teian_context(teian_inputs(), rows, rep)
        self.assertEqual([(x["kind"], x["quote"][:6]) for x in rep.quote_context],
                         [("文の途中から始まる", "照明の整備に"), ("文の途中で終わる", "照明の整備に")])

    def test_columns(self):
        self.assertIn("teian", rc.LEDGERS)
        self.assertIn("teian", rc.OPTIONAL)
        self.assertEqual(rc.KEYS["teian"], ("maru", "sid", "quote"))
        self.assertEqual(rc.COLUMNS["teian"][:4], ["maru", "bill", "sid", "quote"])
        self.assertNotIn("men", rc.COLUMNS["teian"])
        self.assertNotIn("gaku", rc.COLUMNS["teian"])


class GenTeianTest(unittest.TestCase):
    def test_portion_and_candidates(self):
        inp = teian_inputs()
        part = gen_teian.portion(inp.statements[S1]["text"], "議第1号", "令和６年度日野町一般会計補正予算（第１号）")
        self.assertEqual(part[0], "日程第１ 議第1号、令和６年度日野町一般会計補正予算（第１号）。")
        self.assertEqual(part[-1], "ご審議のほど、よろしくお願いいたします。")
        self.assertFalse(any("国民健康保険" in s for s in part))
        self.assertTrue(all("歳出" not in s for s in gen_teian.income(part)))
        found = gen_teian.find_speech(inp, f"gi:{MID}/議第1号", "令和６年度日野町一般会計補正予算（第１号）")
        self.assertEqual(found[0], S1)
        cands = gen_teian.candidates(inp, inp.struct)
        self.assertEqual(list(cands[0]), gen_teian.COLUMNS)
        # 候補は歳入の段の文だけ
        self.assertTrue(all("歳出" not in c["sentence"] for c in cands))
        m1 = [c for c in cands if c["maru"] == f"hj:{K[0]}/m001"]
        self.assertEqual(m1[0]["rank"], "1")
        self.assertIn("児童手当交付金", m1[0]["sentence"])
        # 議案と回の台帳の confirmed の行が無い回（第2号・第3号）は、候補を作らず報告に数える
        self.assertEqual({c["maru"].split("/")[0] for c in cands}, {f"hj:{K[0]}"})
        rep = {}
        gen_teian.candidates(inp, inp.struct, rep)
        self.assertEqual(rep["no_bill"], [K[1], K[2]])
        self.assertEqual(rep["targets"], 2)


class ApplyTeianTest(unittest.TestCase):
    KEYS_H = "maru\tsid\tquote\n"
    DEC_H = "maru\tsid\tquote\tstatus\treviewer\tdate\tnote\n"

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, "teian.tsv")
        with open(self.path, "w", encoding="utf-8", newline="\n") as f:
            f.write(rc.format_tsv(rc.COLUMNS["teian"], two()))

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
        r1, r2 = two()
        k1, k2 = [r1[c] for c in ad.TEIAN_KEY_COLUMNS], [r2[c] for c in ad.TEIAN_KEY_COLUMNS]
        kp, dp = self.files([k1, k2], [k1 + ["confirmed", "kken78", "2026-11-10", "判定：行ごと（判定シート 15D-5b）"],
                                       k2 + ["rejected", "kken78", "2026-11-10", "別の文"]])
        out = io.StringIO()
        applied = ad.write_teian(dp, kp, self.path, out)
        self.assertIn("書き写す前の件数：confirmed 1・rejected 1", out.getvalue())
        self.assertEqual(applied["confirmed"], 1)
        self.assertEqual(applied["rejected"], 1)
        with open(self.path, "rb") as f:
            rows = rc.parse_tsv(f.read(), rc.COLUMNS["teian"], "teian")
        self.assertTrue(rows[0]["note"].endswith("。判定：行ごと（判定シート 15D-5b）"))
        self.assertTrue(rows[1]["note"].endswith("。却下：別の文"))
        rep = check(rows)
        self.assertEqual(rep.errors, [])

    def test_refused(self):
        r1, r2 = two()
        k1 = [r1[c] for c in ad.TEIAN_KEY_COLUMNS]
        before = self.read()
        cases = [([k1], [k1 + ["confirmed", "kken78", "2026-11-10", "メモだけ"]], "判定："),
                 ([k1], [k1 + ["candidate", "kken78", "2026-11-10", "判定：x"]], "status が"),
                 ([k1], [[r2[c] for c in ad.TEIAN_KEY_COLUMNS] + ["confirmed", "k", "2026-11-10", "判定：x"]],
                  "範囲の外"),
                 ([k1], [k1[:2] + ["違う引用", "confirmed", "k", "2026-11-10", "判定：x"]], "範囲の外"),
                 ([k1, k1], [k1 + ["confirmed", "k", "2026-11-10", "判定：x"]], "2 回ある")]
        for keys, decs, msg in cases:
            kp, dp = self.files(keys, decs)
            with self.assertRaises(gm.GenError) as cm:
                ad.write_teian(dp, kp, self.path, io.StringIO())
            self.assertIn(msg, str(cm.exception))
            self.assertEqual(self.read(), before)


if __name__ == "__main__":
    unittest.main()
