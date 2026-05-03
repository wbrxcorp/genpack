# genpack/devlauncher メタパッケージ

## 概要

`genpack/devlauncher` は、Wayland環境でのGUI開発作業に必要なツール一式をまとめたメタパッケージである。GTK4ベースのアプリケーションランチャー (`devlauncher`) をインストールし、エディタ、ブラウザ、ターミナルエミュレータ、コンテナツール、コマンドラインユーティリティ等を一括で導入する。

## 依存パッケージ一覧

### 開発基盤 (genpack/devel 経由)

| パッケージ | 説明 |
|---|---|
| `sys-devel/binutils` | バイナリユーティリティ |
| `sys-devel/gcc` | GCC コンパイラ |
| `dev-debug/gdb` | GDB デバッガ |

### GUI アプリケーション

| パッケージ | 説明 |
|---|---|
| `www-client/google-chrome` | Web ブラウザ |
| `app-editors/vscode[wayland]` | Visual Studio Code |
| `x11-terms/ghostty` (<1.2) | Ghostty ターミナルエミュレータ |
| `app-text/xournalpp` | 手書きノート・PDF注釈 (GTK3) |
| `dev-util/claude-code` | Claude Code CLI |

### GUI 基盤

| パッケージ | 説明 |
|---|---|
| `gui-apps/waypipe[lz4,zstd]` | Wayland リモートディスプレイ転送 |
| `gui-libs/gtk[wayland]` | GTK4 (devlauncher 本体が使用) |
| `x11-libs/gtk+[wayland]` | GTK3 (xournalpp 等が使用) |
| `dev-python/pygobject` | Python GObject バインディング |
| `media-fonts/noto` | Noto フォント |
| `media-fonts/noto-cjk` | Noto CJK フォント |
| `media-fonts/noto-emoji` | Noto 絵文字フォント |
| `media-sound/alsa-utils` | ALSA オーディオユーティリティ |

### コンテナ

| パッケージ | 説明 |
|---|---|
| `app-containers/docker` | Docker コンテナエンジン |
| `app-containers/docker-compose` | Docker Compose |

### コマンドラインツール

| パッケージ | 説明 |
|---|---|
| `app-admin/sudo` | 特権昇格 |
| `sys-process/psmisc` | プロセス管理ユーティリティ |
| `app-misc/jq` | JSON プロセッサ |
| `sys-apps/fd` | ファイル検索 |
| `app-text/tree` | ディレクトリツリー表示 |
| `sys-apps/bat` | シンタックスハイライト付き cat |
| `dev-python/pip` | Python パッケージマネージャ |
| `dev-python/pylint` | Python リンター |
| `dev-python/pytest` | Python テストフレームワーク |

## devlauncher アプリケーション

`/usr/bin/devlauncher` としてインストールされる GTK4 (PyGObject) ベースのアプリケーションランチャー。起動するとインストール済みの `.desktop` アプリケーションをグリッド表示し、クリックで起動できる。

### Wayland 環境の自動検出

`devlauncher` は起動時に以下の条件を確認し、環境変数を自動設定する：

- `WAYLAND_DISPLAY` が設定されている
- `DISPLAY` が設定されていない（X11 でない）
- `XDG_SESSION_TYPE` が `wayland` でない

この条件に該当する場合、`XDG_SESSION_TYPE=wayland` と `MOZ_ENABLE_WAYLAND=1` を設定する。waypipe SSH 経由でのリモート接続時に Wayland セッション情報が不完全なケースを補完する目的がある。

## 間接的に必須となるフラグ

devlauncher とその依存パッケージを正しくビルドするには、ebuild の RDEPEND で直接指定されるもの以外にも、間接的な依存関係で要求される USE フラグがある。`weston` プロファイルを使用する場合はプロファイル側で設定されるが、`paravirt` 等の GUI 設定を持たないプロファイルと組み合わせる場合は `genpack.json5` の `use` セクションで明示的に指定する必要がある。

### ライセンス承諾

プロプライエタリパッケージには `genpack.json5` の `license` セクションでの承諾が必要：

```json5
license: {
    "www-client/google-chrome": "google-chrome",
    "dev-util/claude-code": "all-rights-reserved",
    "app-editors/vscode": "Microsoft-vscode"
}
```

### Wayland/ディスプレイ関連

GTK が Wayland バックエンドで動作するには、グラフィックスタックにも Wayland サポートが必要となる。

| パッケージ | USE フラグ | 理由 |
|---|---|---|
| `gui-libs/gtk` | `wayland` | GTK4 の Wayland バックエンド。devlauncher が直接使用 |
| `x11-libs/gtk+` | `wayland` | GTK3 の Wayland バックエンド。xournalpp 等が使用 |
| `media-libs/mesa` | `vulkan wayland` | `gtk[wayland]` が `mesa[wayland]` を要求。`vulkan` は lavapipe/zink の REQUIRED_USE |
| `x11-libs/cairo` | `X` | `gtk+[X]` が要求。Chrome/Electron 系の依存チェーンで必要 |
| `media-libs/libglvnd` | `X` | `gtk+` 経由で要求 |
| `app-crypt/gcr` | `gtk` | VSCode → gnome-keyring → gcr の依存チェーン |
| `media-libs/freetype` | `harfbuzz` | フォントレンダリング。harfbuzz との循環依存あり |
| `app-text/poppler` | `cairo` | xournalpp の PDF 描画で必要 |

### 循環依存の解決

`media-libs/freetype` と `media-libs/harfbuzz` は相互依存の関係にあるため、`circulardep_breaker` の設定が必要：

```json5
circulardep_breaker: {
    packages: ["media-libs/freetype", "media-libs/harfbuzz"],
    use: "-harfbuzz -truetype"
}
```

### genpack.json5 での設定例

`paravirt` プロファイルで devlauncher を使用する場合の最小限の USE フラグ設定：

```json5
{
    profile: "paravirt",
    packages: ["genpack/devlauncher"],
    use: {
        "gui-libs/gtk": "wayland",
        "x11-libs/gtk+": "wayland",
        "media-libs/mesa": "vulkan wayland",
        "x11-libs/cairo": "X",
        "media-libs/libglvnd": "X",
        "media-libs/freetype": "harfbuzz",
        "app-crypt/gcr": "gtk",
        "app-text/poppler": "cairo"
    },
    circulardep_breaker: {
        packages: ["media-libs/freetype", "media-libs/harfbuzz"],
        use: "-harfbuzz -truetype"
    },
    license: {
        "www-client/google-chrome": "google-chrome",
        "dev-util/claude-code": "all-rights-reserved",
        "app-editors/vscode": "Microsoft-vscode"
    }
}
```

### weston プロファイルとの関係

`weston` プロファイルは `make.defaults` でグローバルに `USE="wayland -X"` を設定し、`package.use` で上記のほとんどの USE フラグをカバーしている。ただし `weston/paravirt` プロファイルは Weston コンポジタを含む完全なデスクトップ環境を前提としており、waypipe 経由のリモート表示のみで使う場合は過剰になる。`paravirt` プロファイルに必要な USE フラグを個別指定する方が軽量なイメージを構築できる。

## ソースリファレンス

- [genpack/devlauncher ebuild](https://github.com/wbrxcorp/genpack-overlay/tree/main/genpack/devlauncher)
- [profiles/genpack/weston/package.use](https://github.com/wbrxcorp/genpack-overlay/blob/main/profiles/genpack/weston/package.use)
- [profiles/genpack/paravirt/package.use](https://github.com/wbrxcorp/genpack-overlay/blob/main/profiles/genpack/paravirt/package.use)
