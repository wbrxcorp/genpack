# genpack CLI リファレンス

## 概要

`genpack` は genpack ツールチェーンのメインコマンドです。カレントディレクトリの `genpack.json5`（または `genpack.json`）を読み取り、サブコマンドに応じた処理を実行します。

```bash
genpack [グローバルオプション] <サブコマンド>
```

## グローバルオプション

全サブコマンドに共通のオプションです。

| オプション | 型 | デフォルト | 説明 |
|---|---|---|---|
| `--debug` | フラグ | false | DEBUG レベルのログを表示 |
| `--overlay-override <DIR>` | パス | (なし) | genpack-overlay のローカルオーバーライドディレクトリ |
| `--independent-binpkgs` | フラグ | false | アーティファクト固有のバイナリパッケージキャッシュを使用 |
| `--deep-depclean` | フラグ | false | ビルド依存を含む深いクリーンアップを実行 |
| `--compression <ALG>` | 選択 | (設定に従う) | SquashFS 圧縮: `gzip`, `xz`, `lzo`, `none` |
| `--devel` | フラグ | false | 開発イメージの生成 |
| `--variant <NAME>` | 文字列 | (設定に従う) | 使用するバリアント名 |

### --overlay-override

genpack-overlay のリポジトリ (通常は GitHub から自動取得) をローカルディレクトリで上書きします。genpack-overlay 自体の開発時に使用します。

### --independent-binpkgs

デフォルトでは `~/.cache/genpack/{arch}/binpkgs/` にある共有バイナリパッケージキャッシュを使用しますが、このオプションを指定するとアーティファクトごとに独立したキャッシュを使います。USE フラグが大きく異なるアーティファクト間での干渉を避けるために使用します。

## サブコマンド

### build

フルビルドパイプライン (lower → upper → pack) を実行します。

```bash
genpack build
```

サブコマンドを省略した場合のデフォルト動作です。以下の 3 フェーズを順に実行します:

1. **Lower 層のビルド**: stage3 + Portage でパッケージをコンパイル
2. **Upper 層のビルド**: ランタイムファイルの抽出とカスタマイズ
3. **パック**: SquashFS 圧縮

初回実行時に `.gitignore` と `.vscode/settings.json` がなければ自動生成します。

### lower

Lower 層（ビルド環境）を構築します。

```bash
genpack lower
```

処理の流れ:

1. `work/{arch}/` ディレクトリを作成
2. Gentoo stage3 tarball をダウンロード（キャッシュあり）
3. Portage スナップショットをダウンロード（キャッシュあり）
4. ext4 ファイルシステムイメージ (`lower.img`) を作成
5. stage3 と Portage を展開
6. genpack-overlay を同期
7. Portage プロファイルを設定
8. `genpack.json5` の設定（USE フラグ、キーワード、ライセンス、マスク）を適用
9. 循環依存の解決（`circulardep_breaker` がある場合）
10. 全パッケージを emerge
11. カーネルモジュールの再ビルド
12. depclean, eclean によるクリーンアップ
13. Upper 層用のファイルリスト (`lower.files`) を生成

Lower 層の再ビルドが必要かどうかは `genpack.json5` と Portage 関連サブディレクトリ（`savedconfig/`, `patches/`, `kernel/`, `env/`, `overlay/`）のタイムスタンプで判定されます。

### upper

Upper 層（ランタイム環境）を構築します。

```bash
genpack upper
```

**前提条件**: `lower` の実行が完了していること。

処理の流れ:

1. Upper 層用の ext4 イメージ (`upper.img`) を作成
2. Lower 層から `lower.files` に記載されたファイルをコピー
3. パッケージスクリプトを実行
4. グループとユーザーを作成
5. `files/` ディレクトリの内容をルートにコピー
6. `files/build.d/` のビルドスクリプトを実行
7. `setup_commands` を実行
8. systemd サービスを有効化

### pack

Upper 層から SquashFS イメージを生成します。

```bash
genpack pack
```

**前提条件**: `lower` と `upper` の両方が完了していること。

処理:

1. Upper 層を SquashFS に圧縮
2. `build.d/`、ログファイル、一時ファイルを除外
3. EFI ファイルが存在する場合は EFI スーパーフロッピーイメージも生成

**出力ファイル**:

| ファイル | 条件 |
|---|---|
| `{name}-{arch}.squashfs` | 常に生成 |
| `{name}-{arch}.img` | EFI ブートローダーが含まれる場合 |

**圧縮方式の詳細**:

| 方式 | mksquashfs オプション | 特徴 |
|---|---|---|
| `gzip` | `-Xcompression-level 1` | デフォルト。高速 |
| `xz` | `-comp xz -b 1M` | 最小サイズ。時間がかかる |
| `lzo` | `-comp lzo` | 高速。gzip より低圧縮 |
| `none` | `-no-compression` | 無圧縮 |

### bash

Lower 層で対話シェルを開くか、指定したコマンドを実行します。

```bash
genpack bash [command...]
```

コマンドを指定しない場合、systemd-nspawn コンテナ内で bash シェルが起動し、Lower 層のファイルシステムを直接操作・確認できます。パッケージのインストール状態の確認やデバッグに使用します。

コマンドを指定した場合、そのコマンドを Lower 層の nspawn コンテナ内で非対話的に実行します。コマンドが失敗した場合はエラーで終了します。

### upper-bash

Upper 層のオーバーレイ上で対話的デバッグシェルを開きます。

```bash
genpack upper-bash
```

**前提条件**: `upper` の実行が完了していること。

最終イメージの内容を確認・デバッグするために使用します。

### archive

アーティファクト定義の配布用アーカイブを作成します。

```bash
genpack archive
```

`genpack.json5` と全サブディレクトリ（`files/`, `savedconfig/`, `patches/`, `kernel/`, `env/`, `overlay/`）を含む `genpack-{name}.tar.gz` を生成します。

## ワークディレクトリの構造

`genpack` は `work/` ディレクトリ以下にビルド成果物とキャッシュを配置します。

```
work/
├── .dirlock                    # 排他ロックファイル
├── portage.tar.xz              # Portage スナップショット (キャッシュ)
├── portage.tar.xz.headers      # キャッシュ検証用ヘッダ
└── {arch}/
    ├── lower.img               # Lower 層ファイルシステム (デフォルト 128 GiB)
    ├── lower.files             # Upper 層にコピーするファイルリスト
    ├── upper.img               # Upper 層ファイルシステム (デフォルト 20 GiB)
    ├── stage3.tar.xz           # stage3 tarball (キャッシュ)
    └── stage3.tar.xz.headers   # キャッシュ検証用ヘッダ
```

## キャッシュ

### ダウンロードキャッシュ

stage3 と Portage スナップショットは `work/` 以下にキャッシュされます。HTTP ヘッダ（`Last-Modified`, `ETag`, `Content-Length`）で検証し、変更がなければ再ダウンロードしません。

### バイナリパッケージキャッシュ

デフォルトでは `~/.cache/genpack/{arch}/binpkgs/` にバイナリパッケージが共有キャッシュとして保存されます。同じアーキテクチャの異なるアーティファクト間でコンパイル済みパッケージを再利用できます。

`--independent-binpkgs` を指定すると、この共有キャッシュの代わりにアーティファクトごとの独立したキャッシュを使用します。

### genpack-overlay キャッシュ

`~/.cache/genpack/overlay/` に genpack-overlay の git リポジトリがキャッシュされます。

## 環境変数

genpack 自体が参照する環境変数はありませんが、ビルドプロセス中に以下の環境変数がコンテナ内で設定されます:

| 変数 | 設定タイミング | 値 |
|---|---|---|
| `ARTIFACT` | Upper 層ビルド時 | `genpack.json5` の `name` |
| `VARIANT` | Upper 層ビルド時 | バリアント名（指定時のみ） |

## デフォルト値

| 設定 | 値 |
|---|---|
| Lower 層イメージサイズ | 128 GiB |
| Upper 層イメージサイズ | 20 GiB |
| genpack-overlay リポジトリ | `https://github.com/wbrxcorp/genpack-overlay.git` |
| Gentoo ミラー | `http://ftp.iij.ad.jp/pub/linux/gentoo/` |
| デフォルト圧縮 | gzip |

## 典型的な使い方

```bash
# フルビルド
genpack build

# フルビルド (xz 圧縮)
genpack --compression xz build

# バリアントを指定してビルド
genpack --variant cuda build

# ステップごとのビルド
genpack lower
genpack upper
genpack pack

# デバッグ (Lower 層のシェル)
genpack bash

# Lower 層内でコマンドを実行
genpack bash emerge --info

# デバッグ (Upper 層のシェル)
genpack upper-bash

# デバッグ (詳細ログ)
genpack --debug build

# genpack-overlay のローカル版でビルド
genpack --overlay-override ~/projects/genpack-overlay build

# アーカイブ作成
genpack archive
```

## ソースリファレンス

このドキュメントは以下のリポジトリのスナップショットに基づいて作成されました:

- [wbrxcorp/genpack @ 6aa1e82](https://github.com/wbrxcorp/genpack/tree/6aa1e8244e53499cacb3b15e78ba215c3a6a23a9)
