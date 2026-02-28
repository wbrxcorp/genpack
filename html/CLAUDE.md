# genpackについてのドキュメント

## 制作方針

- index.md をはじめとするすべての Markdownファイルをオリジナルのドキュメントとする。(このCLAUDE.mdはもちろん除く！)
- .mdファイルにはそれぞれ対応する .htmlファイルを生成する
    - 図形を用いた表現をアスキーアートで行うと崩れがち（日本語環境特有？）なので代わりにCSS(または追加の表現力が必要な場合SVG)で行うこと
    - HTMLファイル間で共有されるリソースは別ファイルに抜き出して良い。その際、サブディレクトリを設けても構わない。
    - 生成されたファイルのデプロイ先は https://www.walbrix.co.jp/genpack/ を想定すること(デプロイ作業自体は不要)
- genpack自体に何らかの修正や拡張があった場合は指示に従い Markdownを更新する
    - Markdownドキュメントには関連gitリポジトリのどの時点のスナップショットを元にドキュメントが書かれたかを（githubのリンクで）残すためのセクションを末尾に記載する。
    - ソースコードの読み取りからドキュメントを起こした場合、設計意図の不明な点があれば質問をし、その回答をADRとして役立てるため脚注としてドキュメントに記載すること。ただし質問への回答に疑問が残る場合は再度質問すること。それでも要領を得ない場合は一旦その件は記載せずに先に進んで良い。
- Markdownを更新したときは対応するHTMLも更新する
- Markdownはオリジナルを日本語とするが、それぞれの .md ファイルに対して .en.md というネーミングで英語版も作成・維持する
- 英語版についてもオリジナルの日本語版と同様HTMLを生成する

## HTML生成の仕組み

HTMLは `generate-page.py` + Jinja2テンプレート (`templates/page.html.j2`) + メタデータ (`docs.json`) で生成する。

### ファイル構成

| ファイル | 役割 |
|---|---|
| `docs.json` | 全ページのメタデータ（slug, タイトル, 説明文） |
| `history.json` | 更新履歴データ（日付、対象slug、日英の説明文） |
| `templates/page.html.j2` | 共通HTMLテンプレート。`<head>` メタタグ、言語リンク、更新履歴、ナビゲーションを生成 |
| `templates/history.html.j2` | 全更新履歴一覧ページのテンプレート |
| `generate-page.py` | 既存HTMLから本文を抽出し、テンプレートで `<head>` とナビゲーションを再生成するスクリプト |

### テンプレートが自動生成する部分

- `<head>` 内のメタタグ一式（OGP, Twitter Card, favicon, CSS）
- 日本語版の英語版リンク (`<p class="lang-link">`)
- 最終更新日 (`<p class="last-updated">`) — `history.json` から該当ページの最新日付を導出
- 更新履歴セクション (`<section class="update-history">`) — `history.json` から該当ページの履歴を抽出して表示
- ページ末尾のナビゲーション (`<nav class="doc-nav">`)

### 本文のマーカーコメント

各HTMLの本文は `<!-- content:begin -->` と `<!-- content:end -->` で囲まれている。`generate-page.py` はこのマーカー間の内容を抽出し、テンプレートで囲み直して書き戻す。

```html
<body class="ja">

<p class="lang-link">...</p>

<!-- content:begin -->
<h1>タイトル</h1>
...本文...
<section class="source-references">...</section>
<!-- content:end -->

<nav class="doc-nav">...</nav>
</body>
```

本文を手動で編集する場合は、マーカーの内側だけを変更すること。マーカーの外側はスクリプトが上書きする。

### 使い方

```bash
# 全ページを再生成
python generate-page.py

# 指定ページのみ再生成
python generate-page.py cli-install

# docs.json にあるが HTML が存在しないスラッグを表示
python generate-page.py --print-missing
```

### 典型的なワークフロー

#### 既存ページの本文を更新する場合

1. Markdownを編集する
2. 対応するHTMLの `<!-- content:begin -->` 〜 `<!-- content:end -->` 間を更新する
3. 英語版 (.en.md, .en.html) も同様に更新する
4. `python generate-page.py {slug}` を実行してメタタグとナビゲーションを再生成する

#### 新しいページを追加する場合

1. `{slug}.md` と `{slug}.en.md` を作成する
2. `{slug}.html` と `{slug}.en.html` を作成する（本文を `<!-- content:begin/end -->` マーカーで囲むこと）
3. `docs.json` にエントリを追加する
4. `python generate-page.py` を実行して全ページのナビゲーションを更新する

#### docs.json のタイトルや説明文を変更した場合

`python generate-page.py` を実行すれば全ページの `<head>` メタタグとナビゲーションに反映される。

#### ドキュメントを更新した場合の履歴管理

1. `history.json` の**先頭**にエントリを追加する（新しい順を維持）
2. エントリには日付、関連するスラッグのリスト、日英の説明文を記載する
3. `python generate-page.py` を実行すれば各ページの更新履歴セクションと `history.html` / `history.en.html` に反映される

`history.json` エントリの例:

```json
{
  "date": "2026-02-28",
  "slugs": ["cli", "index"],
  "description": {
    "ja": "genpack bash の非対話モードサポートを反映",
    "en": "Reflect non-interactive genpack bash support"
  }
}
```
