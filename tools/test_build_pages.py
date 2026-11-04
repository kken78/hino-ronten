"""tools/build_pages.py の検査（LINK_SCHEMA §16）。"""
import json
import os
import re
import shutil
import subprocess
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import build_pages as bp  # noqa: E402

P = "node:jisshi/e008"


def sheet(view, kind, name, **kw):
    s = {"view": view, "view_kind": kind, "name": name, "kadai": [], "cost": [], "desc": [], "vision": [], "tsunagari": [],
         "kotogara": [], "shisetsu": [], "katei": [], "asked": []}
    s.update(kw)
    return s


def data(**kw):
    d = {"theme": "hoiku", "name": "幼児教育・保育施設の再編",
         "programs": [{"key": P, "name": "認定こども園整備事業", "desc": "", "years": ["R8"], "layer": "確定", "policy": ""}],
         "sheets": [sheet(P, "事業", "認定こども園整備事業"), sheet("plan:youho", "期の計画", "再編整備計画"),
                    sheet("fa:a", "施設", "見本園"), sheet("hoiku", "テーマ", "幼児教育・保育施設の再編")],
         "records": {}, "names": {"sources": {}, "facilities": {}}, "theme_questions": 1, "chushin": P,
         "issues": [{"statement": "引用「</script><script>alert(1)</script>」"}]}
    d.update(kw)
    return json.dumps(d, ensure_ascii=False).encode("utf-8")


def template():
    with open(bp.TEMPLATE, encoding="utf-8") as f:
        return f.read()


def page_of(out):
    m = re.search(r'<script id="page" type="application/json">(.*?)</script>', out, re.S)
    return json.loads(m.group(1))


class RenderTest(unittest.TestCase):
    def test_template_shape(self):
        t = template()
        for p in bp.PLACEHOLDERS:
            self.assertEqual(t.count(p), 1, p)
        self.assertIsNone(bp.RE_EXTERNAL.search(t))
        self.assertNotIn("事業ノート", t)       # 見方の種類に依らない言い方（§16）

    def test_render(self):
        out = bp.render(template(), data(), P)
        self.assertTrue(out.startswith("<!doctype html>"))
        self.assertIn("<title>認定こども園整備事業ノート</title>", out)
        for p in bp.PLACEHOLDERS:
            self.assertNotIn(p, out)
        # データの中の </script> で script が閉じない
        body = out[out.index('<script id="data"'):]
        self.assertEqual(body.count("</script>"), 3)   # data・page・本体の3つ
        m = re.search(r'<script id="data" type="application/json">(.*?)</script>', out, re.S)
        self.assertEqual(json.loads(m.group(1))["issues"][0]["statement"], "引用「</script><script>alert(1)</script>」")
        page = page_of(out)
        self.assertEqual((page["view"], page["view_kind"], page["name"], page["theme"], len(page["source_sha256"])),
                         (P, "事業", "認定こども園整備事業", "hoiku", 64))
        self.assertIsNone(bp.RE_EXTERNAL.search(out))

    def test_render_views(self):
        for view, kind, title in (("plan:youho", "期の計画", "再編整備計画ノート"), ("fa:a", "施設", "見本園ノート"),
                                  ("hoiku", "テーマ", "幼児教育・保育施設の再編ノート")):
            with self.subTest(view=view):
                out = bp.render(template(), data(), view)
                self.assertIn(f"<title>{title}</title>", out)
                self.assertEqual((page_of(out)["view"], page_of(out)["view_kind"]), (view, kind))

    def test_same_input_same_output(self):
        self.assertEqual(bp.render(template(), data(), P), bp.render(template(), data(), P))

    def test_stops(self):
        with self.assertRaises(bp.PageError):
            bp.render(template(), data(), "node:jisshi/e999")
        with self.assertRaises(bp.PageError):
            bp.render(template(), data(sheets=[]), P)
        with self.assertRaises(bp.PageError):
            bp.render(template(), data(programs=[]), P)      # 見方が事業なのに programs に無い
        for k in ("names", "chushin"):
            d = json.loads(data())
            del d[k]
            with self.assertRaises(bp.PageError):
                bp.render(template(), json.dumps(d).encode("utf-8"), P)
        with self.assertRaises(bp.PageError):
            bp.render(template().replace("__PAGE__", "__PAGE____PAGE__"), data(), P)
        with self.assertRaises(bp.PageError):
            bp.render(template().replace("<main>", '<script src="https://example.jp/x.js"></script><main>'), data(), P)

    def test_out_path(self):
        for view, name in ((P, "hoiku-e008.html"), ("plan:kaigo9", "hoiku-kaigo9.html"), ("fa:nishioji-yo", "hoiku-nishioji-yo.html"),
                           ("hoiku", "hoiku-theme.html")):
            with self.subTest(view=view):
                self.assertTrue(bp.out_path("hoiku", view).endswith(os.path.join("build", "pages", name)))
        for bad in ("e008", "kaigo", "plan:", "fa:A"):
            with self.subTest(bad=bad):
                with self.assertRaises(bp.PageError):
                    bp.out_path("hoiku", bad)


# ---- ひな形の JS を node で動かす（node が無ければ飛ばす） ----

DOM = r"""
const fs=require('fs');const [data,page,script]=JSON.parse(fs.readFileSync(0,'utf8'));
const els={};
function el(id){return els[id]=els[id]||{id,textContent:id==='data'?data:id==='page'?page:'',innerHTML:'',hidden:false,
  addEventListener(){},setAttribute(){},removeAttribute(){},querySelectorAll(){return []},dataset:{}}}
global.document={title:'',getElementById:el,querySelector:s=>el(s),querySelectorAll:()=>[]};
global.location={hash:''};global.window={addEventListener(){}};
new Function(script)();
process.stdout.write(JSON.stringify({title:document.title,h1:els.h1.textContent,facts:els.facts.innerHTML,
  gaiyo:els['p-gaiyo'].innerHTML,ronten:els['p-ronten'].innerHTML,unei:els['p-unei'].innerHTML}));
"""


def run_page(out):
    """画面の文書のひな形の JS を、小さな DOM の代わりで動かし、書き込まれた欄を返す。"""
    data = re.search(r'<script id="data" type="application/json">(.*?)</script>', out, re.S).group(1)
    page = re.search(r'<script id="page" type="application/json">(.*?)</script>', out, re.S).group(1)
    script = re.search(r'<script>\n(.*?)</script>', out, re.S).group(1)
    p = subprocess.run(["node", "-e", DOM], input=json.dumps([data, page, script]), capture_output=True, text=True, timeout=60)
    if p.returncode != 0:
        raise AssertionError(p.stderr)
    return json.loads(p.stdout)


@unittest.skipIf(shutil.which("node") is None, "node が無い")
class ScriptTest(unittest.TestCase):
    """tools/test_build_theme.py の見本のデータから、見方ごとの画面を作って動かす。"""

    @classmethod
    def setUpClass(cls):
        import test_build_theme as tbt
        import test_records as tr
        d = tbt.make_data()
        d.inp.plans_in_lineage |= {"youho"}
        rows = tbt.with_views(tbt.theme_rows(), **{"記載/提言": "plan:youho", "施設/fa:a": "fa:a"})
        led = tr.ledgers()
        # テーマ全体の事柄（どの見方にも無い点）を1つ足す
        led["kotogara"].append(tr.row("kotogara", point="新こども園の用地", source="doc:teigen/2", source_date="2025-02",
                                      quote="再編の方針がある", kind="予定", target="令和10年度"))
        rows = tbt.with_views(rows, **{"事柄/新こども園の用地": ""})
        # 同じ最新の日付に value・target のある行がもう1つ（§16.2：全部を「／」で示す）
        led["kotogara"].append(tr.row("kotogara", point="新こども園の用地", source="doc:teigen/2", source_date="2025-02",
                                      quote="候補地は2つある", kind="予定", target="令和11年度"))
        # from の無い過程の段階（§16.2：1つ前の段階の直後に「日付なし」、年度の表は「年度不明」）
        led["katei"].append(tr.row("katei", theme="hoiku", step="2", name="検討会", sources="doc:teigen/1", quote="一頁目の文"))
        cls.bytes = json.dumps(tbt.build(led=led, themes=rows, d=d), ensure_ascii=False).encode("utf-8")
        cls.data = json.loads(cls.bytes)

    def run_view(self, view):
        return run_page(bp.render(template(), self.bytes, view))

    def test_program(self):
        r = self.run_view(P)
        self.assertEqual((r["title"], r["h1"]), ("認定こども園整備事業ノート", "認定こども園整備事業"))
        self.assertIn("基本施策(3) 幼児教育・保育の充実", r["facts"])      # policies から PROG.policy で引く
        self.assertIn("当初予算額", r["facts"])
        # 主な事項：その見方の事柄を先に、テーマ全体の事柄を後に（§16.2）
        g = r["gaiyo"]
        self.assertLess(g.index("新こども園の定員"), g.index("新こども園の用地"))
        self.assertIn("から本事業に関する記載を抜き出し", g)      # 事業の見方は「本事業」（§16.4）

    def test_plan(self):
        r = self.run_view("plan:youho")
        self.assertEqual(r["h1"], "再編整備計画")
        self.assertIn("2024〜2029年度", r["facts"])
        self.assertIn("令和7年3月策定", r["facts"])
        self.assertIn("① 人口減少、② 保育ニーズの変化", r["facts"])
        self.assertNotIn("当初予算額", r["facts"])
        # e008 の見方だけの事柄は出さない。テーマ全体の事柄は出す
        self.assertNotIn("新こども園の定員", r["gaiyo"])
        self.assertIn("新こども園の用地", r["gaiyo"])
        # 「本事業」は見方の種類で言い換える（§16.4）
        self.assertIn("から本計画に関する記載を抜き出し", r["gaiyo"])
        self.assertNotIn("本事業", "".join(r.values()))

    def test_facility(self):
        r = self.run_view("fa:a")
        self.assertEqual(r["h1"], "見本園")
        self.assertIn("日野", r["facts"])
        self.assertIn("<span>状況</span> 未記録", r["facts"])     # 状態の行が無い

    def test_theme(self):
        r = self.run_view("hoiku")
        self.assertEqual(r["h1"], "幼児教育・保育施設の再編")
        self.assertIn("再編整備計画", r["facts"])
        self.assertIn("中心の見方</span> 認定こども園整備事業（node:jisshi/e008）", r["facts"])
        self.assertIn("新こども園の定員", r["gaiyo"])
        self.assertIn("新こども園の用地", r["gaiyo"])
        self.assertTrue(r["ronten"] and r["unei"])

    def test_latest_all_and_katei_order(self):
        r = self.run_view("hoiku")
        g = r["gaiyo"]
        # 最新の日付の行が2つ：カードの値は「／」でつなぎ、開いた欄は値と引用を行ごとに（§16.2）
        self.assertIn("令和10年度／令和11年度（予定）", g)
        self.assertIn("<b>令和11年度</b>　候補地は2つある", g)
        # from の無い段階は、1つ前の段階（懇話会 2022-07）の直後に「日付なし」。「日付不明」ではない
        i, j = g.index("<b>懇話会</b>"), g.index("<b>検討会</b>")
        self.assertLess(i, j)
        self.assertEqual(g[g.rfind('<div class="d">', 0, j):j].count("日付なし"), 1)
        self.assertNotIn("日付不明", g)
        # 年度ごとの節目：末尾に「年度不明」の行
        u = r["unei"]
        self.assertIn("年度不明", u)
        self.assertGreater(u.index("年度不明"), u.index("令和4年度"))


if __name__ == "__main__":
    unittest.main()
