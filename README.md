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

対象ごとに扱いが異なる。詳しくは [LICENSE-DATA.md](LICENSE-DATA.md) を参照。

- プログラム（tools/）：GNU Affero General Public License v3.0 以降（AGPL-3.0-or-later、[LICENSE](LICENSE)）
- データの構造（ref/ の系譜表・別名辞書、links/ の判定と注記、LINK_SCHEMA.md のキーの形）：CC BY 4.0
- 教材・プロンプト（prompts/ など。まだ置いていない）：CC BY-SA 4.0
- 会議録・議会だより・計画から転記した部分（links/ の evidence・context・to_label、ref/lineage.tsv の name・start_fy・end_fy、note のうち原典から写した計画の名称・期間と「」で引いた文言）：このリポジトリのライセンスの対象外（著作権は日野町議会、日野町など各発行者にある）

プログラムは、コミット a15ccfb までの版を MIT License で公開していた。その版は、引き続き MIT License の条件で使える。

Copyright (C) 2026 Kenjiro HIGASHI

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
