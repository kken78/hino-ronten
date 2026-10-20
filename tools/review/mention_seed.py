"""言及の確認ページ（tools/review/mention_page.html）に入れる候補の束を作る（LINK_SCHEMA.md §3・§6、CLAUDE.md 不変の制約11）。

台帳 links/mention.tsv の candidate のうち、to が一致し（「,」で区切って複数）、発言日の年度が範囲に入る行を、
to の引数の順、その中は日付・from の順に並べる。年度の初めを 0 にすると年度で絞らない（期間不明の行も含める）。
各行に、場面・発言者・会議・出典のリンク（やりとりの中の発言は会議録の画面、外の発言は会議録の PDF、議会だよりは PDF）を付ける。

実行: python3 -B tools/review/mention_seed.py <to> <年度の初め> <年度の終わり> <束の id> <束の名前> <通し番号の始め> <out.json> [--ledger <links/mention.tsv>]
      python3 -B tools/review/mention_seed.py --targets   （ページの付け替え先の一覧 TARGETS を、系譜表と manifest から作って表示する）
入力の clone の場所は、環境変数 HINO_RONTEN_INPUTS で変えられる（gen_mentions.py と同じ）。
"""
import csv, hashlib, json, os, re, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import gen_mentions as g, mention  # noqa: E402

ROOT = g.ROOT


def targets(gi, lock):
    """付け替え先の一覧：系譜表の行ごとに key（plan:<id> か lin:<series>/<edition>）・series・名前（plan は manifest の name）。"""
    man = {p["id"]: p["name"] for p in gi.read_json("shiga-hino-plans", "data/manifest.json")["plans"]}
    out = []
    for r in csv.DictReader(open(g.LINEAGE, encoding="utf-8"), delimiter="\t"):
        key = f"plan:{r['plan']}" if r["plan"] else f"lin:{r['series']}/{r['edition']}"
        out.append({"key": key, "series": r["series"], "label": man[r["plan"]] if r["plan"] else r["name"]})
    return out


lock = g.load_lock(g.LOCK_PATH)
gi = g.GitInputs(g.INPUTS_ROOT, lock)
gi.verify()
if sys.argv[1:] == ["--targets"]:
    print("const TARGETS = " + json.dumps(targets(gi, lock), ensure_ascii=False) + ";")
    sys.exit(0)
args = sys.argv[1:]
ledger_path = os.path.join(ROOT, "links", "mention.tsv")
if "--ledger" in args:
    i = args.index("--ledger"); ledger_path = args[i + 1]; del args[i:i + 2]
to, fy0, fy1, batch, label, start, out = args[0], int(args[1]), int(args[2]), args[3], args[4], int(args[5]), args[6]


inp = g.read_inputs(gi, lock)
idx = {e['sid']: e for e in inp.index}
scenes = g.scene_of(inp.index, inp.proceedings)
ex = g.exchanges_of(inp.index, inp.proceedings)
qs = {g.bq_key(q): q for q in inp.questions}
mdates = g.meeting_dates(inp.meetings)

def date_of(r):
    """発言日：sp は sid の日付、bq は議会だよりの会議の日付（§8）。取れなければ ''。"""
    f = r['from']
    if f.startswith('sp:'):
        d = g.sid_date(f[3:])
    else:
        d = g.question_date(qs[f], inp.minutes_links, mdates)[1]
    return d.isoformat() if d else ''


def fy_of(r):
    d = date_of(r)
    if not d:
        return None
    y, mo = int(d[:4]), int(d[5:7])
    return y if mo >= 4 else y - 1


# fy0 が 0 なら年度で絞らない（期間不明の行も含める）
rows = [r for r in csv.DictReader(open(ledger_path, encoding='utf-8'), delimiter='\t')
        if r['status'] == 'candidate' and r['to'] in to.split(',')
        and (fy0 == 0 or (fy_of(r) is not None and fy0 <= fy_of(r) <= fy1))]


TO_ORDER = to.split(',')
rows.sort(key=lambda r: (TO_ORDER.index(r['to']), date_of(r), r['from']))  # to は引数の順、その中は日付順
docs = []
for n, r in enumerate(rows):
    d = {k: r[k] for k in ('evidence', 'where', 'context', 'to_label', 'note')}
    d = {'key_from': r['from'], 'key_to': r['to'], 'method': r['method'], **d, 'date': date_of(r)}
    f = r['from']
    if f.startswith('sp:'):
        sid = f[3:]
        e = idx[sid]
        d['scene'] = scenes.get(sid) or '範囲外'
        d['speaker'] = ' '.join(x for x in (e.get('role'), e.get('name')) if x)
        d['meeting'] = e.get('meeting')
        if sid in ex:
            d['link'] = f"https://kken78.github.io/hino-council-search/#thread={ex[sid][0][0]}&focus={sid}"
            d['link_label'] = '会議録で前後のやりとりを見る'
        else:
            d['link'] = e.get('pdf')
            d['link_label'] = '会議録PDFを開く'
    else:
        q = qs[f]
        d['scene'] = ''
        d['speaker'] = f"{q['member']} 議員（議会だより {q['issue']}号）"
        d['meeting'] = f"議会だより {q['issue']}号"
        d['qtitle'] = q['title']
        d['link'] = q['bulletin']
        d['link_label'] = '議会だよりを開く'
    d.update(order=start + n, batch=batch, batchLabel=label)
    d['id'] = hashlib.sha1(f"{r['from']}\t{r['to']}\t{r['method']}".encode()).hexdigest()[:16]
    docs.append(d)
json.dump(docs, open(out, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print(len(docs), 'orders', start, '-', start + len(docs) - 1)
