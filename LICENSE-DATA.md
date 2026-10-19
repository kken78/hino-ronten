# データのライセンス

このリポジトリには、作者が書いたもの、作者が整理したもの、会議録・議会だより・計画から転記したものが含まれており、それぞれ扱いが異なります。

| 対象 | 該当するもの | 扱い |
|---|---|---|
| プログラム | tools/ | GNU Affero General Public License v3.0 以降（AGPL-3.0-or-later、LICENSE） |
| データの構造 | ref/lineage.tsv の series・edition・plan・source・note、ref/aliases.tsv（別名辞書）、links/ の from・to・method・where・status・reviewer・date・note（判定と注記）、LINK_SCHEMA.md に定めたキーの形 | CC BY 4.0 |
| 教材・プロンプト | prompts/ など（まだ置いていない） | CC BY-SA 4.0 |
| 会議録・議会だより・計画から転記した部分 | links/ の evidence・context・to_label、ref/lineage.tsv の name・start_fy・end_fy、links/ と ref/lineage.tsv の note のうち、原典から写した計画の名称・期間と「」で引いた原典の文言 | このリポジトリのライセンスの対象外 |

会議録と議会だよりから転記した部分の著作権は、日野町議会にあります。計画から転記した部分の著作権は、日野町など各計画の発行者にあります。この部分を利用する場合は、各発行者に確かめてください。発言の正確な内容は会議録の原本PDFで、計画の内容は各計画の原典で確かめてください。

links/ の to_label と ref/lineage.tsv の name は、計画の名称を原典または shiga-hino-plans の manifest の表記のまま写したものです。start_fy・end_fy は、原典に書かれた計画期間を西暦の年度に直したものです。どちらも転記として扱います。

別名辞書（ref/aliases.tsv）は、照合に使う語の選び方と組み合わせを作者が整理したものとして CC BY 4.0 とします。個々の計画の名称について権利を主張するものではありません。

データの構造を利用する場合は、「hino-ronten（https://github.com/kken78/hino-ronten）をもとに作成」のように出典を表示し、CC BY 4.0 であることを示してください。改変した場合は、その旨もあわせて書いてください。

教材・プロンプトを利用する場合も、同じように出典を表示し、CC BY-SA 4.0 であることを示してください。改変したものを公開する場合は、CC BY-SA 4.0 で公開してください。

## 入力のリポジトリ

links/ のキーと ref/lineage.tsv の plan は、次のリポジトリのデータの構造（いずれも CC BY 4.0）をもとにしています。

- bq：council-dashboard（https://github.com/kken78/council-dashboard）の docs/data/questions.json
- sp：hino-council-search（https://github.com/kken78/hino-council-search）の public/data/index/ の sid
- plan・node：shiga-hino-plans（https://github.com/kken78/shiga-hino-plans）の data/manifest.json と data/plans/
