"""応用編の確かめ（docs/eval-shisaku1.md §8）：Claude Code（claude -p）に ronten の MCP の道具だけをつなぎ、会話を分けて動かす。

依頼文と会話の分け方は docs/eval-shisaku1.md §8.1 の表から読む（この道具に書かない）。どの会話も新しい会話で始め、
2つ以上の依頼がある会話（会話A）は、2つめから同じ会話を続ける（--resume）。使える道具は mcp__ronten__* だけで、
ほかの MCP・ファイル・コマンド・ウェブは使わせない。CLAUDE.md とメモリは読ませない。2つのモデルの会話を同時に進める。
標準ライブラリだけ。リポジトリの build/ のほかには何も書かない（--copy-to を渡したときの写しを除く）。

実行: python3 -I -B tools/run_oyo.py --run <回の名前> [--models opus,sonnet] [--convs A,B,C,D] [--jobs 4]
          [--common <共通の指示>] [--oyo <応用編の指示>] [--copy-to <まとめの写しを置くフォルダ>] [--dry-run]
      → build/eval/<回の名前>/<モデル>-<会話>.md・.meta.json・.t<番号>.jsonl・.mcp.jsonl、summary.md、all.md
      --dry-run は、行うことを表示するだけで、何も書かない
終了コード：0 は書いた（会話の中で止まったものは summary.md に書く）。1 は止めた。
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
EVAL_DOC = os.path.join(ROOT, "docs", "eval-shisaku1.md")
INPUTS = os.environ.get("HINO_RONTEN_INPUTS", "/home/kken78/GitHub")
TIMEOUT = 45 * 60
DISALLOWED = ["Bash", "Edit", "Write", "Read", "Glob", "Grep", "NotebookEdit", "WebFetch", "WebSearch", "Agent", "Task"]
RE_REQ = re.compile(r"(依頼\d+)：(.+?)(?=(?:→ 同じ会話で)?依頼\d+：|$)")


class RunError(ValueError):
    pass


def read_convs(text):
    """§8.1 の表：会話 → [(依頼の名前, 依頼文)]。"""
    s = text.find("### 8.1")
    if s < 0:
        raise RunError("docs/eval-shisaku1.md に §8.1 が無い")
    e = text.find("\n### ", s + 1)
    convs = {}
    for line in text[s:e if e > 0 else len(text)].split("\n"):
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) != 2 or not re.fullmatch(r"[A-Z]", cells[0]):
            continue
        reqs = [(m.group(1), m.group(2).strip().removesuffix("→").strip()) for m in RE_REQ.finditer(cells[1])]
        if not reqs:
            raise RunError(f"§8.1 の会話 {cells[0]} の依頼が読めない")
        convs[cells[0]] = reqs
    if not convs:
        raise RunError("§8.1 の表が読めない")
    return convs


def body(path):
    """指示のファイルの「---」の行より後。"""
    with open(path, encoding="utf-8") as f:
        lines = f.read().split("\n")
    if "---" not in lines:
        raise RunError(f"{path} に「---」の行が無い")
    return "\n".join(lines[lines.index("---") + 1:]).strip()


def sha(b):
    return hashlib.sha256(b if isinstance(b, bytes) else b.encode("utf-8")).hexdigest()


def env():
    e = {k: v for k, v in os.environ.items() if not k.startswith(("CLAUDE", "CCR_"))}
    e["CLAUDE_CODE_DISABLE_CLAUDE_MDS"] = "1"
    e["CLAUDE_CODE_DISABLE_AUTO_MEMORY"] = "1"
    return e


def first_message(prompt, req):
    return f"{prompt}\n\n## 依頼\n\n{req}\n"


def command(model, cfg, resume=None, single=True):
    cmd = ["claude", "-p", "--model", model, "--restricted", "--tools", "",
           "--allowedTools", "mcp__ronten__*", "--disallowedTools", *DISALLOWED,
           "--permission-mode", "dontAsk", "--disable-slash-commands",
           "--strict-mcp-config", "--mcp-config", cfg, "--output-format", "stream-json", "--verbose"]
    if resume:
        cmd += ["--resume", resume]
    if single:
        cmd += ["--no-session-persistence"]
    return cmd


def parse(log):
    init, result, calls = {}, {}, []
    with open(log, encoding="utf-8") as f:
        for line in f:
            try:
                ev = json.loads(line)
            except ValueError:
                continue
            if ev.get("type") == "system" and ev.get("subtype") == "init":
                init = ev
            elif ev.get("type") == "assistant":
                for c in (ev.get("message") or {}).get("content") or []:
                    if c.get("type") == "tool_use":
                        calls.append(f"{c.get('name')} {json.dumps(c.get('input'), ensure_ascii=False)}")
            elif ev.get("type") == "result":
                result = ev
    return init, result, calls


def run_conv(a, prompt, reqs, model, conv):
    name = f"{model}-{conv}"
    out = os.path.join(a.out, name)
    work = os.path.join(a.out, "work", name)
    cfg = os.path.join(work, "mcp.json")
    single = len(reqs) == 1
    if a.dry_run:
        return {"name": name, "conv": conv,
                "turns": [{"req": r, "msg_sha256": sha(first_message(prompt, t) if k == 0 else t + "\n")} for k, (r, t) in enumerate(reqs)]}
    os.makedirs(work, exist_ok=True)
    with open(cfg, "w", encoding="utf-8") as f:
        json.dump({"mcpServers": {"ronten": {
            "command": "python3", "args": ["-B", os.path.join(HERE, "mcp_ronten.py"), a.theme, a.program, "--log", out + ".mcp.jsonl"],
            "env": {"HINO_RONTEN_INPUTS": INPUTS}}}}, f, ensure_ascii=False)
    turns, sid, t_all = [], None, time.time()
    for k, (req, text) in enumerate(reqs, 1):
        msg = first_message(prompt, text) if k == 1 else f"{text}\n"
        log = f"{out}.t{k}.jsonl"
        t0 = time.time()
        with open(log, "w", encoding="utf-8") as f:
            p = subprocess.run(command(model, cfg, sid, single) + [msg], cwd=work, env=env(),
                               stdout=f, stderr=subprocess.PIPE, text=True, timeout=TIMEOUT)
        init, result, calls = parse(log)
        sid = result.get("session_id") or init.get("session_id")
        tools = init.get("tools") or []
        turns.append({"req": req, "model": init.get("model"), "exit_code": p.returncode, "stderr": p.stderr[-1500:],
                      "seconds": round(time.time() - t0), "num_turns": result.get("num_turns"),
                      "is_error": result.get("is_error"), "total_cost_usd": result.get("total_cost_usd"),
                      "usage": result.get("usage"), "tools_other_than_ronten": [t for t in tools if not t.startswith("mcp__ronten__")],
                      "mcp_servers": init.get("mcp_servers"), "tool_calls": calls, "msg_sha256": sha(msg),
                      "text": result.get("result") or ""})
        if p.returncode != 0 or not result or (not single and not sid):
            break
    meta = {"name": name, "conv": conv, "seconds": round(time.time() - t_all), "turns": turns}
    with open(out + ".meta.json", "w", encoding="utf-8") as f:
        json.dump({**meta, "turns": [{k: v for k, v in t.items() if k != "text"} for t in turns]}, f, ensure_ascii=False, indent=1)
    texts = dict(reqs)
    md = [f"# {name}（会話{conv}）", ""]
    for t in turns:
        md += [f"## {t['req']}", "", f"依頼文：{texts[t['req']]}", "",
               f"モデル {t['model']}・{t['seconds']}秒・道具の呼び出し {len(t['tool_calls'])}回・終了コード {t['exit_code']}", "",
               "### 答え", "", t["text"].rstrip("\n"), ""]
    with open(out + ".md", "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(md) + "\n")
    return meta


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    ap.add_argument("--models", default="opus,sonnet")
    ap.add_argument("--convs", default="")
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--theme", default="hoiku")
    ap.add_argument("--program", default="node:jisshi/e008")
    ap.add_argument("--common", default=os.path.join(ROOT, "prompts", "shisaku1-common-v3.md"))
    ap.add_argument("--oyo", default=os.path.join(ROOT, "prompts", "shisaku1-oyo-v4.md"))
    ap.add_argument("--copy-to", default="")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv[1:])
    try:
        with open(EVAL_DOC, encoding="utf-8") as f:
            all_convs = read_convs(f.read())
        convs = [c for c in a.convs.split(",") if c] or sorted(all_convs)
        for c in convs:
            if c not in all_convs:
                raise RunError(f"会話 {c} は §8.1 に無い（{'・'.join(sorted(all_convs))}）")
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", a.run):
            raise RunError("--run は英数字と _ . - だけにする")
        if shutil.which("claude") is None:
            raise RunError("claude のコマンドが見つからない")
        theme = os.path.join(ROOT, "build", "theme", f"{a.theme}.json")
        if not os.path.exists(theme):
            raise RunError(f"{theme} が無い（tools/build_theme.py {a.theme} で作る）")
        a.out = os.path.join(ROOT, "build", "eval", a.run)
        if os.path.exists(a.out) and not a.dry_run:
            raise RunError(f"{a.out} がもうある（--run で別の名前にする）")
        prompt = body(a.common) + "\n\n" + body(a.oyo)
    except (RunError, OSError) as e:
        print(f"止めた：{e}", file=sys.stderr)
        return 1
    models = [m for m in a.models.split(",") if m]
    head = subprocess.run(["git", "-C", ROOT, "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
    with open(theme, "rb") as f:
        theme_sha = sha(f.read())
    info = [f"# {a.run}：応用編の確かめ（docs/eval-shisaku1.md §8）", "",
            f"- hino-ronten {head}、build/theme/{a.theme}.json {theme_sha[:12]}、事業 {a.program}",
            f"- 指示：{os.path.relpath(a.common, ROOT)}（{sha(body(a.common))[:12]}）＋ {os.path.relpath(a.oyo, ROOT)}（{sha(body(a.oyo))[:12]}）",
            f"- 会話：{'・'.join(c + '（' + '→'.join(r for r, _ in all_convs[c]) + '）' for c in convs)}。モデル：{'・'.join(models)}。同時に {a.jobs}",
            "- どの会話も新しい会話で始め、使える道具は ronten の MCP の道具だけ。CLAUDE.md とメモリは読ませない", ""]
    print("\n".join(info), flush=True)
    jobs = [(m, c) for c in convs for m in models]       # モデルを交互に並べ、同時に進める
    if not a.dry_run:
        os.makedirs(a.out)
    with ThreadPoolExecutor(max_workers=max(1, a.jobs)) as ex:
        metas = list(ex.map(lambda j: run_conv(a, prompt, all_convs[j[1]], *j), jobs))
    if a.dry_run:
        for m in metas:
            print(m["name"], [(t["req"], t["msg_sha256"][:12]) for t in m["turns"]])
        return 0
    rows = ["| 会話 | モデル | 依頼 | 秒 | 道具の呼び出し | ronten 以外の道具 | 終了コード | 答えの字数 |",
            "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    for m in metas:
        for t in m["turns"]:
            rows.append(f"| {m['conv']} | {t['model']} | {t['req']} | {t['seconds']} | {len(t['tool_calls'])} | "
                        f"{'・'.join(t['tools_other_than_ronten']) or 'なし'} | {t['exit_code']} | {len(t['text'])} |")
        if len(m["turns"]) < len(all_convs[m["conv"]]):
            rows.append(f"| {m['conv']} | | 止まった：{m['name']} は {len(m['turns'])} 回目で止まった（.meta.json の stderr を見る） | | | | | |")
    summary = info + ["## まとめ", ""] + rows + [""]
    with open(os.path.join(a.out, "summary.md"), "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(summary) + "\n")
    parts = ["\n".join(summary)]
    for m in metas:
        with open(os.path.join(a.out, m["name"] + ".md"), encoding="utf-8") as f:
            parts.append(f.read())
    allp = os.path.join(a.out, "all.md")
    with open(allp, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n\n---\n\n".join(parts))
    if a.copy_to:
        shutil.copy(allp, os.path.join(a.copy_to, f"{a.run}-all.md"))
    print("\n".join(rows))
    print(f"\n書いた：{a.out}/" + (f" と {os.path.join(a.copy_to, a.run + '-all.md')}" if a.copy_to else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
