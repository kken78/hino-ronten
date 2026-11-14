# 監査委員の資料の意見の部分の、段落と文の調べ（2026-11-14）

監査委員の資料の記録（DESIGN.md ADR-37）で、項目（列 suji）の切り方と記載の種類（列 kind）の付け方を決め直すために、意見の部分を全部、段落と文に分けて数えた。依頼者の指摘（文の構造が先、まず全部を調べる）による。調べと下書きは Fable 5.2。

## 1. 範囲

入力は hino-town-docs（60cd50b）の文字の層（data/text）と、構造化の層の表（data/struct/kansa-kekka.tsv・kessan-iken.tsv）の行の範囲。

| 資料 | 本数 | 範囲 | 段落 | 文 |
| --- | --- | --- | --- | --- |
| 各会計決算審査意見書 | 5冊 | 全会計のまとめと、健全化判断比率・資金不足比率の節（kessan-iken.tsv の115の部分） | 393 | 927 |
| 定期監査の報告 | 67本 | 「監査の結果」の本文（kansa-kekka.tsv の kekka_from〜kekka_to） | 157 | 482 |
| 財政援助団体等の監査の報告 | 13本 | 同じ | 24 | 50 |
| 計 | 85本 | | 574 | 1,459 |

範囲に入れていないもの：意見書の「決算の概要」の文章（まとめより前）、報告の「監査の結果」より前の部分。「指摘事項なし」など、「。」で終わらない1行だけの段落（13）は数から除いた。

## 2. 数え方

- 段落：表の行（かなが2字より少なく、読点・句点の無い行）とページ番号の行を除き、行をつなぐ。行が「。」で終わり、行の長さがその範囲の行の長さの9割の位置の値より3字以上短いとき、段落の終わりとする。①②…・ア．・○ などで始まる行は、新しい段落の始まりとする
- 文：空白を除いて「。」で切る
- 文の分け方：文末の字で、次の5つに仮に分けた。求め（〜されたい・〜お願いしたい・〜願いたい・〜期待する・〜望まれる など）、必要（〜必要がある・〜必要である・〜不可欠である・〜重要である・〜急務である・〜が求められる など）、先のこと（〜予想される・〜予測される・〜見込まれる・〜懸念される・〜心配される・〜恐れがある など）、判断（〜と思われる・〜が伺える・〜見受けられる・〜評価できる・〜認められる・〜推測される など）、述べる（ほかの全部）。この分け方は数えるための仮のもので、台帳の記載の種類（事実・見通し・評価・要望）とは別

## 3. 結果

文の数：述べる 789、求め 488、判断 89、先のこと 61、必要 32。

段落の文の数：1文 197、2文 138、3文 99、4文 76、5文 31、6文以上 33。

### 3.1 段落の最後の文

| 資料 | 段落 | 求め | 述べる | 判断 | 先のこと | 必要 |
| --- | --- | --- | --- | --- | --- | --- |
| 意見書 | 393 | 190 | 176 | 9 | 11 | 7 |
| 定期監査 | 157 | 132 | 20 | 3 | 1 | 1 |
| 団体の監査 | 24 | 7 | 8 | 9 | 0 | 0 |
| 計 | 574 | 329 | 204 | 21 | 12 | 8 |

2文以上の段落377では、求め 286、述べる 73、先のこと 10、判断 6、必要 2。

### 3.2 求めの文の位置

求めの文488のうち、段落の最後 286、段落の途中 144、1文だけの段落 43、段落の最初 15。1つの段落に求めの文が2つ以上ある段落は115。

求めの文に求めの文が続く所は106か所（86段落）。あとの文の書き出しは、また 28、なお 15、加えて 11、併せて 7、あわせて 4、特に 2、さらに 2、一方 2、他方 1、今後も 1、これらの語で始まらないもの 33。

### 3.3 段落の中の並び（同じ分け方が続く所は1つにまとめた。多い順）

| 並び | 段落 |
| --- | --- |
| 述べる | 187 |
| 述べる → 求め | 138 |
| 求め | 54 |
| 述べる → 求め → 述べる → 求め | 23 |
| 述べる → 判断 → 求め | 21 |
| 必要 → 求め | 16 |
| 判断 | 15 |
| 先のこと → 求め | 11 |
| 判断 → 述べる → 求め | 9 |
| 述べる → 先のこと → 求め | 9 |

### 3.4 「必要」に分けた32文

次に来るもの：求めの文 21、段落の終わり 8、述べる文 2、同じ分け方の文 1。段落の1文目は25文。

| 資料 | 部分 | 段落の中の位置 | 次 | 文の終わり |
| --- | --- | --- | --- | --- |
| kansa-r4-12 |  | 1／2 | 求め | …の実態があり、その原因を認知しているならば打開策を考える必要がある。 |
| kansa-r5-12 |  | 1／2 | 求め | …境施策も公共交通施策も関係課・関係機関や住民との連携が不可欠である。 |
| kansa-r6-02 |  | 1／5 | 求め | …ラブルの原因になるため、しっかりと外国人に説明することが必要である。 |
| kansa-r6-08 |  | 1／1 | （段落の終わり） | …や地権者が計画を策定する過程で話し合い、明確化することが重要である。 |
| kansa-r6-14 |  | 2／3 | 求め | …、孤立や“しんどさ”を抱えており、本人に寄り添った支援が必要である。 |
| kansa-r7-01 |  | 1／6 | 求め | …豪雨災害時の被害軽減や環境保全の面でも河川の適正な管理は重要である。 |
| kansa-r7-10 |  | 2／3 | 求め | …で行ってきたことを支援機関のネットワークで調整することが重要である。 |
| kessan-r3-ikensho | noshu/matome/zentai | 1／2 | 求め | …どに関する技術・専門知識を有する職員の技術・知識の継承が必要である。 |
| kessan-r3-ikensho | kaigo/matome/zentai | 1／3 | 求め | …とができるように地域包括ケアシステムの推進・深化を進める必要がある。 |
| kessan-r4-ikensho | noshu/matome/zentai | 1／2 | 求め | …どに関する技術・専門知識を有する職員の技術・知識の継承が必要である。 |
| kessan-r4-ikensho | kaigo/matome/zentai | 1／3 | 求め | …とができるように地域包括ケアシステムの推進・深化を進める必要がある。 |
| kessan-r4-ikensho | suido/matome/zentai | 3／4 | 述べる | …業収支を見極めながら進めなければならず、難しい事業運営が求められる。 |
| kessan-r4-ikensho | suido/matome/zentai | 1／2 | 求め | …持続するためには、専門的な技術・知識を有する職員が必要不可欠である。 |
| kessan-r4-ikensho | gesuido/matome/zentai | 1／4 | 述べる | …管路の整備も急務であり、これらの整備のための必要な投資が求められる。 |
| kessan-r4-ikensho | gesuido/matome/zentai | 1／1 | （段落の終わり） | …設の維持管理には、専門的な技術・知識を有する職員が必要不可欠である。 |
| kessan-r5-ikensho | kaigo/matome/zentai | 1／3 | 求め | …とができるように地域包括ケアシステムの推進・深化を進める必要がある。 |
| kessan-r5-ikensho | suido/matome/zentai | 1／2 | 求め | …持続するためには、専門的な技術・知識を有する職員が必要不可欠である。 |
| kessan-r5-ikensho | gesuido/matome/zentai | 1／1 | （段落の終わり） | …整備が急務であり、あと数年は雨水排水事業への大きな投資が求められる。 |
| kessan-r5-ikensho | gesuido/matome/zentai | 1／1 | （段落の終わり） | …設の維持管理には、専門的な技術・知識を有する職員が必要不可欠である。 |
| kessan-r6-ikensho | kaigo/matome/zentai | 1／3 | 求め | …とができるように地域包括ケアシステムの推進・深化を進める必要がある。 |
| kessan-r6-ikensho | suido/matome/zentai | 1／2 | 求め | …持続するためには、専門的な技術・知識を有する職員が必要不可欠である。 |
| kessan-r6-ikensho | gesuido/matome/zentai | 1／1 | （段落の終わり） | …整備が急務であり、あと数年は雨水排水事業への大きな投資が求められる。 |
| kessan-r6-ikensho | gesuido/matome/zentai | 1／1 | （段落の終わり） | …設の維持管理には、専門的な技術・知識を有する職員が必要不可欠である。 |
| kessan-r7-ikensho | ippan/matome/iken④ | 1／3 | 求め | …策目標を達成するための手段であり、その効果は高い公益性が求められる。 |
| kessan-r7-ikensho | ippan/matome/iken⑤ | 3／5 | 求め | …然防止・早期発見に向けたきめ細やかな労務管理体制の強化が急務である。 |
| kessan-r7-ikensho | ippan/matome/musubi | 6／6 | （段落の終わり） | …て、金利環境の変化による将来の公債費負担の増加にも留意が必要である。 |
| kessan-r7-ikensho | kaigo/matome/zentai | 1／3 | 求め | …できるように地域包括ケアシステムの推進・深化を一層進める必要がある。 |
| kessan-r7-ikensho | koki/matome/zentai | 1／2 | 求め | …、後期高齢者医療、保健事業の各部門が緊密に連携することが重要である。 |
| kessan-r7-ikensho | suido/matome/zentai | 1／2 | 求め | …持続するためには、専門的な技術・知識を有する職員が必要不可欠である。 |
| kessan-r7-ikensho | gesuido/matome/zentai | 2／3 | 必要 | …急務であることから、引き続き雨水排水事業への大きな投資が求められる。 |
| kessan-r7-ikensho | gesuido/matome/zentai | 3／3 | （段落の終わり） | …接続が計画されており、具体的な接続についての検討を進める必要がある。 |
| kessan-r7-ikensho | gesuido/matome/zentai | 1／2 | 求め | …設の維持管理には、専門的な技術・知識を有する職員が必要不可欠である。 |

## 4. この数の限り

- 段落の切れ目は、文字の層の改行と行の長さから決めた。行が「。」で終わり、行の長さが幅いっぱいの91行は、段落の終わりかどうかを決められず、続きとして数えた。原典の PDF の画像とは見比べていない
- 令和7年度の意見書の介護保険特別会計のまとめでは、文字の層の行が文の途中で切れている所があり、段落が実際より多く数えられている
- 文の分け方は文末の字による。「述べる」に入れた789文の中は読んでいない
- 意見書の一般会計の意見（①②…）は、番号の行で段落を分けた。番号の付いた意見1つの中の段落の数は、この調べでは見ていない

## 5. ここから決めたこと

LINK_SCHEMA §15.3（項目の境目の目安）と §15.6（記載の種類の付け方）。経過は DESIGN.md ADR-37。項目の境目は、この数を目安にして、文を読んで人が決める。

題材 kaigo の10本（定期監査5本と、意見書5冊の介護保険特別会計のまとめ）は、段落の切れ目を原典の PDF の字下げで確かめた（2026-11-14）。文字の層からの数えと違ったのは2本。意見書の令和7年度は、「当年度（令和７年度）は…」から「…推測される。」までが1つの段落（7段落）。定期監査の kansa-r7-02 は、書き出しの文が次の文と同じ段落（3段落）。kansa-r3-14 は4段落で、文字の層からの数え（3段落）より1つ多い。

## 6. 数え直し方

hino-town-docs を `/home/claude/hino-town-docs` に置いたときの道具。場所が違うときは `R` を書き換える。1つめで段落と文に分け（paras2.json）、2つめで分けて数える。

```python
import csv,re,collections,json,sys
R='/home/claude/hino-town-docs/'
def lines(doc): return open(R+f'data/text/{doc}.txt',encoding='utf-8').read().split('\n')
units=[]
for r in csv.DictReader(open(R+'data/struct/kansa-kekka.tsv'),delimiter='\t'):
    L=lines(r['doc']); units.append((r['shurui'],r['doc'],'kekka',L[int(r['kekka_from'])-1:int(r['kekka_to'])]))
for r in csv.DictReader(open(R+'data/struct/kessan-iken.tsv'),delimiter='\t'):
    L=lines(r['doc']); units.append(('ikensho',r['doc'],f"{r['kaikei']}/{r['bubun']}/{r['shurui']}{r['bango']}",L[int(r['line_from'])-1:int(r['line_to'])]))
HIRA=re.compile(r'[ぁ-ん]')
MARK=re.compile(r'^(?:[①-⑳]|[ア-オ]．|[・○◯●]|（[0-9０-９]+）|\([0-9]+\))')
def is_text(s):
    if re.fullmatch(r'[0-9０-９\-－ ]{1,6}',s): return False
    if len(HIRA.findall(s))>=2: return True
    if MARK.match(s): return True
    return bool(re.search(r'[。、]',s)) and not re.search(r'\d[\d,\.]+\s+[\d△]',s)
def paras(ls):
    tl=[l for l in ls if l.strip() and is_text(l.strip())]
    skipped=sum(1 for l in ls if l.strip())-len(tl)
    lens=sorted(len(l.rstrip()) for l in tl)
    w=lens[int(len(lens)*0.9)] if lens else 0
    out=[];cur='';unsure=0
    for l in tl:
        s=l.strip().strip('\f')
        if MARK.match(s) and cur: out.append(cur);cur=''
        cur+=s
        if s.endswith('。') and len(l.rstrip())<w-2:
            out.append(cur);cur=''
        elif s.endswith('。') and len(l.rstrip())>=w-2: unsure+=1
    if cur: out.append(cur)
    return out,skipped,unsure
def sents(p):
    p=re.sub(r'\s+','',p)
    return [x for x in re.findall(r'[^。]*。|[^。]+$',p) if x.strip()]
res=[];sk=un=0
for g,doc,lab,ls in units:
    ps,a,b=paras(ls);sk+=a;un+=b
    for i,p in enumerate(ps,1):
        res.append(dict(g=g,doc=doc,lab=lab,p=i,s=sents(p)))
json.dump(res,open('paras2.json','w'),ensure_ascii=False)
print('範囲',len(units),'段落',len(res),'文',sum(len(r['s']) for r in res),'表などとして除いた行',sk,'行末が「。」で幅いっぱいの行（段落の終わりか決められない）',un)
```

```python
import json,collections,re
res=json.load(open('paras2.json'))
def fam(s):
    t=s.rstrip('。')
    if re.search(r'(評価|期待)したい$',t): return '判断' if '評価' in t[-6:] else '求め'
    if re.search(r'(たい|願う|お願いする|いたします|お願いします|望む|望まれる|望むものである|期待する|期待している|期待される|期待するものである|求める|要望する|申し添える)$',t): return '求め'
    if re.search(r'(必要(が|で)ある|不可欠である|重要である|求められる|べきである|肝要である|急務である|大切である)$',t): return '必要'
    if re.search(r'(予想される|予測される|見込まれる|見込みである|懸念される|心配される|危惧される|恐れ(が|も)ある|ことになる|考えられる)$',t): return '先のこと'
    if re.search(r'(思われる|伺える|伺えた|窺える|見受けられ[るた]|評価(できる|する|すべき.*)|認められ[るた]|認める|認めます|否めない|いえる|言える|推測される|考える|感じ[るた]|感謝.*)$',t): return '判断'
    return '述べる'
out=[]
for r in res:
    if not r['s'][-1].endswith('。') and len(r['s'])==1: continue  # 「指摘事項なし」など
    r['f']=[fam(s) for s in r['s']]; out.append(r)
json.dump(out,open('fam.json','w'),ensure_ascii=False)
G={'ikensho':'意見書','teiki':'定期監査','dantai':'団体の監査'}
print('段落',len(out),'文',sum(len(r['s']) for r in out))
print(collections.Counter(G[r['g']] for r in out), {G[g]:sum(len(r['s']) for r in out if r['g']==g) for g in G})
c=collections.Counter(f for r in out for f in r['f']); print('文の数',c)
print('段落の文数',sorted(collections.Counter(min(len(r['s']),6) for r in out).items()))
print('段落の最後の文',collections.Counter(r['f'][-1] for r in out))
for g in G: print(' ',G[g],collections.Counter(r['f'][-1] for r in out if r['g']==g))
multi=[r for r in out if len(r['s'])>1]
print('2文以上の段落',len(multi),'最後',collections.Counter(r['f'][-1] for r in multi))
print('求めの文の位置',collections.Counter(('1文だけ' if len(r['f'])==1 else '最後' if i==len(r['f'])-1 else '最初' if i==0 else '途中') for r in out for i,f in enumerate(r['f']) if f=='求め'))
print('段落に求めが2つ以上',sum(1 for r in out if r['f'].count('求め')>=2))
def col(f):
    o=[]
    for x in f:
        if not o or o[-1]!=x: o.append(x)
    return '→'.join(o)
print(collections.Counter(col(r['f']) for r in out).most_common(25))
print('--必要')
for r in out:
    for i,f in enumerate(r['f']):
        if f=='必要':
            nxt=r['f'][i+1] if i+1<len(r['f']) else '（段落の終わり）'
            print(G[r['g']],r['doc'],r['lab'],f"{i+1}/{len(r['f'])}",'次:',nxt,'|',r['s'][i][-34:])
```
