"""tools/hosei.py・tools/gen_gian_yosan.py・tools/gen_hosei_fuhyo.py と、tools/ledger.py・tools/update_links.py・
tools/check_links.py・tools/records.py・tools/apply_decisions.py に足した決まりの検査（LINK_SCHEMA.md §2・§3・§5・§7 gian-yosan・
§7 hosei-fuhyo・§10・§11、DESIGN.md ADR-34）。

実行: python3 -B tools/test_hosei.py -v
見本の小さな構造化の層（回2つ、款の行1つ、主な内容の行3つ、事項1つと、その検収の台帳）・議案・附表を作り、
足した決まりごとに、通る例と通らない例を確かめる。
"""
import copy
import io
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import apply_decisions as ad  # noqa: E402
import check_links  # noqa: E402
import gen_gian_yosan as gg  # noqa: E402
import gen_hosei_fuhyo as gh  # noqa: E402
import gen_mentions as gm  # noqa: E402
import hosei  # noqa: E402
import ledger  # noqa: E402
import records as rc  # noqa: E402
import update_links  # noqa: E402
import test_records as tr  # noqa: E402

K1, K2 = "r6-ippan-01", "r6-kokuho-01"


def kai_rows():
    return [{"id": K1, "fiscal_year": "2024", "kaikei": "ippan", "gou": "1", "title": "令和６年度日野町一般会計補正予算（第１号）",
             "prev": "", "prev_from": "", "label_mae": "", "label_hosei": "", "note": ""},
            {"id": K2, "fiscal_year": "2024", "kaikei": "kokuho", "gou": "1", "title": "国民健康保険特別会計補正予算（第 1 号）",
             "prev": "", "prev_from": "", "label_mae": "", "label_hosei": "", "note": ""}]


def kan_row():
    r = {c: "0" for c in hosei.AUDIT_COLS[hosei.KAN]}
    r.update(kai=K1, key="out-03", kan_no="3", name="民 生 費", unit="千円", doc="yosan-r6-hosei-06", page="3", note="")
    return r


def maru_rows():
    base = {"kind": "maru", "mark": "○", "unit": "千円", "line": "", "sub": "", "doc": "yosan-r6-hosei-06", "page": "2",
            "note": ""}
    return [dict(base, kai=K1, key="m001", name="児童手当支給事業", amount="8685", desc="経費を新規計上します。"),
            dict(base, kai=K1, key="m002", name="衆議院議員選挙費", amount="15898", desc="経費を新たに計上します。"),
            dict(base, kai=K2, key="t001", kind="toku", mark="", name="国民健康保険特別会計補正予算（第 1 号）",
                 amount="809", desc="増額補正します。")]


def jiko_row():
    return {"kai": K1, "key": "z001", "kind": "kurikoshi", "kubun_raw": "", "kubun": "", "kaikei_raw": "", "kaikei": "",
            "name": "道路改良事業", "amount": "1000", "unit": "千円", "line": "", "doc": "yosan-r6-hosei-06", "page": "4",
            "note": ""}


def audit_of(table, r, checked="✓", note="", key=None):
    cols = hosei.AUDIT_COLS[table]
    row, value, source = f"{r['kai']}/{r['key']}", "|".join(r[c] for c in cols), f"{r['doc']} p.{r['page']}"
    k = key or hosei.rebuild_key(table, row, ",".join(cols), value, r["unit"], source)
    return {"key": k, "table": table, "row": row, "cols": ",".join(cols), "value": value, "unit": r["unit"],
            "source": source, "checked": checked, "reviewer": "auto:pdftext", "date": "2026-11-08", "note": note}


def struct(audit_edit=None, maru=None):
    tables = {hosei.KAI: kai_rows(), hosei.SHIRYO: [], hosei.KAN: [kan_row()], hosei.MARU: maru or maru_rows(),
              hosei.JIKO: [jiko_row()]}
    audits = [audit_of(hosei.KAN, kan_row())] + [audit_of(hosei.MARU, r) for r in tables[hosei.MARU]]
    audits += [audit_of(hosei.JIKO, jiko_row())]
    audits.append({"key": "x", "table": "hosei-kaikei", "row": f"{K1}/a001", "cols": "", "value": "", "unit": "",
                   "source": "", "checked": "✓", "reviewer": "", "date": "", "note": ""})
    if audit_edit:
        audit_edit(audits)
    return hosei.build_struct(tables, audits)


FUHYO = {"id": "fuhyo-r6", "fiscal_year": {"label": "令和6年度", "year": 2024}, "pillars": [
    {"no": 1, "items": [{"key": "b001", "name": "児童手当支給事業", "desc": "児童手当", "kan": "民生費", "dept": ["子ども支援課"]},
                        {"key": "b002", "name": "道路維持補修事業", "desc": "道路", "kan": "土木費", "dept": ["建設計画課"]}]}]}
GIAN = {"0000000010": {"agenda": [
    {"no": "議第1号", "kind": "予算", "title": "令和６年度日野町一般会計補正予算（第１号）"},
    {"no": "議第2号", "kind": "予算", "title": "令和６年度日野町国民健康保険特別会計補正予算（第１号）"},
    {"no": "議第3号", "kind": "予算", "title": "令和６年度日野町一般会計補正予算（第２号）"},
    {"no": "議第4号", "kind": "予算", "title": "平成３０年度日野町一般会計補正予算（第５号）"},
    {"no": "議第6号", "kind": "予算", "title": "令和７年度日野町一般会計補正予算（第１号）"},
    {"no": "議第5号", "kind": "条例", "title": "日野町税条例の一部を改正する条例"}]},
    "0000000011": {"agenda": [
        {"no": "議第9号", "kind": "予算", "title": "専決処分について（令和６年度日野町一般会計補正予算（第１号））"}]}}


def gian_built(st=None, gian=None):
    return gg.build(gg.GianInputs({}, gian or GIAN, st or struct()))


def hosei_built(st=None, fuhyo=None):
    return gh.build(gh.HoseiInputs({}, st or struct(), {"fuhyo-r6": fuhyo or FUHYO}))


class TestStruct(unittest.TestCase):
    def test_rebuild_key_real_row(self):
        # hino-town-docs f73959d の検収の台帳の1行目（hosei-kan r6-ippan-01/in-01）と同じ key になる
        v = "3486021|3486021|3486021|3486021|0|0|3486021|3486021|0.0"
        k = hosei.rebuild_key("hosei-kan", "r6-ippan-01/in-01", ",".join(hosei.AUDIT_COLS[hosei.KAN]), v, "千円",
                              "yosan-r6-tosho-hosei-tsuika p.3")
        self.assertEqual(k, "161fd45c569e0bd7")
        self.assertNotEqual(hosei.rebuild_key("hosei-kan", "r6-ippan-01/in-01", "", v, "千円", ""), k)

    def test_checked_rows(self):
        st = struct()
        self.assertEqual(st.rekey_counts(), (5, 0, 0, 1))   # 読まない表（hosei-kaikei）の行は数えるだけ
        for k in (f"hj:{K1}/m001", f"hk:{K1}/out-03", f"hz:{K1}/z001", f"hs:{K1}", f"hs:{K2}"):
            self.assertTrue(st.exists(k), k)
            self.assertTrue(st.is_checked(k), k)

    def test_value_changed_not_checked(self):
        # 表の値が変わり、作り直した key が台帳と違う行は、checked が ✓ でも検収の済んだ行でない（§2 の (1)）
        maru = maru_rows()
        st0 = struct()
        maru[0]["amount"] = "9999"
        st = struct(maru=maru, audit_edit=lambda a: a.__setitem__(1, audit_of(hosei.MARU, maru_rows()[0])))
        self.assertTrue(st0.is_checked(f"hj:{K1}/m001"))
        self.assertFalse(st.is_checked(f"hj:{K1}/m001"))
        self.assertFalse(st.is_checked(f"hs:{K1}"))   # 回の行の1つが済んでいないので、回も済んでいない
        self.assertEqual(st.rekey_counts()[1], 1)

    def test_unchecked_and_human_mark(self):
        for edit in ({"checked": ""}, {"note": "要人確認:H4 3点"}):
            with self.subTest(edit=edit):
                st = struct(audit_edit=lambda a: a[1].update(edit))
                self.assertFalse(st.is_checked(f"hj:{K1}/m001"))
                self.assertTrue(st.is_checked(f"hj:{K1}/m002"))

    def test_hs_without_rows_not_checked(self):
        tables = {hosei.KAI: kai_rows(), hosei.SHIRYO: [], hosei.KAN: [], hosei.MARU: [], hosei.JIKO: []}
        st = hosei.build_struct(tables, [])
        self.assertTrue(st.exists(f"hs:{K1}"))
        self.assertFalse(st.is_checked(f"hs:{K1}"))

    def test_key_forms(self):
        for k, want in ((f"hs:{K1}", "hs"), (f"hj:{K1}/m001", "hj"), (f"hj:{K2}/t001", "hj"), (f"hk:{K1}/in-11-1", "hk"),
                        (f"hk:{K1}/sei-total", "hk"), (f"hz:{K1}/z001", "hz")):
            self.assertEqual(hosei.kind_of(k), want, k)
        for k in (f"hj:{K1}/z001", f"hk:{K1}/m001", f"hz:{K1}/m001", "hs:R6-ippan-01", f"hj:{K1}", f"hk:{K1}/a001"):
            self.assertIsNone(hosei.kind_of(k), k)

    def test_duplicate_row_stops(self):
        tables = {hosei.KAI: kai_rows(), hosei.SHIRYO: [], hosei.KAN: [], hosei.MARU: maru_rows() + [maru_rows()[0]],
                  hosei.JIKO: []}
        with self.assertRaises(gm.GenError):
            hosei.build_struct(tables, [])

    def test_kaikei_names(self):
        self.assertEqual(struct().kaikei_names(), {"一般会計": "ippan", "国民健康保険特別会計": "kokuho"})
        tables = {hosei.KAI: kai_rows() + [dict(kai_rows()[1], id="r6-kaigo-01", kaikei="kaigo")], hosei.SHIRYO: [],
                  hosei.KAN: [], hosei.MARU: [], hosei.JIKO: []}
        with self.assertRaises(gm.GenError):
            hosei.build_struct(tables, []).kaikei_names()

    def test_kaikei_names_title_forms(self):
        # §2（2026-11-13）：「補正予算」の字の無い題と、号の前に「（専決処分）」の付く題も会計の名前が取れる
        extra = [dict(kai_rows()[0], id="r7-ippan-06", fiscal_year="2025", gou="6",
                      title="令和７年度日野町一般会計補正予算（専決処分）（第６号）"),
                 dict(kai_rows()[1], id="r7-koki-01", fiscal_year="2025", kaikei="koki",
                      title="後期高齢者医療特別会計（第１号）"),
                 dict(kai_rows()[1], id="r7-koki-02", fiscal_year="2025", kaikei="koki", gou="2",
                      title="後期高齢者医療特別会計補正予算（第２号）")]
        tables = {hosei.KAI: kai_rows() + extra, hosei.SHIRYO: [], hosei.KAN: [], hosei.MARU: [], hosei.JIKO: []}
        self.assertEqual(hosei.build_struct(tables, []).kaikei_names(),
                         {"一般会計": "ippan", "国民健康保険特別会計": "kokuho", "後期高齢者医療特別会計": "koki"})
        # 号の無い題は、これまでどおり止める
        bad = [dict(kai_rows()[1], id="r7-koki-03", kaikei="koki", title="後期高齢者医療特別会計補正予算")]
        tables = {hosei.KAI: kai_rows() + bad, hosei.SHIRYO: [], hosei.KAN: [], hosei.MARU: [], hosei.JIKO: []}
        with self.assertRaises(gm.GenError):
            hosei.build_struct(tables, []).kaikei_names()

    def test_changes(self):
        prev = struct()
        keys = [f"hj:{K1}/m001", f"hj:{K1}/m002", f"hk:{K1}/out-03", f"hs:{K2}", f"hj:{K1}/m009"]
        self.assertEqual(hosei.changes(prev, struct(), keys), {})
        maru = maru_rows()[1:]     # m001 が無くなった
        maru[0]["amount"] = "1"    # m002 の値が変わった（台帳は前の key のまま → 作り直した key と違う）
        now = struct(maru=maru, audit_edit=lambda a: (a.__setitem__(1, audit_of(hosei.MARU, maru[0], key="old")),
                                                       a[0].update(checked="")))
        got = hosei.changes(prev, now, keys)
        self.assertEqual(got[f"hj:{K1}/m001"], "行が無くなった")
        self.assertEqual(got[f"hj:{K1}/m002"], "key が変わった")
        self.assertEqual(got[f"hk:{K1}/out-03"], "検収が済まなくなった")
        self.assertNotIn(f"hj:{K1}/m009", got)   # 前の版に無いキーは比べない
        self.assertEqual(hosei.changes(hosei.build_struct({t: [] for t in hosei.TABLES}, []), now, keys), {})


class TestGianYosan(unittest.TestCase):
    def test_parse_title(self):
        self.assertEqual(gg.parse_title("令和６年度日野町一般会計補正予算（第１０号）"), (2024, "一般会計", 10, False))
        self.assertEqual(gg.parse_title("専決処分について（令和６年度日野町一般会計補正予算（第６号））"), (2024, "一般会計", 6, True))
        self.assertEqual(gg.parse_title("専決処分の報告について（令和７年度日野町一般会計補正予算（第６号））")[:3],
                         (2025, "一般会計", 6))
        self.assertEqual(gg.parse_title("令和元年度日野町一般会計補正予算（第２号）について")[:3], (2019, "一般会計", 2))
        self.assertEqual(gg.parse_title("平成３０年度日野町一般会計補正予算（第５号）")[:3], (None, None, None))

    def test_build(self):
        b = gian_built()
        got = {(r["from"], r["to"]) for r in b.rows}
        self.assertEqual(got, {("gi:0000000010/議第1号", f"hs:{K1}"), ("gi:0000000010/議第2号", f"hs:{K2}"),
                               ("gi:0000000011/議第9号", f"hs:{K1}")})
        self.assertEqual([r["from"] for r in b.no_kai], ["gi:0000000010/議第3号"])   # 資料の無い回の議案
        self.assertEqual([r["from"] for r in b.no_title], ["gi:0000000010/議第4号"])  # 平成の題は取れない
        # 回の表に行の無い年度（令和7年度）の議案は一覧に出さず、件数だけ（PR #19 の問い3）
        self.assertEqual([r["from"] for r in b.no_year], ["gi:0000000010/議第6号"])
        lines = "\n".join(gg.count_lines(b.rows, b))
        self.assertIn("回の表に行の無い年度の議案（一覧に出さない）：1（2025年度 1）", lines)
        self.assertIn("題から年度・会計・号が取れない議案（一覧に出さない）：1", lines)
        r = next(x for x in b.rows if x["from"].endswith("議第9号"))
        self.assertIn("専決処分", r["note"])
        self.assertEqual(r["to_label"], "令和６年度日野町一般会計補正予算（第１号）")
        self.assertEqual(r["evidence"], r["context"])

    def test_duplicate_bill_stops(self):
        g = copy.deepcopy(GIAN)
        g["0000000010"]["agenda"].append(dict(g["0000000010"]["agenda"][0]))
        with self.assertRaises(gm.GenError):
            gian_built(gian=g)

    def test_label_match(self):
        b = gian_built()
        c = gg.corpus(b)
        r = dict(b.rows[0])
        self.assertEqual(ledger.match_full(r, c).result, ledger.MATCH)
        self.assertEqual(ledger.match_full(dict(r, to_label="違う題"), c).result, ledger.STOPPED)
        self.assertEqual(ledger.match_full(dict(r, to="hs:r6-ippan-99"), c).result, ledger.STOPPED)
        self.assertEqual(ledger.sentinel([r], c), [])   # gi の行には sentinel をかけない
        self.assertEqual(ledger.sentinel_rows([r]), 0)

    def test_gian_errors(self):
        b = gian_built()
        r = dict(b.rows[0], status="confirmed", reviewer="kken78", date="2026-11-09")
        self.assertEqual(check_links.gian_errors([r], b.inputs.struct), [])
        st = struct(audit_edit=lambda a: a[0].update(checked=""))
        self.assertEqual(len(check_links.gian_errors([r], st)), 1)          # confirmed の hs が検収の済んだ行でない
        self.assertEqual(check_links.gian_errors([b.rows[0]], st), [])     # candidate は止めない


class TestHoseiFuhyo(unittest.TestCase):
    def test_build(self):
        b = hosei_built()
        self.assertEqual([(r["from"], r["to"], r["kind"]) for r in b.rows], [(f"hj:{K1}/m001", "fh:fuhyo-r6/b001", "増額")])
        # 特別会計・企業会計の行（t001）は対象にしない（PR #19 の問い2）。名前の一致しない○の行は一覧だけ（問い1）
        self.assertEqual(b.unmatched, [{"from": f"hj:{K1}/m002", "name": "衆議院議員選挙費", "amount": "15898",
                                        "kind": "新規", "desc_head": "経費を新たに計上します。"}])
        self.assertEqual(b.toku, 1)
        self.assertEqual(b.ambiguous, [])
        maru = maru_rows()
        maru[1]["desc"] = "あ" * 50
        self.assertEqual(hosei_built(st=struct(maru=maru)).unmatched[0]["kind"], "附表に無い")
        self.assertEqual(hosei_built(st=struct(maru=maru)).unmatched[0]["desc_head"], "あ" * 40)

    def test_toku_name_not_matched(self):
        # t の行の名前が附表の事業名と同じでも、候補にしない
        maru = maru_rows()
        maru[2]["name"] = "道路維持補修事業"
        b = hosei_built(st=struct(maru=maru))
        self.assertEqual([r["from"] for r in b.rows], [f"hj:{K1}/m001"])

    def test_ambiguous(self):
        f = copy.deepcopy(FUHYO)
        f["pillars"][0]["items"].append(dict(f["pillars"][0]["items"][0], key="b003", kan="衛生費"))
        b = hosei_built(fuhyo=f)
        self.assertEqual(b.rows, [])
        self.assertEqual({a["to"] for a in b.ambiguous}, {"fh:fuhyo-r6/b001", "fh:fuhyo-r6/b003"})

    def test_kind(self):
        r = maru_rows()[0]
        self.assertEqual(gh.fh_kind(dict(r, amount="-3402")), "減額")
        self.assertEqual(gh.fh_kind(dict(r, amount="0", desc="財源を更正します。")), "財源更正")
        self.assertIsNone(gh.fh_kind(dict(r, amount="0", desc="補正します。")))
        self.assertIsNone(gh.fh_kind(dict(r, amount="")))
        maru = maru_rows()
        maru[0]["amount"] = ""
        with self.assertRaises(gm.GenError):   # 金額が数でない：止める
            hosei_built(st=struct(maru=maru))

    def test_kind_undecided(self):
        # 名前は一致したが、金額0で説明に「財源」の字が無い：台帳の候補にせず、一覧（kind_undecided.tsv）に出す（2026-11-13）
        maru = maru_rows()
        maru[0].update(amount="0", desc="工事請負費を減額し、補償金を新規計上します。")
        b = hosei_built(st=struct(maru=maru))
        self.assertEqual(b.rows, [])
        self.assertEqual(b.undecided, [{"from": f"hj:{K1}/m001", "to": "fh:fuhyo-r6/b001", "name": "児童手当支給事業",
                                        "amount": "0", "desc_head": "工事請負費を減額し、補償金を新規計上します。"}])
        self.assertEqual([u["from"] for u in b.unmatched], [f"hj:{K1}/m002"])   # name_unmatched には入れない
        self.assertIn("- 名前は一致したが kind の決まらない○の行：1（金額0で説明に「財源」の字が無い。kind_undecided.tsv。"
                      "台帳には書かない）", gh.count_lines(b.rows, b))
        # 「財源」の字があれば、これまでどおり財源更正の候補
        maru[0]["desc"] = "財源を更正します。"
        b2 = hosei_built(st=struct(maru=maru))
        self.assertEqual([r["kind"] for r in b2.rows], ["財源更正"])
        self.assertEqual(b2.undecided, [])
        self.assertTrue(gh.is_zero("0"))
        self.assertFalse(gh.is_zero("-0x"))
        self.assertFalse(gh.is_zero(""))

    def test_hosei_errors(self):
        b = hosei_built()
        note = b.rows[0]["note"] + "。メモ：判定：依頼者が名前の一致の規則と一覧（1行）を確認して確定"
        ok = dict(b.rows[0], status="confirmed", reviewer="kken78", date="2026-11-09", note=note)
        self.assertEqual(gh.hosei_errors([ok], b), [])
        self.assertEqual(gh.hosei_errors([b.rows[0]], b), [])        # candidate
        cases = {"kind の値": dict(ok, kind="増加"), "新規は台帳に付けない": dict(ok, kind="新規"),
                 "kind が空": dict(ok, kind=""), "判定の出どころが無い": dict(ok, note=b.rows[0]["note"]),
                 "行数が合わない": dict(ok, note=note.replace("（1行）", "（2行）")),
                 "name の行で名前が違う": dict(ok, to="fh:fuhyo-r6/b002", to_label="道路維持補修事業")}
        for name, r in cases.items():
            with self.subTest(name=name):
                self.assertEqual(len(gh.hosei_errors([r], b)), 1, gh.hosei_errors([r], b))
        two = [ok, dict(ok, to="fh:fuhyo-r6/b002", to_label="道路維持補修事業", method="manual",
                        note="説明と概要の一致：「道路」。判定：依頼者が会話で確認（2026-11-09）")]
        self.assertEqual(len(gh.hosei_errors(two, b)), 1)            # 同じ hj が2行
        self.assertEqual(gh.hosei_errors([ok, dict(two[1], status="rejected")], b), [])  # rejected は数えない
        un = struct(audit_edit=lambda a: a[1].update(checked=""))
        self.assertEqual(len(gh.hosei_errors([ok], hosei_built(st=un))), 1)  # confirmed の hj が検収の済んだ行でない
        f7 = copy.deepcopy(FUHYO)
        f7.update(id="fuhyo-r7", fiscal_year={"label": "令和7年度", "year": 2025})
        b2 = gh.build(gh.HoseiInputs({}, struct(), {"fuhyo-r6": FUHYO, "fuhyo-r7": f7}))
        self.assertEqual(len(gh.hosei_errors([dict(ok, to="fh:fuhyo-r7/b001")], b2)), 1)  # 年度が違う

    def test_manual_row(self):
        b = hosei_built()
        d = {"from": f"hj:{K1}/m002", "to": "fh:fuhyo-r6/b002", "method": "manual", "context": "衆議院議員選挙費",
             "status": "confirmed", "reviewer": "kken78", "date": "2026-11-09",
             "note": "説明と概要の一致：「選挙」。判定：依頼者が会話で確認（2026-11-09）"}
        row, bad = gh.manual_row(b, d["from"], d["to"], d)
        self.assertEqual(bad, [])
        self.assertEqual((row["kind"], row["to_label"], row["evidence"]), ("増額", "道路維持補修事業", "衆議院議員選挙費"))
        self.assertEqual(gh.hosei_errors([row], b), [])
        self.assertTrue(gh.manual_row(b, f"hj:{K1}/m001", "fh:fuhyo-r6/b001", dict(d, context="児童手当支給事業"))[1])  # 名前が同じ
        self.assertTrue(gh.manual_row(b, f"hj:{K2}/t001", "fh:fuhyo-r6/b002", d)[1])   # t の行
        self.assertTrue(gh.manual_row(b, d["from"], "fh:fuhyo-r6/b009", d)[1])         # 附表に無い事業
        self.assertTrue(gh.manual_row(b, d["from"], d["to"], dict(d, context="別"))[1])  # context が違う
        self.assertEqual(len(gh.hosei_errors([dict(row, note="判定：見本")], b)), 1)   # manual の note の頭

    def test_match_hj(self):
        b = hosei_built()
        c = gh.corpus(b)
        r = b.rows[0]
        self.assertEqual(ledger.match_full(r, c).result, ledger.MATCH)
        self.assertEqual(ledger.match_full(dict(r, context="別の事業", evidence="別の事業"), c).result, ledger.STOPPED)
        self.assertEqual(ledger.match_full(dict(r, **{"from": f"hj:{K1}/m009"}), c).result, ledger.STOPPED)
        self.assertEqual(ledger.match_full(dict(r, to_label="別の名前"), c).result, ledger.STOPPED)
        self.assertEqual(ledger.sentinel([r], c), [])


class TestLedgerForm(unittest.TestCase):
    def fmt(self, method, rows):
        return ledger.format_ledger(rows, method)

    def test_round_trip(self):
        g = gian_built().rows
        self.assertEqual(ledger.parse_ledger(self.fmt("gian-yosan", g), "gian-yosan"), g)
        h = gh.generated_rows(hosei_built())
        self.assertEqual(ledger.parse_ledger(self.fmt("hosei-fuhyo", h), "hosei-fuhyo"), h)
        self.assertTrue(self.fmt("hosei-fuhyo", h).decode().startswith("\t".join(ledger.LEDGER_COLUMNS + ["kind"])))

    def test_row_errors(self):
        g = gian_built().rows[0]
        h = gh.generated_rows(hosei_built())[0]
        cases = [("gian-yosan", dict(g, to="fh:fuhyo-r6/b001"), "to に fh は使えない"),
                 ("gian-yosan", dict(g, method="name"), "method が title でない"),
                 ("gian-yosan", dict(g, where="text"), "where が"),
                 ("gian-yosan", dict(g, **{"from": "gi:000001/議第1号"}), "from の形が違う"),
                 ("hosei-fuhyo", dict(h, to="hs:r6-ippan-01"), "to に hs は使えない"),
                 ("hosei-fuhyo", dict(h, method="title"), "method が name・manual でない"),
                 ("hosei-fuhyo", dict(h, method="manual"), "candidate は置かない"),
                 ("hosei-fuhyo", dict(h, **{"from": "hj:r6-ippan-01/z001"}), "from の形が違う"),
                 ("hosei-fuhyo", dict(h, **{"from": "hj:r6-kokuho-01/t001"}), "from は○の行"),
                 ("hosei-fuhyo", dict(h, to="none:fuhyo-r6", to_label="附表に無い"), "to に none は使えない")]
        for method, r, msg in cases:
            with self.subTest(msg=msg), self.assertRaises(ledger.LedgerError) as cm:
                ledger.parse_ledger(self.fmt(method, [r]), method)
            self.assertIn(msg, str(cm.exception))
        with self.assertRaises(ledger.LedgerError):   # 12列の台帳に11列のヘッダ
            ledger.parse_ledger(ledger.format_ledger([g]), "hosei-fuhyo")


class TestTools(unittest.TestCase):
    def test_update_then_check(self):
        gb, hb = gian_built(), hosei_built()
        with tempfile.TemporaryDirectory() as tmp:
            gpath, hpath = os.path.join(tmp, "gian-yosan.tsv"), os.path.join(tmp, "hosei-fuhyo.tsv")
            self.assertEqual(update_links.run_gian(gb, gpath, os.path.join(tmp, "g"))[0], 0)
            self.assertEqual(update_links.run_hosei(hb, hpath, os.path.join(tmp, "h"))[0], 0)
            self.assertEqual(check_links.run_gian(gb, gpath, os.path.join(tmp, "g"))[0], 0)
            self.assertEqual(check_links.run_hosei(hb, hpath, os.path.join(tmp, "h"))[0], 0)
            with open(os.path.join(tmp, "g", "no_kai.tsv"), encoding="utf-8") as f:
                self.assertEqual(f.read(), "from\ttitle\ngi:0000000010/議第3号\t令和６年度日野町一般会計補正予算（第２号）\n")
            with open(os.path.join(tmp, "h", "name_unmatched.tsv"), encoding="utf-8") as f:
                self.assertEqual(f.read(), "from\tname\tamount\tkind\tdesc_head\n"
                                           f"hj:{K1}/m002\t衆議院議員選挙費\t15898\t新規\t経費を新たに計上します。\n")
            with open(os.path.join(tmp, "h", "kind_undecided.tsv"), encoding="utf-8") as f:
                self.assertEqual(f.read(), "from\tto\tname\tamount\tdesc_head\n")
            # 人の判定を保つ：confirmed にした行は、更新しても変わらない
            rows = ledger.read_ledger(hpath, "hosei-fuhyo")
            rows[0].update(status="confirmed", reviewer="kken78", date="2026-11-09", note="判定：見本")
            ledger.write_ledger(hpath, rows, "hosei-fuhyo")
            self.assertEqual(update_links.run_hosei(hb, hpath, os.path.join(tmp, "h"))[0], 0)
            self.assertEqual(ledger.read_ledger(hpath, "hosei-fuhyo"), rows)
            # 名前が変わると confirmed の行は出なくなり、更新も検査も止める
            maru = maru_rows()
            maru[0]["name"] = "児童手当支給事務"
            hb2 = hosei_built(st=struct(maru=maru))
            self.assertEqual(update_links.run_hosei(hb2, hpath, os.path.join(tmp, "h"))[0], 1)
            self.assertEqual(check_links.run_hosei(hb2, hpath, os.path.join(tmp, "h"))[0], 1)

    def test_kind_undecided_ledger(self):
        # kind の決まらない○の行は台帳に書かず一覧に出す。confirmed の行がその○の行になれば、根拠の消失で止まる
        maru = maru_rows()
        maru[0].update(amount="0", desc="補償金を新規計上します。")
        hb = hosei_built(st=struct(maru=maru))
        with tempfile.TemporaryDirectory() as tmp:
            hpath, out = os.path.join(tmp, "hosei-fuhyo.tsv"), os.path.join(tmp, "h")
            self.assertEqual(update_links.run_hosei(hb, hpath, out)[0], 0)
            self.assertEqual(ledger.read_ledger(hpath, "hosei-fuhyo"), [])
            self.assertEqual(check_links.run_hosei(hb, hpath, out)[0], 0)
            with open(os.path.join(out, "kind_undecided.tsv"), encoding="utf-8") as f:
                self.assertEqual(f.read(), "from\tto\tname\tamount\tdesc_head\n"
                                           f"hj:{K1}/m001\tfh:fuhyo-r6/b001\t児童手当支給事業\t0\t補償金を新規計上します。\n")
            hb0 = hosei_built()
            self.assertEqual(update_links.run_hosei(hb0, hpath, out)[0], 0)
            rows = ledger.read_ledger(hpath, "hosei-fuhyo")
            rows[0].update(status="confirmed", reviewer="kken78", date="2026-11-09", note="判定：見本")
            ledger.write_ledger(hpath, rows, "hosei-fuhyo")
            self.assertEqual(update_links.run_hosei(hb, hpath, out)[0], 1)
            self.assertEqual(check_links.run_hosei(hb, hpath, out)[0], 1)

    def test_check_missing_ledger_stops(self):
        with tempfile.TemporaryDirectory() as tmp, self.assertRaises(ledger.LedgerError):
            check_links.run_gian(gian_built(), os.path.join(tmp, "gian-yosan.tsv"), tmp)


class TestApply(unittest.TestCase):
    """tools/apply_decisions.py の --ledger hosei-fuhyo・--ledger gian-yosan（§11 判定の範囲）。"""

    def write(self, tmp, name, columns, rows):
        path = os.path.join(tmp, name)
        with open(path, "wb") as f:
            f.write(("\n".join(["\t".join(columns)] + ["\t".join(r[c] for c in columns) for r in rows]) + "\n").encode())
        return path

    def decisions(self, tmp, rows):
        keys = self.write(tmp, "keys.tsv", ad.KEY_COLUMNS, rows)
        return keys, self.write(tmp, "dec.tsv", ad.DECISION_COLUMNS, rows)

    def test_hosei_name_and_manual(self):
        hb = hosei_built()
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "hosei-fuhyo.tsv")
            self.assertEqual(update_links.run_hosei(hb, path, os.path.join(tmp, "h"))[0], 0)
            name = {"from": f"hj:{K1}/m001", "to": "fh:fuhyo-r6/b001", "method": "name", "context": "児童手当支給事業",
                    "status": "confirmed", "reviewer": "kken78", "date": "2026-11-09",
                    "note": "判定：依頼者が名前の一致の規則と一覧（1行）を確認して確定"}
            manual = {"from": f"hj:{K1}/m002", "to": "fh:fuhyo-r6/b002", "method": "manual", "context": "衆議院議員選挙費",
                      "status": "confirmed", "reviewer": "kken78", "date": "2026-11-09",
                      "note": "説明と概要の一致：「見本」。判定：依頼者が会話で確認（2026-11-09）"}
            keys, dec = self.decisions(tmp, [name, manual])
            out = io.StringIO()
            code, applied, rows, _, errors = ad.run_hosei(dec, keys, path, hb, os.path.join(tmp, "h"), out=out)
            self.assertEqual((code, errors), (0, []))
            self.assertEqual(out.getvalue(), "書き写す前の件数：name confirmed 1・rejected 0\n"
                                             "書き写す前の件数：manual confirmed 1・rejected 0\n")
            self.assertEqual(applied, {("name", "confirmed"): 1, ("manual", "confirmed"): 1})
            self.assertEqual([(r["method"], r["status"]) for r in rows], [("name", "confirmed"), ("manual", "confirmed")])
            self.assertTrue(rows[0]["note"].endswith("。メモ：判定：依頼者が名前の一致の規則と一覧（1行）を確認して確定"))
            # 更新しても人の判定（manual の行を含む）は変わらない
            self.assertEqual(update_links.run_hosei(hb, path, os.path.join(tmp, "h"))[0], 0)
            self.assertEqual(ledger.read_ledger(path, "hosei-fuhyo"), rows)

    def test_hosei_scope_and_errors(self):
        hb = hosei_built()
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "hosei-fuhyo.tsv")
            update_links.run_hosei(hb, path, os.path.join(tmp, "h"))
            before = ledger.read_ledger(path, "hosei-fuhyo")
            d = {"from": f"hj:{K1}/m001", "to": "fh:fuhyo-r6/b001", "method": "name", "context": "児童手当支給事業",
                 "status": "confirmed", "reviewer": "kken78", "date": "2026-11-09", "note": "メモ"}
            keys = self.write(tmp, "keys.tsv", ad.KEY_COLUMNS, [dict(d, to="fh:fuhyo-r6/b002")])
            dec = self.write(tmp, "dec.tsv", ad.DECISION_COLUMNS, [d])
            with self.assertRaises(ad.DecisionError):    # 範囲の外の行
                ad.write_hosei(dec, keys, path, hb, out=io.StringIO())
            keys, dec = self.decisions(tmp, [d])
            with self.assertRaises(gm.GenError):         # note に「判定：」が無い（§11）
                ad.write_hosei(dec, keys, path, hb, out=io.StringIO())
            t = dict(d, **{"from": f"hj:{K2}/t001", "to": "fh:fuhyo-r6/b002", "method": "manual",
                           "context": "国民健康保険特別会計補正予算(第1号)", "note": "説明と概要の一致：「x」。判定：見本"})
            keys, dec = self.decisions(tmp, [t])
            with self.assertRaises(ad.DecisionError):    # t の行は manual にもできない
                ad.write_hosei(dec, keys, path, hb, out=io.StringIO())
            self.assertEqual(ledger.read_ledger(path, "hosei-fuhyo"), before)

    def test_gian(self):
        gb = gian_built()
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "gian-yosan.tsv")
            update_links.run_gian(gb, path, os.path.join(tmp, "g"))
            r = ledger.read_ledger(path, "gian-yosan")[0]
            d = {"from": r["from"], "to": r["to"], "method": "title", "context": r["context"], "status": "confirmed",
                 "reviewer": "kken78", "date": "2026-11-09", "note": "判定：見本"}
            keys, dec = self.decisions(tmp, [d])
            out = io.StringIO()
            code, applied, rows, _, errors = ad.run_gian(dec, keys, path, gb, os.path.join(tmp, "g"), out=out)
            self.assertEqual((code, errors, applied[ledger.CONFIRMED]), (0, [], 1))
            self.assertEqual(out.getvalue(), "書き写す前の件数：confirmed 1\n書き写す前の件数：rejected 0\n")


# ---- 記録の台帳の target・target_text（§11 対象の形・対象の照合・対象と議案・名前） ----

def rec_inputs(**kw):
    inp = tr.inputs()
    inp.fuhyo_keys = {"fh:fuhyo-r6/b001", "fh:fuhyo-r6/b002"}
    inp.struct = struct()
    for k, v in kw.items():
        setattr(inp, k, v)
    return inp


def with_target(ledger_name, i, target, text, **kw):
    led = tr.ledgers()
    led[ledger_name][i].update(target=target, target_text=text, **kw)
    return led


class TestTargets(tr.RecordsTestCase):
    def test_baseline_and_counts(self):
        # 発言 2 の字「新こども園の定員」を名の字にする（対象の照合の (3) は sid の発言の本文で照らす）
        led = with_target("yaritori", 0, f"hj:{K1}/m001,fh:fuhyo-r6/b002", "名:新こども園の定員;額:定員")
        rep = tr.run(led=led, inp=rec_inputs())
        self.assertEqual(rep.errors, [])
        self.assertEqual(rep.target_counts, {"hj": 1, "fh": 1})
        self.assertEqual(rep.text_counts, {"名": 1, "額": 1})
        self.assertEqual(len(rep.target_name), 1)   # (b)：○の行の名前が名・款の字に当たらない
        self.assertEqual(rep.target_name[0]["key"], f"hj:{K1}/m001")

    def test_form_errors(self):
        cases = [("node:jisshi/e008", "名:定員", "fh・hs・hj・hk・hz の形"),
                 (f"hj:{K1}/m001,hj:{K1}/m001", "名:定員", "同じキーが2つ"),
                 (f"hj:{K1}/m001", "", "target_text が空"),
                 ("", "名前:定員", "target_text が「種類:字」"),
                 ("", "名:定員:3", "target_text が「種類:字」"),
                 ("", "名:定員;", "target_text が「種類:字」"),
                 (f"hj:{K1}/m001,", "名:定員", "fh・hs・hj・hk・hz の形")]
        for target, text, msg in cases:
            with self.subTest(target=target, text=text):
                self.assertErr(tr.run(led=with_target("yaritori", 0, target, text), inp=rec_inputs()), msg)
        # 字の中の全角の「：」「；」は区切りでない（§15.2）
        rep = tr.run(led=with_target("yaritori", 1, "", "名：定員；285人"), inp=rec_inputs())
        self.assertErr(rep, "target_text が「種類:字」")
        rep = tr.run(led=with_target("yaritori", 1, "", "額:定員は285人です。"), inp=rec_inputs())
        self.assertEqual(rep.errors, [])

    def test_exists(self):
        for k in ("fh:fuhyo-r6/b009", f"hj:{K1}/m009", "hs:r6-ippan-09", f"hz:{K1}/z009"):
            with self.subTest(k=k):
                self.assertErr(tr.run(led=with_target("yaritori", 0, k, "名:定員"), inp=rec_inputs()), "(1)")

    def test_unchecked(self):
        inp = rec_inputs(struct=struct(audit_edit=lambda a: a[1].update(checked="")))
        rep = tr.run(led=with_target("yaritori", 0, f"hj:{K1}/m001", "名:定員"), inp=inp)
        self.assertErr(rep, "(2)")   # confirmed の行は止める
        led = with_target("yaritori", 0, f"hj:{K1}/m001", "名:定員", status="candidate", reviewer="", date="")
        rep = tr.run(led=led, inp=inp)
        self.assertFalse(any("(2)" in e for e in rep.errors))
        self.assertEqual([(r["question"], r["row"], r["key"]) for r in rep.target_unchecked], [(tr.IQ, "1", f"hj:{K1}/m001")])

    def test_text_in_statement(self):
        rep = tr.run(led=with_target("yaritori", 0, "", "名:用地"), inp=rec_inputs())
        self.assertErr(rep, "(3)")
        rep = tr.run(led=with_target("yaritori", 0, "", "名:新こども園の 定員"), inp=rec_inputs())  # §4 の正規化のあとで比べる
        self.assertEqual(rep.errors, [])

    def test_hj_and_fh(self):
        inp = rec_inputs(hj_fh={f"hj:{K1}/m001": {"fh:fuhyo-r6/b001"}})
        rep = tr.run(led=with_target("yaritori", 0, f"hj:{K1}/m001,fh:fuhyo-r6/b001", "名:定員"), inp=inp)
        self.assertErr(rep, "(4)")
        rep = tr.run(led=with_target("yaritori", 0, f"hj:{K1}/m001,fh:fuhyo-r6/b002", "名:定員"), inp=inp)
        self.assertFalse(any("(4)" in e for e in rep.errors))

    def test_target_bill(self):
        led = with_target("shitsugi", 0, f"hk:{K1}/out-03", "款:土地")
        rep = tr.run(led=led, inp=rec_inputs())
        self.assertEqual([(r["key"], r["kai"]) for r in rep.target_bill], [(f"hk:{K1}/out-03", "")])
        inp = rec_inputs(gian_hs={f"gi:{tr.M}/議第1号": {f"hs:{K1}"}})
        rep = tr.run(led=led, inp=inp)
        self.assertEqual(rep.target_bill, [])
        led = with_target("shitsugi", 0, f"hs:{K2}", "名:土地")
        rep = tr.run(led=led, inp=inp)
        self.assertEqual([(r["key"], r["kai"]) for r in rep.target_bill], [(f"hs:{K2}", f"hs:{K1}")])

    def test_target_name(self):
        # hk は kan_no か name が、名・款の字に当たれば一覧に出ない
        tr.TEXTS[13] = ("議員", "予算について。３款民生費、こども園の土地はどうか。道路はどうか。")
        try:
            rep = tr.run(led=with_target("shitsugi", 0, f"hk:{K1}/out-03", "款:３款民生費"), inp=rec_inputs())
            self.assertEqual(rep.errors, [])
            self.assertEqual(rep.target_name, [])
            rep = tr.run(led=with_target("shitsugi", 0, f"hk:{K1}/out-03", "頁:３款民生費"), inp=rec_inputs())
            self.assertEqual(len(rep.target_name), 1)   # 頁の字は見ない
        finally:
            tr.TEXTS[13] = ("議員", "予算について。こども園の土地はどうか。道路はどうか。")

    def test_target_changed(self):
        led = with_target("yaritori", 0, f"hj:{K1}/m001,hs:{K1},hs:{K2}", "名:定員")
        self.assertEqual(rc.target_changed(led, struct(), struct()), [])
        now = struct(maru=maru_rows()[1:])
        got = rc.target_changed(led, struct(), now)
        self.assertEqual([(r["ledger"], r["key"], r["change"]) for r in got],
                         [("yaritori", f"hj:{K1}/m001", "行が無くなった"), ("yaritori", f"hs:{K1}", "key が変わった")])


if __name__ == "__main__":
    unittest.main()
