"""提案理由の記録（records/teian.tsv）と回をまたぐ同じ事業の台帳（links/hosei-tsuzuki.tsv）の検査
（LINK_SCHEMA.md §3・§5・§7 hosei-tsuzuki・§11・§15.11、DESIGN.md ADR-35）。tools/gen_hosei_tsuzuki.py・tools/gen_teian.py と、
tools/ledger.py・tools/records.py・tools/update_links.py・tools/check_links.py に足した決まりを確かめる。

実行: python3 -B tools/test_teian.py -v
見本の小さな構造化の層（同じ年度の一般会計の回3つと国保の回1つ、○の行4つ）と発言を作り、通る例と通らない例を確かめる。
"""
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import check_links  # noqa: E402
import gen_gian_yosan as gg  # noqa: E402
import gen_hosei_tsuzuki as gt  # noqa: E402
import gen_mentions as gm  # noqa: E402
import gen_teian  # noqa: E402
import hosei  # noqa: E402
import ledger  # noqa: E402
import records as rc  # noqa: E402
import update_links  # noqa: E402
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


def built(st=None):
    return gt.build(st or struct())


class KaiOrderTest(unittest.TestCase):
    def test_order(self):
        order, pos = gt.kai_order(struct())
        self.assertEqual(order[("2024", "ippan")], K)
        self.assertEqual(pos[K[2]], ("2024", "ippan", 2))
        self.assertEqual(order[("2024", "kokuho")], [KK])

    def test_errors(self):
        for prev, msg in (({K[0]: "", K[1]: "", K[2]: K[1]}, "prev が空の回が 2 個"),
                          ({K[0]: "", K[1]: K[0], K[2]: K[0]}, "2つの回"),
                          ({K[0]: "", K[1]: K[0], K[2]: KK}, "同じ年度・会計の回でない")):
            with self.assertRaises(gm.GenError) as cm:
                gt.kai_order(struct(prev))
            self.assertIn(msg, str(cm.exception))

    def test_no_prev_column(self):
        rows = [{k: v for k, v in r.items() if k != "prev"} for r in kai_rows()]
        with self.assertRaises(gm.GenError) as cm:
            gt.kai_order(struct(kai=rows))
        self.assertIn("prev の列が無い", str(cm.exception))


class BuildTest(unittest.TestCase):
    def test_pairs_and_note(self):
        b = built()
        pairs = [(r["from"], r["to"]) for r in b.rows]
        self.assertEqual(pairs, [(f"hj:{K[2]}/m001", f"hj:{K[0]}/m001"), (f"hj:{K[2]}/m002", f"hj:{K[1]}/m001")])
        self.assertIn(f"間の回（{K[1]}）", b.rows[0]["note"])
        self.assertNotIn("間の回", b.rows[1]["note"])
        self.assertEqual(b.rows[1]["context"], "会計年度任用職員人件費(社会福祉総務費)")
        self.assertEqual(b.rows[1]["to_label"], "会計年度任用職員人件費（社会福祉総務費）")
        # t の行（特別会計）は対象にしない
        self.assertEqual(b.maru, 4)

    def test_ambiguous(self):
        base = maru_rows()[0]
        st = struct(maru=maru_rows([dict(base, key="m002")]))   # 第1号に同じ名前が2つ
        b = built(st)
        self.assertEqual(b.ambiguous, [f"hj:{K[2]}/m001"])
        self.assertEqual([r["from"] for r in b.rows], [f"hj:{K[2]}/m002"])

    def test_ledger_rows_parse(self):
        b = built()
        data = ledger.format_ledger(gt.generated_rows(b), gt.METHOD)
        rows = ledger.parse_ledger(data, gt.METHOD)
        self.assertEqual(len(rows), 2)
        bad = dict(rows[0], to=f"hj:{KK}/t001")
        with self.assertRaises(ledger.LedgerError) as cm:
            ledger.parse_ledger(ledger.format_ledger([bad], gt.METHOD), gt.METHOD)
        self.assertIn("to は○の行", str(cm.exception))
        bad = dict(rows[0], method="manual", status="confirmed", reviewer="kken78", date="2026-11-09")
        with self.assertRaises(ledger.LedgerError) as cm:
            ledger.parse_ledger(ledger.format_ledger([bad], gt.METHOD), gt.METHOD)
        self.assertIn("method が name でない", str(cm.exception))

    def test_match_to(self):
        b = built()
        c = gt.corpus(b)
        r = b.rows[0]
        self.assertEqual(ledger.match_full(r, c).result, ledger.MATCH)
        self.assertEqual(ledger.match_full(dict(r, to_label="違う名前"), c).result, ledger.STOPPED)
        self.assertEqual(ledger.match_full(dict(r, to=f"hj:{K[0]}/m009"), c).result, ledger.STOPPED)
        self.assertEqual(ledger.sentinel([r], c), [])


class TsuzukiErrorsTest(unittest.TestCase):
    def test_ok_and_errors(self):
        b = built()
        rows = gt.generated_rows(b)
        self.assertEqual(gt.tsuzuki_errors(rows, b), [])
        rev = dict(rows[0], **{"from": rows[0]["to"], "to": rows[0]["from"]})
        self.assertTrue(any("より後でない" in e for e in gt.tsuzuki_errors([rev], b)))
        conf = dict(rows[0], status="confirmed", reviewer="kken78", date="2026-11-09")
        self.assertTrue(any("判定：" in e for e in gt.tsuzuki_errors([conf], b)))
        conf["note"] += "。メモ：判定：行ごと（判定シート 15D-5）"
        self.assertEqual(gt.tsuzuki_errors([conf], b), [])
        dup = dict(rows[1], **{"from": rows[0]["from"]})
        self.assertTrue(any("1つまで" in e for e in gt.tsuzuki_errors([rows[0], dup], b)))
        rej = dict(dup, status="rejected", reviewer="kken78", date="2026-11-09", note="別の給付金の経費")
        self.assertEqual(gt.tsuzuki_errors([rows[0], rej], b), [])

    def test_update_and_check(self):
        b = built()
        with tempfile.TemporaryDirectory() as tmp:
            path, out = os.path.join(tmp, "hosei-tsuzuki.tsv"), os.path.join(tmp, "out")
            code, merged, checked, errors, lines = update_links.run_tsuzuki(b, path, out)
            self.assertEqual(code, 0)
            self.assertEqual(len(ledger.read_ledger(path, gt.METHOD)), 2)
            self.assertTrue(any("回をまたぐ同じ事業（§11）の誤り：0" in x for x in lines))
            code, rows, rep, errors = check_links.run_tsuzuki(b, path, out)
            self.assertEqual(code, 0)
            # 台帳から行を消すと、lock の版と違う（台帳と lock の版）
            ledger.write_ledger(path, rows[:1], gt.METHOD)
            code, rows, rep, errors = check_links.run_tsuzuki(b, path, out)
            self.assertEqual(code, 1)
            self.assertEqual(len(rep.stale), 1)
            os.remove(path)
            with self.assertRaises(ledger.LedgerError):
                check_links.run_tsuzuki(b, path, out)


TEXT1 = ("日程第１ 議第1号、令和６年度日野町一般会計補正予算（第１号）。\n"
         "まず、歳入でございます。第15款・国庫支出金につきましては、児童手当交付金を増額補正しております。\n"
         "続きまして、歳出でございます。児童手当支給事業におきまして、経費を新規計上しております。\n"
         "ご審議のほど、よろしくお願いいたします。\n"
         "日程第２ 議第2号、令和６年度日野町国民健康保険特別会計補正予算（第１号）。本案は国保です。")


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
    r = {"target": f"hj:{K[0]}/m001", "men": "事情", "bill": f"gi:{MID}/議第1号", "sid": f"sp:{S1}",
         "quote": "児童手当支給事業におきまして、経費を新規計上しております。", "status": "candidate", "reviewer": "", "date": "",
         "note": "下書き：2026-11-09・Opus 5.5（プロンプトの版なし）"}
    r.update(kw)
    return r


def check(rows, inp=None):
    rep = rc.Report()
    rc.check_teian(rows, inp or teian_inputs(), rep)
    return rep


class TeianTest(unittest.TestCase):
    def test_ok(self):
        z = trow(men="財源", quote="第15款・国庫支出金につきましては、児童手当交付金を増額補正しております。")
        z2 = trow(men="財源", quote="まず、歳入でございます。")
        rep = check([trow(), z, z2])
        self.assertEqual(rep.errors, [])
        self.assertEqual(rep.teian_segment, [])
        self.assertEqual(rep.teian_name, [])
        # 提案理由の記録に行のある回（第1号）の○の行は m001 だけで、事情の行がある
        self.assertEqual(rep.teian_no_jijo, [])
        self.assertEqual(rep.teian_group, [])

    def test_errors(self):
        cases = [(trow(target=f"hj:{KK}/t001"), "○の行"),
                 (trow(target=f"hj:{K[0]}/m009"), "構造化の層に無い"),
                 (trow(men="jijo"), "men が"),
                 (trow(bill=f"gi:{MID}/議第9号"), "gian.json に無い"),
                 (trow(bill=f"gi:{MID}/議第2号"), "対応しない"),
                 (trow(sid=f"sp:{S2}", quote="児童手当支給事業について伺います。"), "議員"),
                 (trow(sid="sp:0000000099_20240601_0001"), "索引に無い"),
                 (trow(note="見本"), "下書き：")]
        for r, msg in cases:
            rep = check([r])
            self.assertTrue(any(msg in e for e in rep.errors), (msg, rep.errors))

    def test_confirmed_quote_and_hantei(self):
        rep = check([trow(status="confirmed", reviewer="kken78", date="2026-11-10", quote="本文に無い文。")])
        self.assertTrue(any("判定：" in e for e in rep.errors))
        self.assertTrue(any("confirmed の引用" in e for e in rep.errors))

    def test_two_jijo(self):
        rep = check([trow(), trow(quote="続きまして、歳出でございます。")])
        self.assertTrue(any("事情の行が 2 行" in e for e in rep.errors))
        rep = check([trow(), trow(quote="続きまして、歳出でございます。", status="rejected", reviewer="kken78",
                                   date="2026-11-10", note="下書き：見本。判定：行ごと（判定シート X）")])
        self.assertFalse(any("事情の行が" in e for e in rep.errors))

    def test_lists(self):
        inp = teian_inputs(proposals=[])
        a = trow(target=f"hj:{K[2]}/m001", bill=f"gi:{MID}/議第1号")
        b = trow(target=f"hj:{K[2]}/m002", bill=f"gi:{MID}/議第1号")
        inp.gian_hs[f"gi:{MID}/議第1号"] = {f"hs:{K[0]}", f"hs:{K[2]}"}
        rep = check([trow(sid=f"sp:{S3}"), a, b], inp)
        self.assertEqual(rep.errors, [])
        self.assertEqual(len(rep.teian_segment), 3)                    # 区切りが無い
        self.assertEqual([x["target"] for x in rep.teian_name], [f"hj:{K[2]}/m002"])   # 名前が引用に無い
        self.assertEqual(rep.teian_no_jijo, [])
        self.assertEqual([(x["group"], x["size"], x["target"]) for x in rep.teian_group],
                         [("1", "2", f"hj:{K[2]}/m001"), ("1", "2", f"hj:{K[2]}/m002")])

    def test_no_jijo(self):
        rep = check([trow(men="財源")])
        self.assertEqual([x["target"] for x in rep.teian_no_jijo], [f"hj:{K[0]}/m001"])

    def test_base_name(self):
        self.assertEqual(rc.base_name("職員人件費（議会費） ほか"), "職員人件費")
        self.assertEqual(rc.base_name("会計年度任用職員人件費（社会福祉総務費）"), "会計年度任用職員人件費")
        self.assertEqual(rc.base_name("物価高騰対応重点支援事業（一体支援）"), "物価高騰対応重点支援事業")

    def test_columns(self):
        self.assertIn("teian", rc.LEDGERS)
        self.assertIn("teian", rc.OPTIONAL)
        self.assertEqual(rc.KEYS["teian"], ("target", "men", "sid", "quote"))


class GenTeianTest(unittest.TestCase):
    def test_portion_and_candidates(self):
        inp = teian_inputs()
        part = gen_teian.portion(inp.statements[S1]["text"], "議第1号", "令和６年度日野町一般会計補正予算（第１号）")
        self.assertEqual(part[0], "日程第１ 議第1号、令和６年度日野町一般会計補正予算（第１号）。")
        self.assertEqual(part[-1], "ご審議のほど、よろしくお願いいたします。")
        self.assertFalse(any("国民健康保険" in s for s in part))
        found = gen_teian.find_speech(inp, f"gi:{MID}/議第1号", "令和６年度日野町一般会計補正予算（第１号）")
        self.assertEqual(found[0], S1)
        cands = gen_teian.candidates(inp, inp.struct)
        jijo = [c for c in cands if c["target"] == f"hj:{K[0]}/m001" and c["men"] == "事情"]
        self.assertEqual(jijo[0]["sentence"], "児童手当支給事業におきまして、経費を新規計上しております。")
        self.assertEqual(jijo[0]["rank"], "1")
        self.assertEqual(jijo[0]["name_in"], "1")
        self.assertIn("児童手当支給事業", jijo[0]["sentence"])
        zai = [c for c in cands if c["target"] == f"hj:{K[0]}/m001" and c["men"] == "財源"]
        self.assertTrue(any("児童手当交付金" in c["sentence"] for c in zai))
        # 議案と回の台帳の confirmed の行が無い回（第2号・第3号）は、候補を作らず報告に数える
        self.assertEqual({c["target"].split("/")[0] for c in cands}, {f"hj:{K[0]}"})


if __name__ == "__main__":
    unittest.main()
