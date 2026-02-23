# アーティファクトのディレクトリ構造

## 概要

genpack のアーティファクト（イメージ定義）は、`genpack.json5` を中心として複数のサブディレクトリで構成されます。各ディレクトリは特定のビルドフェーズで処理され、Portage の設定からカスタムファイルの配置、ビルドスクリプトの実行まで、イメージの内容を定義します。

## ディレクトリ構造の全体像

```
artifact-name/
├── genpack.json5          # 宣言的イメージ定義 (必須)
├── files/                 # ルートファイルシステムにマージされるファイル
│   ├── build.d/           # ビルド時実行スクリプト (最終イメージには含まれない)
│   ├── etc/               # 設定ファイル
│   ├── usr/               # ライブラリ、バイナリ、systemd ユニット
│   ├── var/               # Web コンテンツ、スプールなど
│   └── root/              # root ホームディレクトリ
├── kernel/                # カーネル設定
│   └── config.d/          # カーネル設定フラグメント
├── savedconfig/           # Portage savedconfig (アーキテクチャ別)
├── patches/               # Portage パッケージパッチ
├── env/                   # Portage パッケージ環境設定
└── overlay/               # ローカル Portage オーバーレイ
```

全てのサブディレクトリは任意です。最小構成では `genpack.json5` のみでアーティファクトを定義できます。

## ビルドフェーズとの対応

genpack のビルドは Lower 層（コンパイル環境）と Upper 層（ランタイム環境）の 2 フェーズで構成されます。各ディレクトリがどのフェーズで処理されるかが重要です。

| ディレクトリ | フェーズ | コピー先 | 目的 |
|---|---|---|---|
| `savedconfig/` | Lower | `/etc/portage/savedconfig/` | パッケージのカスタムビルド設定 |
| `patches/` | Lower | `/etc/portage/patches/` | パッケージへのパッチ適用 |
| `kernel/` | Lower | `/etc/kernel/` | カーネルビルド設定 |
| `env/` | Lower | `/etc/portage/env/` | パッケージ別ビルド環境変数 |
| `overlay/` | Lower | `/var/db/repos/genpack-local-overlay/` | カスタム ebuild |
| `files/` | Upper | `/` (ルート) | カスタムファイルの配置 |

Lower フェーズで処理されるディレクトリはいずれも Portage（パッケージマネージャ）に関連するもので、パッケージのコンパイル時に参照されます。`files/` だけが Upper フェーズで処理され、最終イメージに直接ファイルを配置します。

## files/ — カスタムファイルとビルドスクリプト

`files/` はアーティファクトのカスタマイズにおいて最も重要なディレクトリです。この下に置いたファイルは、Upper 層の構築時にルートファイルシステムへ再帰的にコピーされます。

### コピーの仕組み

Upper フェーズで以下のように処理されます:

```bash
cp -rdv /mnt/host/files/. /
```

- `files/etc/systemd/system/myservice.service` → `/etc/systemd/system/myservice.service`
- `files/usr/bin/myscript` → `/usr/bin/myscript`
- `files/root/.bashrc` → `/root/.bashrc`

シンボリックリンクは保持され、ファイルのパーミッションも維持されます。

### 処理順序

Upper フェーズ内での処理順序は以下の通りです:

1. Lower 層からランタイムファイルを選択的にコピー
2. パッケージスクリプト (genpack-overlay 由来) を実行
3. グループの作成 (`genpack.json5` の `groups`)
4. ユーザーの作成 (`genpack.json5` の `users`)
5. **`files/` ディレクトリの内容をルートにコピー**
6. **`files/build.d/` 内のビルドスクリプトを実行**
7. `setup_commands` を実行
8. サービスの有効化 (`genpack.json5` の `services`)

この順序により、ビルドスクリプトは `files/` からコピーされたファイルやユーザー定義を前提とした処理が可能です。

### files/build.d/ — ビルドスクリプト

`files/build.d/` 内のスクリプトは Upper フェーズで実行され、**最終イメージには含まれません**（SquashFS 生成時に除外されます）。パッケージのインストールやファイルのコピーだけでは対応できないカスタマイズに使います。

#### 実行順序

スクリプトはファイル名の **アルファベット順** に実行されます。実行順序を制御したい場合は数字プレフィックスを使います:

```
build.d/
├── 01-setup-database.sh
├── 02-configure-app.sh
└── 03-download-plugins.sh
```

#### インタプリタの自動判定

スクリプトのインタプリタは拡張子と実行権限から自動的に決定されます:

| 条件 | 実行方法 |
|---|---|
| 実行権限あり | そのまま直接実行（shebang に従う） |
| `.sh` 拡張子（実行権限なし） | `/bin/sh` で実行 |
| `.py` 拡張子（実行権限なし） | `/usr/bin/python` で実行 |
| その他の拡張子（実行権限なし） | エラー |

#### ユーザー別実行

`build.d/` 内にサブディレクトリを作成すると、そのディレクトリ名のユーザーとしてスクリプトが実行されます:

```
build.d/
├── setup-system.sh           # root として実行
└── user/                     # "user" ユーザーとして実行
    ├── setup-dotfiles.sh
    └── install-extensions.py
```

サブディレクトリ名がシステム上に存在するユーザー名と一致する必要があります。`HOME` 環境変数はそのユーザーのホームディレクトリに設定されます。

#### 利用可能な環境変数

| 変数 | 説明 |
|---|---|
| `ARTIFACT` | `genpack.json5` の `name` フィールドの値 |
| `VARIANT` | ビルド中のバリアント名（指定時のみ） |

#### 典型的な用途

**ソフトウェアのダウンロードとインストール:**

```bash
#!/bin/sh
# GitHub リリースからバイナリをダウンロード
ARCH=$(uname -m)
curl -Lo /usr/bin/tool \
  "https://github.com/org/tool/releases/latest/download/tool-${ARCH}"
chmod +x /usr/bin/tool
```

**設定ファイルの編集:**

```bash
#!/bin/sh
# Apache の SSL モジュールを無効化
sed -i 's/-D SSL //' /etc/conf.d/apache2
```

**データベースの初期化:**

```bash
#!/bin/sh
# MySQL のデータベースとユーザーを作成
/etc/init.d/mysql start
mysql -e "CREATE DATABASE IF NOT EXISTS myapp;"
mysql -e "GRANT ALL ON myapp.* TO 'myapp'@'localhost';"
/etc/init.d/mysql stop
```

**ソースからのビルド:**

```bash
#!/bin/sh
# llmnrd をスタティックビルド
cd /tmp
git clone --depth 1 https://github.com/tklauser/llmnrd
cd llmnrd
make LDFLAGS="-static"
cp llmnrd /usr/bin/
cd / && rm -rf /tmp/llmnrd
```

### files/ の典型的な構造

サーバーアーティファクト:

```
files/
├── build.d/
│   ├── apache-enable-php.sh
│   ├── apache-ssl.sh
│   └── setup-app.sh
├── etc/
│   ├── logrotate.d/
│   │   └── myapp
│   └── systemd/system/
│       └── myapp.service
├── usr/
│   ├── bin/
│   │   └── myapp-helper
│   └── lib/systemd/system/
│       └── myapp-backup.timer
└── var/www/
    └── myapp/
```

デスクトップアーティファクト:

```
files/
├── build.d/
│   ├── enable-automatic-login
│   ├── enable-noto-cjk.sh
│   └── enable-pipewire-for-all-users
└── etc/
    ├── polkit-1/rules.d/
    └── xdg/autostart/
```

組み込みアーティファクト:

```
files/
├── build.d/
│   └── setup.sh
└── etc/
    └── sysctl.d/
        └── tuning.conf
```

## kernel/ — カーネル設定

カーネルのビルド設定をカスタマイズするためのディレクトリです。Lower フェーズで `/etc/kernel/` にコピーされ、カーネルパッケージのビルド時に参照されます。

### config.d/ — 設定フラグメント

`kernel/config.d/` 以下に `.config` ファイルを配置すると、カーネル設定にマージされます。特定のカーネルオプションを有効化・無効化するために使います。

```
kernel/
└── config.d/
    └── unset.config
```

`unset.config` の例（stub アーティファクトより、不要機能の無効化）:

```
# CONFIG_HIBERNATION is not set
# CONFIG_SUSPEND is not set
# CONFIG_XEN is not set
# CONFIG_NUMA is not set
# CONFIG_DEBUG_KERNEL is not set
# CONFIG_KEXEC_SIG is not set
```

## savedconfig/ — Portage savedconfig

カーネルなど、ビルド時にカスタム設定ファイルを参照するパッケージのための設定を配置するディレクトリです。Lower フェーズで `/etc/portage/savedconfig/` にコピーされます。

### アーキテクチャ別の構成

savedconfig はアーキテクチャごとにサブディレクトリを分けます。ディレクトリ名は Gentoo の CHOST 値です:

```
savedconfig/
├── aarch64-unknown-linux-gnu/
│   └── sys-kernel/
│       └── gentoo-kernel
├── riscv64-unknown-linux-gnu/
│   └── sys-kernel/
│       └── gentoo-kernel
└── x86_64-pc-linux-gnu/
    └── sys-kernel/
        └── gentoo-kernel
```

これにより、同一アーティファクトから複数アーキテクチャのイメージをビルドする際に、アーキテクチャ固有のカーネル設定を適用できます。カーネルパッケージの USE フラグに `savedconfig` を指定すると Portage がこの設定を参照します。

## patches/ — Portage パッケージパッチ

特定のパッケージにパッチを適用するためのディレクトリです。Lower フェーズで `/etc/portage/patches/` にコピーされ、Portage のユーザーパッチ機能 (`user patches`) を通じて適用されます。

### ディレクトリ構造

```
patches/
└── <category>/<package>/
    └── <patchname>.patch
```

例:

```
patches/
└── dev-libs/weston/
    └── default-output-and-autolaunch-args.patch
```

この場合、`dev-libs/weston` パッケージのビルド時に自動的にパッチが適用されます。バージョン固有のパッチが必要な場合は `<package>-<version>/` でディレクトリ名を指定できます。

## env/ — Portage パッケージ環境設定

特定のパッケージのビルド時に環境変数を設定するためのディレクトリです。Lower フェーズで `/etc/portage/env/` にコピーされます。

### 使い方

設定ファイルを作成し、`genpack.json5` の `env` フィールドからパッケージに割り当てます:

env/torch_cuda.conf:

```bash
CUDA_HOME="/opt/cuda"
MAKEOPTS="-j4"
```

genpack.json5:

```json5
{
  env: {
    "sci-libs/pytorch": "torch_cuda.conf"
  }
}
```

## overlay/ — ローカル Portage オーバーレイ

公式リポジトリや genpack-overlay にないカスタムパッケージ（ebuild）を追加するためのディレクトリです。Lower フェーズで `/var/db/repos/genpack-local-overlay/` にコピーされ、repos.conf やメタデータが自動生成されます。

### ディレクトリ構造

標準的な Gentoo オーバーレイの構造に従います:

```
overlay/
└── <category>/<package>/
    ├── Manifest
    └── <package>-<version>.ebuild
```

例:

```
overlay/
└── media-libs/virglrenderer/
    ├── Manifest
    └── virglrenderer-9999.ebuild
```

genpack が自動的に `metadata/layout.conf`、`profiles/repo_name`、`repos.conf` を生成するため、これらのファイルを手動で用意する必要はありません。

## リビルドのトリガー

Lower 層の再ビルドが必要かどうかは、以下のファイル・ディレクトリの更新タイムスタンプで判定されます:

- `genpack.json5`（または `genpack.json`）
- `savedconfig/`
- `patches/`
- `kernel/`
- `env/`
- `overlay/`

**`files/` ディレクトリは Lower 層の再ビルドトリガーに含まれません。** `files/` は Upper フェーズでのみ処理されるため、`files/` の変更は Upper 層の再ビルドで反映されます。

## アーカイブ

`genpack archive` コマンドを実行すると、`genpack.json5` と全てのサブディレクトリ（`files/`, `savedconfig/`, `patches/`, `kernel/`, `env/`, `overlay/`）を含む `genpack-<name>.tar.gz` が生成されます。これによりアーティファクト定義を配布できます。

## ソースリファレンス

このドキュメントは以下のリポジトリのスナップショットに基づいて作成されました:

- [wbrxcorp/genpack @ b71eb6b](https://github.com/wbrxcorp/genpack/tree/b71eb6b025f7cd1ec5ae9220a21f2229c274c7bd)
- [wbrxcorp/genpack-overlay @ 45a7e1e](https://github.com/wbrxcorp/genpack-overlay/tree/45a7e1e7440104f6592150261858c4ddd498d15b)
