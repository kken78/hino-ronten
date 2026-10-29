"""tools/build_pages.py の検査（LINK_SCHEMA §16）。"""
import json
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import build_pages as bp  # noqa: E402

P = "node:jisshi/e008"


def data(**kw):
    d = {"theme": "hoiku", "name": "幼児教育・保育施設の再編",
         "programs": [{"key": P, "name": "認定こども園整備事業", "desc": "", "years": ["R8"], "layer": "確定"}],
         "sheets": [{"program": P}], "records": {}, "names": {"sources": {}, "facilities": {}}, "theme_questions": 1,
         "issues": [{"statement": "引用「</script><script>alert(1)</script>」"}]}
    d.update(kw)
    return json.dumps(d, ensure_ascii=False).encode("utf-8")


def template():
    with open(bp.TEMPLATE, encoding="utf-8") as f:
        return f.read()


class RenderTest(unittest.TestCase):
    def test_template_shape(self):
        t = template()
        for p in bp.PLACEHOLDERS:
            self.assertEqual(t.count(p), 1, p)
        self.assertIsNone(bp.RE_EXTERNAL.search(t))

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
        m = re.search(r'<script id="page" type="application/json">(.*?)</script>', out, re.S)
        page = json.loads(m.group(1))
        self.assertEqual((page["program"], page["theme"], len(page["source_sha256"])), (P, "hoiku", 64))
        self.assertIsNone(bp.RE_EXTERNAL.search(out))

    def test_same_input_same_output(self):
        self.assertEqual(bp.render(template(), data(), P), bp.render(template(), data(), P))

    def test_stops(self):
        with self.assertRaises(bp.PageError):
            bp.render(template(), data(), "node:jisshi/e999")
        with self.assertRaises(bp.PageError):
            bp.render(template(), data(sheets=[]), P)
        d = json.loads(data())
        del d["names"]
        with self.assertRaises(bp.PageError):
            bp.render(template(), json.dumps(d).encode("utf-8"), P)
        with self.assertRaises(bp.PageError):
            bp.render(template().replace("__PAGE__", "__PAGE____PAGE__"), data(), P)
        with self.assertRaises(bp.PageError):
            bp.render(template().replace("<main>", '<script src="https://example.jp/x.js"></script><main>'), data(), P)

    def test_out_path(self):
        self.assertTrue(bp.out_path("hoiku", P).endswith(os.path.join("build", "pages", "hoiku-e008.html")))
        with self.assertRaises(bp.PageError):
            bp.out_path("hoiku", "e008")


if __name__ == "__main__":
    unittest.main()
