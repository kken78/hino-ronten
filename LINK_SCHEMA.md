# LINK_SCHEMA.md — 参照表とリンク台帳の規則

この文書は規範である。`tools/` の実装はこの文書に従う。キー・列・状態・正規化・照合の規則を変えるときは、この文書を先に改定し、検査 → 生成の順で実装を追従させる（CLAUDE.md 制約3）。設計判断の経緯は DESIGN.md に置く。

---

## 1. ファイルの共通形式

- TSV、UTF-8（BOMなし）、改行は LF、1行目がヘッダ
- セルの中にタブ・改行を入れない
- evidence・context は §4 の正規化を通した値を書く。名称（to_label・name など）は正規化せず、元のデータの表記のまま書く（どのデータの表記を使うかは §3 と §8 による）
- 空欄は空文字とする。推定で埋めない
- 行は from → to → method の文字コード順に並べる。並び順に意味を持たせない

---

## 2. キー

| 接頭辞 | 対象 | 形式 | 例 | 元のデータ |
| --- | --- | --- | --- | --- |
| bq | 議会だよりの一般質問 | `bq:<号>/<議員名>/<問番号>` | `bq:36/中西佳子/2` | council-dashboard `docs/data/questions.json` の issue・member・q_num |
| sp | 会議録の発言 | `sp:<sid>` | `sp:0000008942_20260305_0161` | hino-council-search `public/data/index/<年>.json` の sid |
| plan | manifest にある計画 | `plan:<id>` | `plan:kodomo` | shiga-hino-plans `data/manifest.json` の id |
| lin | manifest に無い前の期の計画 | `lin:<系列>/<期>` | `lin:kodomo/2` | `ref/lineage.tsv` |
| node | 計画の事業 | `node:<id>/<key>` | `node:jisshi/e001` | `data/plans/<id>.json` の programs（`items[].key`） |
| fh | 当初予算の附表の事業 | `fh:<附表id>/<key>` | `fh:fuhyo-r8/b001` | shiga-hino-plans `data/fuhyo/<附表id>.json` の `pillars[].items[].key` |
| none | 計画に当たる事業が無いこと（記載なし） | `none:<id>` | `none:jisshi` | shiga-hino-plans `data/manifest.json` の id |

- bq の議員名は、member を NFKC 正規化し、空白を除いたもの。この形で326問すべてが一意であることを確認済み（2026-10-10）
- sp は発言の位置に依存し、node の key は元のデータの管理に依存するため、単独では信頼しない。必ず §5 の照合を通す
- node は programs を持つ計画の事業にだけ定義する。key は shiga-hino-plans が事業に付ける番号で、一度付けたら変えず、使い回さない（shiga-hino-plans の CLAUDE.md・PLAN_SCHEMA）。key の無い事業は指さない
- node は、2026-10-19 に番号（`groups[].no`・`subgroups[].no`・`items[].no`）による形から key による形に替えた。番号の無い事業（jisshi など6計画）を指せないため（issue #1）。替えた時点で、台帳に node の行は無かった
- fh と none は、附表の台帳（`links/fuhyo.tsv`）だけで使う（§7 fuhyo）。fh の key は shiga-hino-plans が附表の事業に付ける番号で、一度付けたら変えず、使い回さない（shiga-hino-plans の PLAN_SCHEMA §9）。none は、附表の事業が `<id>` の計画のどの事業にも当たらないこと（記載なし）を表す決まったキーで、事業を指さない

---

## 3. リンク台帳 `links/<method>.tsv`

ファイル：`links/mention.tsv`、`links/program.tsv`、`links/fuhyo.tsv`（附表と計画の事業の対応。列の使い方は下の「附表の台帳」）。人が付け替えた行は `links/relink.tsv` に置く（§6 付け替え）。semantic を使う場合は `links/semantic.tsv` を加え、列の使い方をこの節に追記してから使う。crosswalk は台帳に行を持たず、`ref/crosswalk.tsv` から表示のときに求める（DESIGN.md ADR-3）。

| 列 | 内容 | 例 |
| --- | --- | --- |
| from | 議会側のキー（bq・sp） | `sp:0000008942_20260305_0161` |
| to | 計画側のキー（plan・lin・node） | `plan:kodomo` |
| method | mention・program・semantic・relink・fuhyo | `mention` |
| evidence | 一致した語（正規化後） | `子ども・子育て支援事業計画` |
| where | from のどこで一致したか。bq は title・question_text・answer_title・answers、sp は text | `text` |
| context | evidence を含む前後各15文字の抜粋（正規化後）。前後が15文字に満たない場合は、ある分だけ | `す。まとめるにあたりましては、子ども・子育て支援事業計画に掲げる3つの基本目標に分類し` |
| to_label | 確定した時点の to の名称。plan は manifest の name、lin は `ref/lineage.tsv` の name、node は `data/plans/<id>.json` の事業名（items[].name）。表記は元のデータのまま | `第3期 日野町子ども・子育て支援事業計画` |
| status | candidate・confirmed・rejected | `candidate` |
| reviewer | 確定・却下した人。candidate では空 | |
| date | 確定・却下した日（YYYY-MM-DD）。candidate では空 | |
| note | 期の判別の根拠、却下の理由など | `2026-03-05 は令和7年度。第3期（2025〜2029年度）` |

- 行の同一性は (from, to, method) の組とする。同じ組の行は1行だけ置く
- 例の行は、令和8年3月定例会議の企画振興課長の発言（実在）から作った候補で、まだ人は確定していない

附表の台帳（`links/fuhyo.tsv`）は、同じ11列を次のように使う（DESIGN.md ADR-10）。

- from：附表の事業（fh）。to：計画の事業（node）か、記載なし（none）。method：fuhyo
- evidence・context：附表の事業名（§4 の正規化を通した値。evidence と context は同じ）。where：name
- to_label：node は計画の事業名（items[].name）、none は「記載なし」
- note：候補を作った決まり（§7 fuhyo）、却下の理由など

---

## 4. 正規化

evidence・context と、照合の相手の本文に、同じ規則をかける。順に次のとおり。

1. NFKC 正規化
2. 改行に続く会議録のページ番号（`\n` の後の「数字-数字」）を除去
3. 前後をハイフンで挟んだページ番号（「-数字-」）を除去
4. 空白（全角・半角・改行・タブ）をすべて除去

- 照合のときは、台帳に記録済みの context にも現在の規則をかけ直してから比べる
- この規則は、hino-council-search の解析器の改善（ページ番号の除去など）に追従するためのもの。規則を変えたときは、全台帳の照合をやり直し、一致・移動・停止の件数を DESIGN.md ADR-4 に追記する
- 2026-10-10 の規則で、2026-08-01 と 2026-10-10 の会議録の発言索引を比べた結果は DESIGN.md ADR-4 にある

---

## 5. 位置依存キーの照合

ビルドのたびに、台帳の confirmed と candidate の全行について行う。rejected の行は、sp の移動を探すためだけに同じ手順をかける（下の「rejected の行」）。

sp（会議録の発言）：

1. sid の発言が存在し、その正規化本文に context が含まれる → 一致
2. 含まれない、または sid が存在しない → sid の最後の連番を除いた部分が同じ発言のうち、連番が前後5以内のものを探す
   - 1件だけ context を含む → 移動。移動先の sid を一覧（moved.tsv）に出す。その行は、人が from を書き換えるまで出力に使わない。ビルドは続ける
   - 0件、または2件以上 → 停止。行を一覧（stopped.tsv）に出し、終了コード1で終える

bq（議会だよりの質問）：where の欄の正規化テキストに context が含まれなければ停止する。where が answers の行は、answers のいずれかの要素の text に含まれれば一致とする。

node：現在の `data/plans/<id>.json` の programs に同じ key の事業が無いか、その事業の name が to_label と一致しなければ停止する。

fh：lock の版の `data/fuhyo/<附表id>.json` に同じ key の事業が無いか、その事業の name を §4 で正規化した値が context と一致しなければ停止する。

none：to_label が「記載なし」でないか、`<id>` が manifest に無ければ停止する。

plan・lin：to_label と、manifest または `ref/lineage.tsv` の name が一致しなければ停止する。

rejected の行：sp の行に 1・2 と同じ手順をかける。移動先が1件だけ見つかれば、移動の一覧（moved.tsv）に出す（人が from を書き換える。§6 のとおり、移動先に candidate を作らない）。移動先が0件または2件以上の場合は、一覧（rejected_unmatched.tsv）に出すだけで、終了コード1にはしない（rejected は出力に使わないため）。bq・node・plan・lin の rejected の行は照合しない。

停止したときは、人が原本で確かめ、from・to を直すか、status を rejected にして note に理由を書く。

一覧のファイルと列は §11 にある。

---

## 6. 状態の変わり方

- 生成：tools が candidate を作る。機械は status を confirmed・rejected にしない。台帳の更新（`tools/update_links.py`）は、候補の生成（`tools/gen_mentions.py`）の結果を同じ処理の中で受け取り（`build/` の候補のファイルは読まない）、次のとおり台帳に合わせる
  - 台帳に無い (from, to, method) の行：candidate として足す
  - 台帳に同じ組の candidate の行がある：11列すべてを新しい値にする（candidate の行は機械が持つ行とする）。note が変わった行は一覧（note_changed.tsv）に出す
  - 台帳に同じ組の confirmed・rejected の行がある：11列すべてを変えない（evidence・context は §5 の照合の土台であり、to_label は確定した時点の名称のため）
  - 台帳の confirmed・rejected の sp の行が §5 で移動となり、移動先の (sid, to, method) が生成の結果にある場合：移動先の組を candidate として足さない（人が from を書き換えたときに、同じ組の行が重ならないようにするため）
  - 付け替えの台帳（links/relink.tsv）の confirmed の行と同じ (from, to) の組が生成の結果にある場合：その組を mention の candidate として足さない（人がすでに付け替えで結び付けているため。§11 の付け替えの重なりにしない）。足さなかった組は件数を表示する
- 確定・却下：人が status を confirmed または rejected に変え、reviewer・date を書く。人が note を書くのはこのときとする（candidate の行の note は再生成で置き換わる）。rejected の行には、note に却下の理由を書く。confirmed と rejected の間の変更も人だけが行い、note に理由を書く
- まとめて確定：人は、同じ性質の candidate の組（例：期の明記がある、同じ to の行）から抜き取った行を1件ずつ判定し、その結果を見て、組の残りをまとめて confirmed にしてよい。抜き取りの数・選び方・まとめて確定する条件は、判定の前に DESIGN.md に書く。まとめて確定した行は、note に「抜き取りでまとめて確定（<組>、抜き取り<N>件・誤り0）」の形で書き、1件ずつ判定した行と区別する
- 計画期間の前の行（§7）：発言がその計画の策定（策定の予定・審議会・パブリックコメント・案など）を指していれば confirmed とする。その時点で計画期間中だった前の版を指していれば、理由を書いて rejected とする（期の番号が無い前の版は、付け替えの対象にしない）
- 付け替え：人は、却下した mention の行の発言が、別の計画（manifest にある plan か、`ref/lineage.tsv` にある lin）を指していると分かるときは、`links/relink.tsv` に method が relink の行を足して、その計画に結び付けてよい。from・evidence・where・context は却下した行と同じにし、to に正しい計画、to_label にその名称（§3）、status に confirmed、reviewer・date に付け替えた人と日を書く。note は「付け替え：<却下した行の to> の却下から。<理由>」の形にする。relink の行は機械が作らず、台帳の更新（tools/update_links.py）でも変えない。付け替えを取り消すときは、行を消さずに status を rejected にして note に理由を書く。期の番号が無い前の版の計画は、系譜表に載せる方法が決まるまで付け替えの対象にしない。附表の台帳（fuhyo）では付け替えを使わない
- 再生成で出なくなった行：candidate は削除し、一覧（removed.tsv）に出す。confirmed と rejected は削除せず、一覧（vanished.tsv）に出す。confirmed のうち再生成で出なくなったものがあれば、ビルドを停止する（別名辞書や系譜表の変更が既存の確定に影響したことを見落とさないため）。ただし、§5 で移動となり、移動先の (sid, to, method) が生成の結果にある confirmed・rejected は、出なくなった行に数えず、移動の一覧（moved.tsv）にだけ出す
- 台帳と lock の版：台帳は、lock の版の入力でこの節のとおり更新した結果と同じでなければならない。台帳を確かめる道具（`tools/check_links.py`）は、更新と同じ処理で台帳を作り直していまの台帳と比べ、違えば停止して、更新の道具を先に動かすよう示す（§10）
- 出力に使うのは、confirmed で、かつ §5 の照合が「一致」の行だけとする

---

## 7. 照合方法ごとの規則

mention：

- `ref/aliases.tsv` の全 series の語（正式名・略称）をまとめて、正規化後の本文から最長一致で探す。一致した範囲が重なる場合は長い方を採り、短い方は数えない（例：「文化財保存活用地域計画」の中の「地域計画」は chiiki-nogyo に数えない）
- 文脈で決める略称：ある series の語が、別の series の語の末尾と同じになる場合（例：chiiki-nogyo の「地域計画」は、bunkazai の「文化財保存活用地域計画」や kyojin の「国土強靭化地域計画」の末尾と同じ）、最長一致でその語だけが一致した言及は、語だけでは計画を決めず、次のとおり同じやりとりの中の手がかりで決める
  - 同じやりとり：会議録は、その発言を含む一般質問・質疑のまとまり（hino-council-search の segments のうち kind が ippan・shitsugi のもの）。まとまりに入らない発言は、その発言だけとする。議会だよりは、その問いの欄すべて（title・question_text・answer_title・answers）とする
  - 手がかり：その語を持つ series と、その語を末尾に持つ語の series（例では chiiki-nogyo・bunkazai・kyojin）の、語（正式名・略称）と文脈語（§9）
  - 言及より前にある手がかりのうち、いちばん近いものの series とする。前に無ければ、同じ本文（会議録は1つの発言、議会だよりは1つの欄）の言及より後ろで、いちばん近いものの series とする
  - どちらにも無ければ、台帳に行を作らず、`build/` の「文脈で決まらない」一覧に出す
  - 決まった series について、期の明記、系譜表による期の判別（§8）、期間外を、ほかの言及と同じに扱う。同じ本文で同じ to になる一致は、ほかの言及と同じに1行にまとめる
  - 文脈で決めた行は、note に「文脈で決めた（手がかり：文化財）」の形で、使った手がかりの語を書く
- 除外語（§9）の範囲に含まれる一致は数えない
- 期の明記：一致した語の直前に「第N期」または「第N次」がある場合、または直後に「（第N期）」「（第N次）」がある場合、その N を期とする。直前の場合は、「第N期」「第N次」と語の間に、「の」か「「」のどちらか1つと「日野町」を挟んでもよい（例：「第6次の総合計画」「第3期「子ども・子育て支援事業計画」」「第4期の日野町教育振興基本計画」）。N は算用数字または漢数字で、「期」と「次」のどちらで書かれていても N だけを使う
- 明記された期の行が `ref/lineage.tsv` に無い場合は、台帳に行を作らず、`build/` の「期の行なし」一覧に出す。人が系譜表に行を足してから再生成する（§2 の lin は系譜表にある期だけを指すため）
- 期の明記がない言及は `ref/lineage.tsv` で期を判別する（§8）。複数の期に当たる場合は、それぞれ candidate を作る
- 同じ本文（会議録は1つの発言、議会だよりは1つの欄）に、同じ series の期の明記のある言及と明記の無い言及があり、明記の無い言及が発言日で別の期に当たる場合も、どちらの行も candidate とする（明記の期にそろえない）。発言日で決めた行のうち、to が明記で決まったどの行とも違うものは、note に「同じ本文に期の明記がある（第6次）」の形で、その本文にある期の明記を書く（複数あれば、本文で出た順に「・」でつなぐ。期の行なしになった明記も含める）。明記の無い言及が明記と同じ期を指すか、発言日の期を指すかは本文によって違うため、人が確定する
- 期間外：期の明記がなく、発言日がその series のどの期の計画期間にも入らない場合は、台帳に行を作らず、`build/` の「期間外」一覧に出す。人が系譜表に行を足すか、対象外と判断する（前の版への言及を現行の計画に結び付けないため）。ただし、計画期間が空欄の期がある series は、その期の candidate を作り、note に「期間不明」と書く（§8）
- 計画期間の前：期間外のうち、発言の年度が、その series で初年度が最も早い期の初年度より前の3年以内（初年度−3 ≦ 年度 ＜ 初年度）の言及は、その計画を策定している間の言及の可能性があるため、期間外の一覧に出さず、その期の candidate を作る。note は「計画期間の前（2年前）。2023-09-01 は令和5年度。日野町文化財保存活用地域計画（2025〜2034年度）」の形とし、何年前かは初年度から発言の年度を引いた数とする。文脈で決めた行は、§7 の「文脈で決めた（手がかり：…）。」をその前に付ける。その時点で計画期間中だった前の版（系譜表に無い版）を指す場合もあるため、どちらを指すかは人が確定する（§6）
- 同じ plan への一致：系譜表で同じ plan を持つ複数の series（例：shogai-fukushi と shogai-jifukushi は、どちらも plan が shogai-fukushi7）に同じ発言が一致した場合は、to を `plan:<id>` とする1行にまとめる。evidence と context には本文で先に出た一致を使い、ほかに一致した語は note に書く
- 会議録は、role が議長の発言を対象から除く（設計案の試算と同じ）
- 会議録の目次の項目（sid の真ん中に mokuji を含むもの）は、発言ではないため対象から除く

program：

- 事業名（`items[].name`）を照合の語とする。一般的な語で誤った一致が多い事業は、`ref/aliases.tsv` に別名・除外語を足して対応する（工程8で決める）

fuhyo（附表と計画の事業の対応。DESIGN.md ADR-10）：

- 対象は、lock の files に名指しした附表（`data/fuhyo/<附表id>.json`）の全事業と、突き合わせる計画（令和8年度の附表は jisshi）の programs の全事業。事業名と事業概要は §4 で正規化して比べる
- 柱：附表の柱の no と、計画の programs ブロックを持つタブを文書の順に1から数えた番号を対応させる
- 事業名が同じ計画の事業を候補にする。同じ名前の事業が計画に2つ以上あるときは、事業概要も同じものだけを候補にする。事業概要も同じものが無ければ、同じ名前のすべてを候補にする。柱が違っても候補にし、note に書く
- 事業名も事業概要も同じ計画の事業が無い附表の事業には、none（記載なし）も候補にする
- 事業名が同じ計画の事業が無い附表の事業には、none と、同じ柱の計画の事業のうち、事業名の文字の2つ組（2-gram）の Dice 係数が大きい順に3つまで（0 のものは除く。同じ値は key の順）を候補にする
- Dice 係数は、正規化した事業名の隣り合う2文字の組の集まり（同じ組は1つと数える）で、2×共通の組の数÷（両方の組の数の和）とする。どちらかの組が0個なら0とする。note の値は小数第3位を四捨五入して小数第2位まで書き、並べるときは四捨五入する前の値を使う
- note は「事業名が同じ。事業概要も同じ」「事業名が同じ。事業概要は違う」「事業名が近い（Dice 0.67）」「事業名が同じ事業が無い」「事業名と事業概要が同じ事業が無い」の形とし、柱が違うときは「。柱が違う（附表 柱1・計画 柱5）」を後ろに付ける
- 判定は、確認ページで附表の事業を突き合わせの区分に仕分けてから、区分ごとに行う（DESIGN.md §5 工程5）。区分は、一致（事業名も概要も同じ）・一致（柱違い）（事業名も概要も同じで、柱だけ違う）・表記の違い（事業名は同じで、概要に小さな違いがあるだけ）・名称の変更（事業名が近く、同じ事業）・一部（実施計画の事業の一部を切り出した事業）・年度の事業（実施計画に無く、その年度に予算化された事業）・中身の違い（事業名は同じで、別の事業）。仕分けの案は Claude が作り、依頼者が確認ページで区分を移せる。一致と一致（柱違い）は、確認ページの一覧で全件を見たうえで、区分ごとにまとめて確定してよい（§6 の抜き取りによるまとめて確定とは別）。ほかの区分は1件ずつ判定する。附表の各事業は、confirmed の node が1行以上か、confirmed の none が1行のどちらかになる（DESIGN.md §5 工程5 のゲート）
- 一致・一致（柱違い）・表記の違い・名称の変更は、実施計画の事業（node）を確定する。一部・年度の事業・中身の違いは、記載なし（none）を確定し、附表の柱によって総合計画の柱に位置づける（実施計画の事業には結び付けない）
- 確定するときの判定のメモ（判定の一覧の note）は「区分：<区分>」で始める。依頼者が書いた説明があれば、その後ろに「。」でつなぐ（例「区分：一部。地域未来交付金事業（e163）の人員」）。台帳の note は、書き写しの道具が、候補を作った決まりの後ろに「。メモ：」でつないだ形になる（例「事業名が同じ。事業概要も同じ。メモ：区分：一致」）
- 判定の範囲（`--keys`）には、附表の事業ごとに、その事業の candidate の行をすべて入れる。書き写したあとに附表の分類（§11）の誤りが出るなら、台帳に書かずに終了コード1
- 正しい計画の事業が候補に無いときは、区分を一部・年度の事業・中身の違いのどれかにして、記載なし（none）を確定する。候補をすべて却下すると附表の分類（§11）の誤りになるため、記載なしは却下しない

semantic：使う時点で、この節と §3 に規則を追加する。

---

## 8. 系譜表 `ref/lineage.tsv`

| 列 | 内容 | 例 |
| --- | --- | --- |
| series | 計画の系列（下の規則で決める短い名前） | `kodomo` |
| edition | 期（数字）。期の概念がない計画は空 | `3` |
| plan | manifest の id。manifest に無い期は空（キーは `lin:<series>/<edition>`） | `kodomo` |
| name | manifest の name。manifest に無い期は原典の表記。1文書を分けた行は、manifest の name のうちその計画の部分 | `第3期 日野町子ども・子育て支援事業計画` |
| start_fy | 計画期間の初年度（西暦の年度） | `2025` |
| end_fy | 計画期間の最終年度（西暦の年度） | `2029` |
| source | 期間の出典（`manifest`、または原典の文書id＋ページ） | `manifest` |
| note | 延長・改定・中間見直しなどの注記 | |

- 載せる行：manifest の43本は全件載せる。manifest に無い期は、原典に名称が書かれているもの（現行の計画の本文に前の期として書かれているものなど）だけを載せ、source にその箇所を書く
- series：manifest の id から、末尾の期を表す数字を除いたもの（例：kyoiku3・kyoiku4 → kyoiku、sogo6 → sogo、kaigo9 → kaigo。kodomo はそのまま）。同じ系列の計画は同じ series にまとめる。数字を除くと別の系列と同じ名前になる場合は、人が決めて note に書く
- edition：その計画自体の名称に付いた「第N期」「第N次」の N（算用数字で書く）。名称に無い場合は空。上位の計画の期は edition にしない（例：jisshi「第6次総合計画 実施計画」の6は総合計画の期なので、jisshi の edition は空）
- 1つの文書に複数の計画が入っている場合は、計画ごとに行を分け、plan 列には同じ manifest の id を書く（例：shogai-fukushi7「第7期 障がい福祉計画・第3期 障がい児福祉計画」は、edition 7 の行と edition 3 の行の2行）。分けた行の series は人が決め、note に理由を書く
- source の書き方：`manifest`（manifest の start・end）、`plan:<id>`（`data/plans/<id>.json` の meta.period）、`<id>/<file> p.N`（shiga-hino-plans の `data/sources_index.tsv` の id と file、原典のページ）、または `<id>/page:<掲載ページのID>`（原典の台帳（sources_index.tsv）で file が空欄の、町の掲載ページ（HTML）の行を出典にする場合。`<id>` は台帳の id、ID は掲載ページの URL の番号（例：`senryaku2/page:8594`））。p.N は PDF ファイルの中のページ番号（印刷されたページ番号ではない）
- 年度は4月1日から翌年3月31日まで。令和N年度＝西暦2018＋N年度、平成N年度＝西暦1988＋N年度
- 発言日：会議録は sid の日付。sid に日付が無い場合は `meetings.json` の会議の日付（各会議の `date` 項目。hino-council-search #22 で足された。`dateFrom` が `pdf` の会議は、`date` が日付のある PDF のうち最も早い日と一致することを、`dateFrom` が `name` の会議は、日付のある PDF が無いことを確かめてから使う。合わなければ停止する）。議会だよりは対応する会議（`minutes_links.json` の meeting_id）の日付。対応する会議が無い号は人が確定する
- 期間を確認できない計画は start_fy・end_fy を空にする。その計画への期の明記がない言及は、candidate を作り、note に「期間不明」と書く

---

## 9. 別名辞書 `ref/aliases.tsv`

| 列 | 内容 | 例 |
| --- | --- | --- |
| series | 系譜表の series | `chiiki-nogyo` |
| term | 照合の語（正規化後） | `地域計画` |
| kind | 正式名・略称・除外・文脈語 | `略称` |
| note | 根拠・注記 | |

- 除外：日野町のどの計画の語でもない語（県や国の計画名、系譜表に無い計画の名前、計画名を含む会議や組織の名前など）で、その範囲を一致から外すための語。series 列には、その語の中で誤って一致する計画の series を書く（例：series が kyoiku、term が「滋賀県教育振興基本計画」、kind が除外）
- 文脈語：§7 の「文脈で決める略称」で、どの計画の話かの手がかりにする語（例：series が chiiki-nogyo、term が「農地」、kind が文脈語）。照合の語には使わない（文脈語だけでは言及にしない）
- 日野町の計画名どうしの重なり（「文化財保存活用地域計画」の中の「地域計画」など）は、§7 の最長一致で処理するため、除外には登録しない。最長一致で決まらない短い語（ほかの計画名の末尾と同じ語）は、§7 の「文脈で決める略称」で決める
- kanbatsu と chiiki-nogyo はダッシュボードを作らない計画だが、言及の照合と除外のために辞書に載せる

---

## 10. 入力の固定 `inputs.lock.json`

```json
{
  "council-dashboard": {
    "sha": "<40桁のコミットSHA>",
    "files": ["docs/data/questions.json", "data/minutes_links.json"]
  },
  "hino-council-search": {
    "sha": "<40桁のコミットSHA>",
    "files": ["public/data/index-manifest.json", "public/data/index/*.json", "public/data/proceedings.json", "public/data/meetings.json"]
  },
  "shiga-hino-plans": {
    "sha": "<40桁のコミットSHA>",
    "files": ["data/manifest.json", "data/plans/*.json", "data/sources_index.tsv", "data/fuhyo/fuhyo-r8.json"]
  }
}
```

- ビルドは、ここに書いた SHA の、ここに書いたファイルだけを読む
- 附表は年度ごとのファイルを名指しする（`data/fuhyo/*.json` とは書かない。見本の `_fuhyotest.json` を読まないため）
- lock の更新は1コミットにまとめ、追加・変更・削除された質問と発言の件数をコミットメッセージに書く

---

## 11. 実装に必要な検査

| 検査 | 内容 |
| --- | --- |
| 台帳の形 | §1 と §3 に合う（列名と列の順、UTF-8・BOMなし・LF、セルにタブ・改行が無い、行が from → to → method の文字コード順）。合わない台帳は、更新でも確かめでも停止し、並べ直さない |
| キーの形式 | 全行の from・to が §2 の形式に合う。from は bq・sp・fh、to は plan・lin・node・none。mention と relink の台帳は、from が bq・sp、to が plan・lin だけ。fuhyo の台帳は、from が fh、to が node・none だけ |
| 行の同一性 | (from, to, method) の重複が0件 |
| 状態 | status が3つの値のいずれか。confirmed・rejected は reviewer と date（YYYY-MM-DD）がある。candidate は reviewer と date が空。rejected は note が空でない |
| 欄の値 | where が、bq は title・question_text・answer_title・answers、sp は text、fh は name のいずれか。evidence・context が §4 の正規化を通した値で、context に evidence が含まれる |
| 位置依存キーの照合 | §5 の一致・移動・停止の件数を表示する。停止が1件以上なら終了コード1。rejected の行で移動先が見つからないものは件数を表示し、終了コードは変えない |
| 根拠の消失 | §6 の「再生成で出なくなった confirmed」が1件以上なら終了コード1 |
| 台帳と lock の版 | §6 のとおり lock の版で作り直した台帳と、いまの台帳が同じ。違えば終了コード1 |
| sentinel | 台帳を確かめるたびに、§5 の照合の対象の全行（confirmed と candidate）で、context の真ん中（文字数を2で割り、切り捨てた位置）の1文字を「〓」（context に「〓」が含まれるときは「※」）に替えて §5 の手順をかけ、移動か停止になることを確かめる。一致になる行が1件でもあれば終了コード1。台帳に検査用の行は置かない |
| 付け替えの元 | relink の各行について、from・evidence・context が同じで status が rejected の mention の行があり、その行の to と relink の行の to が違う。無ければ終了コード1。relink の行の status は confirmed か rejected で、candidate は置かない |
| 付け替えの重なり | relink の confirmed の行と同じ (from, to) を持つ mention の行が candidate か confirmed なら、一覧（relink_conflict.tsv）に出して終了コード1。人が、どちらかを却下するか、付け替えを取り消す |
| 方法の制限 | 台帳に crosswalk の行が無い。各行の method が台帳のファイル名（`links/<method>.tsv`）と同じ |
| 判定の範囲 | 人の判定の一覧を台帳に書き写すとき（`tools/apply_decisions.py`）、人が判定した範囲（`--keys` で渡す (from, to, method) の一覧。§1 の形で、列は from・to・method）と、判定の一覧の (from, to, method) の集まりが同じ。範囲の外の行、範囲にあって判定の無い行、範囲の一覧の中の重複が1件でもあれば、どちらの台帳にも書かずに終了コード1。書き写す前に、to と status ごとの件数を表示する。fuhyo の台帳では、to の種類（node・none）と status ごとに表示する（CLAUDE.md 不変の制約11） |
| 附表の分類 | fuhyo の台帳で、附表の全事業が from に1行以上ある。同じ from に confirmed の none と confirmed の node が両方あれば終了コード1。candidate の無い from で confirmed が1行も無ければ（候補をすべて却下した）終了コード1。confirmed の node か none で分類された事業の数と、まだ candidate のある事業の数を表示する（DESIGN.md §5 工程5 のゲート） |

一覧は `build/links/<method>/` に、§1 の形（行は from → to → method の文字コード順）で出す。

| ファイル | 内容 | 列 |
| --- | --- | --- |
| moved.tsv | §5 で移動となった行（confirmed・candidate・rejected） | from・to・method・status・moved_to・context |
| stopped.tsv | §5 で停止となった行（confirmed・candidate） | from・to・method・status・reason・context |
| rejected_unmatched.tsv | §5 で移動先が見つからなかった rejected の行（0件・2件以上） | from・to・method・status・reason・context |
| vanished.tsv | 再生成で出なくなった confirmed・rejected（移動として数えたものを除く） | §3 の11列・check（§5 の結果） |
| removed.tsv | 更新で削除した candidate | §3 の11列 |
| note_changed.tsv | 更新で note が変わった candidate | from・to・method・old_note・new_note |
| relink_conflict.tsv | 付け替えの重なりになった relink の行と mention の行 | from・to・relink_status・mention_status・context |
| update.md・check.md | 更新・確かめの件数の報告 | — |
