# tools/review — 人が候補を判定する確認ページの道具

台帳の candidate を人が判定するための、確認ページと、その前後の道具を置く（CLAUDE.md 不変の制約11 の「1件ずつのページの判定」）。機械が作るのは候補と区分の案までで、確定・却下は人がページで行う（DESIGN.md ADR-2）。

| ファイル | 中身 |
| --- | --- |
| `mention_page.html` | 言及（links/mention.tsv）の確認ページ。1行ずつ確定・却下し、却下には理由を書く。却下の行には付け替え先を付けられる（LINK_SCHEMA §6） |
| `mention_seed.py` | 言及の確認ページに入れる候補の束を作る |
| `mention_export.py` | 言及の確認ページの判定を、判定の一覧と判定した範囲の TSV に書き出す |
| `fuhyo_page.html` | 附表（links/fuhyo.tsv）の確認ページ。附表の事業を突き合わせの区分に仕分け、区分ごとに確かめる（LINK_SCHEMA §7 fuhyo） |
| `fuhyo_seed.py` | 附表の確認ページに入れる事業の一覧を作る。区分の案と、事業概要の違う箇所を付ける |
| `fuhyo_export.py` | 附表の確認ページの判定を、判定の一覧と判定した範囲の TSV に書き出す |

## ページの動かし方

2つのページは、claude.ai のアーティファクト（共有のデータベースの機能 `db` を使うもの）として公開して使う。ページは、データベースの集まりを次のように読み書きする。

| ページ | 読む集まり | 書く集まり |
| --- | --- | --- |
| mention_page.html | `candidates`（束の行。1行1文書、文書の id は束の id） | `decisions`（判定。文書の id は候補と同じ） |
| fuhyo_page.html | `items`（附表の事業。1事業1文書、文書の id は附表の key）、`meta/reasons`（区分の案の理由と、案の上書き） | `decisions`（判定。文書の id は候補の id）、`cats`（人が移した区分） |

判定は、送るまでのあいだ、ブラウザの localStorage に残す（送れなかった判定を失わないため）。

候補の id は、どちらのページも `from<TAB>to<TAB>method` の SHA-1 の先頭16文字。

## 流れ

1. 候補を作る：tools/update_links.py で台帳に candidate を書く（いつもの工程）
2. 束や一覧を作る：`mention_seed.py` か `fuhyo_seed.py`
3. ページを公開し、2 の出力をデータベースに入れる（Claude が ArtifactData で入れる）
4. 人がページで判定する
5. データベースの `decisions` を、1判定1ファイルの JSON でフォルダに書き出す（Claude が ArtifactData で書き出す）
6. 判定の一覧と範囲を書く：`mention_export.py` か `fuhyo_export.py`
7. 台帳に書き写す：`python3 -B tools/apply_decisions.py [--ledger fuhyo] --keys <範囲.tsv> <判定の一覧.tsv>`

判定の一覧と範囲の TSV、データベースから書き出した JSON は、リポジトリに入れない。

## 実行の例

```
python3 -B tools/review/mention_seed.py plan:kankyo,plan:toshimaster 0 0 before-13 "計画期間の前" 1118 batch.json
python3 -B tools/review/mention_seed.py --targets
python3 -B tools/review/mention_export.py batch.json dump-new/decisions dump-old/decisions decisions.tsv decisions.keys.tsv --reviewer kken78
python3 -B tools/review/fuhyo_seed.py items.json --suggest suggest.json --docs docs/
python3 -B tools/review/fuhyo_export.py items.json dump/decisions decisions.tsv decisions.keys.tsv
```

- `--ledger` で、台帳の代わりに別の TSV を読める（過去の回の再現を確かめるとき）
- `fuhyo_seed.py --suggest` は、区分の案の上書き（`{"b049": ["ichibu", null], "b131": ["meisho", "e124"]}`）。区分の id は icchi（一致）・icchi-hashira（一致（柱違い））・hyoki（表記の違い）・meisho（名称の変更）・ichibu（一部）・nendo（年度の事業）・nakami（中身の違い）
- 区分の案の理由の文（`meta/reasons`）は、回ごとに Claude が書いてデータベースに入れる。ここには置かない

## 置いたときの確かめ（2026-10-21）

作業場所で使っていた道具をここに移したとき、次の4つで、当時の出力と1字も違わないことを確かめた。

- `fuhyo_seed.py`：c1dc8fb の links/fuhyo.tsv と当時の上書きから、附表の一覧（181事業・213候補）
- `fuhyo_export.py`：上の一覧と当時の判定から、判定の一覧（sha256 3e0150e1…）と範囲（d5f113d0…）。28099c3 で書き写したもの
- `mention_seed.py`：22b4989 の links/mention.tsv から、束 before-13（102行）
- `mention_export.py`：上の束と当時の判定から、判定の一覧（sha256 11cd611a…）。73ba687 で書き写したもの

`mention_page.html` の付け替え先の一覧（TARGETS）は、当時のページのまま。`mention_seed.py --targets` が作る一覧とは、lin:kaigo/6・lin:kaigo/7 の表示名だけが違う（ページは長い名前、系譜表の name は「第6期」「第7期」）。表示だけの違いで、付け替え先のキーは同じ。
