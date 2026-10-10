# hino-ronten（日野町 論点ノート）

滋賀県日野町の計画・予算・議会の公開資料を、事業や地域課題ごとに整理し、出典とあわせて示すための仕組み（非公式）。評価や結論は記載せず、資料を比較して確認すべき点を示すところまでを扱う。

現在は設計の段階で、実装はまだ無い。

| 文書 | 内容 |
| --- | --- |
| [DESIGN.md](DESIGN.md) | 設計判断（ADR）、入力の状況、工程とゲート、判断事項 |
| [LINK_SCHEMA.md](LINK_SCHEMA.md) | 参照表とリンク台帳の列・キー・状態・正規化・照合の規則 |
| [CLAUDE.md](CLAUDE.md) | 作業の手順と制約 |
| [docs/proposal-2026-10-09.md](docs/proposal-2026-10-09.md) | 元の設計案（履歴） |

## 入力（読み取りのみ）

| リポジトリ | 内容 |
| --- | --- |
| [council-dashboard](https://github.com/kken78/council-dashboard) | 議会だよりの一般質問 |
| [hino-council-search](https://github.com/kken78/hino-council-search) | 会議録の発言、審議構造 |
| [shiga-hino-plans](https://github.com/kken78/shiga-hino-plans) | 町の計画 |

## ライセンス

コードは MIT。データのライセンスは、データを置く工程で決める。
