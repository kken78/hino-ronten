"""tools/gen_fuhyo.py の検査（LINK_SCHEMA.md §2・§3・§7 fuhyo・§10、DESIGN.md §5 工程5）。

実行: python3 -B tools/test_gen_fuhyo.py -v
見本の附表と計画（FuhyoTestCase）は、tools/test_ledger.py・tools/test_apply_decisions.py でも使う。
"""
import copy
import os
import sys
import tempfile
import unittest
from fractions import Fraction

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import gen_fuhyo as gf  # noqa: E402
import gen_mentions as gm  # noqa: E402
import ledger  # noqa: E402

FID, PID = "fuhyo-r8", "jisshi"
FUHYO_FILE = f"data/fuhyo/{FID}.json"


def item(key, name, desc):
    return {"key": key, "kubun": [], "kan": "見本費", "name": name, "desc": desc, "details": [], "amount": 1,
            "dept": ["見本課"], "page": 1}


# 見本の附表：柱1・柱2 に8事業。§7 fuhyo の決まりの各場合を1つずつ持つ
FUHYO = {"id": FID, "fiscal_year": {"label": "令和8年度", "year": 2026},
         "source": {"id": FID, "file": "r8jigyou.pdf", "page_id": "8534"},
         "pillars": [
             {"no": 1, "name": "見本の柱1", "items": [
                 item("b001", "子育て支援事業", "子育てを支える。"),          # 名前も概要も同じ → node 1行
                 item("b002", "学校管理運営事業", "学校を新しく管理する。"),  # 名前は同じ・概要は違う → node と none
                 item("b003", "公民館　運営事業", "公民館を運営する。"),      # 全角空白を正規化して同じ名前。計画では柱2 → 柱が違う
                 item("b004", "学校給食事業", "給食を出す。"),                # 名前の同じものが無い → none と近いもの3つ（同じ値は key の順）
             ]},
             {"no": 2, "name": "見本の柱2", "items": [
                 item("b010", "組合負担金", "組合（救急）に負担金を出す。"),  # 同じ名前が2つ。概要で1つに絞れる（全角括弧を正規化）
                 item("b011", "組合負担金", "組合（総務）に負担金を出す。"),  # 同じ名前が2つ。絞れない → 2つと none
                 item("b012", "防災訓練", "訓練をする。"),                    # 名前の同じものが無く、近いものも無い（Dice 0）→ none だけ
                 item("b013", "道路改良事業", "道路を改良する。"),            # 名前の同じものが無く、近いものが2つ（0 は除く）
             ]}]}


def program(key, name, desc):
    return {"key": key, "name": name, "desc": desc, "years": ["R8"], "cost": {"label": "概算事業費", "amount": 1, "unit": "千円"}}


# 見本の計画：programs の無いタブを先頭に置き、programs を持つタブを1から数える。柱2 は subgroups の形
PLAN = {"schema_version": 1, "id": PID, "meta": {}, "theme": {}, "sources": [], "tabs": [
    {"id": "summary", "label": "まとめ", "blocks": [{"type": "narrative", "text": "見本"}]},
    {"id": "hito", "label": "柱1", "blocks": [
        {"type": "narrative", "text": "見本"},
        {"type": "programs", "title": "分野①", "source": "honpen p.1", "groups": [
            {"no": "分野①", "name": "見本", "items": [
                program("e001", "子育て支援事業", "子育てを支える。"),
                program("e002", "学校管理運営事業", "学校を管理する。"),
                program("e003", "学校教育振興事業", "教育を進める。")]}]}]},
    {"id": "chiiki", "label": "柱2", "blocks": [
        {"type": "programs", "title": "分野②", "source": "honpen p.2", "groups": [
            {"no": "分野②", "name": "見本", "subgroups": [
                {"no": "(1)", "name": "見本", "items": [
                    program("e010", "組合負担金", "組合(救急)に負担金を出す。"),
                    program("e011", "組合負担金", "組合(消防)に負担金を出す。"),
                    program("e012", "公民館運営事業", "公民館を運営する。"),
                    program("e013", "道路維持事業", "道路を直す。")]}]}]}]}]}

MANIFEST = {"schema": 1, "plans": [{"id": PID, "name": "第6次日野町総合計画 実施計画"}]}
LOCK = {"council-dashboard": {"sha": "a" * 40, "files": []},
        "hino-council-search": {"sha": "b" * 40, "files": []},
        "shiga-hino-plans": {"sha": "c" * 40, "files": ["data/manifest.json", "data/plans/*.json",
                                                        "data/sources_index.tsv", FUHYO_FILE]}}


def fh(key):
    return f"fh:{FID}/{key}"


def node(key):
    return f"node:{PID}/{key}"


NONE = f"none:{PID}"


class FakeInputs:
    """GitInputs の代わり（read_json だけ）。files にないパスは止める。"""

    def __init__(self, files):
        self.files = files
        self.read = []

    def read_json(self, repo, path):
        self.read.append((repo, path))
        if path not in self.files:
            raise gm.GenError(f"見本に無いパス（{path}）")
        return copy.deepcopy(self.files[path])


class FuhyoTestCase(unittest.TestCase):
    def inputs(self, fuhyo=None, plan=None, manifest=None):
        return gf.FuhyoInputs(lock=LOCK, manifest=copy.deepcopy(manifest or MANIFEST),
                              fuhyo={FID: copy.deepcopy(fuhyo or FUHYO)}, plans={PID: copy.deepcopy(plan or PLAN)})

    def built(self, **kw):
        return gf.build(self.inputs(**kw))

    def fuhyo_base(self, **kw):
        """見本の附表で、空の台帳から作った附表の台帳（すべて candidate）。"""
        b = self.built(**kw)
        return ledger.merge([], gf.generated_rows(b), gf.corpus(b)).rows

    @staticmethod
    def edited_fuhyo(target, **values):
        """見本の附表の写しで、key が target の事業の値を替えたもの。"""
        out = copy.deepcopy(FUHYO)
        for p in out["pillars"]:
            for it in p["items"]:
                if it["key"] == target:
                    it.update(values)
        return out

    @staticmethod
    def edited_plan(target, **values):
        """見本の計画の写しで、key が target の事業の値を替えたもの。"""
        out = copy.deepcopy(PLAN)
        for it in (x for t in out["tabs"] for b in t["blocks"] if b["type"] == "programs" for x in gf._program_items(b)):
            if it["key"] == target:
                it.update(values)
        return out

    @staticmethod
    def pairs(rows, frm):
        return [(r["to"], r["note"]) for r in rows if r["from"] == frm]

    @staticmethod
    def row(rows, frm, to):
        hits = [r for r in rows if r["from"] == frm and r["to"] == to]
        assert len(hits) == 1, (frm, to, hits)
        return hits[0]

    @staticmethod
    def decide(rows, frm, to, status, note="見本の判断"):
        """人の確定・却下（status・reviewer・date・note を書く）。"""
        out = [dict(r) for r in rows]
        for r in out:
            if r["from"] == frm and r["to"] == to:
                r.update(status=status, reviewer="見本", date="2026-10-20", note=note)
        return out


# 1. Dice 係数と note の値（§7 fuhyo）
class TestDice(unittest.TestCase):
    def test_set_of_bigrams(self):
        # 同じ2文字の組は1つと数える（重複を数えると 0.5 になる）
        self.assertEqual(gf.dice("ああああ", "ああ"), 1)
        self.assertEqual(gf.dice("学校給食事業", "学校管理運営事業"), Fraction(1, 3))
        self.assertEqual(gf.dice("子育て支援事業", "学校給食事業"), Fraction(2, 11))

    def test_zero(self):
        for a, b in (("", "学校"), ("学", "学校"), ("防災訓練", "道路維持事業")):
            with self.subTest(a=a, b=b):
                self.assertEqual(gf.dice(a, b), 0)

    def test_text_rounds_half_up(self):
        cases = {Fraction(2, 3): "0.67", Fraction(1, 3): "0.33", Fraction(1, 8): "0.13", Fraction(5, 8): "0.63",
                 Fraction(1, 200): "0.01", Fraction(2, 11): "0.18", Fraction(1): "1.00", Fraction(0): "0.00"}
        for v, text in cases.items():
            with self.subTest(v=v):
                self.assertEqual(gf.dice_text(v), text)


# 2. 候補の決まり（§7 fuhyo）
class TestCandidates(FuhyoTestCase):
    def setUp(self):
        self.rows = self.built().rows

    def test_same_name_same_desc(self):
        self.assertEqual(self.pairs(self.rows, fh("b001")), [(node("e001"), "事業名が同じ。事業概要も同じ")])

    def test_same_name_other_desc(self):
        self.assertEqual(self.pairs(self.rows, fh("b002")),
                         [(node("e002"), "事業名が同じ。事業概要は違う"), (NONE, "事業名と事業概要が同じ事業が無い")])

    def test_other_pillar(self):
        # 全角空白を除いて同じ名前。計画では柱2 → 候補にし、note に柱を書く
        self.assertEqual(self.pairs(self.rows, fh("b003")),
                         [(node("e012"), "事業名が同じ。事業概要も同じ。柱が違う（附表 柱1・計画 柱2）")])

    def test_two_same_names_narrowed(self):
        # 全角括弧を NFKC で正規化して、事業概要が同じものだけ
        self.assertEqual(self.pairs(self.rows, fh("b010")), [(node("e010"), "事業名が同じ。事業概要も同じ")])

    def test_two_same_names_not_narrowed(self):
        self.assertEqual(self.pairs(self.rows, fh("b011")),
                         [(node("e010"), "事業名が同じ。事業概要は違う"), (node("e011"), "事業名が同じ。事業概要は違う"),
                          (NONE, "事業名と事業概要が同じ事業が無い")])

    def test_no_same_name_near_three(self):
        # 同じ柱の3つ。e002 と e003 は同じ値（1/3）なので key の順、e001 は 2/11
        self.assertEqual(self.pairs(self.rows, fh("b004")),
                         [(node("e001"), "事業名が近い（Dice 0.18）"), (node("e002"), "事業名が近い（Dice 0.33）"),
                          (node("e003"), "事業名が近い（Dice 0.33）"), (NONE, "事業名が同じ事業が無い")])
        b = self.built()
        rows = gf.candidate_rows(FID, b.items[FID], PID, b.programs[PID])  # 並べ替える前の、候補を作った順
        self.assertEqual([r["to"] for r in rows if r["from"] == fh("b004")],
                         [NONE, node("e002"), node("e003"), node("e001")])

    def test_near_at_most_three(self):
        # 同じ柱に Dice が0より大きいものが4つ以上あっても3つまで
        plan = copy.deepcopy(PLAN)
        plan["tabs"][1]["blocks"][1]["groups"][0]["items"].append(program("e004", "学校給食センター事業", "見本"))
        rows = self.built(plan=plan).rows
        self.assertEqual([to for to, _ in self.pairs(rows, fh("b004"))], [node("e002"), node("e003"), node("e004"), NONE])

    def test_no_same_name_zero_excluded(self):
        self.assertEqual(self.pairs(self.rows, fh("b012")), [(NONE, "事業名が同じ事業が無い")])
        # 0 のもの（組合負担金）と別の柱のものは入れない。2つだけでもよい
        self.assertEqual(self.pairs(self.rows, fh("b013")),
                         [(node("e012"), "事業名が近い（Dice 0.18）"), (node("e013"), "事業名が近い（Dice 0.40）"),
                          (NONE, "事業名が同じ事業が無い")])

    def test_counts(self):
        kinds = [r["to"].partition(":")[0] for r in self.rows]
        self.assertEqual((len(self.rows), kinds.count("node"), kinds.count("none")), (16, 11, 5))
        self.assertEqual(len({r["from"] for r in self.rows}), 8)  # 附表のどの事業にも1行以上

    def test_row_columns(self):
        r = next(r for r in self.rows if r["from"] == fh("b003"))
        self.assertEqual(r, {"from": fh("b003"), "to": node("e012"), "method": "fuhyo", "evidence": "公民館運営事業",
                             "where": "name", "context": "公民館運営事業", "to_label": "公民館運営事業",
                             "status": "candidate", "reviewer": "", "date": "",
                             "note": "事業名が同じ。事業概要も同じ。柱が違う（附表 柱1・計画 柱2）"})
        r = next(r for r in self.rows if r["from"] == fh("b012"))
        self.assertEqual((r["to_label"], r["evidence"], r["context"]), ("記載なし", "防災訓練", "防災訓練"))
        # 台帳の形（§1・§3・§11）に合い、from → to → method の順に並ぶ
        self.assertEqual(ledger.parse_ledger(ledger.format_ledger(self.rows), "fuhyo"), self.rows)

    def test_to_label_is_raw(self):
        # to_label は計画の事業名の元の表記（正規化しない）
        plan = self.edited_plan("e001", name="子育て　支援事業")
        rows = self.built(plan=plan).rows
        self.assertEqual([(r["to_label"], r["evidence"]) for r in rows if r["from"] == fh("b001")],
                         [("子育て　支援事業", "子育て支援事業")])


# 3. 柱と事業の読み方
class TestItems(FuhyoTestCase):
    def test_plan_pillars(self):
        programs = gf.plan_programs(PID, PLAN)
        self.assertEqual([(x["key"], x["pillar"]) for x in programs],
                         [("e001", 1), ("e002", 1), ("e003", 1), ("e010", 2), ("e011", 2), ("e012", 2), ("e013", 2)])

    def test_fuhyo_items(self):
        items = gf.fuhyo_items(FID, FUHYO)
        self.assertEqual([(f["key"], f["pillar"]) for f in items][:5],
                         [("b001", 1), ("b002", 1), ("b003", 1), ("b004", 1), ("b010", 2)])
        self.assertEqual(gf.fuhyo_keys(self.built())[:2], [fh("b001"), fh("b002")])

    def test_fuhyo_errors(self):
        bad_no = copy.deepcopy(FUHYO)
        bad_no["pillars"][1]["no"] = 3
        cases = {"key の形": (self.edited_fuhyo("b001", key="b01"), "key の形が違う"),
                 "key の重なり": (self.edited_fuhyo("b002", key="b001"), "key が重なっている"),
                 "柱の no": (bad_no, "no が 3"),
                 "事業名が空": (self.edited_fuhyo("b001", name="　"), "事業名が空")}
        for name, (data, needle) in cases.items():
            with self.subTest(name=name):
                with self.assertRaises(gm.GenError) as cm:
                    gf.fuhyo_items(FID, data)
                self.assertIn(needle, str(cm.exception))

    def test_plan_errors(self):
        for name, (plan, needle) in {"key が無い": (self.edited_plan("e001", key=None), "key の形が違う"),
                                     "key の重なり": (self.edited_plan("e002", key="e001"), "key が重なっている")}.items():
            with self.subTest(name=name):
                with self.assertRaises(gm.GenError) as cm:
                    gf.plan_programs(PID, plan)
                self.assertIn(needle, str(cm.exception))


# 4. 入力の読み方（§10）：lock の files に名指しした附表だけを読む
class TestReadInputs(unittest.TestCase):
    FILES = {"data/manifest.json": MANIFEST, FUHYO_FILE: FUHYO, f"data/plans/{PID}.json": PLAN}

    def lock_with(self, files):
        lock = copy.deepcopy(LOCK)
        lock["shiga-hino-plans"]["files"] = files
        return lock

    def test_read(self):
        gi = FakeInputs(self.FILES)
        inp = gf.read_fuhyo_inputs(gi, LOCK)
        self.assertEqual((sorted(inp.fuhyo), sorted(inp.plans)), ([FID], [PID]))
        self.assertEqual(sorted(p for _, p in gi.read), sorted(self.FILES))  # 会議録・議会だよりは読まない

    def test_stops(self):
        base = ["data/manifest.json", "data/plans/*.json", "data/sources_index.tsv"]
        other = copy.deepcopy(FUHYO)
        other["id"] = "fuhyo-r7"
        files = dict(self.FILES, **{"data/fuhyo/fuhyo-r7.json": other, "data/fuhyo/fuhyo-r9.json": FUHYO})
        cases = {"「*」で指す": (base + ["data/fuhyo/*.json"], "「*」"),
                 "見本のファイル": (base + ["data/fuhyo/_fuhyotest.json"], "の形でない"),
                 "附表が無い": (base, "附表"),
                 "id がファイル名と違う": (base + ["data/fuhyo/fuhyo-r9.json"], "id がファイル名と違う"),
                 "突き合わせる計画が無い": (base + ["data/fuhyo/fuhyo-r7.json"], "FUHYO_PLANS に無い")}
        for name, (lock_files, needle) in cases.items():
            with self.subTest(name=name):
                with self.assertRaises(gm.GenError) as cm:
                    gf.read_fuhyo_inputs(FakeInputs(files), self.lock_with(lock_files))
                self.assertIn(needle, str(cm.exception))

    def test_plan_not_in_manifest(self):
        files = dict(self.FILES, **{"data/manifest.json": {"schema": 1, "plans": [{"id": "kodomo", "name": "見本"}]}})
        with self.assertRaises(gm.GenError) as cm:
            gf.read_fuhyo_inputs(FakeInputs(files), LOCK)
        self.assertIn("manifest に無い", str(cm.exception))

    def test_git_inputs_refuse_unlisted(self):
        # GitInputs は lock の files に無い附表（見本の _fuhyotest.json）を git に渡す前に止める
        gi = gm.GitInputs("/nonexistent", LOCK)
        with self.assertRaises(gm.GenError):
            gi.read_bytes("shiga-hino-plans", "data/fuhyo/_fuhyotest.json")


# 5. build/fuhyo/ への書き出し
class TestWriteOutputs(FuhyoTestCase):
    def test_twice_identical(self):
        outs = []
        with tempfile.TemporaryDirectory() as d:
            for n in range(2):
                out = os.path.join(d, f"out{n}")
                self.assertEqual(gf.write_outputs(out, self.built()), ["candidates.tsv", "report.md"])
                files = {}
                for name in os.listdir(out):
                    with open(os.path.join(out, name), "rb") as f:
                        files[name] = f.read()
                outs.append(files)
        self.assertEqual(outs[0], outs[1])
        self.assertEqual(outs[0]["candidates.tsv"], ledger.format_ledger(self.built().rows))
        report = outs[0]["report.md"].decode("utf-8")
        self.assertIn("候補：16 行（node 11・none 5）", report)
        self.assertIn("事業名が同じ計画の事業がある附表の事業 5・無い事業 3", report)


if __name__ == "__main__":
    unittest.main()
