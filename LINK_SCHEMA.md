# LINK_SCHEMA.md — 参照表とリンク台帳の規則

この文書は規範である。`tools/` の実装はこの文書に従う。キー・列・状態・正規化・照合の規則を変えるときは、この文書を先に改定し、検査 → 生成の順で実装を追従させる（CLAUDE.md 制約3）。設計判断の経緯は DESIGN.md に置く。

---

## 1. ファイルの共通形式

- TSV、UTF-8（BOMなし）、改行は LF、1行目がヘッダ
- セルの中にタブ・改行を入れない
- evidence・context は §4 の正規化を通した値を書く。名称（to_label・name など）は正規化せず、元のデータの表記のまま書く（どのデータの表記を使うかは §3 と §8 による）
- 空欄は空文字とする。推定で埋めない
- 行は、ファイルごとの行のキーの順に並べる。キーの列は文字コード順とし、記録の台帳の row と step（1からの整数）は数の順とする（リンク台帳は from → to → method、テーマの定義は theme → kind → value（§11）、記録の台帳は §15 の各台帳の行のキー、施設の参照表は key（§15.8）。系譜表と別名辞書は、並び順を決めていない）。並び順に意味を持たせない
- 引用（記録の台帳の quote）は原文の表記のまま書き、照合のときに §4 の正規化をかける

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
| gi | 議案 | `gi:<会議id>/<議案番号>` | `gi:0000008942/議第115号` | hino-council-search `public/data/gian.json` の会議の id と `agenda[].no` |
| iq | 一般質問の問い | `iq:<sid>` | `iq:0000008397_20250310_0285` | hino-council-search `public/data/proceedings.json` の一般質問（kind が ippan）の turns で、問い（q）の最初の発言の sid |
| sq | 議案の質疑のまとまり | `sq:<sid>` | `sq:0000008942_20260305_0013` | hino-council-search `public/data/proceedings.json` の質疑（kind が shitsugi）のまとまりの、最初の発言の sid（from） |
| doc | 町の公開資料（1本、またはそのページ） | `doc:<id>` または `doc:<id>/<ページ>` | `doc:koho-no792-04`、`doc:koho-no792-04/1` | hino-town-docs `data/sources.tsv` の id と、PDF のページ（1から） |
| pt | 計画の原典の文字（1本、またはそのページ） | `pt:<id>/<名前>` または `pt:<id>/<名前>/<ページ>` | `pt:youho/honpen`、`pt:youho/honpen-202503/25` | shiga-hino-plans `data/sources_index.tsv` の id と file（拡張子を除いた名前）と、PDF のページ（1から）。原典の文字は `data/text/<id>/<名前>.txt` と `data/text_raw/<id>/<名前>.txt`（shiga-hino-plans PLAN_SCHEMA §10） |
| fa | 施設（建物・場所） | `fa:<英字>` | `fa:nishioji-yo` | `ref/shisetsu.tsv` の key（§15.8） |
| mb | 議員 | `mb:<名前>` | `mb:松田洋子` | hino-council-search の proceedings.json の一般質問の member と index の name、council-dashboard の questions.json の member。名前のそろえ方は bq と同じ |

- bq の議員名は、member を NFKC 正規化し、空白を除いたもの。この形で326問すべてが一意であることを確認済み（2026-10-10）
- sp は発言の位置に依存し、node の key は元のデータの管理に依存するため、単独では信頼しない。リンク台帳では §5 の照合を、記録の台帳では §15.1 の引用の照合を通す
- node は programs を持つ計画の事業にだけ定義する。key は shiga-hino-plans が事業に付ける番号で、一度付けたら変えず、使い回さない（shiga-hino-plans の CLAUDE.md・PLAN_SCHEMA）。key の無い事業は指さない
- node は、2026-10-19 に番号（`groups[].no`・`subgroups[].no`・`items[].no`）による形から key による形に替えた。番号の無い事業（jisshi など6計画）を指せないため（issue #1）。替えた時点で、台帳に node の行は無かった
- gi は、テーマの定義（§12）、テーマのノートのデータ（§13）、記録の台帳（§15）で使う。議案番号は gian.json の表記のまま（例「議第115号」「決議案第2号」）。同じ会議に同じ番号の議案が2つ以上あれば、その会議の gi は作らずに止める
- fh と none は、附表の台帳（`links/fuhyo.tsv`）だけで使う（§7 fuhyo）。fh の key は shiga-hino-plans が附表の事業に付ける番号で、一度付けたら変えず、使い回さない（shiga-hino-plans の PLAN_SCHEMA §9）。none は、附表の事業が `<id>` の計画のどの事業にも当たらないこと（記載なし）を表す決まったキーで、事業を指さない
- iq・sq と doc・pt は、記録の台帳（§15）とテーマの定義（§12）とテーマのノートのデータ（§13）だけで使う。iq・sq は sid と同じく位置に依存するため、記録の引用（quote）が発言の本文にあることで照合する。doc・pt は、引用がそのページの原典の文字にあることで照合する（§15.1）
- pt は計画の版ごとの原典の文字を指す。改正の前の版は、file の名前の末尾に策定か改正の年月6桁が付く（例 `honpen-202503`。shiga-hino-plans PLAN_SCHEMA §10.3）。計画の JSON の項目を指す参照（`plan:<id>/<tab>/<type>/<n>/<item>`、§13.1）とは別のもので、引用の照らし先には pt を使う（DESIGN.md ADR-22）
- fa は、施設の記録（§15.8）・テーマの定義（§12）・テーマのノートのデータ（§13）で使う。名前や所在地では施設を決められないので、参照表で決めた英字のキーとする（DESIGN.md ADR-23）
- mb も、記録の台帳・テーマの定義・テーマのノートのデータで使う。3つの入力で、この形の名前が一致することを確認した（2026-10-25。審議の記録25人・発言25人・議会だより13人）。表記の揺れが出たら、別名辞書に足す方法を決めてから使う

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

停止したときは、人が原本で確認し、from・to を直すか、status を rejected にして note に理由を書く。

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
- 台帳と lock の版：台帳は、lock の版の入力でこの節のとおり更新した結果と同じでなければならない。台帳を検査する道具（`tools/check_links.py`）は、更新と同じ処理で台帳を作り直していまの台帳と比べ、違えば停止して、更新の道具を先に動かすよう示す（§10）
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

- 対象は、lock の files に名指しした附表（`data/fuhyo/<附表id>.json`）の全事業と、突き合わせる計画（令和8年度の附表は jisshi）の programs の全事業。事業名と事業概要は §4 で正規化して比べる。計画の programs に key の無い事業や key の重なる事業があれば止める（§2 のとおり key の無い事業は指さないが、候補から黙って抜けないよう、候補を作る段階で止める）
- 柱：附表の柱の no と、計画の programs ブロックを持つタブを文書の順に1から数えた番号を対応させる。附表の柱に当たる計画の柱に事業が無ければ止める（名前の近い候補が黙って0件にならないように）
- 事業名が同じ計画の事業を候補にする。同じ名前の事業が計画に2つ以上あるときは、事業概要も同じものだけを候補にする。事業概要も同じものが無ければ、同じ名前のすべてを候補にする。柱が違っても候補にし、note に書く
- 事業名も事業概要も同じ計画の事業が無い附表の事業には、none（記載なし）も候補にする
- 事業名が同じ計画の事業が無い附表の事業には、none と、同じ柱の計画の事業のうち、事業名の文字の2つ組（2-gram）の Dice 係数が大きい順に3つまで（0 のものは除く。同じ値は key の文字コード順。§1 の並べ方と同じ）を候補にする
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
- 発言日：会議録は sid の日付。sid に日付が無い場合は `meetings.json` の会議の日付（各会議の `date` 項目。hino-council-search #22 で足された。`dateFrom` が `pdf` の会議は、`date` が日付のある PDF のうち最も早い日と一致することを、`dateFrom` が `name` の会議は、日付のある PDF が無いことを確認してから使う。合わなければ停止する）。議会だよりは対応する会議（`minutes_links.json` の meeting_id）の日付。対応する会議が無い号は人が確定する
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
    "files": ["public/data/index-manifest.json", "public/data/index/*.json", "public/data/proceedings.json", "public/data/meetings.json", "public/data/gian.json"]
  },
  "shiga-hino-plans": {
    "sha": "<40桁のコミットSHA>",
    "files": ["data/manifest.json", "data/plans/*.json", "data/sources_index.tsv", "data/fuhyo/fuhyo-r8.json"]
  },
  "hino-town-docs": {
    "sha": "<40桁のコミットSHA>",
    "files": ["data/sources.tsv", "data/text/*.txt", "data/ocr/*.txt"]
  }
}
```

- ビルドは、ここに書いた SHA の、ここに書いたファイルだけを読む
- `public/data/gian.json`（会議ごとの議案と結果）は、経緯の検証やテーマの議案の候補に使う（DESIGN.md §5）。いまの台帳の候補と照合には使わない
- hino-town-docs（町の公開資料。DESIGN.md ADR-14）は、テーマのノートのデータ（§13）の語の一致・資料の一覧、記録の台帳（§15）の引用の照合に使う。リンク台帳の候補と照合には使わない。data/text/ は原典の文字、data/ocr/ は OCR の下書きで、§13 と §15.1 の決まりで使い分ける
- 附表は年度ごとのファイルを名指しする（`data/fuhyo/*.json` とは書かない。見本の `_fuhyotest.json` を読まないため）
- lock の更新は1コミットにまとめ、追加・変更・削除された質問と発言の件数をコミットメッセージに書く

---

## 11. 実装に必要な検査

| 検査 | 内容 |
| --- | --- |
| 台帳の形 | §1 と §3 に合う（列名と列の順、UTF-8・BOMなし・LF、セルにタブ・改行が無い、行が from → to → method の文字コード順）。合わない台帳は、更新でも検査でも停止し、並べ直さない |
| キーの形式 | 全行の from・to が §2 の形式に合う。from は bq・sp・fh、to は plan・lin・node・none。mention と relink の台帳は、from が bq・sp、to が plan・lin だけ。fuhyo の台帳は、from が fh、to が node・none だけ |
| 行の同一性 | (from, to, method) の重複が0件 |
| 状態 | status が3つの値のいずれか。confirmed・rejected は reviewer と date（YYYY-MM-DD）がある。candidate は reviewer と date が空。rejected は note が空でない |
| 欄の値 | where が、bq は title・question_text・answer_title・answers、sp は text、fh は name のいずれか。evidence・context が §4 の正規化を通した値で、context に evidence が含まれる。fh の行は evidence と context が同じ |
| 位置依存キーの照合 | §5 の一致・移動・停止の件数を表示する。停止が1件以上なら終了コード1。rejected の行で移動先が見つからないものは件数を表示し、終了コードは変えない |
| 根拠の消失 | §6 の「再生成で出なくなった confirmed」が1件以上なら終了コード1 |
| 台帳と lock の版 | §6 のとおり lock の版で作り直した台帳と、いまの台帳が同じ。違えば終了コード1 |
| sentinel | 台帳を検査するたびに、§5 の照合の対象の全行（confirmed と candidate）で、context の真ん中（文字数を2で割り、切り捨てた位置）の1文字を「〓」（context に「〓」が含まれるときは「※」）に替えて §5 の手順をかけ、移動か停止になることを確認する。一致になる行が1件でもあれば終了コード1。台帳に検査用の行は置かない |
| 付け替えの元 | relink の各行について、from・evidence・context が同じで status が rejected の mention の行があり、その行の to と relink の行の to が違う。無ければ終了コード1。relink の行の status は confirmed か rejected で、candidate は置かない |
| 付け替えの重なり | relink の confirmed の行と同じ (from, to) を持つ mention の行が candidate か confirmed なら、一覧（relink_conflict.tsv）に出して終了コード1。人が、どちらかを却下するか、付け替えを取り消す |
| 方法の制限 | 台帳に crosswalk の行が無い。各行の method が台帳のファイル名（`links/<method>.tsv`）と同じ |
| 判定の範囲 | 人の判定の一覧を台帳に書き写すとき（`tools/apply_decisions.py`）、人が判定した範囲（`--keys` で渡す (from, to, method) の一覧。§1 の形で、列は from・to・method）と、判定の一覧の (from, to, method) の集まりが同じ。範囲の外の行、範囲にあって判定の無い行、範囲の一覧の中の重複が1件でもあれば、どちらの台帳にも書かずに終了コード1。書き写す前に、to と status ごとの件数を表示する。fuhyo の台帳では、to の種類（node・none）と status ごとに表示する（CLAUDE.md 不変の制約11） |
| テーマの定義 | `ref/themes.tsv` が §1 と §12 の形に合う（列名と列の順、行が theme → kind → value の文字コード順、(theme, kind, value) の重複が0件）。theme ごとに 名前 が1行だけある。kind が §12 の13のどれか。value が kind ごとの形に合い、lock の版の入力にある（系列は系譜表の series、施策と事業は計画の programs の key、議案は gian.json の議案、問いは proceedings.json の一般質問の問い、資料は hino-town-docs の data/sources.tsv の id、施設は ref/shisetsu.tsv の key）。問いの行の source に書いた議員の名前（§2 の mb のそろえ方で）が、審議の記録のその問いの member と同じ。資料の行の value が doc:<id> の形（ページ無し）。reviewer と date がある。合わなければ、テーマのノートのデータを作らずに終了コード1 |
| 施設の参照表 | `ref/shisetsu.tsv` が §1 と §15.8 の形に合う（列名と列の順、行が key の文字コード順、key の重複が0件、key が §2 の fa の形）。reviewer と date がある。合わなければ、テーマのノートのデータを作らずに終了コード1 |
| 附表の分類 | fuhyo の台帳で、附表の全事業が from に1行以上ある。同じ from に confirmed の none と confirmed の node が両方あれば終了コード1。candidate の無い from で confirmed が1行も無ければ（候補をすべて却下した）終了コード1。confirmed の行の note に §7 fuhyo の区分（「メモ：区分：<区分>」）が無いか、node の行の区分が一致・一致（柱違い）・表記の違い・名称の変更のどれでもないか、none の行の区分が一部・年度の事業・中身の違いのどれでもなければ終了コード1。confirmed の node か none で分類された事業の数と、まだ candidate のある事業の数を表示する（DESIGN.md §5 工程5 のゲート）。誤りは、台帳の更新（`tools/update_links.py --ledger fuhyo`。台帳を書かない）でも検査（`tools/check_links.py`）でも止め、誤りの事業を表示する |
| 記録の台帳 | `records/` の8つの台帳が §1 と §15 の形に合う。行の同一性（§15 の各台帳）の重複が0件。status・種類などの値が §15 の決まりのどれか。引用（quote）が、§15.1 のとおり資料の本文にある。参照（answers・yaritori・upper_ref・lower_ref・sources など）が、指す先の行や資料にある。やりとりの記録と質疑の記録で、n が1からの整数で、round が「最初の問い」か「再質問」と1からの整数を続けたもので、答えの行の n が answers の指す問いの行の n と同じ。round が turns から求めた値と違う行は、件数を表示して一覧（build/records/round_diff.tsv）に出すが、終了コードは変えない（round は人が決め、turns から求めた値は候補のため。§15.2）。事柄の記録の point が、その行のテーマの kind 事柄の値のどれか。事柄の記録の value が、空か、§4 の正規化のあとで引用（quote）の中にある。やりとりの記録と質疑の記録の point が、空か、その問いかそのまとまりを持つテーマの kind 事柄か記載の値のどれか。構造にしていない記載の about が、空か、そのテーマの kind 事柄か記載の値のどれか。同じテーマ・同じ point の事柄の記録の行で、program が同じ（空を除く）。つながりの記録の upper・lower が、そのテーマの kind 記載の値のどれか。施設の記録の facility が ref/shisetsu.tsv にあり、aspect が §15.8 の4つのどれか。やりとりの記録の bq が §2 の bq の形で、議会だよりにある。記録しない文の question・n が、やりとりの記録か質疑の記録にある問いで、sid がその問いの発言で、quote がその発言の本文にある（§15.9）。合わなければ、テーマのノートのデータを作らずに終了コード1。引用が本文に無い行は、一覧（build/records/quote_mismatch.tsv）に出す |
| 発言の取りこぼし | やりとりの記録の問い（question と n の組）ごとに、行のある発言のうち審議の記録の turns の順で最初のものから最後のものまでを見る。最後の行の発言が議員の発言でなければ、そのあとの議員の最初の発言（次の問いの頭。締めくくりの要望や意見が入る）も見る。質疑の記録は、まとまりの全部の発言を見て、テーマの語（§12 の kind 語）を含む文だけを残す。見る発言の本文を §4 の正規化にかけ、「。」「？」「！」（正規化のあとの「?」「!」を含む）のあとで文に分ける。同じ発言を引いた行の引用と1字も重ならず、記録しない文の台帳（§15.9）にも無い文を、件数を表示して一覧（build/records/torikoboshi.tsv）に出す。終了コードは変えない。人が、行を足すか、記録しない文の台帳に理由を書く（DESIGN.md ADR-24） |
| 引用の前後 | 記録の台帳の引用のうち、§4 の正規化のあとの頭が指示語（その・この・これ・それ・あの・こうした・そうした・こういった・そういった・上記・前述・同様・先ほど・さきほど・今申し上げ・以上）で始まるもの（つなぎの言葉と時の語「それと」「それから」「それぞれ」「それでは」「これまで」「これから」「このあと」で始まるものは数えない）と、引用の終わりが本文の文の終わり（「。」「？」「！」の直前か、本文の終わり。§4 の正規化のあとの「?」「!」を含む）でないものを、件数を表示して一覧（build/records/quote_context.tsv）に出す。終了コードは変えない。指す先や文の続きを引用に入れるか、行を分けるか、note に書くかは、人がそのつど決める（§15.1） |

テーマの定義・施設の参照表・記録の台帳・発言の取りこぼし・引用の前後は、`tools/check_records.py` で確かめる。報告と一覧は `build/records/` に出す（check.md・round_diff.tsv・quote_mismatch.tsv・torikoboshi.tsv・quote_context.tsv）。記録しない文の台帳（§15.9）が無ければ、0行として扱う。ほかの検査は、リンク台帳の道具（`tools/update_links.py`・`tools/check_links.py`）で行う。

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
| update.md・check.md | 更新・検査の件数の報告 | — |

---

## 12. テーマの定義 `ref/themes.tsv`

試作のテーマ（DESIGN.md ADR-13）ごとに、含める計画・施策・事業・議案と、語の一致に使う語を、人が根拠つきで決めて書く表。台帳ではなく、系譜表・別名辞書と同じ参照表である。

| 列 | 内容 | 例 |
| --- | --- | --- |
| theme | テーマの id（英小文字） | `hoiku` |
| kind | 名前・系列・施策・事業・議案・語・除外の語・問い・資料・質疑・事柄・記載・施設のどれか | `系列` |
| value | kind ごとの値（下の表） | `youho` |
| source | 根拠（入力のどこを見て決めたか） | `shiga-hino-plans data/plans/jisshi.json 分野① e008` |
| reviewer | 決めた人の GitHub ユーザー名 | `kken78` |
| date | 決めた日（YYYY-MM-DD） | `2026-10-24` |
| note | 注記 | |

| kind | value | 使い道 |
| --- | --- | --- |
| 名前 | テーマの名前（画面に出す表記） | 1テーマに1行だけ |
| 系列 | 系譜表（§8）の series | その series の全期の計画（plan と lin）を、テーマの計画とする。計画への確定の言及（mention・relink の confirmed）を、議会での経緯に使う |
| 施策 | 総合計画の施策の node キー（例 `node:sogo6/e011` 分野、`node:sogo6/e047` 基本施策） | テーマの位置づけ（共通の軸。DESIGN.md 判断事項3）に使う |
| 事業 | 計画の事業の node キー（例 `node:jisshi/e008`） | テーマの事業とする。附表の台帳でこの事業に確定した附表の事業を、予算として引く |
| 議案 | §2 の gi キー | テーマの議案とする。議案は名前で選べないため（docs/review-2026-10-21.md §7.3）、人が1件ずつ選ぶ |
| 語 | §4 の正規化を通した語 | 語の一致（§13）を探す。語が一致しても、台帳の行にはしない（ADR-3） |
| 除外の語 | §4 の正規化を通した語 | この語の中で一致した語は、語の一致にしない（例 テーマ hoiku で「学童保育」の中の「保育」） |
| 問い | §2 の iq キー | テーマの一般質問の問いとする。やりとりの記録（§15.2）を、この問いについて作る。問いは名前や語で選ばず、人が1件ずつ選ぶ |
| 資料 | §2 の doc キー（ページ無し。例 `doc:shingi-youho-teigen`、`doc:koho-no792-04`） | テーマの資料とする。過程・事柄・つながりの記録の下書きは、この資料と、テーマの計画・問いから作る。語の一致（hits.docs）とは別に、人が選んだものとして示す |
| 質疑 | §2 の sq キー | テーマの議案の質疑のうち、テーマにかかわるものとする。質疑の記録（§15.7）を、この質疑について作る。1つの質疑がいくつもの事業や議案にまたがるため、人が1件ずつ選ぶ |
| 事柄 | 事柄の名前（人が決めた表記。例「新こども園の開園時期」） | 事柄の記録（§15.3）の point と、やりとりの記録（§15.2）・質疑の記録（§15.7）の point・構造にしていない記載（§15.6）の about に使う名前を決める。source に、かかわる事業の node キーと、その事柄を書いた主な資料を書く |
| 記載 | 記載の見出し（人が決めた表記。例「子育て環境の未来に向けての提言」「再編整備方針」） | つながりの記録（§15.4）の upper・lower と、やりとりの記録・質疑の記録の point・構造にしていない記載の about に使う名前を決める。source に、その記載がある資料のキーか計画の記載の参照を書く |
| 施設 | §2 の fa キー | テーマの施設とする。施設の記録（§15.8）を、この施設について作る。人が1件ずつ選ぶ |

- 行は人が決める。エージェントが自分の判断で行を足したり変えたりしない（CLAUDE.md 不変の制約11 と同じ扱い。依頼者が会話で行を特定して認めた行は書いてよい）
- source には、決めた根拠の入力と場所を書く（計画の programs の分野・事業の key、議案の会議と番号など）。語は、どの資料のどの表記によるかを書く
- 問いの行の source には、会議・日付・議席・議員の名前（会議録の表記のまま）・問いの番号・題を書く
- 質疑の行の source には、会議・日付・議席・議員の名前（会議録の表記のまま）・対象の議案の番号と、テーマにかかわる部分（例「新こども園の用地」）を書く
- 行を変えたら、テーマのノートのデータ（§13）を作り直す

## 13. テーマのノートのデータ `build/theme/<theme>.json`

テーマのノートの画面（DESIGN.md §5 試作の工程 U4、§16）と、生成AIに渡す MCP の道具（U3）が読むデータ。`tools/` が、lock の版の入力・台帳・`ref/themes.tsv`・記録の台帳（§15）から作る。手で直さない（CLAUDE.md 不変の制約8）。git に入れない。

全体の形：

```json
{
  "theme": "hoiku",
  "name": "幼児教育・保育施設の再編",
  "lock": {"<入力のリポジトリ>": "<コミットSHA>"},
  "ledgers": {"links/mention.tsv": "<sha256>", "links/relink.tsv": "<sha256>", "links/fuhyo.tsv": "<sha256>", "ref/themes.tsv": "<sha256>", "records/yaritori.tsv": "<sha256>", "records/katei.tsv": "<sha256>", "records/kotogara.tsv": "<sha256>", "records/tsunagari.tsv": "<sha256>", "records/kisai.tsv": "<sha256>", "records/shitsugi.tsv": "<sha256>", "records/shisetsu.tsv": "<sha256>", "records/nozoki.tsv": "<sha256>", "ref/shisetsu.tsv": "<sha256>", "ref/lineage.tsv": "<sha256>", "ref/aliases.tsv": "<sha256>"},
  "plans": [], "policies": [], "programs": [], "budget": [], "council": [], "exchanges": [], "bills": [],
  "docs": [], "records": {"yaritori": [], "katei": [], "kotogara": [], "tsunagari": [], "kisai": [], "shitsugi": [], "shisetsu": []},
  "hits": {"council": [], "docs": []},
  "sheets": [], "issues": [],
  "names": {"sources": {"<資料のキー>": "<資料の名前>"}, "facilities": {"<fa キー>": {"name": "", "district": ""}}},
  "theme_questions": 16
}
```

- 各項目に `layer` を付ける。値は「確定」（確定した台帳の行と、入力の構造データ。records は confirmed の行）、「語の一致（未確認）」、「OCR の下書き」、「記録（未確認）」（records の candidate の行）、「論点の候補（未確認）」（13.2）のどれか。画面と MCP の道具は、layer の違う項目をまぜずに示す
- 各項目に、出典の `url` を付ける（下の表）。出典の無い項目は作らない
- names と theme_questions は、項目を示すための名前と数で、項目ではない。layer と url を付けない（§13.3）
- 抜粋（`excerpt`）は、照合の語や一致した語を中心に前後あわせて200字までとする（不変の制約9）。会議録の発言は、台帳の context か、入力の発言の本文から切り出す
- 日付は YYYY-MM-DD。並びは、council・exchanges・bills・hits は日付の順（同じ日付は from のキーの文字コード順）、ほかはキーの順（§1。records の row と step は数の順）
- 序列化しない（不変の制約6）：議員ごとの件数や順位を作らない

| 項目 | 中身 | layer | 出典の url |
| --- | --- | --- | --- |
| plans | 系列の計画（キー・名前・計画期間） | 確定 | plan は `https://kken78.github.io/shiga-hino-plans/plans/<id>.html`。lin は系譜表の source の原典 |
| policies | 施策（キー・番号・名前・説明） | 確定 | sogo6 の計画のページ |
| programs | 事業（キー・名前・説明・実施年度・概算事業費） | 確定 | 事業の計画のページ |
| budget | テーマの事業に確定した附表の事業（附表のキー・名前・予算額・区分・どの事業に当たるか） | 確定 | 附表の原典の PDF（`#page=<n>`） |
| council | 系列の計画への確定の言及（発言日・from・役職の区分・場面・抜粋） | 確定 | 会議録の発言は `https://kken78.github.io/hino-council-search/#thread=<やりとりの最初の sid>&focus=<sid>`（やりとりに入らない発言は会議録の原本 PDF）。議会だよりの問いは questions.json の minutes_exchange か議会だよりの PDF |
| exchanges | council の会議録の言及を含む一般質問の問いと、テーマの問い（§12 の kind 問い）ごとの、問い（議員）と答え（当局）の並び（発言日・問いの番号・発言ごとの役職の区分・抜粋）（§13.4） | 確定 | council と同じ |
| bills | テーマの議案（gi キー・会議・日付・番号・件名・結果・採決の方法・討論の並び（日付・議員・賛否・発言の sid）） | 確定 | 会議の掲載ページ（meetings.json の url） |
| docs | テーマの資料（§12 の kind 資料。hino-town-docs の id・区分・名前・年度・日付・ページ数・check） | 確定 | 原典の PDF の URL |
| records | テーマの記録（§15.2〜§15.8 の7つの台帳のうち、テーマの行と、テーマの問いのやりとりの記録と、テーマの質疑の記録と、テーマの施設についての施設の記録。rejected は入れない） | 確定か記録（未確認） | 行ごとの資料の出典 |
| hits.council | テーマの語が題名か本文に一致した、一般質問の問い・議案の質疑のまとまり・議会だよりの問いのうち、確定の層（exchanges・council・テーマの質疑）に無いもの（発言日・from・一致した語・抜粋）（§13.4） | 語の一致（未確認） | council と同じ |
| hits.docs | テーマの語が一致した町の公開資料のページ（資料の id・名前・年度・ページ・一致した語・抜粋・どの層で一致したか・想定外の字のあるページか） | 語の一致（未確認） | 原典の PDF の URL に `#page=<n>` |
| sheets | テーマの事業ごとの整理シート（DESIGN.md ADR-19。資料の種類から機械で置ける記載と、その事業にかかわる記録への参照） | 項目ごとに、もとの項目の layer | 項目ごとの出典 |
| issues | 論点の候補（比べ方・事業のキー・比べた事実・比べた項目への参照） | 論点の候補（未確認） | 比べた項目ごとの出典 |

- 役職の区分は、会議録の発言の role から「議員」「当局」「議長」「その他」に分ける（docs/review-2026-10-21.md §5.3 e）。role が議席（「4番」など）なら議員、議長・副議長・臨時議長・新議長・新副議長なら議長、空か、委員長（選挙管理委員長を除く）・事務局長・議会事務局長ならその他、ほかは当局。その他の分け方は暫定で、あとで決める（DESIGN.md 判断事項24）
- 語の一致は、本文に §4 の正規化をかけて探す。除外の語の中で一致した語は数えない。抜粋は、§4 の正規化をかけた本文から、最初に一致した語を中心に200字を切り出す（言及の台帳の context と同じく、空白を除いた文になる）
- hits.docs の語は、原典の文字（data/text/、当たらなければ data/text_raw/）で探し、当たらないページは OCR の下書き（data/ocr/）でも探す。ページごとに、最初に一致した層で1行にする。抜粋は、原典の文字で当たったページは原典の文字から、OCR の下書きでだけ当たったページは OCR の下書きから切り出し、layer を「OCR の下書き」とする（ADR-14）。テーマの資料（docs）のページも入れる（docs は資料の単位で、どのページに語があるかは hits.docs で分かる）
- 台帳の note に「想定外の字のあるページ」とある資料のそのページは、`unexpected` を true にする。画面と MCP の道具は、そのページの数字を出典に使えないことを示す（ADR-14）
- 数字（予算額・概算事業費）は、入力の構造データ（附表・計画の programs）の値をそのまま使う。町の公開資料の文字から数字を取り出さない

### 13.1 整理シート（sheets）

整理シートは、テーマの事業（§12 の kind 事業）ごとに1つ作る（DESIGN.md ADR-19）。記載をロジックモデルの区分に置くことはしない。

| 欄 | 入れるもの |
| --- | --- |
| 課題の記載 | テーマの系列の計画の課題のブロック（`challenges`）の項目の見出し（title）。説明（desc）は置かない（計画の JSON の文で、原典の文とは限らないため。§15.1）。url は原典の PDF のそのページ（challenges の source のページに、計画の sources の pdf_page_offset を足す） |
| 事業費と予算 | 事業の概算事業費・実施年度（programs の cost・years）。附表の予算額と区分（budget） |
| 事業の説明 | 事業の説明（programs の desc） |
| めざす姿 | テーマの施策のうち分野（総合計画）の説明（desc）の、「めざす姿:」で始まる行 |
| つながり | つながりの記録（§15.4）のうち、この事業にかかわる記載を upper か lower に持つ行への参照。この事業にかかわる記載は、テーマの定義の kind 記載のうち、source にこの事業の node キーを書いた値（事柄の記録の program と同じく、人が根拠つきで決めたテーマの定義だけで選ぶ） |
| 事柄 | 事柄の記録（§15.3）のうち、この事業にかかわる事柄（§15.3 の program がこの事業）の行への参照。事柄ごとに資料の日付の順 |
| 過程 | 過程の記録（§15.5）のうち、テーマの段階への参照 |
| 議会での問い | テーマの問いのやりとりの記録（§15.2）と、テーマの質疑の記録（§15.7）への参照と、問いの行をロジックモデルの区分（課題・投入・活動・手続き・結果・成果・めざす姿）で数えた数 |

- 項目は、もとの資料の文や値のまま並べる。要約や言い換えをしない
- 課題の記載・めざす姿・過程・議会での問いは、テーマの単位のもので、どの事業のシートにも同じものを置く
- 欄に項目が無いときは、空の配列とする。画面は「記録に無い」と示す（資料に無いのか、まだ記録していないのかは分けられないため、「資料に無い」とは書かない）。機械で置く4つの欄は、項目が無ければ「資料の構造からは置けない」と示す
- 参照（ref）の形は、§13 の項目は `<項目>/<キー>`（例 `programs/node:jisshi/e008`）、記録は `records/<台帳>/<行のキー>`、計画の記載は `<plan キー>/<タブ id>/<ブロックの種類>/<そのタブでのそのブロックの種類の番号>/<項目か行の番号>`（番号は1から。例 `plan:sogo6/mokuhyo/table/1/2` は sogo6 の「施策と目標」のタブの1つめの表の2行目「保育所等待機児童数(件)」）

### 13.2 論点の候補の比べ方（issues）

DESIGN.md ADR-16・ADR-19 による。どの比べ方も、比べた事実と出典だけを示す。理由・評価・どうすべきかは書かない。

| 比べ方 | 比べるもの | 候補にする条件 |
| --- | --- | --- |
| 予定の変更 | 事柄の記録の、同じ事柄の行。施設の記録の、同じ施設・同じ面の行 | 種類が変更の行がある。または、種類が予定の行の対象の時期が、資料の日付のあとの予定の行と違う |
| 留保のその後 | やりとりの記録の答えのうち種類が留保の行と、同じ点（point）の、そのあとの記録 | 留保の答えがある。そのあとの日付に同じ点のやりとりの記録か事柄の記録があれば並べ、無ければ「記録に無い」とする。中身が合っているかは比べない |
| 繰り返し問われている点 | やりとりの記録と質疑の記録の問いの行の点 | 同じ点の問いが、2つ以上の会議にある。議員ごとには数えない（不変の制約6） |
| 問われていない区分 | やりとりの記録と質疑の記録の問いの行のロジックモデルの区分 | テーマの問いの行を区分ごとに数え、すべての区分の数を、一般質問と質疑に分けて並べる。0件の区分があれば、その区分を示す |
| 問われていない点 | テーマの定義の kind 事柄・記載の値と、やりとりの記録と質疑の記録の問いの行の点 | 値のうち、問いの行の点に一度も無いもの。その値を about に持つ構造にしていない記載、point に持つ事柄の記録、upper か lower に持つつながりの記録の行の資料（意見募集の結果を含む）を並べる |
| つながりの記録に無い目的 | つながりの記録 | 目的と手段の行で、目的の側にだけ現れ、手段の側に現れない記載がある（その記載を手段とする、さらに上の目的の記録が無い）。「資料に無い」ではなく「つながりの記録に無い」と書く |
| 役割のその後 | 施設の記録の、役割の行と状態の行 | 役割の行（例 指定避難所）がある施設に、そのあとの日付の状態の行（休園・閉園・移行など）がある。その役割について、状態の行のあとの日付の記録（同じ施設の役割の行、同じ地区の施設の同じ役割の行）があれば並べ、無ければ「記録に無い」とする |
| 計画と予算 | 実施計画の事業と附表 | 附表の事業に当たる実施計画の事業が無い（記載なし）、実施計画の事業に当たる附表の事業が無い、または実施年度にその年度があるのに附表に無い |

- 候補の refs には、比べた項目の layer を付ける。記録（未確認）の行から作った候補は、statement の頭に「記録（未確認）による」と書く
- statement の形（DESIGN.md ADR-25。判定シート S5-1 の #64〜69 で決めた言い方）：
  - 日付は「2025年3月10日」「2025年3月」と書く（項目の date の欄は YYYY-MM-DD のまま）。会議の名前と資料の名前は §13.4 による
  - 予定の変更「<事柄>は、<資料の日付>の<資料>では<対象の時期>（<種類>）、<資料の日付>の<資料>では<対象の時期>（<種類>）」。変更の行に理由の引用があれば、そのあとに「。変更理由として「<引用>」」
  - 留保のその後「<日付>の答弁（<役職>）では、<点>について、時期や内容を今後決めるとされた。その後の記載として、<日付>の<資料>がある」。無ければ「その後の記載は未記録」
  - 繰り返し問われている点「「<点>」は、<会議の一覧>で質問されている」
  - 問われていない区分「記録した質問（一般質問N問・議案質疑N件、<最初の会議>〜<最後の会議>）を内容により分類すると、一般質問は課題N件、投入（予算・人員）N件、活動N件、手続きN件、結果（施設・定員等）N件、成果N件、めざす姿N件（全N件）、議案質疑は課題N件、…（全N件）」。区分のかっこ書きは最初に出る所にだけ付ける
  - 問われていない点「「<値>」は、記録した質問（一般質問N問・議案質疑N件、<最初の会議>〜<最後の会議>）では取り上げられていない。この事項の記載がある資料：<資料の一覧>」
  - つながりの記録に無い目的「「<記載の見出し>」を手段とする上位の目的との関係は、未記録」
  - 役割のその後「<施設>は、<資料の日付>の<資料>で<役割>。<資料の日付>の<資料>では<状態>（<種類>）。その後の記載として、<日付>の<資料>がある」。無ければ「その後の記載は未記録」
  - 計画と予算「<附表の事業>は実施計画に当たる事業が無い（記載なし）」「<実施計画の事業>は実施年度に令和N年度があるが、令和N年度の附表に当たる事業が無い」
- 問われていない区分と問われていない点の statement には、比べた範囲を書く。テーマの問い（§12 の kind 問い）のうち、やりとりの記録の無い問いがあれば、そのあとに「テーマ「<テーマの名前>」の一般質問として選定したN問のうち、N問は未記録」と書く。議論すべきだったか、問わなかったことの良し悪しは書かない（DESIGN.md ADR-12）
- scope：計画と予算の実施計画の側と、整理シートの事業にかかわる事柄の候補は「事業」、ほかは「テーマ」

### 13.3 項目の欄

どの項目にも `layer` と `url` を付ける（§13）。値の無い欄は空文字か空の配列とし、推定で埋めない。

| 項目 | 欄 |
| --- | --- |
| plans | key（plan・lin のキー）・series・edition・name・start_fy・end_fy・posted（計画の meta の posted を原文のまま。例「令和7年3月策定・令和8年6月一部改正」。計画の策定・改正の日はこの文でしか分からないため）・url |
| policies | key・kind（「分野」か「基本施策」）・no・name・desc・source（原典のページ）・url |
| programs | key・plan・field_no・field_name・name・desc・years・cost（label・amount・unit）・source・url |
| budget | key（fh のキー）・program（当たる事業の node キー）・category（附表の台帳の区分）・name・desc・kan・kubun・amount・unit（千円）・dept・page・url |
| council | from・to・to_label・method・date・kind（sp か bq）・speaker（議員・当局・議長・その他）・role・scene・excerpt・url |
| exchanges | meeting_id・meeting・date・n（問いの番号）・question（iq のキー）・member（mb のキー・名前・議席）・titles（議会だよりの題名とテーマ）・turns（sid・side（問い・答え）・speaker・role・excerpt・url の並び）・mentions（この問いの中の council の from） |
| bills | key・meeting_id・meeting・date・no・kind・title・committee・result・method（gian.json の議案の値）・debates（date・member（mb のキー・名前・議席）・stance・sid・url の並び。審議の記録の討論（kind が debate）のうち、bills にこの議案を含むもの）・url |
| docs | id・category・title・fiscal_year・date・pages・check・text_layers（原典の文字・OCR の下書きのどれがあるか）・url |
| records | yaritori・shitsugi・katei・kotogara・tsunagari・kisai・shisetsu の7つ。それぞれ §15 の行の列と、資料の url・layer。yaritori は問いの単位、shitsugi は質疑の単位にまとめ、問いと質疑に member（mb のキー・名前・議席）を持たせる |
| hits.council | kind（「問い」「質疑」「議会だより」）・meeting_id・meeting・date・n・question（iq・sq・bq のキー）・member（mb のキー・名前・議席）・bills（質疑の対象の議案の gi キー）・titles（審議の記録の topics のうちその問番号のもの。議会だよりと会議録の両方を、src で分ける。議会だよりの問いはその題名）・words（一致した語と回数）・from（語が最初に一致した発言の sp のキー。題名だけで一致したときは問いの最初の発言。議会だよりの問いは bq のキー）・excerpt（その発言から）・first_sid・url |
| hits.docs | doc・title・category・fiscal_year・date（資料の日付。並べるため）・page・words・text_layer（「原典の文字」か「OCR の下書き」）・excerpt・unexpected・url |
| sheets | program・name（事業の名前）・kadai（課題の記載）・cost（事業費と予算）・desc（事業の説明）・vision（めざす姿）・tsunagari・kotogara・katei・asked（やりとりの記録と質疑の記録への参照と、問いの行の区分ごとの数）。どれも、項目への参照（ref）・text か value・source・url・layer の並び。asked は、問いと質疑のまとまりごとに1項目とし、value を区分ごとの問いの行の数（7つの区分。0も書く）とする |
| issues | type（13.2 の比べ方）・scope（「事業」か「テーマ」）・program（scope が事業のときの node キー）・statement・refs（比べた項目への参照・text か value・url・layer の並び）・layer |
| names | sources（records・council・issues の refs に出る資料のキーごとの、§13.4 の資料の名前）・facilities（records.shisetsu に出る施設ごとの、ref/shisetsu.tsv の name と district）。layer と url は付けない |
| theme_questions | テーマの定義（§12）の kind 問いの行の数（数だけ。layer と url は付けない） |

- hits.council の単位は3つとする。一般質問の問い（turns の問番号の単位。exchanges に無いもの）、議案の質疑のまとまり（テーマの質疑に無く、council の発言を含まないもの）、議会だよりの問い（council に無いもの）。委員長報告・提案説明・討論など、問いと答えの形でない発言は入れない
- 議会だよりの問いは、題名・問い・答えの題名・答えの順に探し、最初に一致した欄から抜粋する。date は号の公表日とし、meeting_id・meeting・first_sid は空、member の議席は空とする
- excerpt は、テーマの語か照合の語が一致した箇所を中心に切り出す。どの語も一致しない発言（問いの中の当局の答えなど）は、発言の頭から切り出す
- 議員は、問いの単位で member（キー・名前・議席）として持つ。行ごとに名前を繰り返さない。画面と出力での見せ方は DESIGN.md ADR-12 の決まりによる

### 13.4 項目の作り方

テーマのノートのデータは `tools/build_theme.py` が作る。先に記録の台帳の検査（§11 のテーマの定義・施設の参照表・記録の台帳）をかけ、誤りがあれば作らない。出典の url の無い項目が1つでもあれば作らない。

- plans：系譜表（ref/lineage.tsv）のテーマの系列の行。plan のある行は、key を plan、url を計画のページ、posted を計画の meta の posted とする。plan の無い行（前の期）は、key を lin、url を系譜表の source の PDF のページとし、posted は空
- policies・programs：計画の programs の事業（key がテーマの kind 施策・事業）。policies の kind は、desc に「めざす姿:」で始まる行があれば分野、無ければ基本施策（§13.1 のめざす姿と同じ見分け方）。source は計画の原典の PDF（計画の JSON の sources の1つめ）。事業ごとのページは計画の JSON に無いので付けない
- budget：附表の台帳の confirmed の行のうち、to がテーマの事業のもの。category は note の「メモ：区分：<区分>」。url は附表の原典の PDF にページを付けたもの
- council：言及の台帳（mention・relink）の confirmed の行のうち、to がテーマの plans の key のもの。会議録の言及の scene は審議の記録の場面（どの場面にも入らない発言は「範囲外」）。議会だよりの言及は、date を号の公表日（pub_date）、scene を「議会だより」とし、speaker は問いの欄（title・question_text）なら議員、答えの欄（answer_title・answers）なら当局
- exchanges：問いの単位は、審議の記録の turns の問番号（機械の値。やりとりの記録の n とは違うことがある）。question は、その問番号の最初の q の発言。titles は、審議の記録の topics のうち議会だよりのもの。会議録の言及（sp）を含む問いと、テーマの問いから作る。議会だよりの言及（bq）からは作らない（議会だよりの問いと会議録の問いのつなぎを、問いごとに確かめていないため。暫定で、あとで決める。DESIGN.md 判断事項25）
- bills：結果と採決の方法は gian.json（§15.7）。date は採決の日（審議の記録の採決。無ければ会議の日）。debates は、審議の記録の討論のうち bills にその議案を含むもの
- docs：text_layers は、「原典の文字」（data/text か data/text_raw がある）と「OCR の下書き」（data/ocr がある）のある方
- records：やりとりの記録と質疑の記録は、問い（question）の単位にまとめ、meeting_id・meeting・date（question の発言の日）・member と、行（rows）を持つ。ほかの台帳は行の並び。どの行にも資料の url と layer（confirmed は確定、candidate は記録（未確認））を付ける。rejected と、記録しない文の台帳（§15.9）は入れない
- ledgers：§13 の台帳と参照表に、系譜表（plans を作るため）、別名辞書（言及の台帳を作ったときの参照表）、記録しない文の台帳（検査に使うため）を入れる
- hits・sheets：§13 と §13.1・§13.3 の決まりによる
- issues の予定の変更：対象の時期は、元号と年の数で比べる（「令和10年度」と「令和10年4月」はどちらも令和10とする。表記の読み替えはせず、字の並びの「令和N年」「平成N年」などから取り出す。取り出せない行は比べない）。施設の記録は、施設・面・値（value）が同じ行どうしで比べる（同じ施設の「休園」と「開設」の時期を比べないため）。statement には、最初の予定の行と、年の数が前の予定の行と変わった予定の行と、変更の行を書き、refs には比べた予定と変更の行をすべて入れる
- issues の留保のその後：候補は、問い（と質疑のまとまり）と点の組ごとに1つ。そのあとの記録は、同じ点の、やりとりの記録と質疑の記録の問い（日付が後のもの）と、事柄の記録の行。statement には一番早いものを書き、ほかは「（ほかN件）」とする
- issues の役割のその後：状態の行は、役割の行（一番早いもの）より後の日付のもの。statement には一番早い状態の行を書く。同じ地区は ref/shisetsu.tsv の district で見る。district が空の施設は、どの地区にも数えない
- issues の計画と予算：「その年度の附表」は lock の版にある附表とする。附表の事業のうち記載なしのものは、テーマの事業に当たらないので、テーマの候補にしない
- issues の「日付が後」：月だけの日付（広報ひのなど）は、その月が比べる日付の月より後のときに後とする（同じ月は後にしない）
- issues の statement の資料の名前：町の公開資料は「」で囲んだ題名、計画は計画の名前、会議録の発言は「<会議の名前>の<役職>の発言」（議員は「議員の発言」とし、議席や名前を書かない）、議会だよりは「議会だより第N号」、議案は「<会議の名前>の<番号>」。施設は ref/shisetsu.tsv の name
- 会議の名前：hino-council-search の会議の名前から「第N回」と「会議録」を除き、「（M月）」「（M月D日）」は「M月」とする（「令和7年第2回（3月）定例会会議録」→「令和7年3月定例会」、「令和7年第3回（5月14日）臨時会会議録」→「令和7年5月臨時会」）。「令和7年6月定例会議」「令和7年7月臨時会議」の形の名前はそのまま。定例会と定例会議は分けたままにする（令和7年6月から町の会議の名前が変わったため。DESIGN.md ADR-25）。statement のほか、records・exchanges・bills・hits の meeting の欄も同じ書き方にする
- names：sources は、records の source・sid・upper_ref・lower_ref・sources と、council の from と、issues の refs に出る資料のキーごとに、上の資料の名前を入れる。facilities は、records.shisetsu の facility ごとに ref/shisetsu.tsv の name と district を入れる

## 14. MCP の道具 `tools/mcp_ronten.py`

生成AIに、テーマのノートのデータ（§13）を読ませる道具（DESIGN.md ADR-13・ADR-27）。読むだけで、何も書かない（呼び出しの記録を除く）。2026-10-30 に、試作で確かめた形（docs/eval-shisaku1.md §7）に改めた。

- 形：MCP（Model Context Protocol）の stdio のサーバー。標準ライブラリだけで作る。JSON-RPC 2.0（1行に1つ）で、`initialize`・`tools/list`・`tools/call`・`ping` に答える
- 起動：`python3 -B tools/mcp_ronten.py <theme> <node キー> [--log <jsonl>]`。1つのサーバーが1つの事業を扱う
- 読むもの：`build/theme/<theme>.json`（§13）、`ref/themes.tsv`（テーマの語）、lock の版の hino-council-search の `public/data/index/<年>.json`（speeches が読む会議録の本文）だけ。ネットワークを使わない
- 記載の書き方：持ち込み用の資料（§17.1）と同じ「［資料の日付］資料の名前：欄：値。「引用」（出典：url）」とし、記録（未確認）の行には【未確認】を付ける。過程の記録の行、照合結果の文の出典、町の資料に記載なしの書き方も §17.1 による。どの記載にも id（`kotogara:3`・`yaritori:<問いのキー>/<行>`・`issue:2` など）を付け、fetch で取れるようにする
- キーワード検索の結果（hits）は返さない（DESIGN.md ADR-26 と同じ理由）
- 道具の説明（tools/list の description）と返す文は、決まった文とデータの項目だけで作る。評価で数える語の一覧（docs/eval-shisaku1.md §7）を道具に入れない
- 呼び出しの記録：`--log` を渡したときは、呼び出しごとに、日時・道具の名前・引数・返した文の字数を1行ずつ書く。返した中身は書かない
- 引数が決まりに合わないとき（無い id・名前・比べ方）は、その旨を返し、推定で近いものを返さない

| 道具 | 引数 | 返すもの |
| --- | --- | --- |
| overview | なし | 頭に【未確認】と照合結果の意味、記載の書き方、取り込んだ資料のうちいちばん新しい記載の日付。事業の要点（§17.2 の1と同じ）。正式な名前（関連計画の名前と、つながりの記録の上位・下位の記載のうち計画・構想・提言で終わるもの）。目的（つながりの記録の「目的と手段」の上位の記載ごとに、資料の日付がいちばん新しい行の原文）。いまの段階（過程の記録の、期間の始まりが新しい3つ）。事項・施設・記載の見出し・照合結果の比べ方の一覧と件数。議会の件数 |
| search | query（空白で区切った語）・kind（記載の種類。省ける）・limit（省くと20） | 記載の id・種類・抜粋（160字まで）。合う語の数の多い順、同じなら資料の日付順。語は NFKC にそろえ空白を除いて比べる |
| fetch | ids | 記載の全文。`yaritori:<問いのキー>`・`shitsugi:<キー>` は記録した質問・質疑の全行、`issue:<番号>` は照合結果と比べた記載 |
| topic | name（事項・施設・記載の見出しの名前） | 事項：町の資料の最新の記載（§16.2 と同じ選び方。町の資料の行が無いときは「町の資料に記載なし（会議録の発言 N 件）」）、いまの町の説明（その記載の原文）、当局の答弁のうち新しい3つ（原文）、記載の推移（資料の日付順）、この事項についての質問・答弁。いまの町の説明が広報ひのの記載のときは、広報ひの以外でいちばん新しい町の資料の記載を並べ、数字や時期の出典にはそちらを使うことを書く。施設・記載の見出し：その記載を資料の日付順に |
| council | from_date・to_date（YYYY-MM-DD。省ける） | 関連する一般質問（日付・会議・質問者・議会だよりの見出し）と関係議案（議決結果・採決方法・討論）、項目ごとに記録した質問・質疑の一覧 |
| speeches | exchange（council が返す `exchange:<番号>`） | その一般質問の会議録の本文のうち、テーマの語（ref/themes.tsv の kind 語）のある発言の全文（質問か答弁か・発言者・url）。頭に、資料そのもので項目ごとの記録ではないことを書く |
| issues | type（比べ方。省ける） | 省いたとき：照合結果の id と文の一覧（文の後ろに比べた記載の出典。§17.1）。指定したとき：その比べ方の照合結果と比べた記載（§17.1 と同じ書き方。問われていない点は記録の節と件数） |
| links | なし | つながりの記録の全行、過程の記録（期間の始まりの順）、総合計画のめざす姿と計画に掲げる課題 |

## 15. 記録の台帳 `records/`

資料の文を引いて、議会でのやりとり（一般質問と議案の質疑）、政策の過程、事柄の時点、記載どうしのつながり、構造にしていない記載、施設の役割と状態を記録する台帳（DESIGN.md ADR-16・ADR-19・ADR-21・ADR-23）。やりとりの記録と質疑の記録で記録しない文と、その理由も台帳に置く（§15.9、ADR-24）。

### 15.1 共通の決まり

- 形は §1 による。どの台帳にも、status（candidate・confirmed・rejected）・reviewer・date・note の列を、この順で最後に置く
- 生成AIと機械は candidate だけを作る。人は行ごとに判定し、引用・種類・参照などを直してから confirmed にしてよい。直したときは note に書く。却下は rejected にして note に理由を書く。抜き取りでまとめて確定しない（§6 のまとめて確定を使わない）
- note の頭には、下書きの作り方を「下書き：<日付>・<作り方>」の形で書く（例「下書き：2026-10-24・生成AI（プロンプトの版なし）」）。プロンプトに版を付けたあとは、その版を書く（ADR-9）
- 資料（source）は、§2 の sp・bq・doc・pt・gi のキーで書く。計画の記載の参照（`plan:<id>/<tab>/<type>/<n>/<item>`、§13.1）は、計画の JSON の項目を指すため（つながりの記録の upper_ref・lower_ref、テーマの定義の source）にだけ使い、引用のある行の source にしない。計画の JSON の文は、画面のために平易に書き直したものがあり、原典の文とは限らないため（shiga-hino-plans PLAN_SCHEMA §8・§10、DESIGN.md ADR-22）
- 引用（quote）は、資料の本文から原文のまま、200字まで（不変の制約9）。照合のしかた：sp は lock の版の発言の本文、bq は議会だよりの問いと答えの本文、doc はそのページの原典の文字（hino-town-docs の data/text/ か data/text_raw/ の、そのページの部分）、pt はそのページの原典の文字（shiga-hino-plans の data/text/ か data/text_raw/ の、そのページの部分）。data/text/ は既定の取り出し、data/text_raw/ は PDF の中で書かれた順の取り出しで、どちらも原典の文字である（hino-town-docs DOCS_SCHEMA.md §5.1、shiga-hino-plans PLAN_SCHEMA §10.1）。どちらか一方にあればよい。data/text_raw/ だけにある引用は、段や文字の枠の順が入れ替わることがあるため、判定のときに原典のページの画像で文の続きを確かめる。どれも §4 の正規化を通して、引用が本文にあること。原典の文字の無いページ（check が image か、そのページの文字が無いもの）からは、校正済みの読みができるまで引用しない（その行は candidate のまま置けるが、confirmed にしない）
- 資料の日付（source_date）は YYYY-MM-DD か YYYY-MM。DESIGN.md ADR-19 の時点の取り方による。広報ひのは発行月（YYYY-MM）
- 台帳の行には、議員の名前の列を置かない。問いのキー（iq）と質疑のキー（sq）から、入力の審議の記録で議員が引けるため（同じことを2か所に写さない）。評価や良し悪しは書かない。議員ごとの件数は作らない（DESIGN.md ADR-12 の画面と出力の決まり）
- 計画の文を引く行は pt で書き、その版の原典の文字から引く。改正の前の版は、shiga-hino-plans が前の版の原典の文字を残している（PLAN_SCHEMA §10.3）。同じ PDF が hino-town-docs にもあるとき（例 doc:jigyo-youhosaihen-keikaku-202503）は、pt で引く。資料の日付は、その版の策定か改正の年月（原典の表紙などによる。分からなければ人が決め、note に根拠を書く）
- 広報ひのの引用に数字（日付・年度を含む）があるときは、判定するときに原典の PDF のページの画像と見比べる（ADR-14）
- 行の並びは、台帳ごとの行のキーの順（§1。row と step は数の順）
- 公開を確認できない資料（例 子育て支援施設の個別施設計画）は引かない。その資料の中身を述べた答弁などを資料（sp）として記録し、note にもとの資料の名前を書く

### 15.2 やりとりの記録 `records/yaritori.tsv`

一般質問の問いと答えを、議会でのやりとりの型で記録する（DESIGN.md ADR-16）。

| 列 | 内容 | 例 |
| --- | --- | --- |
| question | 問い（§2 の iq） | `iq:0000008691_20251212_0229` |
| n | 問いの番号（その議員の一般質問の中の、何番目の問いか。人が決める。審議の記録の turns の問番号を候補として示し、議会だよりの問番号（bq の問番号）と、会議録の中の「２つ目の…」などの言い方で確かめる） | `1` |
| row | 問いの中の行の番号（1から） | `6` |
| side | 問い・答え | `問い` |
| sid | 引用した発言（§2 の sp） | `sp:0000008691_20251212_0233` |
| quote | 発言の本文からの引用 | `やはりそれでも285人の定員の新こども園を建てるのか、なぜそんなに大きい保育園を建てなければならないのか` |
| speaker | 問いは「議員」。答えは発言の役職のまま（例 町長・教育長・子ども支援課長） | `議員` |
| round | 質問の回。問いの番号（n）の中で人が決める：最初の問い、再質問1・再質問2… turns から機械で求めた値（最初の問い（q）、再質問1・再質問2…（rq の順））を候補として示す | `再質問1` |
| stage | 問いの行だけ：課題・投入・活動・手続き・結果・成果・めざす姿 のどれか。答えの行は空 | `結果` |
| kind | 問いの行：「事実の確認」「数字・見込み」「方針・考え」「提案への考え」「住民意見・手続き」「時期・手順」「要望」「その他」のどれか。答えの行：「事実・数字」「方針・考え」「留保」「考えていない」「時期・手順」「その他」のどれか。「その他」のときは、補いを note に書く | `方針・考え` |
| answers | 答えの行だけ：答えている問いの行の row（2つ以上は「,」で区切る） | |
| point | 点の名前。テーマの定義の kind 事柄か記載の値のどれか（事柄の記録・つながりの記録と同じ名前を使う）。当たる名前が無ければ空とし、note に理由を書く | `新こども園の定員` |
| bq | 問いの行だけ：この問いが議会だよりに載っているとき、その問いの bq キー（人が決める。council-dashboard の minutes_links.json の問いごとのリンクは候補として使う。同じ号・同じ議員の問1と問2が同じ発言を指すものがあり（2026-10-25 に、問1と問2の両方がある104まとまりのうち6）、問いごとのリンクが審議の記録の正しい問いに当たるかも確認していないため） | `bq:36/中西佳子/2` |
| bulletin | 議会だよりとの違い：載っている・載っていない・言い回しが違う のどれか。議会だよりが無い問いは空 | `載っていない` |
| status・reviewer・date・note | §15.1 | |

- 行のキーは (question, row)
- iq は、審議の記録の turns の問い（q）の最初の発言を指す（§2）。審議の記録の q と議会だよりの問いは一対一でないので、1つの iq の中に問いがいくつも入ることがある（審議の記録の上で、問2 が問1 の再質問の発言の途中から始まることがある。例 2025年6月の松田議員の問2）。turns の順の番号は、問いの中の回を表さないことがあるため、round は問いの番号の中で人が決める（DESIGN.md ADR-22）
- round は、議会の運び方の「再々質問まで」を当てはめない。一問一答の方式では再質問が何回も続くため、番号だけを書く。最初の問い・再質問・再々質問・要望の読み分けは、kind（要望）と画面で行う
- 1つの発言が2つ以上の点を問うときや答えるときは、点ごとに行を分ける（審議の記録の1つの発言が2つ以上の問いにまたがることがある。docs/review-2026-10-21.md §7.7）
- 試作1では、依頼者が選んだ問いの行を1行ずつ判定する

### 15.3 事柄の記録 `records/kotogara.tsv`

| 列 | 内容 | 例 |
| --- | --- | --- |
| theme | テーマの id | `hoiku` |
| point | 事柄の名前。テーマの定義の kind 事柄の値のどれか | `新こども園の開園時期` |
| program | かかわる事業の node キー（無ければ空） | `node:jisshi/e008` |
| source | 資料 | `doc:koho-no792-04/1` |
| source_date | 資料の日付 | `2026-07` |
| quote | 引用 | `開園時期：令和11年４月（予定）` |
| value | 事柄の値（引用の中の語をそのまま短く。対象の時期だけで足りるときと、会議録の発言（sp）の行は空でよい） | `２８５名`（定員の行の例） |
| target | 対象の時期（資料に書かれた表記のまま。無ければ空） | `令和11年４月` |
| kind | 済んだこと・いまのこと・予定・変更 のどれか | `予定` |
| prev | 変更のとき、前の値（資料に書かれた表記のまま） | `令和10年４月` |
| reason | 変更のとき、理由を書いた文の引用（無ければ空） | `施設の確実な整備と安全性・品質確保を優先する観点から、開園時期（当初：令和10年４月）を見直しました。` |
| yaritori | 資料が会議録の答えで、やりとりの記録にその行があるとき、その行への参照（`<question>/<row>`）。ほかは空 | |
| status・reviewer・date・note | §15.1 | |

- 行のキーは (theme, point, source, quote)
- 施設の状態（開設・休園・閉園・移行など）は、この台帳ではなく施設の記録（§15.8）に記録する（DESIGN.md ADR-23）
- 会議録の答えは、やりとりの記録にあっても、事柄にかかわるものはこの台帳にも1行置く（yaritori の列でつなぐ）。議会と広報と計画の記載を、同じ表で資料の日付の順に見るため
- value は、テーマのノートの画面で事柄の最新の記載を短く示すために使う。施設の記録の value（§15.8）と同じく資料の表記のまま書き、言い換えや単位の付け足しをしない。会議録の発言は話し言葉で、短く切ると意味が変わりやすいため、空でよい（2026-10-29 の依頼者の判断）
- kind の決め方は、資料の書き方による（「〜しました」は済んだこと、「〜しています」はいまのこと、「〜します」「（予定）」「〜をめどに」は予定、「当初〜」「見直しました」「延期」など前の予定を変えたと書いてあるものは変更）。書き方から決められないときは、note に書いて人が決める

### 15.4 つながりの記録 `records/tsunagari.tsv`

| 列 | 内容 | 例 |
| --- | --- | --- |
| theme | テーマの id | `hoiku` |
| link | 目的と手段・もとにした のどちらか | `もとにした` |
| upper | 目的の側、またはもとにした側の記載。テーマの定義の kind 記載の値のどれか | `子育て環境の未来に向けての提言` |
| upper_ref | その記載の参照（資料のキーか計画の記載の参照。無ければ空） | `doc:shingi-youho-teigen/1` |
| lower | 手段の側、またはもとにされた側の記載。テーマの定義の kind 記載の値のどれか | `再編整備方針` |
| lower_ref | その記載の参照 | `doc:koho-no792-04/1` |
| source | つながりを書いた文のある資料 | `doc:koho-no792-04/1` |
| source_date | 資料の日付 | `2026-07` |
| quote | つながりを書いた文の引用（1つの文。2つの資料をまたがない） | `日野町幼児教育保育の在り方検討懇話会において、保護者、保育者、地域住民等からの意見を踏まえた「子育て環境の未来に向けての提言」を基に、` |
| status・reviewer・date・note | §15.1 | |

- 行のキーは (theme, link, upper, lower, source)
- つながりは、1つの資料の文が書いているものだけを記録する。2つの資料の記載が似ている、同じ語を使っている、というだけでつながりを作らない
- 同じつながりを、別の資料が書いていれば、資料ごとに行を分ける（どの資料がいつそう書いたかが残る）

### 15.5 過程の記録 `records/katei.tsv`

| 列 | 内容 | 例 |
| --- | --- | --- |
| theme | テーマの id | `hoiku` |
| step | 段階の番号（テーマの中で、時の順に1から） | `2` |
| name | 段階の名前（テーマごとに人が決める） | `懇話会の提言` |
| from | 始まりの日（YYYY-MM-DD か YYYY-MM。分からなければ空） | `2024-02` |
| to | 終わりの日（1日のものは from と同じ。続いているものは空） | `2024-02` |
| sources | 段階を示す資料のキーを「,」でつないだもの | `doc:shingi-youho-teigen/1` |
| quote | 段階の日付や中身を示す引用（sources の1つめから） | `令和６年２月` |
| status・reviewer・date・note | §15.1 | |

- 行のキーは (theme, step)
- 段階の名前と区切り方は、テーマごとに決める（DESIGN.md ADR-19。政策の始まりと過程の現れ方はテーマによって違う）。決めた名前は、テーマの最初の行の note に書く
- 議会での議論は、過程の段階としては記録しない。画面で、過程の段階の期間と、やりとりの記録・議案の日付を並べて示す

### 15.6 構造にしていない記載 `records/kisai.tsv`

| 列 | 内容 | 例 |
| --- | --- | --- |
| theme | テーマの id | `hoiku` |
| title | 短い見出し（人が決める） | `ワークショップの開き方` |
| about | かかわる事柄か記載の名前。テーマの定義の kind 事柄か記載の値のどれか（無ければ空） | `適正な集団規模の確保` |
| source | 資料 | `doc:shingi-youho-teigen/5` |
| source_date | 資料の日付 | `2024-02` |
| quote | 引用 | |
| status・reviewer・date・note | §15.1 | |

- 行のキーは (theme, title, source)
- 欄に分けず、出典つきの文として残す。分けられるものは、ほかの台帳に記録する
- about に、ほかの台帳の point・upper・lower と同じ名前を書くと、テーマのノートで、その事柄や記載の経緯として、ほかの台帳の行と資料の日付の順に並べられる（DESIGN.md ADR-21）

### 15.7 質疑の記録 `records/shitsugi.tsv`

議案の質疑の問いと答えを、やりとりの記録（§15.2）と同じ型で記録する（DESIGN.md ADR-21）。

| 列 | 内容 | 例 |
| --- | --- | --- |
| question | 質疑のまとまり（§2 の sq） | `sq:0000008942_20260305_0013` |
| n | 問いの番号（そのまとまりの中の、何番目の問いか。人が決める。審議の記録の turns の問番号を候補として示し、会議録の中の「２点目」などの言い方で確かめる） | `1` |
| row | まとまりの中の行の番号（1から） | `3` |
| bills | 質疑の対象の議案（§2 の gi。2つ以上は「,」で区切る）。審議の記録のそのまとまりの bills から機械で求める | `gi:0000008942/議第115号` |
| side | 問い・答え | `答え` |
| sid | 引用した発言（§2 の sp） | |
| quote | 発言の本文からの引用 | |
| speaker | 問いは「議員」。答えは発言の役職のまま | |
| round | 質問の回。§15.2 と同じく、問いの番号（n）の中で人が決め、turns から機械で求めた値を候補として示す | `最初の問い` |
| stage | 問いの行だけ：§15.2 と同じ | |
| kind | §15.2 と同じ値 | |
| answers | 答えの行だけ：§15.2 と同じ | |
| point | §15.2 と同じ | |
| status・reviewer・date・note | §15.1 | |

- 行のキーは (question, row)
- 1つのまとまりの中に問いがいくつも入ることは、やりとりの記録と同じように起こりうる（審議の記録の turns の問番号は、一般質問と議案の質疑の両方にある。hino-council-search README）。そのため n と round は §15.2 と同じ決め方にする（DESIGN.md ADR-22）
- テーマの定義の kind 質疑で選んだまとまりだけを記録する。1つのまとまりがいくつもの事業や議案にまたがるときは、テーマにかかわる部分だけを記録し、note にそう書く
- 議会だよりとの対応（bq・bulletin）は置かない。議会だよりが質疑をどう載せているかを、まだ確認していないため
- 討論と採決は記録しない。審議の記録の討論（kind が debate の stance）と、gian.json の議案の結果（result・method）を、テーマのノートのデータの bills（§13 の debates・result・method）でそのまま示す。審議の記録の採決（kind が vote）にも result・method があり、lock 1af9baa の版では、gian.json の結果のある議案1,066のうち989で採決があり、値はすべて同じだった。77は審議の記録に採決が無い

### 15.8 施設の記録 `records/shisetsu.tsv`

施設ごとに、種類・運営・役割・状態について、資料が何と書いたかを記録する（DESIGN.md ADR-23）。

| 列 | 内容 | 例 |
| --- | --- | --- |
| facility | 施設（§2 の fa。ref/shisetsu.tsv にあるもの） | `fa:nishioji-yo` |
| aspect | 種類・運営・役割・状態 のどれか | `状態` |
| value | 資料の表記のまま（短く。引用の中の語） | `休園` |
| source | 資料（§2 の sp・bq・doc・pt・gi） | `doc:koho-no788-05/1` |
| source_date | 資料の日付（§15.1） | `2026-03` |
| quote | 引用（§15.1） | `【休園する幼稚園】日野町立西大路幼稚園日野町立南比都佐幼稚園` |
| target | 対象の時期（資料の表記のまま。無ければ空） | `令和８年４月１日（水）～令和９年３月31日（水）` |
| kind | 済んだこと・いまのこと・予定・変更 のどれか（§15.3 と同じ決め方） | `予定` |
| prev | 変更のとき、前の値（資料の表記のまま） | |
| status・reviewer・date・note | §15.1 | |

- 行のキーは (facility, aspect, source, quote)
- 種類は、幼稚園・保育所・認定こども園・小規模保育施設など、資料の表記による。運営は、直営・民営など、資料の表記による
- 役割は、資料に書かれたものだけを記録する（例 指定避難所）。推定で足さない
- 状態は、開設・休園・閉園・移行・跡地の使い方など、施設の状態の変わり方を書いた資料の文を記録する
- 1つの引用が2つ以上の施設を書いているときは、施設ごとに行を分ける（引用は同じ）
- 議員の発言（sp）も資料にしてよい。町の資料と議員の発言の区別は、source のキーと、審議の記録の役職で分かる
- テーマの定義の kind 施設で選んだ施設について記録する

参照表 `ref/shisetsu.tsv`（系譜表・別名辞書と同じ参照表。人が根拠つきで決める。エージェントが自分の判断で行を足したり変えたりしない）：

| 列 | 内容 | 例 |
| --- | --- | --- |
| key | `fa:<英小文字・数字・ハイフン>` | `fa:kaneka` |
| name | いまの名前（資料の表記） | `みらいしゃくなげ保育園` |
| aliases | 前の名前と、その時期（「名前（時期）」を「;」で区切る。時期は資料の表記） | `日野幼稚園鎌掛分園（平成10年〜）;保育所あおぞら園鎌掛分園（平成28年〜）` |
| district | 地区（日野・東桜谷・西桜谷・西大路・鎌掛・南比都佐・必佐。資料の表記） | `鎌掛` |
| source | 根拠（入力のどこを見て決めたか） | `doc:jigyo-shinkodomoen-kousou/14 の施設概況の表` |
| reviewer・date・note | 決めた人の GitHub ユーザー名・決めた日・注記 | |

- 行は key の文字コード順
- 1つの建物（場所）を1つの施設とする。名前や運営が変わっても key は変えず、使い回さない

### 15.9 記録しない文 `records/nozoki.tsv`

発言の取りこぼしの検査（§11）で、やりとりの記録か質疑の記録の行と重ならない文のうち、記録しないと決めた文と、その理由を記録する（DESIGN.md ADR-24）。

| 列 | 内容 | 例 |
| --- | --- | --- |
| question | 問い（§2 の iq）か、質疑のまとまり（§2 の sq） | `iq:0000008489_20250613_0023` |
| n | 問いの番号（§15.2・§15.7 の n） | `2` |
| sid | 文のある発言（§2 の sp） | `sp:0000008489_20250613_0031` |
| quote | 文の全体を原文のまま。200字を超える文は頭から200字 | |
| reason | 記録しない理由 | `答えの前置き` |
| status・reviewer・date・note | §15.1 | |

- 行のキーは (question, n, sid, quote)
- 生成AIは理由の下書き（candidate）だけを作る。confirmed は、人が記録しないと決めた文。rejected は、人が記録すると決めた文で、やりとりの記録か質疑の記録に行を足し、この行の note に足した行を書く
- 同じ理由の文をまとめて見せてよいが、判定は文ごとに行う（§15.1）
- 検査のための台帳で、テーマのノートのデータ（§13）と MCP の道具（§14）には入れない

## 16. テーマのノートの画面 `build/pages/<theme>-<事業の番号>.html`

DESIGN.md ADR-25 による。事業（テーマの定義の kind 事業）ごとの画面。公開しない（DESIGN.md ADR-13）。人に見せるときは非公開のアーティファクトにする。

- 作り方：`python3 -B tools/build_pages.py <theme> <node キー>`（例 `hoiku node:jisshi/e008` で build/pages/hoiku-e008.html）。build/theme/<theme>.json（§13）だけを読み、ひな形 `tools/pages/note.html` にデータを入れて書く。lock の版の入力は読まない。手で直さない（CLAUDE.md 不変の制約8）
- 形：外から何も読み込まない1つの HTML の文書。データは `<script type="application/json">` に、JSON の `</` を `<\/` に替えて入れる。同じデータからは同じファイルができる
- 文：画面の文は、決まった文（16.4）とデータの項目だけで作る。テーマや事業に固有の語をひな形に書かない。資料の文は引用のまま示し、要約や言い換えをしない
- 層：layer の違う項目をまぜない（§13）。記録（未確認）の行には「未確認」の印を付ける。論点の候補は「照合結果（未確認）」の欄にまとめる。語の一致は「キーワード検索の結果（参考）」として閉じた欄に置く
- 序列化しない：議員ごとの件数や順位を示さない（不変の制約6）。議会だよりと会議録の違いを、誤りや欠けとして読ませる言葉を使わない（DESIGN.md ADR-12）

### 16.1 メニューと欄

| メニュー | 説明の文 | 欄 | もとの項目 |
| --- | --- | --- | --- |
| （全体） | | 事業名・事業の説明・事業の要点（概算事業費・当初予算額・担当課・総合計画の分野と基本施策） | programs・budget・policies |
| 概要 | 事業の現状と経過を把握する | 主な事項（16.2） | records.kotogara |
| | | 経過（検討の段階・議決・一般質問・予定の変更を日付順） | records.katei・bills・exchanges・records.kotogara |
| | | 施設の再編（施設ごとに種別・運営・役割・状況） | records.shisetsu・names.facilities |
| | | 資料（参照資料・関連計画） | docs・plans |
| 論点整理 | 質問・答弁の作成の準備 | 事項ごとの質問・答弁（質問・答弁と町の資料を日付順） | records.yaritori・records.shitsugi・records.kotogara・theme_questions |
| | | 照合結果（未確認） | issues |
| | | 一般質問と議案（関連する一般質問・関係議案と議決結果・キーワード検索の結果（参考）） | exchanges・bills・hits |
| 事業の運営 | 目的と手段、予算と議会の節目 | 目的と手段（総合計画のめざす姿・計画に掲げる課題・目的と手段の関係） | sheets・records.tsunagari |
| | | 年度ごとの節目（検討の段階・議会・予定の記載） | records.katei・bills・exchanges・records.shitsugi・records.kotogara・budget |

- 主な事項・施設の再編・事項ごとの質問・答弁は「選ぶ→全幅で開く」で示す
- 資料の名前と施設の名前は names から示す
- 欄に項目が無いときは「未記録」と示す（資料に無いのか、まだ記録していないのかを分けられないため。§13.1）

### 16.2 主な事項

- 並び：その事業の事柄（事柄の記録の program がその事業）を先に、テーマの単位の事柄（program が空）を後にする。それぞれ、町の資料（会議録の発言でない資料）の最新の記載の資料の日付が新しい順とし、同じ日付は事柄の記録の行の数が多い順（それも同じならテーマの定義の順）、町の資料の記載が無い事柄は最後
- カードの値：町の資料の行のうち資料の日付が最新のものから、value か target のある行を選ぶ（種類が変更の行より、変更でない行を先に選ぶ）。value があれば value、無ければ target を示す。カードには種類を付けない
- 開いた欄：値（種類が予定なら「（予定）」を付ける）、その行の引用、資料の名前と資料の日付、変更の行があれば「当初：<prev>　→　<資料の日付>に変更」と変更理由、そのあとに記載の推移（会議録と町の資料を日付順）
- 町の資料の行が無い事柄：カードと開いた欄に「町の資料に記載なし」と示し、会議録の発言を日付順に並べる

### 16.3 表示の言葉

| データ | 画面 |
| --- | --- |
| 会議の名前 | §13.4 の会議の名前 |
| 日付 YYYY-MM-DD・YYYY-MM | 2025年3月10日・2025年3月 |
| やりとりの記録の side 問い・答え | 質問・答弁 |
| 答えの種類 留保 | 答弁（今後検討）（印）、今後検討（種類） |
| 答えの種類 考えていない | 予定なし |
| 種類 事実・数字／数字・見込み／方針・考え／提案への考え | 事実・数値／数値・見込み／方針・考え方／提案への見解 |
| 種類 事実の確認／住民意見・手続き／時期・手順／要望／その他 | そのまま |
| 区分 投入・結果 | 投入（予算・人員）・結果（施設・定員等）（最初に出る所だけ） |
| 施設の記録の aspect 種類・状態 | 種別・状況 |
| 資料の区分 koho／shingi／jigyo／yosan／kessan／kofukin／bosai | 広報ひの／懇話会・審議会／事業資料／予算／決算／交付金／防災 |
| 資料が会議録の発言（sp）／それ以外 | 会議録／町の資料 |
| layer 論点の候補（未確認） | 照合結果（未確認） |
| layer 語の一致（未確認） | キーワード検索の結果（参考） |

### 16.4 決まった文

画面の説明の文と注記は、ひな形に置く。判定シート S5-1（2026-10-28）と、試作の9回目までの直しで決めた文とする。主なもの：

- 一番下：資料の文は原文のまま引用しています。「未確認」の表示がある項目は、機械による照合の結果で、人による確認が済んでいません。議員ごとの件数や順位は示していません。
- 概要：公開資料（計画・予算・会議録・議会だより・広報ひの等）から本事業に関する記載を抜き出し、出典付きで整理したものです。評価や判断は加えていません。
- 論点整理：一般質問や答弁を作成する際の準備に使います。事項ごとに、これまでの質問・答弁と町の資料の記載を日付順に並べ、過去の答弁との整合や、まだ取り上げられていない事項を確認できます。
- 事業の運営：事業担当課が、事業の目的と手段を整理し、予算要求や議会での説明に備えるために使います。
- 目的と手段：資料に記載された関係のみを示し、記載のない関係は加えていません。ロジックモデル（課題・投入・活動・結果・成果）への位置付けは、担当課が判断します。
- 照合結果（未確認）：資料を機械的に照合した結果で、人による確認は済んでいません。
- キーワード検索の結果（参考）：「<テーマの定義の語を3つまで>」等のキーワードが一致した会議録・議会だより・町の資料です。本事業に関するものとは限りません。

## 17. 持ち込み用の資料 `build/rag/<theme>-<事業の番号>-honpen.md`・`-kiroku.md`（と同じ名前の .docx）

DESIGN.md ADR-26 による。議員や職員が、各自の生成AI（LoGoAIアシスタントの RAG、ファイルを添えられる生成AI）に持ち込むための文書。公開しない（DESIGN.md ADR-13）。

- 作り方：`python3 -B tools/build_rag.py <theme> <node キー>`（例 `hoiku node:jisshi/e008`）。build/theme/<theme>.json（§13）だけを読み、lock の版の入力は読まない。手で直さない（CLAUDE.md 不変の制約8）。標準ライブラリだけで作る（DOCX は zipfile と XML で書く）。同じデータからは同じファイルができる（DOCX の中の日時は固定する）
- 添えるもの：prompts/shisaku1-common-v2.md の「---」より後（共通の指示と、場面ごとの依頼文の例）を、build/rag/<theme>-<事業の番号>-prompt.md に写す

### 17.1 共通の決まり

- 頭に「この資料の読み方」を置く：何の資料か（事業名・テーマ名・本編か記録編か）、作ったデータの版（データの sha256 と lock の版）、取り込んだ資料の時点、記載の書き方（下の形）、【未確認】の意味、評価や判断を加えていないこと、議員ごとの件数や順位を示していないこと
- 見出しは階層を付け（Markdown の「#」、DOCX の見出し1〜3）、章と節の見出しに事業名を入れる（RAG で切られても、どの事業のどの章かが分かるように）
- 記載は1つごとに1段落とし、形は「［資料の日付］資料の名前：「引用」（出典：url）」とする。事柄の値・施設の面・答弁の種類などの欄は、引用の前に「欄の名前：値。」で書く。資料の名前は names（§13）、日付と会議の名前・表示の言葉は §13.4・§16.3 による
- 過程の記録（§15.5）の行は、資料の日付の列が無いので［ ］を付けず、「検討の段階：段階：<段階の名前>。期間：<期間>。資料：<sources の1つめの資料の名前>。「引用」（出典：url）」とする。並びは期間の始まりの順。期間の始まりを［ ］に書くと、資料の日付と読み違えられるため（2026-10-29 の生成AIの出力の確認で、2026年4月に始まる予算の段階を「2026年4月の予算」と書いた例があった）
- 記録（未確認）の行は、段落の頭に「【未確認】」を付ける。照合結果（論点の候補）は節を分けて「照合結果（未確認）」とし、比べた記載を出典つきで並べる。ただし、比べ方「問われていない点」は、比べた記載を並べず、それが記録編のどの節にあるか（節の名前と件数）を書く（同じ引用を本編と記録編に重ねて置かないため。記録の行に当たらない比べた記載は、そのまま並べる）
- 照合結果の文（statement）の後ろには、比べた記載（refs）の出典の url を「（比べた記載の出典：url、url）」の形で付ける。並びは比べた記載の資料の日付の順（記録の行に当たらず日付の分からないものは、最後に refs の順で）とし、同じ url は1回だけ書く。比べ方「問われていない点」は付けず、上のとおり記録編の節と件数を書く。照合結果の一覧だけを示すところ（MCP の issues で type を省いたとき）にも付ける
- 主な事項で町の資料の行が無い事柄（§16.2）は、「町の資料に記載なし（会議録の発言 N 件）」と書く。記載が無いことを言う文で、付けられる url が無いため。N はその事柄の事柄の記録のうち資料が会議録の発言（sp）の行の数
- キーワード検索の結果（hits）は入れない（DESIGN.md ADR-26）
- 文は、決まった文（見出し・読み方・節の説明）とデータの項目だけで作る。生成AIの補足を入れない（DESIGN.md ADR-17）。評価や結論を書かない
- 序列化しない（CLAUDE.md 不変の制約6）。議員の名前は、問いの単位で「質問者」として書く（§13.3）
- 表は使わない（RAG で表が崩れるのを避ける）。並べるものは段落か箇条にする
- DOCX は Markdown と同じ中身で、見出しは Word の見出しスタイル、出典の URL は文字のまま書く

### 17.2 本編の章（画面 §16 と同じ範囲）

1. 事業の要点：事業名・事業の説明・概算事業費と実施年度・当初予算額と担当課・総合計画の分野と基本施策（どれも出典つき）
2. 概要：主な事項（§16.2 の並びと値。事柄ごとに最新の記載と、記載の推移を日付の順に）、経過（検討の段階・議決・一般質問・予定の変更を日付の順に）、施設の再編（施設ごとに種別・運営・役割・状況の記載を日付の順に）、資料と関連計画の一覧
3. 論点整理：事項ごとの質問・答弁（問いと答えと町の資料の記載を日付の順に。答弁の種類と区分を欄として書く）、照合結果（未確認）（比べ方ごとに、文と比べた記載）、関連する一般質問と関係議案の一覧
4. 事業の運営：目的と手段の関係（つながりの記録の行ごとに、上位・下位の記載と、その関係を書いた引用）、総合計画のめざす姿と計画に掲げる課題、年度ごとの節目

### 17.3 記録編の章

- 記録の台帳（records）の全行を、台帳ごとの章に置く：事柄（事柄ごと）・施設（施設ごと）・やりとり（問いごと）・質疑（質疑のまとまりごと）・つながり・過程・構造にしていない記載（記載の見出しごと）。章の中は資料の日付の順
- テーマの単位の台帳（つながり・過程・構造にしていない記載など）は、どの事業の記録編にも同じものを置く
