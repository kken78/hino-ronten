# LINK_SCHEMA.md — 参照表とリンク台帳の規則

この文書は規範である。`tools/` の実装はこの文書に従う。キー・列・状態・正規化・照合の規則を変えるときは、この文書を先に改定し、検査 → 生成の順で実装を追従させる（CLAUDE.md 制約3）。設計判断の経緯は DESIGN.md に置く。

---

## 1. ファイルの共通形式

- TSV、UTF-8（BOMなし）、改行は LF、1行目がヘッダ
- セルの中にタブ・改行を入れない
- evidence・context は §4 の正規化を通した値を書く。名称（to_label・name など）は原典の表記のまま書く
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
| node | 計画の事業 | `node:<id>/<節>/<基本施策>/<事業>` | `node:kodomo/第1節/(1)/①` | `data/plans/<id>.json` の programs（`groups[].no`・`subgroups[].no`・`items[].no`） |

- bq の議員名は、member を NFKC 正規化し、空白を除いたもの。この形で326問すべてが一意であることを確認済み（2026-10-10）
- sp と node は位置や番号に依存するため、単独では信頼しない。必ず §5 の照合を通す
- node は programs を持つ計画にだけ定義する（2026-10-10 時点で kodomo 100事業・koutsu 19事業。例：`node:koutsu/Ⅰ./1./事業1`）。programs の無い計画や、subgroups の無い programs が必要になった場合は、この表に形式を追加してから使う

---

## 3. リンク台帳 `links/<method>.tsv`

ファイル：`links/mention.tsv`、`links/program.tsv`。semantic を使う場合は `links/semantic.tsv` を加え、列の使い方をこの節に追記してから使う。crosswalk は台帳に行を持たず、`ref/crosswalk.tsv` から表示のときに求める（DESIGN.md ADR-3）。

| 列 | 内容 | 例 |
| --- | --- | --- |
| from | 議会側のキー（bq・sp） | `sp:0000008942_20260305_0161` |
| to | 計画側のキー（plan・lin・node） | `plan:kodomo` |
| method | mention・program・semantic | `mention` |
| evidence | 一致した語（正規化後） | `子ども・子育て支援事業計画` |
| where | from のどこで一致したか。bq は title・question_text・answer_title・answers、sp は text | `text` |
| context | evidence を含む前後各15文字の抜粋（正規化後）。前後が15文字に満たない場合は、ある分だけ | `す。まとめるにあたりましては、子ども・子育て支援事業計画に掲げる3つの基本目標に分類し` |
| to_label | 確定した時点の to の名称（計画名・事業名）。原典の表記 | `第3期 日野町子ども・子育て支援事業計画` |
| status | candidate・confirmed・rejected | `candidate` |
| reviewer | 確定・却下した人。candidate では空 | |
| date | 確定・却下した日（YYYY-MM-DD）。candidate では空 | |
| note | 期の判別の根拠、却下の理由など | `2026-03-05 は令和7年度。第3期（2025〜2029年度）` |

- 行の同一性は (from, to, method) の組とする。同じ組の行は1行だけ置く
- 例の行は、令和8年3月定例会議の企画振興課長の発言（実在）から作った候補で、まだ人は確定していない

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

ビルドのたびに、台帳の confirmed と candidate の全行について行う。

sp（会議録の発言）：

1. sid の発言が存在し、その正規化本文に context が含まれる → 一致
2. 含まれない、または sid が存在しない → sid の最後の連番を除いた部分が同じ発言のうち、連番が前後5以内のものを探す
   - 1件だけ context を含む → 移動。移動先の sid を一覧に出す。その行は、人が from を書き換えるまで出力に使わない。ビルドは続ける
   - 0件、または2件以上 → 停止。行を一覧に出し、終了コード1で終える

bq（議会だよりの質問）：where の欄の正規化テキストに context が含まれなければ停止する。

node：to_label と、現在の `data/plans/<id>.json` の該当事業の name が一致しなければ停止する。

plan・lin：to_label と、manifest または `ref/lineage.tsv` の name が一致しなければ停止する。

停止したときは、人が原本で確かめ、from・to を直すか、status を rejected にして note に理由を書く。

---

## 6. 状態の変わり方

- 生成：tools が candidate を作る。同じ (from, to, method) の行が既にあれば、status・reviewer・date・note は変えない
- 確定・却下：人が status を confirmed または rejected に変え、reviewer・date を書く。confirmed と rejected の間の変更も人だけが行い、note に理由を書く
- 再生成で出なくなった行：candidate は削除する。confirmed と rejected は削除しない。confirmed のうち再生成で出なくなったものは一覧に出し、ビルドを停止する（別名辞書や系譜表の変更が既存の確定に影響したことを見落とさないため）
- 出力に使うのは、confirmed で、かつ §5 の照合が「一致」の行だけとする

---

## 7. 照合方法ごとの規則

mention：

- `ref/aliases.tsv` の語（正式名・略称）を、正規化後の本文から最長一致で探す。除外語の範囲に含まれる一致は数えない
- 期の明記がない言及は `ref/lineage.tsv` で期を判別する（§8）。複数の期に当たる場合は、それぞれ candidate を作る
- 会議録は、role が議長の発言を対象から除く（設計案の試算と同じ）

program：

- 事業名（`items[].name`）を照合の語とする。一般的な語で誤った一致が多い事業は、`ref/aliases.tsv` に別名・除外語を足して対応する（工程8で決める）

semantic：使う時点で、この節と §3 に規則を追加する。

---

## 8. 系譜表 `ref/lineage.tsv`

| 列 | 内容 | 例 |
| --- | --- | --- |
| series | 計画の系列（人が決める短い名前） | `kodomo` |
| edition | 期（数字）。期の概念がない計画は空 | `3` |
| plan | manifest の id。manifest に無い期は空（キーは `lin:<series>/<edition>`） | `kodomo` |
| name | 正式名（原典の表記） | `第3期 日野町子ども・子育て支援事業計画` |
| start_fy | 計画期間の初年度（西暦の年度） | `2025` |
| end_fy | 計画期間の最終年度（西暦の年度） | `2029` |
| source | 期間の出典（`manifest`、または原典の文書id＋ページ） | `manifest` |
| note | 延長・改定・中間見直しなどの注記 | |

- 年度は4月1日から翌年3月31日まで。令和N年度＝西暦2018＋N年度、平成N年度＝西暦1988＋N年度
- 発言日：会議録は sid の日付。sid に日付が無い場合は `meetings.json` の会議の日付。議会だよりは対応する会議（`minutes_links.json` の meeting_id）の日付。対応する会議が無い号は人が確定する
- 期間を確認できない計画は start_fy・end_fy を空にする。その計画への期の明記がない言及は、candidate を作り、note に「期間不明」と書く

---

## 9. 別名辞書 `ref/aliases.tsv`

| 列 | 内容 | 例 |
| --- | --- | --- |
| series | 系譜表の series | `chiiki-nogyo` |
| term | 照合の語（正規化後） | `地域計画` |
| kind | 正式名・略称・除外 | `略称` |
| note | 根拠・注記 | |

- 除外：他の計画名の一部になっている語の範囲を、一致から外すための語。例：series が chiiki-nogyo の「地域計画」に対し、「文化財保存活用地域計画」（bunkazai）と「国土強靭化地域計画」（kyojin）を kind=除外 で登録する
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
    "files": ["data/manifest.json", "data/plans/*.json", "data/sources_index.tsv"]
  }
}
```

- ビルドは、ここに書いた SHA の、ここに書いたファイルだけを読む
- lock の更新は1コミットにまとめ、追加・変更・削除された質問と発言の件数をコミットメッセージに書く

---

## 11. 実装に必要な検査

| 検査 | 内容 |
| --- | --- |
| キーの形式 | 全行の from・to が §2 の形式に合う |
| 行の同一性 | (from, to, method) の重複が0件 |
| 状態 | status が3つの値のいずれか。confirmed・rejected は reviewer と date がある |
| 位置依存キーの照合 | §5 の一致・移動・停止の件数を表示する。停止が1件以上なら終了コード1 |
| 根拠の消失 | §6 の「再生成で出なくなった confirmed」が1件以上なら終了コード1 |
| sentinel | 検査用の行の context を1文字変えると、移動か停止になる |
| 方法の制限 | 台帳に crosswalk の行が無い |
