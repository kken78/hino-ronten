"""tools/run_oyo.py の検査（docs/eval-shisaku1.md §8）。claude は呼ばない。"""
import io
import os
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import run_oyo as ro  # noqa: E402

DOC = """# 評価
### 8.1 依頼文と会話の分け方

| 会話 | 依頼（言い換えない） |
| --- | --- |
| A | 依頼1：答弁の案を書いてください。→ 同じ会話で依頼2：上の答弁案を点検してください。 |
| B | 依頼3：一般質問を組み立ててください。 |

- どの会話も新しい会話で始める

### 8.2 動かし方
"""


class RunOyoTest(unittest.TestCase):
    def test_read_convs(self):
        c = ro.read_convs(DOC)
        self.assertEqual(c, {"A": [("依頼1", "答弁の案を書いてください。"), ("依頼2", "上の答弁案を点検してください。")],
                             "B": [("依頼3", "一般質問を組み立ててください。")]})

    def test_read_convs_of_eval_doc(self):
        with open(ro.EVAL_DOC, encoding="utf-8") as f:
            c = ro.read_convs(f.read())
        self.assertEqual({k: [r for r, _ in v] for k, v in c.items()},
                         {"A": ["依頼1", "依頼2"], "B": ["依頼3"], "C": ["依頼4"], "D": ["依頼5"]})
        for v in c.values():
            for _, t in v:
                self.assertTrue(t.endswith("。"), t)
                self.assertNotIn("→", t)

    def test_read_convs_stops(self):
        with self.assertRaises(ro.RunError):
            ro.read_convs("# 無い")

    def test_command(self):
        cmd = ro.command("opus", "/x/mcp.json")
        self.assertEqual(cmd[:4], ["claude", "-p", "--model", "opus"])
        self.assertIn("--strict-mcp-config", cmd)
        self.assertEqual(cmd[cmd.index("--allowedTools") + 1], "mcp__ronten__*")
        self.assertEqual(cmd[cmd.index("--tools") + 1], "")
        self.assertIn("--no-session-persistence", cmd)
        cmd = ro.command("opus", "/x/mcp.json", resume="sid1", single=False)
        self.assertEqual(cmd[cmd.index("--resume") + 1], "sid1")
        self.assertNotIn("--no-session-persistence", cmd)     # 続ける会話は保存する

    def test_env(self):
        with mock.patch.dict(os.environ, {"CLAUDECODE": "1", "CLAUDE_X": "1", "PATH": "/bin"}):
            e = ro.env()
        self.assertNotIn("CLAUDECODE", e)
        self.assertEqual(e["CLAUDE_CODE_DISABLE_CLAUDE_MDS"], "1")
        self.assertEqual(e["PATH"], "/bin")

    def test_body(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = os.path.join(tmp, "p.md")
            with open(p, "w", encoding="utf-8") as f:
                f.write("# 指示\n\n説明\n\n---\n\n決まり1\n")
            self.assertEqual(ro.body(p), "決まり1")
            with open(p, "w", encoding="utf-8") as f:
                f.write("# 指示\n")
            with self.assertRaises(ro.RunError):
                ro.body(p)

    def test_dry_run_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, "build", "theme"))
            with open(os.path.join(tmp, "build", "theme", "hoiku.json"), "w") as f:
                f.write("{}")
            with mock.patch.object(ro, "ROOT", tmp), mock.patch.object(shutil, "which", return_value="/bin/claude"), \
                    mock.patch.object(ro.subprocess, "run") as run:
                run.return_value = mock.Mock(stdout="abc1234\n")
                buf = io.StringIO()
                with redirect_stdout(buf):
                    rc = ro.main(["run_oyo.py", "--run", "t1", "--dry-run",
                                  "--common", os.path.join(ro.HERE, "..", "prompts", "shisaku1-common-v3.md"),
                                  "--oyo", os.path.join(ro.HERE, "..", "prompts", "shisaku1-oyo-v3.md")])
            self.assertEqual(rc, 0)
            self.assertFalse(os.path.exists(os.path.join(tmp, "build", "eval")))
            out = buf.getvalue()
            for name in ("opus-A", "sonnet-A", "opus-D", "sonnet-D"):
                self.assertIn(name, out)
            self.assertEqual(run.call_count, 1)          # git rev-parse だけ。claude は呼ばない


if __name__ == "__main__":
    unittest.main()
