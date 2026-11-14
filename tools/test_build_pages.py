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
                    sheet("fa:a", "施設", "見本園"), sheet("dist:hino", "地区", "日野"), sheet("org:kucho-kai", "組織", "日野町区長会"),
                    sheet("hoiku", "テーマ", "幼児教育・保育施設の再編")],
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
                                  ("dist:hino", "地区", "日野ノート"), ("org:kucho-kai", "組織", "日野町区長会ノート"),
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

    def test_template_frame(self):
        # 枠組みの表・事項の所の記載の行・同じ項目の記載・資料の種類と根拠法令の表（LINK_SCHEMA §16.1・§16.4。DESIGN.md ADR-37）
        t = template()
        for w in ("と、資料の記載状況", "該当する事項", "資料別の記載年", "議会での質問・答弁の記録数", "該当する事項なし", "未記録",
                  "項目の全文（", "文）", "の所へ", "資料は、まだ記録していません。", "この年度の決算の議案は、まだ記録していません。",
                  "提案の説明は、この会議の会議録にあります。発言ごとの出典は、まだ示していません。", "質疑・委員長の報告・討論は、まだ記録していません。",
                  "委員会の会議録はありません。", "この資料には、ここに出していない記載が", "件あります（事項の欄に出ます）。",
                  "文の頭の印は記載の種類、文の後ろの札は対応づけた事項（論点）です。",
                  "の手続きの順に、資料と議案を示します。", "の要素の順に、資料と議案を示します。", "による", "とは別のものです。",
                  "資料ごとに、記録した項目を段落で示します", "資料の種類と根拠法令", "作成者", "根拠法令", "提出先・公表",
                  "対応状況を確認できる資料",
                  "評価・要望・見通しの区分は、資料の作成者（監査委員など）が記した内容の種類です。論点ノートによる評価ではありません。",
                  "要素の名前は出典の語のままです。要素間の関係は、出典の図をご覧ください。", "'枠の要素':'本要素'"):
            with self.subTest(w=w):
                self.assertIn(w, t)
        # 利用者に見える文言に、作った言い方を出さない。要素の note（作業の注）を出さない
        for w in ("区切りのデータ", "項目の番号の無い行", "要素を番号の順", "段階を順に", "この段階", "テーマの議案", "同じ項目の記載", "筋", "述べ方", "書き手", "当たる点", "点が無い", "記録なし", "点なし", "作る者", "あて先", "現れる所", "確かめた所",
                  "e.note", "何にもとづく"):
            with self.subTest(w=w):
                self.assertNotIn(w, re.sub(r"/\*.*?\*/", "", t, flags=re.S))

    def test_out_path(self):
        for view, name in ((P, "hoiku-e008.html"), ("plan:kaigo9", "hoiku-kaigo9.html"), ("fa:nishioji-yo", "hoiku-nishioji-yo.html"),
                           ("dist:hino", "hoiku-hino.html"), ("org:kucho-kai", "hoiku-kucho-kai.html"), ("hoiku", "hoiku-theme.html"),
                           ("waku:kaigo-hokenryo/6", "hoiku-kaigo-hokenryo-6.html")):
            with self.subTest(view=view):
                self.assertTrue(bp.out_path("hoiku", view).endswith(os.path.join("build", "pages", name)))
        for bad in ("e008", "kaigo", "plan:", "fa:A", "dist:", "org:Kucho", "chiku:hino", "waku:kaigo-hokenryo",
                    "waku:kaigo-hokenryo/0"):
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

    def test_kadai_by_plan(self):
        # 課題が1つの計画だけ：箱の見出しは「<計画の名前>に掲げる課題」（§16.1）
        r = self.run_view("hoiku")
        self.assertIn("再編整備計画に掲げる課題", r["unei"])
        # 複数の計画にわたる：見出しは「計画に掲げる課題」、計画ごとの小見出しと出典
        d = json.loads(self.bytes.decode("utf-8"))
        d["plans"].append(dict(d["plans"][0], key="plan:other", name="別の計画"))
        sh = next(s for s in d["sheets"] if s["view"] == "hoiku")
        sh["kadai"].append({"ref": "plan:other/kadai/challenges/1/1", "text": "別の課題", "source": "other/honpen p.5",
                            "url": "https://example.invalid/other.pdf", "layer": "確定"})
        r2 = run_page(bp.render(template(), json.dumps(d, ensure_ascii=False).encode("utf-8"), "hoiku"))
        u = r2["unei"]
        self.assertIn("<h3>計画に掲げる課題</h3>", u)
        self.assertIn("<b>別の計画</b>", u)
        self.assertIn("別の計画 5ページ", u)
        self.assertIn("再編整備計画 18〜19ページ", u)

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

    def test_kessan_flow_records(self):
        # 決算の認定までの流れの要素3・4：提案の説明の記録の行（paras）と質疑の記録の行（rows）（LINK_SCHEMA §16.1。2026-11-15）
        import test_build_rag as tb
        d = json.loads(self.bytes.decode("utf-8"))
        b = tb.kessan_bill()
        d["bills"].append(b)
        d["waku"] = [{"key": "waku:kessan-nintei", "name": "決算の認定までの流れ", "source": "地方自治法233条", "url": "", "note": "",
                      "layer": "確定",
                      "elements": [{"view": f"waku:kessan-nintei/{n}", "n": n, "name": nm, "note": "", "source": "", "shiryo": [],
                                    "points": [], "rec": {}, "gikai": 0} for n, nm in ((3, "提出"), (4, "審議"), (5, "議決"))],
                      "nendo": [{"fiscal_year": "2023", "elements": [{"n": n, "docs": [], "gian": [b["key"]]} for n in (3, 4, 5)]}]}]
        u = run_page(bp.render(template(), json.dumps(d, ensure_ascii=False).encode("utf-8"), "hoiku"))["unei"]
        # 提案の説明：その行の下に段落ごと。同じ文は1回で札を行の数だけ、記載の種類が違う行の札に「（要望）」。事項の無い行は札なし
        self.assertIn('提案の説明　代表監査委員　<a href="p1"', u)
        self.assertIn('<p class="para"><span class="kd">事実</span>３年目にあたります。 <span class="kd">事実</span>計画比率は81.6パーセントにとどまりました。'
                      '<span class="fuda">給付費の計画と実績</span><span class="fuda">要介護認定率（要望）</span></p>', u)
        self.assertIn('<p class="para"><span class="kd">要望</span>連携をお願いします。<span class="um">未確認</span>'
                      '<span class="fuda">介護予防の取り組み</span></p>', u)
        self.assertLess(u.index("提案の説明　代表監査委員"), u.index("３年目にあたります。"))
        self.assertLess(u.index("提案の説明　町長"), u.index("提案の説明　代表監査委員"))
        # 質疑：発言ごとに見出しと、引用を字のまま1つの段落に。札は事項が変わる所の前と段落の終わりだけ
        self.assertIn('<div class="dochead">問い　4番 松田洋子 議員</div><p class="para">問1。 問2。<span class="fuda">給付費の計画と実績</span></p>', u)
        self.assertIn('<div class="dochead">答え　厚生主監</div><p class="para">答1。<span class="fuda">給付費の計画と実績</span> '
                      '答2。<span class="fuda">第8期の計画の指標</span> 答3。</p>', u)
        self.assertIn('<div class="dochead">再質問1　4番 松田洋子 議員</div><p class="para">再1。<span class="um">未確認</span>'
                      '<span class="fuda">介護予防の取り組み</span></p>', u)
        self.assertLess(u.index("質疑　4番 松田洋子 議員"), u.index("問1。"))
        self.assertLess(u.index("再1。"), u.index("決算特別委員会の委員長の報告"))
        self.assertIn("委員会の会議録はありません。", u)



@unittest.skipIf(shutil.which("node") is None, "node が無い")
class AreaScriptTest(unittest.TestCase):
    """地区・組織の見方の画面（§16.1・§16.4。DESIGN.md ADR-32）。tools/test_build_theme.py の見本に、
    kind 地区 dist:hino・組織 org:kucho-kai と、事柄「新こども園の定員」を dist:hino に出す views を足して作る。"""

    @classmethod
    def setUpClass(cls):
        import test_build_theme as tbt
        import test_records as tr
        cls.tr = tr
        area = tr.chiku_ref() + [dict(tr.soshiki_ref()[0], aliases="区長会;区長連絡会")]
        led = tr.ledgers()
        led["tsunagari"][0]["link"] = "目的と手段"      # 目的と手段の図に出す（提言 → 再編の方針）
        data = tbt.build(led=led, themes=tbt.area_rows(), area=area)
        cls.bytes = json.dumps(data, ensure_ascii=False).encode("utf-8")

    def run_view(self, view):
        return run_page(bp.render(template(), self.bytes, view))

    def test_district(self):
        r = self.run_view("dist:hino")
        self.assertEqual((r["title"], r["h1"]), ("日野ノート", "日野"))
        # 要点：地区の名前と、その地区の施設（参照表の district が日野の施設。fa:a は日野）
        self.assertIn("<span>地区</span> 日野", r["facts"])
        self.assertIn("<span>施設</span> 見本園", r["facts"])
        for w in ("当初予算額", "総合計画", "実施計画"):
            self.assertNotIn(w, r["facts"])
        self.assertIn("から本地区に関する記載を抜き出し", r["gaiyo"])      # 「本地区」（§16.4）
        self.assertIn("新こども園の定員", r["gaiyo"])                        # point の views に dist:hino
        self.assertNotIn("本事業", "".join(r.values()))

    def test_organization(self):
        r = self.run_view("org:kucho-kai")
        self.assertEqual((r["title"], r["h1"]), ("日野町区長会ノート", "日野町区長会"))
        self.assertIn("<span>組織</span> 日野町区長会", r["facts"])
        self.assertIn("<span>ほかの表記</span> 区長会、区長連絡会", r["facts"])
        self.assertNotIn("当初予算額", r["facts"])
        self.assertIn("から本組織に関する記載を抜き出し", r["gaiyo"])      # 「本組織」（§16.4）
        self.assertNotIn("新こども園の定員", r["gaiyo"])                     # dist:hino と e008 だけの点は出さない
        # 目的と手段の図：org:kucho-kai に出す記載「再編の方針」に「本組織」の印（§16.4）
        self.assertIn("再編の方針<small>本組織</small>", r["unei"])
        self.assertNotIn("<small>本地区</small>", r["unei"])
        self.assertNotIn("本事業", "".join(r.values()))

    def test_none(self):
        # 施設の無い地区（必佐）・ほかの表記の無い組織は「未記録」（§16.1）
        import test_build_theme as tbt
        tr = self.tr
        rows = sorted(tbt.area_rows() + [dict(tbt.theme_rows()[0], kind="地区", value="dist:hisa", views="", note="")],
                      key=lambda r: (r["theme"], r["kind"], r["value"]))
        raw = json.dumps(tbt.build(themes=rows), ensure_ascii=False).encode("utf-8")
        r = run_page(bp.render(template(), raw, "dist:hisa"))
        self.assertIn("<span>施設</span> 未記録", r["facts"])
        r = run_page(bp.render(template(), raw, tr.ORG))
        self.assertIn("<span>ほかの表記</span> 区長会", r["facts"])
        d = json.loads(raw)
        d["names"]["views"][tr.ORG]["aliases"] = []
        r = run_page(bp.render(template(), json.dumps(d, ensure_ascii=False).encode("utf-8"), tr.ORG))
        self.assertIn("<span>ほかの表記</span> 未記録", r["facts"])


if __name__ == "__main__":
    unittest.main()
