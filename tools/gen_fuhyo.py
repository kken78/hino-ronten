"""附表と計画の事業の対応の候補を作る（LINK_SCHEMA.md §2・§3・§7 fuhyo・§10、DESIGN.md ADR-10・§5 工程5）。

inputs.lock.json の shiga-hino-plans の files に名指しした附表（data/fuhyo/<附表id>.json）と、突き合わせる計画
（FUHYO_PLANS。令和8年度の附表は jisshi）の data/plans/<計画id>.json、data/manifest.json を git show で読み、
§7 fuhyo の決まりで候補を作って build/fuhyo/ に書く。台帳（links/）には書かない。
ツールが作るのは candidate まで（DESIGN.md ADR-2）。会議録・議会だよりの入力は読まない。

実行: python3 -B tools/gen_fuhyo.py
入力の clone の場所は、環境変数 HINO_RONTEN_INPUTS で変えられる（gen_mentions.py と同じ）。
終了コード：0 は build/fuhyo/ への書き出しまで終えた。1 は入力の誤りで止めた（件数と該当を表示する）。

§7 fuhyo の決まり：
- 事業名と事業概要（附表は desc、計画は items[].desc）は §4 で正規化して比べる
- 柱：附表の柱の no と、計画の programs ブロックを持つタブを文書の順に1から数えた番号を対応させる
- 事業名が同じ計画の事業を候補にする。同じ名前が計画に2つ以上あれば、事業概要も同じものだけ（無ければ同じ名前のすべて）
- 事業名も事業概要も同じ計画の事業が無ければ、none（記載なし）も候補にする
- 事業名が同じ計画の事業が無ければ、none と、同じ柱の計画の事業のうち Dice 係数の大きい順に3つまで（0 は除く。
  同じ値は key の番号の順）。Dice 係数は、同じ2文字の組を1つと数えた集まりで求め、note には四捨五入して小数第2位まで書く
"""
import math
import os
import re
import sys
from dataclasses import dataclass
from fractions import Fraction

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import gen_mentions as gm  # noqa: E402
import ledger  # noqa: E402
import mention  # noqa: E402

OUT_DIR = os.path.join(gm.ROOT, "build", "fuhyo")
METHOD = "fuhyo"
FUHYO_PLANS = {"fuhyo-r8": "jisshi"}  # 附表 → 突き合わせる計画（LINK_SCHEMA §7 fuhyo）
FUHYO_DIR = "data/fuhyo/"
FUHYO_PATH = re.compile(r"data/fuhyo/([a-z0-9][a-z0-9-]*)\.json")
FUHYO_KEY = re.compile(r"b[0-9]{3,}")
PROGRAM_KEY = re.compile(r"e[0-9]{3,}")
NEAR = 3  # 名前の近いものの数


# ---- 入力（§10） ----

@dataclass
class FuhyoInputs:
    lock: dict
    manifest: dict
    fuhyo: dict   # 附表id → 附表の JSON
    plans: dict   # 計画id → 計画の JSON


def read_fuhyo_inputs(gi, lock):
    """lock の files に名指しした附表と、FUHYO_PLANS の計画、manifest を読む。附表を「*」で指していれば止める（§10）。"""
    files = lock[gm.SP]["files"]
    named = [p for p in files if p.startswith(FUHYO_DIR)]
    gm._fail("lock の files で附表を「*」で指している（年度ごとのファイルを名指しする。LINK_SCHEMA §10）",
             [p for p in named if "*" in p])
    gm._fail("lock の files の附表のパスが data/fuhyo/<附表id>.json の形でない",
             [p for p in named if not FUHYO_PATH.fullmatch(p)])
    if not named:
        raise gm.GenError(f"lock の {gm.SP} の files に附表（{FUHYO_DIR}<附表id>.json）が無い")
    manifest = gi.read_json(gm.SP, "data/manifest.json")
    ids = {p.get("id") for p in manifest["plans"]}
    fuhyo, plans = {}, {}
    for p in named:
        fid = FUHYO_PATH.fullmatch(p).group(1)
        data = gi.read_json(gm.SP, p)
        if data.get("id") != fid:
            raise gm.GenError(f"{p}: id がファイル名と違う（{data.get('id')!r}）")
        pid = FUHYO_PLANS.get(fid)
        if pid is None:
            raise gm.GenError(f"{p}: 突き合わせる計画が FUHYO_PLANS に無い（{fid}）")
        if pid not in ids:
            raise gm.GenError(f"{p}: 突き合わせる計画 {pid} が manifest に無い")
        fuhyo[fid] = data
        if pid not in plans:
            plans[pid] = gi.read_json(gm.SP, f"data/plans/{pid}.json")
    return FuhyoInputs(lock, manifest, fuhyo, plans)


def manifest_names(manifest):
    """manifest の id → name（none の照合に使う）。id か name が空、id の重なりがあれば止める。"""
    names = {}
    for p in manifest["plans"]:
        if not p.get("id") or not p.get("name"):
            raise gm.GenError(f"manifest.json: id か name が空（{p.get('id')!r}）")
        if p["id"] in names:
            raise gm.GenError(f"manifest.json: id が重なっている（{p['id']}）")
        names[p["id"]] = p["name"]
    return names


def fuhyo_items(fid, data):
    """附表の事業の一覧（原典の順）。柱の no が1からの通し番号、key の形と一意、事業名が正規化しても空でないことを確かめる。"""
    errs, items, seen = [], [], set()
    for n, p in enumerate(data.get("pillars") or [], start=1):
        if p.get("no") != n:
            errs.append(f"{n}番目の柱の no が {p.get('no')!r}（{n} のはず）")
        for it in p.get("items") or []:
            key = it.get("key")
            if not isinstance(key, str) or not FUHYO_KEY.fullmatch(key):
                errs.append(f"柱{n}：key の形が違う（{key!r}）")
                continue
            if key in seen:
                errs.append(f"柱{n}：key が重なっている（{key}）")
                continue
            seen.add(key)
            name = mention.normalize(it.get("name") or "")
            if not name:
                errs.append(f"{key}：事業名が空")
                continue
            items.append({"key": key, "pillar": n, "name": it["name"], "n": name,
                          "d": mention.normalize(it.get("desc") or "")})
    if not items and not errs:
        errs.append("事業が0件")
    gm._fail(f"附表 {fid} の誤り", errs)
    return items


def _program_items(block):
    """programs ブロックの事業（groups[].items[] と groups[].subgroups[].items[]。PLAN_SCHEMA §6-B）。"""
    for g in block.get("groups") or []:
        yield from g.get("items") or []
        for s in g.get("subgroups") or []:
            yield from s.get("items") or []


def plan_programs(pid, plan):
    """計画の事業の一覧（文書の順）。柱は、programs ブロックを持つタブを文書の順に1から数えた番号。key が無いか重なれば止める。"""
    errs, items, seen, pillar = [], [], set(), 0
    for t in plan.get("tabs") or []:
        blocks = [b for b in t.get("blocks") or [] if b.get("type") == "programs"]
        if not blocks:
            continue
        pillar += 1
        for b in blocks:
            for it in _program_items(b):
                key = it.get("key")
                if not isinstance(key, str) or not PROGRAM_KEY.fullmatch(key):
                    errs.append(f"柱{pillar}：事業の key の形が違う（{key!r}。{it.get('name')}）")
                    continue
                if key in seen:
                    errs.append(f"柱{pillar}：事業の key が重なっている（{key}）")
                    continue
                seen.add(key)
                items.append({"key": key, "pillar": pillar, "name": it.get("name") or "",
                              "n": mention.normalize(it.get("name") or ""), "d": mention.normalize(it.get("desc") or "")})
    if not items and not errs:
        errs.append("programs の事業が0件")
    gm._fail(f"計画 {pid} の誤り", errs)
    return items


# ---- 候補（§7 fuhyo） ----

def bigrams(text):
    """隣り合う2文字の組の集まり（同じ組は1つと数える）。"""
    return {text[i:i + 2] for i in range(len(text) - 1)}


def dice(a, b):
    """§7 fuhyo の Dice 係数（Fraction）。2×共通の組の数÷（両方の組の数の和）。どちらかの組が0個なら0。"""
    x, y = bigrams(a), bigrams(b)
    if not x or not y:
        return Fraction(0)
    return Fraction(2 * len(x & y), len(x) + len(y))


def dice_text(value):
    """note に書く値：小数第3位を四捨五入して小数第2位まで（例 0.67）。"""
    n = math.floor(value * 100 + Fraction(1, 2))
    return f"{n // 100}.{n % 100:02d}"


def _key_number(key):
    return int(key[1:])


def _row(fid, f, to, to_label, note):
    return {"from": f"fh:{fid}/{f['key']}", "to": to, "method": METHOD, "evidence": f["n"], "where": "name",
            "context": f["n"], "to_label": to_label, "status": ledger.CANDIDATE, "reviewer": "", "date": "",
            "note": note}


def candidate_rows(fid, items, pid, programs):
    """§7 fuhyo の決まりで、附表の事業ごとに候補の行（台帳の11列）を作る。"""
    rows = []
    for f in items:
        same = [x for x in programs if x["n"] == f["n"]]
        cand = ([x for x in same if x["d"] == f["d"]] or same) if len(same) >= 2 else same
        for x in cand:
            note = "事業名が同じ。事業概要も同じ" if x["d"] == f["d"] else "事業名が同じ。事業概要は違う"
            if x["pillar"] != f["pillar"]:
                note += f"。柱が違う（附表 柱{f['pillar']}・計画 柱{x['pillar']}）"
            rows.append(_row(fid, f, f"node:{pid}/{x['key']}", x["name"], note))
        if not same:
            rows.append(_row(fid, f, f"none:{pid}", ledger.NONE_LABEL, "事業名が同じ事業が無い"))
            near = sorted(((dice(f["n"], x["n"]), x) for x in programs if x["pillar"] == f["pillar"]),
                          key=lambda t: (-t[0], _key_number(t[1]["key"])))
            for value, x in [t for t in near if t[0] > 0][:NEAR]:
                rows.append(_row(fid, f, f"node:{pid}/{x['key']}", x["name"], f"事業名が近い（Dice {dice_text(value)}）"))
        elif not any(x["d"] == f["d"] for x in same):
            rows.append(_row(fid, f, f"none:{pid}", ledger.NONE_LABEL, "事業名と事業概要が同じ事業が無い"))
    return rows


@dataclass
class FuhyoBuilt:
    inputs: FuhyoInputs
    rows: list        # 候補の行（台帳の11列。from → to → method の順）
    items: dict       # 附表id → 附表の事業の一覧
    programs: dict    # 計画id → 計画の事業の一覧
    names: dict       # manifest の id → name


def build(inp):
    names = manifest_names(inp.manifest)
    items = {fid: fuhyo_items(fid, data) for fid, data in sorted(inp.fuhyo.items())}
    programs = {pid: plan_programs(pid, plan) for pid, plan in sorted(inp.plans.items())}
    rows = [r for fid in items for r in candidate_rows(fid, items[fid], FUHYO_PLANS[fid], programs[FUHYO_PLANS[fid]])]
    keys = [(r["from"], r["to"], r["method"]) for r in rows]
    if len(set(keys)) != len(keys):
        raise gm.GenError("候補で (from, to, method) が重なっている")
    return FuhyoBuilt(inp, sorted(rows, key=lambda r: (r["from"], r["to"], r["method"])), items, programs, names)


def generated_rows(built):
    """台帳の11列の候補の行（ledger.merge に渡す）。"""
    return [{c: r[c] for c in ledger.LEDGER_COLUMNS} for r in built.rows]


def fuhyo_keys(built):
    """附表の全事業の fh（§11 附表の分類）。"""
    return sorted(f"fh:{fid}/{f['key']}" for fid, items in built.items.items() for f in items)


def corpus(built):
    """§5 の照合の相手（fh は附表の事業、node は計画の事業、none は manifest の id）。"""
    return ledger.Corpus(texts={}, by_pos={}, fields={}, names=built.names, refs=None,
                         fuhyo={(fid, f["key"]): f for fid, items in built.items.items() for f in items},
                         programs={(pid, x["key"]): x for pid, items in built.programs.items() for x in items})


# ---- 書き出し（build/fuhyo/） ----

def report_lines(built):
    rows = built.rows
    L = ["# 附表の候補（build/fuhyo/）", ""]
    for fid, items in built.items.items():
        pid = FUHYO_PLANS[fid]
        programs = built.programs[pid]
        names = {x["n"] for x in programs}
        same = sum(1 for f in items if f["n"] in names)
        L += [f"- 附表 {fid}：{len(items)} 事業。突き合わせる計画 {pid}：{len(programs)} 事業",
              f"- 事業名が同じ計画の事業がある附表の事業 {same}・無い事業 {len(items) - same}"]
    kinds = {k: sum(1 for r in rows if r["to"].startswith(k + ":")) for k in ("node", "none")}
    notes = {}
    for r in rows:
        k = r["note"].split("（")[0].split("。柱")[0]
        notes[k] = notes.get(k, 0) + 1
    per = {}
    for r in rows:
        per[r["from"]] = per.get(r["from"], 0) + 1
    dist = {}
    for v in per.values():
        dist[v] = dist.get(v, 0) + 1
    L += [f"- 候補：{len(rows)} 行（node {kinds['node']}・none {kinds['none']}）",
          f"- note の内訳：{'・'.join(f'{k} {v}' for k, v in notes.items())}",
          f"- 柱が違う行：{sum(1 for r in rows if '柱が違う' in r['note'])}",
          f"- 附表の事業ごとの候補の数：{'・'.join(f'{k}件 {v}事業' for k, v in sorted(dist.items()))}"]
    return L


def write_outputs(outdir, built):
    """build/fuhyo/ の candidates.tsv と report.md を書く。返り値は書いたファイルの名前。"""
    os.makedirs(outdir, exist_ok=True)
    gm.write_tsv(os.path.join(outdir, "candidates.tsv"), ledger.LEDGER_COLUMNS, generated_rows(built))
    with open(os.path.join(outdir, "report.md"), "wb") as f:
        f.write(("\n".join(report_lines(built)) + "\n").encode("utf-8"))
    return ["candidates.tsv", "report.md"]


def load_built():
    """lock の版から候補を作る（update_links.py・check_links.py・apply_decisions.py でも使う）。"""
    lock = gm.load_lock(gm.LOCK_PATH)
    gi = gm.GitInputs(gm.INPUTS_ROOT, lock)
    gi.verify()
    return build(read_fuhyo_inputs(gi, lock))


def main():
    try:
        built = load_built()
        names = write_outputs(OUT_DIR, built)
    except gm.GenError as e:
        print(f"停止：{e}", file=sys.stderr)
        return 1
    print("\n".join(report_lines(built)[2:]))
    print(f"書き出し：{OUT_DIR}/ の {'・'.join(names)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
