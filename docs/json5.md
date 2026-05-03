# genpack.json5 仕様リファレンス

## 概要

`genpack.json5` は genpack でビルドするシステムイメージの宣言的な定義ファイルです。各アーティファクトのルートディレクトリに配置し、パッケージ構成、Portage の設定、ユーザー・サービス定義、圧縮方式などを 1 ファイルに集約します。

フォーマットは [JSON5](https://json5.org/) で、コメントや末尾カンマなどが使えます。`genpack.json5` が存在しない場合は `genpack.json` にフォールバックしますが、両方が存在するとエラーになります。

## 最小構成

```json5
{
  packages: ["genpack/paravirt"]
}
```

`name` を省略するとディレクトリ名が自動的に使用されます（警告が出ます）。

## フィールド一覧

### 基本フィールド

#### name

- **型**: string
- **デフォルト**: カレントディレクトリのベースネーム
- **説明**: アーティファクトの名前。ビルド時に環境変数 `ARTIFACT` として scripts に渡され、出力ファイル名のデフォルトにも使われます。

#### profile

- **型**: string | null
- **デフォルト**: null
- **説明**: genpack-overlay のプロファイル名。内部的に `genpack-overlay:genpack/{arch}/` に連結されて Portage プロファイルとして設定されます。

代表的なプロファイル:

| プロファイル | 用途 |
|---|---|
| `paravirt` | QEMU/KVM 仮想マシン向け（virtio, ゲストエージェント） |
| `baremetal` | 物理マシン向け（BIOS/UEFI, デバイスドライバ） |
| `gnome/baremetal` | 物理マシン + GNOME デスクトップ |
| `weston/paravirt` | 仮想マシン + Wayland (Weston) |

#### outfile

- **型**: string
- **デフォルト**: `{name}-{arch}.squashfs`
- **説明**: 出力ファイル名。CLI の `--outfile` 引数でも上書き可能です。

#### compression

- **型**: string
- **デフォルト**: `"gzip"`
- **許容値**: `"gzip"`, `"xz"`, `"lzo"`, `"none"`
- **説明**: SquashFS 圧縮アルゴリズム。`"xz"` はサイズが最小になりますが圧縮に時間がかかります。CLI の `--compression` 引数でも上書き可能です。

### パッケージ関連

#### packages

- **型**: string[]
- **デフォルト**: `[]`
- **説明**: インストールするパッケージのリスト。Gentoo のパッケージアトム形式 (`category/name`) で指定します。

`-` プレフィックスを付けると、プロファイルやバリアントのマージ時にリストから除外できます:

```json5
{
  packages: [
    "genpack/paravirt",
    "app-misc/screen",
    "-app-misc/unwanted-package"  // マージ元から除外
  ]
}
```

#### buildtime_packages

- **型**: string[]
- **デフォルト**: `[]`
- **説明**: ビルド時のみ必要なパッケージ。Lower 層にはインストールされますが、Upper 層（最終イメージ）にはコピーされません。Go や CMake など、コンパイルに必要だが実行時には不要なパッケージに使います。

```json5
{
  buildtime_packages: ["dev-lang/go", "dev-build/cmake"]
}
```

#### binpkg_excludes

- **型**: string | string[]
- **デフォルト**: `[]`
- **説明**: バイナリパッケージキャッシュ (usepkg/buildpkg) から除外するパッケージ。カーネルなど、設定が異なるためバイナリキャッシュの共有が不適切なパッケージに使います。

### Portage 設定

#### use

- **型**: object
- **デフォルト**: `{}`
- **説明**: パッケージ別の USE フラグ設定。`package.use` に相当します。

キーはパッケージアトム（`*/*` でグローバル指定可）、値は文字列（スペース区切り）またはリストです:

```json5
{
  use: {
    "dev-lang/php": "+mysql +curl +gd +xml +zip",
    "media-libs/mesa": "wayland VIDEO_CARDS: virgl",
    "*/*": "python_targets_python3_12"
  }
}
```

`CPU_FLAGS_X86:`, `VIDEO_CARDS:`, `AMDGPU_TARGETS:`, `APACHE2_MODULES:` などの USE_EXPAND 変数もこのフィールドで設定します。

#### accept_keywords

- **型**: object
- **デフォルト**: `{}`
- **説明**: パッケージ別の ACCEPT_KEYWORDS 設定。`package.accept_keywords` に相当します。

値が `null` の場合はキーワードなし（テスティング版を受け入れる標準的なパターン）:

```json5
{
  accept_keywords: {
    "dev-util/debootstrap": null,      // ~arch を受け入れ
    "app-misc/package": "~amd64",      // 特定キーワード
    "app-misc/other": ["~amd64", "**"] // 複数キーワード
  }
}
```

#### mask

- **型**: string[]
- **デフォルト**: `[]`
- **説明**: パッケージマスク。`package.mask` に相当します。特定バージョン以上をブロックするなどの用途に使います。

```json5
{
  mask: [">=dev-db/mysql-8"]
}
```

#### license

- **型**: object
- **デフォルト**: `{}`
- **説明**: パッケージ別のライセンス受け入れ設定。`package.license` に相当します。

```json5
{
  license: {
    "sys-kernel/linux-firmware": "linux-fw-redistributable",
    "www-client/google-chrome": "google-chrome"
  }
}
```

#### env

- **型**: object
- **デフォルト**: `{}`
- **説明**: パッケージ別の環境設定。`package.env` に相当します。Portage の `env/` ディレクトリ内の設定ファイル名を指定します。

```json5
{
  env: {
    "sci-libs/pytorch": "torch_cuda.conf"
  }
}
```

### ユーザーとグループ

#### users

- **型**: (string | object)[]
- **デフォルト**: `[]`
- **説明**: Upper 層で作成するユーザー。文字列（ユーザー名のみ）またはオブジェクトで指定します。

```json5
{
  users: [
    "simpleuser",
    {
      name: "advanceduser",
      uid: 1000,
      home: "/home/advanceduser",
      shell: "/bin/bash",
      initial_group: "users",
      additional_groups: ["wheel", "video", "audio"],
      create_home: true,
      empty_password: true
    }
  ]
}
```

オブジェクト形式のプロパティ:

| プロパティ | 型 | デフォルト | 説明 |
|---|---|---|---|
| `name` | string | (必須) | ユーザー名 |
| `uid` | integer | (自動) | ユーザー ID |
| `comment` | string | | GECOS フィールド |
| `home` | string | | ホームディレクトリ |
| `shell` | string | | ログインシェル |
| `initial_group` | string | | プライマリグループ |
| `additional_groups` | string \| string[] | | 追加グループ |
| `create_home` | boolean | true | ホームディレクトリを作成するか |
| `empty_password` | boolean | false | 空パスワードを許可するか |

#### groups

- **型**: (string | object)[]
- **デフォルト**: `[]`
- **説明**: Upper 層で作成するグループ。

```json5
{
  groups: [
    "customgroup",
    { name: "groupwithgid", gid: 1002 }
  ]
}
```

### サービスとセットアップ

#### services

- **型**: string[]
- **デフォルト**: `[]`
- **説明**: 有効化する systemd サービス。テンプレートユニットやタイマーユニットも指定可能です。

```json5
{
  services: [
    "sshd",
    "apache2",
    "fstrim.timer",
    "vsock-proxy@80.socket"
  ]
}
```

#### setup_commands

- **型**: string[]
- **デフォルト**: `[]`
- **説明**: Upper 層の構築後に nspawn コンテナ内で実行されるシェルコマンド。ファイルの編集、権限の変更など、パッケージインストールやファイルコピーだけでは対応できないカスタマイズに使います。

```json5
{
  setup_commands: [
    "sed -i 's/-D SSL //' /etc/conf.d/apache2",
    "mkdir -p /var/www/localhost/htdocs"
  ]
}
```

### ビルド設定

#### lower-layer-capacity

- **型**: integer (GiB 単位)
- **デフォルト**: 128
- **説明**: Lower 層のディスクイメージサイズ（GiB）。パッケージ数が非常に多い場合に増やします。

#### independent_binpkgs

- **型**: boolean
- **デフォルト**: false
- **説明**: 共有バイナリパッケージキャッシュの代わりに、アーティファクト固有のバイナリパッケージを使用するかどうか。CLI の `--independent-binpkgs` でも指定可能です。

#### circulardep_breaker

- **型**: object
- **デフォルト**: (なし)
- **説明**: Gentoo の循環依存を解決するための特殊設定。一部のパッケージ（freetype ↔ harfbuzz など）は互いに依存しているため、最初に制限された USE フラグでインストールしてから通常ビルドを行います。

```json5
{
  circulardep_breaker: {
    packages: ["media-libs/freetype", "media-libs/harfbuzz"],
    use: "-truetype -harfbuzz"
  }
}
```

`packages` に指定したパッケージが `use` で指定した USE フラグ付きで先にインストールされ、その後の通常ビルドで正しいフラグで再ビルドされます。

### 条件付き設定

#### arch

- **型**: object
- **デフォルト**: `{}`
- **説明**: アーキテクチャ固有の設定オーバーライド。キーはアーキテクチャ名（`|` で複数指定可）、値はマージされるフィールドのオブジェクトです。

現在のマシンのアーキテクチャ (`uname -m`) と一致するキーの設定のみがマージされます。

```json5
{
  arch: {
    x86_64: {
      packages: ["app-misc/x86-specific"],
      use: {
        "media-video/ffmpeg": "CPU_FLAGS_X86: avx avx2 sse4_2"
      }
    },
    aarch64: {
      accept_keywords: {
        "app-emulation/qemu-guest-agent": null
      }
    }
  }
}
```

マージ可能なフィールド: `packages`, `buildtime_packages`, `accept_keywords`, `use`, `mask`, `license`, `env`, `binpkg_excludes`, `setup_commands`, `services`

#### variants

- **型**: object
- **デフォルト**: `{}`
- **説明**: 名前付きバリアント設定。同一アーティファクトから異なる構成のイメージを生成するために使います。CLI の `--variant` 引数で選択します。

```json5
{
  packages: ["genpack/gnome"],
  services: ["gdm"],
  variants: {
    paravirt: {
      // packages は上位定義とマージされる
      packages: ["-x11-drivers/nvidia-drivers"],
      use: {
        "media-libs/mesa": "VIDEO_CARDS: virgl"
      }
    },
    cuda: {
      packages: ["x11-drivers/nvidia-drivers"],
      use: {
        "sci-libs/pytorch": "CUDA_TARGETS: sm_89"
      }
    }
  }
}
```

バリアント内では `name`, `profile`, `outfile` を含む大半のトップレベルフィールドをオーバーライドまたはマージできます。さらにバリアント内に `arch` を含めることもできます。

#### default_variant

- **型**: string | null
- **デフォルト**: null
- **説明**: CLI で `--variant` を指定しなかった場合に使用されるデフォルトバリアント名。指定されたバリアントが `variants` に存在しない場合はエラーになります。

## マージの仕組み

genpack.json5 の設定は以下の順序でマージされます:

1. **ベース設定**: トップレベルのフィールド
2. **アーキテクチャ固有**: `arch` 内の該当アーキテクチャの設定をマージ
3. **バリアント**: `variants` 内の選択されたバリアントの設定をマージ（バリアント内の `arch` も処理される）

マージ時のリスト型フィールドの動作:
- `packages`: `-` プレフィックス付きの要素は既存リストから除外。それ以外は重複なく追加
- `buildtime_packages`, `mask`, `services`: 重複なく追加
- `accept_keywords`, `use`, `license`, `env`: キー単位で上書き

## 非推奨フィールド名

以下のハイフン区切りの名前は非推奨で、使用するとエラーになります:

| 非推奨名 | 現行の名前 |
|---|---|
| `buildtime-packages` | `buildtime_packages` |
| `binpkg-exclude` | `binpkg_excludes` |
| `circulardep-breaker` | `circulardep_breaker` |

ユーザーオブジェクト内では互換性のためハイフン区切りも受け付けます:
- `create-home` → `create_home`
- `initial-group` → `initial_group`
- `additional-groups` → `additional_groups`
- `empty-password` → `empty_password`

## 完全な構成例

```json5
{
  // 基本情報
  name: "nextcloud",
  profile: "paravirt",
  compression: "xz",

  // パッケージ
  packages: [
    "genpack/paravirt",
    "www-apps/nextcloud",
    "dev-db/mysql",
    "dev-lang/php",
    "net-misc/redis",
    "www-servers/apache"
  ],
  buildtime_packages: [
    "app-arch/rpm2targz"
  ],
  binpkg_excludes: ["sys-kernel/gentoo-kernel"],

  // Portage 設定
  use: {
    "dev-lang/php": "mysql curl gd xml zip",
    "www-servers/apache": "APACHE2_MODULES: http2 proxy proxy_fcgi"
  },
  accept_keywords: {
    "net-vpn/frp": null
  },
  license: {
    "net-analyzer/fping": "fping",
    "dev-db/redis": "SSPL-1"
  },

  // ユーザーとサービス
  users: [
    { name: "nextcloud", uid: 1000 }
  ],
  services: ["apache2", "mysqld", "redis"],

  // セットアップ
  setup_commands: [
    "sed -i 's/-D SSL //' /etc/conf.d/apache2"
  ],

  // バリアント
  variants: {
    selftestable: {
      profile: "weston/paravirt",
      packages: ["www-client/google-chrome"],
      users: [
        { name: "user", uid: 1000, empty_password: true }
      ]
    }
  }
}
```

## ソースリファレンス

このドキュメントは以下のリポジトリのスナップショットに基づいて作成されました:

- [wbrxcorp/genpack @ b71eb6b](https://github.com/wbrxcorp/genpack/tree/b71eb6b025f7cd1ec5ae9220a21f2229c274c7bd)
- [wbrxcorp/genpack-overlay @ 45a7e1e](https://github.com/wbrxcorp/genpack-overlay/tree/45a7e1e7440104f6592150261858c4ddd498d15b)
