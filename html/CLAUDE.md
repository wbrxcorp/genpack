# genpackについてのドキュメント

## 制作方針

- index.md をはじめとするすべての Markdownファイルをオリジナルのドキュメントとする。(このCLAUDE.mdはもちろん除く！)
- .mdファイルにはそれぞれ対応する .htmlファイルを生成する
    - HTMLファイル間で共有されるリソースは別ファイルに抜き出して良い。その際、サブディレクトリを設けても構わない。
    - 図形を用いた表現をアスキーアートで行うと崩れがち（日本語環境特有？）なので代わりにCSS(または追加の表現力が必要な場合SVG)で行うこと
    - 各HTMLの末尾には 他のドキュメントへのリンク一覧を設ける
    - もしドキュメント数が増えたことでmd->html変換をスクリプト化する方が効率的と判断した場合はその旨を提案すること
    - 生成されたファイルのデプロイ先は https://www.walbrix.co.jp/genpack/ を想定すること(デプロイ作業自体は不要)
    - image/favicon.png をページのいわゆるfaviconとして指定すること
- genpack自体に何らかの修正や拡張があった場合は指示に従い Markdownを更新する
    - Markdownドキュメントには関連gitリポジトリのどの時点のスナップショットを元にドキュメントが書かれたかを（githubのリンクで）残すためのセクションを末尾に記載する。
- Markdownを更新したときは対応するHTMLも更新する
- Markdownはオリジナルを日本語とするが、それぞれの .md ファイルに対して .en.md というネーミングで英語版も作成・維持する
- 英語版についてもオリジナルの日本語版と同様HTMLを生成する
- 日本語版のHTMLには対応する英語版へのリンクを設ける。英語版から日本語版へのリンクバックは不要。

## HTMLに挿入するソーシャルメディア用メタデータ

```html
<meta property="og:title" content="記事のタイトル" />
<meta property="og:description" content="記事の概要" />
<meta property="og:image" content="https://www.walbrix.co.jp/genpack/image/article.png" />
<meta property="og:url" content="記事のURL" />
<meta property="og:type" content="article" />

<meta name="twitter:card" content="summary_large_image" />
<meta name="twitter:title" content="記事のタイトル" />
<meta name="twitter:description" content="記事の概要" />
<meta name="twitter:image" content="https://www.walbrix.co.jp/genpack/image/article.png" />
<meta name="twitter:site" content="@wbrxcorp" />
```
