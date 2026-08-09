# genpack/genpack-progs パッケージ

## 概要

`genpack/genpack-progs` は、genpack イメージのビルドプロセスで使用されるサポートツール群をまとめたパッケージである。すべての genpack プロファイルで暗黙的に含まれ、イメージビルド時のファイル収集、依存関係解決、メタデータ生成、外部リソースのダウンロードなどを担う。

各ツールはかつて外部リポジトリ (genpack-progs) から取得していたが、現在は ebuild の `files/` ディレクトリにインライン化されている。

## インストールされるコマンド一覧

### ビルドコアツール

イメージビルドの中核を担い、genpack 本体から直接呼び出されるツール群。

| コマンド | 説明 |
|---|---|
| `genpack-package-scripts` | パッケージ固有のポストインストールスクリプトを実行する |
| `genpack-generate-metadata` | `/.genpack/` 以下にメタデータを生成する。イメージへ書き込む処理がすべて終わった後に実行される |
| `genpack-copyup` | overlayfs の copy-up を利用してランタイムパッケージのファイルを Upper 層へ転送する |
| `execute-artifact-build-scripts` | アーティファクト固有のビルドスクリプト (`/build`, `/build.d/`) を実行する |
| `recursive-touch` | ELF バイナリとスクリプトの依存関係を再帰的に解析し、atime を更新する。initramfs 用ファイルリストの出力にも使用 |
| `rebuild-kernel-modules-if-necessary` | カーネルモジュールの再ビルドが必要な場合に `emerge @module-rebuild` を実行する |

### 後方互換ツール（旧 genpack 向け）

| コマンド | 説明 |
|---|---|
| `list-pkg-files` | ランタイムパッケージのファイル一覧を生成する（genpack `a6ea03c` 以前が使用） |
| `exec-package-scripts-and-generate-metadata` | パッケージスクリプト実行とメタデータ生成を行う（genpack `a6ea03c` 以前が使用） |
| `genpack-exec-package-scripts` | パッケージスクリプト実行とメタデータ生成を行う（メタデータ生成の分離前の genpack が使用） |

いずれも現行の genpack は呼び出さない。それぞれを最後に使っていた世代の genpack が使われなくなった時点で削除する候補。

### ダウンロードユーティリティ

ビルド中に外部リソースを取得するためのツール群。

| コマンド | 説明 |
|---|---|
| `download` | URL からファイルをダウンロードし標準出力に出力する。`/var/cache/download` にキャッシュを保持 |
| `get-rpm-download-url` | YUM/DNF リポジトリから RPM パッケージのダウンロード URL を解決する |
| `get-github-download-url` | GitHub リリースアセットのダウンロード URL を取得する |

### メンテナンスツール

ビルド環境の保守に使用するツール群。

| コマンド | 説明 |
|---|---|
| `unmerge-masked-packages` | マスクされたパッケージを検出・アンマージし、@world を再ビルドする |
| `remove-binpkg` | Portage バイナリパッケージをアトム指定で削除する。デフォルトは dry-run |
| `findelf` | ディレクトリツリー内の ELF バイナリを検索する |
| `with-mysql` | 一時的な MySQL サーバーを起動してコマンドを実行し、終了後にシャットダウンする |

## ランタイム依存パッケージ

| パッケージ | 説明 |
|---|---|
| `sys-apps/util-linux` | 基本的なシステムユーティリティ |
| `app-portage/gentoolkit` | Portage 管理ツール (`equery` 等) |
| `dev-util/pkgdev` | Gentoo パッケージ開発ツール |
| `app-arch/zip` | ZIP アーカイバ |
| `dev-debug/strace` | システムコールトレーサ |
| `net-analyzer/tcpdump` | ネットワークパケットキャプチャ |
| `app-editors/nano` | テキストエディタ |
| `app-editors/vim` | テキストエディタ |
| `app-misc/figlet` | ASCII アートテキスト生成 |
| `sys-fs/squashfs-tools[lz4,lzma,lzo,xattr,zstd]` | SquashFS イメージの作成・展開 |
| `app-admin/eclean-kernel` | 古いカーネルの自動削除 |
| `dev-python/tqdm` | プログレスバーライブラリ（`genpack-copyup` で使用） |

## 各コマンドの詳細

### genpack-package-scripts

Portage の Python API を使用して `@profile`、`@genpack-runtime`（およびオプションで `@genpack-devel`）パッケージセットの依存関係を再帰的に解決し、パッケージごとのポストインストールスクリプト (`/usr/lib/genpack/package-scripts/<pkgname>/`) を実行する。

- `genpack-ignore` eclass を持つパッケージはスキップされる
- 非 devel モードでは man ページ、ドキュメント、ヘッダファイル等を除外
- 共有ライブラリモジュール `genpack_pkg` に依存する

アーティファクトのビルドスクリプトより**前**に実行される必要がある。メタデータ生成を担わないのはこのためで、そちらは `genpack-generate-metadata` が最後に行う。

### genpack-generate-metadata

`/.genpack/` ディレクトリにメタデータを生成する。

**アーティファクトの `files/` マージとビルドスクリプトの後に実行される。** ここで書くのは完成したイメージの説明だからである。`files/` を既存イメージの rootfs から組んだ場合にそのイメージの `/.genpack/` を持ち込んでしまう事故も、最後に生成することで打ち消される。パッケージ一覧は Upper フェーズで runtime set やプロファイルが変化した場合にそれを反映する。

なお `packages` は `@profile` / `@genpack-runtime` を起点とした列挙なので、ビルドスクリプトが `emerge` で追加したパッケージは（set を書き換えない限り）生成タイミングに関わらず載らない。詳細は [ADR-0007](../adr/0007-record-artifact-commit-id-in-image.md)。

`/.genpack/` に生成されるメタデータ：

- `arch` — システムアーキテクチャ
- `profile` — genpack プロファイル名
- `artifact` — アーティファクト名
- `variant` — バリアント名
- `commit-id` — アーティファクト定義の git コミット ID（`include_commit_id` 指定時のみ）
- `timestamp.commit` — Portage ツリーのコミットタイムスタンプ
- `packages` — インストール済みパッケージ一覧（USE フラグ、説明等を含む）

`profile`、`artifact`、`variant`、`commit-id` は genpack がホスト側から nspawn に渡す環境変数（`PROFILE`、`ARTIFACT`、`VARIANT`、`COMMIT_ID`）に由来し、渡されなかったものは単に生成されない。`commit-id` と `timestamp.commit` はどちらもコミット ID を含むが別物で、前者はアーティファクト定義、後者は Portage ツリーのものである。

`banner`（`genpack/base[banner]` 使用時のログインバナー）はここでは生成されない。パッケージスクリプトが生成するものなので、アーティファクトが `files/.genpack/banner` を置けば上書きできる。`/.genpack/` はアーティファクトが自前のファイル（バージョン情報など）を置く場所としても使われており、上記の genpack 生成分と共存する。

### genpack-copyup

overlayfs の copy-up 機構を利用して、ランタイムパッケージのファイルを Upper 層へ転送する。`genpack_pkg` モジュールを使用してランタイムパッケージとそのファイル一覧を列挙し、各ファイルに対して `utime()` を呼び出すことでカーネルの copy-up をトリガーする。

- `mount --bind / <raw_root>` で Lower 層のファイルシステムに直接アクセスし、nspawn が仮想化する `/dev` 等を正確に処理する
- stage3 ブートストラップで作成されたがパッケージに所有されないトップレベルディレクトリ（`/bin`, `/sbin`, `/lib`, `/lib64` 等）も明示的に含める
- `/dev/` 以下は再帰的にすべて copy-up 対象とする
- `tqdm` でプログレスバーを表示する

### execute-artifact-build-scripts

アーティファクトのルートにある `/build` スクリプトおよび `/build.d/` ディレクトリ配下のスクリプトを実行する。

- `/build` が存在すれば root として実行
- `/build.d/` 内のファイルはソート順に root として実行
- `/build.d/` 内のサブディレクトリはディレクトリ名のユーザーとして配下のスクリプトを実行
- 非実行可能ファイルは拡張子からインタプリタを自動検出（`.sh` → `/bin/sh`、`.py` → `/usr/bin/python`）

### recursive-touch

ELF バイナリのヘッダ（マジックナンバー `\x7fELF`）を検査し、`lddtree` を使って共有ライブラリの依存関係を再帰的に解決する。スクリプトの場合はシバン行からインタプリタを検出する。

- デフォルトでは対象ファイルの atime を更新（後続の「最近アクセスされたファイルのみ収集」フェーズで使用）
- `--print-for-initramfs` オプションで initramfs に含めるファイル一覧を出力

### download

`curl` をバックエンドとして URL からファイルをダウンロードする。ダウンロード結果は `/var/cache/download` に URL の SHA1 ハッシュをキーとしてキャッシュされ、再ダウンロード時には HTTP の条件付きリクエスト (`-z` フラグ) で変更の有無を確認する。

### get-rpm-download-url

YUM/DNF リポジトリの `repomd.xml` を解析して `primary.xml` メタデータを取得し、指定パッケージの最新版ダウンロード URL を返す。gzip、bz2、xz 圧縮に対応し、リポジトリメタデータのキャッシュ（デフォルト TTL: 1時間）を保持する。

### get-github-download-url

GitHub API を使用して最新リリースのアセットを取得し、正規表現パターンに一致するアセットのダウンロード URL を返す。特殊キーワード `@tarball`（ソース tarball）と `@zipball`（ソース zip）にも対応する。

### with-mysql

一時的な MySQL サーバーを起動し、指定されたコマンドを実行した後にシャットダウンするラッパーツール。初回起動時にはデータディレクトリの初期化とタイムゾーンデータのロードを行う。ネットワーク接続は無効化され、ローカルソケットのみで通信する。ビルド時のデータベースマイグレーション実行に使用される。

### list-pkg-files（後方互換）

ランタイムパッケージのファイル一覧を生成し、パッケージ依存関係グラフを `/.genpack/_pkgs_with_deps.pkl` に保存する。genpack `a6ea03c`（2026-05-19、Upper 層の転送を overlayfs copy-up へ切り替えたコミット）で `genpack-copyup` に置き換えられ、以降使われていない。

### exec-package-scripts-and-generate-metadata（後方互換）

`list-pkg-files` が保存した依存関係データを読み込み、パッケージスクリプトの実行とメタデータ生成を行う。`list-pkg-files` と対で使われるもので、同じく genpack `a6ea03c` 以降使われていない。

### genpack-exec-package-scripts（後方互換）

パッケージスクリプトの実行とメタデータ生成を 1 つで行っていたツール。`genpack-package-scripts` と `genpack-generate-metadata` への分離前の genpack が使用する。生成したメタデータをその後の `files/` マージやビルドスクリプトが上書きできてしまうのが分離の理由。現行の genpack は使用しない。

## genpack-ignore eclass

`genpack-progs` の ebuild は `genpack-ignore` eclass を継承している。これにより、`genpack-exec-package-scripts` および `genpack-copyup` がイメージに含めるファイルを収集する際にこのパッケージ自体はスキップされる。ビルドツールはビルド環境（lower レイヤー）で使用されるが、最終的なランタイムイメージ（upper レイヤー）には含まれない。

## ソースリファレンス

- [genpack/genpack-progs ebuild](https://github.com/wbrxcorp/genpack-overlay/tree/b0abbd7/genpack/genpack-progs) (b0abbd7)
