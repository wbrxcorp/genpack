# genpack/genpack-progs パッケージ

## 概要

`genpack/genpack-progs` は、genpack イメージのビルドプロセスで使用されるサポートツール群をまとめたパッケージである。すべての genpack プロファイルで暗黙的に含まれ、イメージビルド時のファイル収集、依存関係解決、メタデータ生成、外部リソースのダウンロードなどを担う。

各ツールはかつて外部リポジトリ (genpack-progs) から取得していたが、現在は ebuild の `files/` ディレクトリにインライン化されている。

## インストールされるコマンド一覧

### ビルドコアツール

イメージビルドの中核を担い、genpack 本体から直接呼び出されるツール群。

| コマンド | 説明 |
|---|---|
| `list-pkg-files` | Portage パッケージの依存関係を再帰的に解決し、イメージに含めるファイル一覧を生成する |
| `exec-package-scripts-and-generate-metadata` | パッケージ固有のポストインストールスクリプトを実行し、`/.genpack/` 以下にメタデータを生成する |
| `execute-artifact-build-scripts` | アーティファクト固有のビルドスクリプト (`/build`, `/build.d/`) を実行する |
| `recursive-touch` | ELF バイナリとスクリプトの依存関係を再帰的に解析し、atime を更新する。initramfs 用ファイルリストの出力にも使用 |
| `rebuild-kernel-modules-if-necessary` | カーネルモジュールの再ビルドが必要な場合に `emerge @module-rebuild` を実行する |

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
| `net-misc/netkit-telnetd` | Telnet デーモン |
| `app-misc/figlet` | ASCII アートテキスト生成 |
| `sys-fs/squashfs-tools[lz4,lzma,lzo,xattr,zstd]` | SquashFS イメージの作成・展開 |
| `app-admin/eclean-kernel` | 古いカーネルの自動削除 |

## 各コマンドの詳細

### list-pkg-files

genpack イメージに含めるファイルを決定するコアツール。Portage の Python API を使用して `@profile`、`@genpack-runtime`（およびオプションで `@genpack-devel`）パッケージセットの依存関係を再帰的に解決し、対象ファイルの一覧を出力する。

- `genpack-ignore` eclass を持つパッケージはスキップされる
- 非 devel モードでは man ページ、ドキュメント、ヘッダファイル等を除外
- パッケージ依存関係グラフを `/.genpack/_pkgs_with_deps.pkl` に保存し、後続の `exec-package-scripts-and-generate-metadata` で再利用する

### exec-package-scripts-and-generate-metadata

`list-pkg-files` が保存した依存関係データを読み込み、パッケージごとのポストインストールスクリプト (`/usr/lib/genpack/package-scripts/<pkgname>/`) を実行する。その後、`/.genpack/` ディレクトリに以下のメタデータファイルを生成する：

- `arch` — システムアーキテクチャ
- `profile` — genpack プロファイル名
- `artifact` — アーティファクト名
- `variant` — バリアント名
- `timestamp.commit` — Portage ツリーのコミットタイムスタンプ
- `packages` — インストール済みパッケージ一覧（USE フラグ、説明等を含む）

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

## genpack-ignore eclass

`genpack-progs` の ebuild は `genpack-ignore` eclass を継承している。これにより、`list-pkg-files` がイメージに含めるファイルを収集する際にこのパッケージ自体はスキップされる。ビルドツールはビルド環境（lower レイヤー）で使用されるが、最終的なランタイムイメージ（upper レイヤー）には含まれない。

## ソースリファレンス

- [genpack/genpack-progs ebuild](https://github.com/wbrxcorp/genpack-overlay/tree/7bc4ad0/genpack/genpack-progs) (7bc4ad0)
