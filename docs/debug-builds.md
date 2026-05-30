# デバッグシンボル付きイメージの作り方

特定のクラッシュやパフォーマンス問題を「実機の現場で」追うためのデバッグシンボル + ソース同梱イメージを genpack で組む手順をまとめます。 genpack 本体に専用機能を足す必要はなく、 既存の `env` / `binpkg_excludes` / `files/` / `circulardep_breaker` を組み合わせるだけで成立します。

## なぜこれが価値ある機能か

実機を要するバグ (GPU ドライバ、 firmware、 BIOS 層、 ハードウェア固有の kmod、 特定ロット製品の挙動) は **VM では追えません**。 そして汎用ディストロでこの種のバグを実機で bisect しようとすると、 前回検証の残骸 (古い kmod、 別バージョンの Mesa、 ユーザ設定の堆積) がノイズになって何を測っているか分からなくなります。

genpack なら ESP に置く squashfs を差し替えてリブートするだけで **世界ごと入れ替わります**。 bisect の各点で「同条件 + 1 軸だけ変更」が保証されるため、 何の差分が現象を呼ぶかを定量的に詰められます。 たとえば「特定 GPU での Mesa anv NULL deref」 を調査する場合:

| variant | 変える 1 軸 |
|---|---|
| `xxx-debug` (base) | シンボル + ソース付き、 ハードウェアあり/iHD あり |
| `xxx-debug-no-iHD` | iHD パッケージを抜く |
| `xxx-debug-mesa-prev` | Mesa を 1 つ前のバージョンに pin |
| `xxx-debug-grd-prev` | GRD を 1 つ前に pin |

これらを並列にビルドして同じ機体でブートし直すだけで、 各軸の影響が独立に見えます。 汎用ディストロで同じことをやるとマシンを 4 台用意するか、 検証の合間に丸一日かけて環境を作り直すかの二択になりがちです。

実例: B580 (Intel Arc) の anv NULL deref 調査 (`grd-b580-debug` artifact) は、 この方式で当該機上のシンボル付き coredump を取得し、 root cause を Mesa GitLab に upstream 報告するところまで到達しました。

## 基本方針: 独立 artifact として切り出す

デバッグシンボル + ソースを乗せると `/usr/lib/debug/` だけで数百 MB、 `/usr/src/debug/` も同程度を要し、 これを既存の本体 artifact (例: `gnome`) に variant として乗せると ESP の **FAT32 1 ファイル 4 GiB 上限**を踏みます。 加えて本体 artifact に手を入れると blast radius が広がるため、 デバッグビルドは原則として **`../<name>-debug` のような独立 artifact** に切り出します。

独立 artifact にすると以下が同時に解決します:

- 本体 artifact のサイズは元のまま (= 通常運用に影響なし)
- デバッグ対象パッケージの再ビルドが本体に波及しない
- 共有 binpkg キャッシュとの衝突を `binpkg_excludes` で双方向に遮断できる (後述)
- artifact 直下の `files/etc/claude-code/CLAUDE.md` で現場用 agent に世界観を与えられる

## レシピ

### artifact ディレクトリの構成

```
~/projects/genpack-artifacts/<name>-debug/
├── env/
│   └── genpack-debug.conf       # FEATURES と CFLAGS を上書き
├── files/                       # (任意) 現場用 CLAUDE.md などを置く
│   └── etc/claude-code/
│       └── CLAUDE.md
└── genpack.json5                # env マップ + binpkg_excludes
```

### `env/genpack-debug.conf`

Portage の per-package env で、 対象パッケージだけにデバッグ向け FEATURES / CFLAGS を被せます。

```bash
# Build packages with split debug info and installed sources so that
# coredumpctl gdb on the deployed machine produces a readable backtrace
# with file/line information.

FEATURES="${FEATURES} splitdebug installsources"
CFLAGS="${CFLAGS} -ggdb3 -fno-omit-frame-pointer"
CXXFLAGS="${CXXFLAGS} -ggdb3 -fno-omit-frame-pointer"
```

各オプションの意味:

| 設定 | 役割 |
|---|---|
| `FEATURES=splitdebug` | `.debug` ファイルを `/usr/lib/debug/...` に分離配置。 main の `.so`/`.exe` は strip され、 gdb は `.gnu_debuglink` で自動的に対応する `.debug` を引く |
| `FEATURES=installsources` | `debugedit` 経由でソースツリーを `/usr/src/debug/<category>/<pf>/` に展開。 これで gdb が `list` でソース行を表示できる |
| `CFLAGS=-ggdb3` | gdb 拡張デバッグ情報の最高レベル。 `-g` だけより gdb で得られる情報が増える |
| `CFLAGS=-fno-omit-frame-pointer` | -O2 で省略されがちな frame pointer を残し、 backtrace を読みやすくする |

最適化レベル (`-O2` 等) は profile 既定を維持します。 `-O0` まで落とすと挙動自体が変わってバグが再現しない場合があるため、 リリース相当の最適化のままでデバッグ情報だけ厚くするのが原則。

### `genpack.json5` の最小骨格

```json5
{
    name: "<name>-debug",
    profile: "<関連 profile>",      // 例: "gnome/baremetal"
    compression: "xz",

    binpkg_excludes: [
        // デバッグ対象パッケージ。 共有 binpkg キャッシュとの双方向汚染を遮断
        "media-libs/mesa",
        "net-misc/gnome-remote-desktop",
        "media-video/pipewire",
    ],

    packages: [
        "sys-kernel/gentoo-kernel-bin",  // 必要なら bin 版で十分
        // 再現に必要なパッケージ群
        // 診断ツール
        "dev-debug/gdb",
        "sys-apps/inxi",  // bug report 用システム情報採取に便利
    ],

    env: {
        // env/genpack-debug.conf を per-package で被せる
        "media-libs/mesa": "genpack-debug.conf",
        "net-misc/gnome-remote-desktop": "genpack-debug.conf",
        "media-video/pipewire": "genpack-debug.conf",
    },

    users: [
        { name: "user", uid: 1000, "empty-password": true,
          "additional-groups": ["wheel", "audio", "video", "input"] }
    ],
    services: ["gdm", "NetworkManager"],
}
```

ポイント:

- **`env` フィールドに列挙したパッケージだけがデバッグビルドされます**。 全パッケージに splitdebug を効かせるとイメージが破裂するので必ず絞ります
- **`binpkg_excludes` に同じパッケージを並べるのが必須** (理由は次節)
- profile は本体 artifact と揃えると問題の再現性が高い (例: GNOME 上の問題なら `gnome/baremetal`)
- 再現が kernel に依存しないなら `gentoo-kernel-bin` でビルド時間を短縮できる

### `binpkg_excludes` が双方向遮断であること

`binpkg_excludes` は genpack 内部で emerge に `--usepkg-exclude` と `--buildpkg-exclude` の **両方** に渡されます (`src/genpack.py` の lower() 参照)。 これがデバッグビルドで重要です:

- `--usepkg-exclude`: 既存の strip 済 binpkg を引かない → デバッグ用 `-ggdb3` で必ず再ビルドさせる
- `--buildpkg-exclude`: 生成したデバッグ入り binpkg を共有キャッシュに push しない → 同じ binpkg キャッシュを使う他 artifact (= 通常運用イメージ) が誤って肥大化するのを防ぐ

この双方向性により、 デバッグ artifact と通常 artifact が共有 binpkg キャッシュを問題なく共存できます。 `--independent-binpkgs` を強制する必要はありません。

## イメージに含まれるもの

`FEATURES=splitdebug installsources` で増えたファイル群:

```
/usr/lib/debug/usr/lib64/libvulkan_intel.so.debug      # 各 .so に対応する分離デバッグ情報
/usr/lib/debug/usr/libexec/gnome-remote-desktop-daemon.debug
/usr/src/debug/media-libs/mesa-<ver>/                  # 展開済ソースツリー
/usr/src/debug/net-misc/gnome-remote-desktop-<ver>/
```

これらは portage の各パッケージの `CONTENTS` ファイルに登録されるため、 `genpack-copyup` の対象になります。 `genpack-progs/files/genpack_pkg.py` 内の `is_path_excluded()` でも `/usr/lib/debug/` と `/usr/src/debug/` は除外対象になっていないため、 そのまま upper 層に転送され最終 squashfs に乗ります。

## ターゲット上での使い方

実機 (デバッグ artifact をブートした機械) 上で coredump を解析する基本フロー:

```bash
# クラッシュ一覧
coredumpctl list

# 概要 (シグナル、 ip、 ファイル名など)
coredumpctl info <PID>

# gdb セッションを開く (シンボルは /usr/lib/debug/ から自動ロード)
coredumpctl gdb <PID>
```

gdb 内で:

```
(gdb) bt full                    # フレームを全部見る
(gdb) frame <N>                  # 関心のあるフレームに移動
(gdb) list                       # /usr/src/debug/<cat>/<pf>/ からソース行を表示
(gdb) info args                  # 関数引数を確認
(gdb) info locals                # 局所変数
(gdb) disassemble                # アセンブリ
(gdb) info registers             # レジスタ
(gdb) p *(struct foo *) $rax     # 任意のポインタを構造体として展開
```

## 拡張: 現場 agent による調査

`dev-util/claude-code` (および将来同等の CLI agent) を artifact に同梱すると、 実機ターミナルから直接 agent を起動して `coredumpctl gdb` を走らせ、 ソースを読み、 構造体メンバを特定するところまでを自動化できます。 cold start で agent が迷子にならないよう、 artifact 内に **organization-managed CLAUDE.md** を置いて世界観を渡しておくのが定石です:

```
files/etc/claude-code/CLAUDE.md
```

このファイルは agent (Claude Code) の起動時に system instruction として読み込まれます。 記載しておくと良い内容:

1. **このシステムの目的** (何を調査するための artifact か、 既知の workaround は提案しないこと)
2. **既知のクラッシュ特徴** (fault address、 想定される関数名等の指紋)
3. **デバッグ情報の場所** (`/usr/lib/debug/`、 `/usr/src/debug/<cat>/<pf>/`)
4. **観測コマンド一覧** (`coredumpctl`, `journalctl` 等)
5. **genpack artifact 特性** (squashfs + tmpfs overlay、 emerge は永続しない、 発見は会話で報告し局所ファイルに書き貯めない)
6. **デフォルト調査フロー** と **やってはいけないこと**

実装例は `grd-b580-debug` artifact の `files/etc/claude-code/CLAUDE.md` を参照。

## ビルド後の検証

`genpack build` 完了後、 実機に書き込む前に root 権限なしで squashfs を中身チェックできます:

```bash
# /etc/claude-code/CLAUDE.md が配置されているか
genpack-helper nspawn <name>-debug-x86_64.squashfs ls -la /etc/claude-code/

# デバッグシンボルが入っているか
genpack-helper nspawn <name>-debug-x86_64.squashfs sh -c \
    'ls /usr/lib/debug/usr/lib64/ | grep -i <target>'

# インストール済ソースの確認
genpack-helper nspawn <name>-debug-x86_64.squashfs sh -c \
    'ls /usr/src/debug/'

# サイズ感
genpack-helper nspawn <name>-debug-x86_64.squashfs sh -c \
    'du -sh /usr/lib/debug /usr/src/debug'

# gdb がシンボルを実際に解決できるか
genpack-helper nspawn <name>-debug-x86_64.squashfs \
    /usr/sbin/gdb -batch \
        -ex "set debug-file-directory /usr/lib/debug" \
        -ex "file /usr/lib64/libvulkan_intel.so" \
        -ex "info functions <symbol>"
```

`info functions` がファイル名 + 行番号付きで関数を列挙したら、 デバッグ情報は正しくリンクされています。

## 実装サンプル

`genpack-artifacts/grd-b580-debug/` が本ドキュメントの全要素を実装した参考実装です:

- `genpack.json5`: gnome/baremetal profile、 mesa / grd / pipewire を `env` マップで debug ビルド、 同じ 3 つを `binpkg_excludes`
- `env/genpack-debug.conf`: 本ドキュメント 4 行と同一
- `files/etc/claude-code/CLAUDE.md`: B580 anv NULL deref 調査専用の世界観
- 同梱パッケージ: `dev-debug/gdb`、 `dev-util/claude-code`、 `media-video/libva-utils`、 `sys-apps/inxi`、 トリガー用の `media-libs/libva-intel-media-driver`

最終的にこの artifact で取得した coredump 解析が Mesa GitLab work item 15578 (anv NULL deref regression) の起票に直結しました。

## 参考

### 関連 Gentoo FEATURES

- `splitdebug`: デバッグ情報を `/usr/lib/debug/` 配下の `.debug` ファイルに分離。 main バイナリは strip された状態を保つ
- `installsources`: ソースを `/usr/src/debug/<cat>/<pf>/` に展開。 `debugedit` でソースパスが再書き換えされ、 gdb が `directory` lookup で見つけられる
- `nostrip`: 一切 strip しない。 デバッグ情報がバイナリ内に残るため、 splitdebug と組み合わせる必要はなく、 通常は splitdebug の方を推奨

### 関連 genpack フィールド

詳細は [`json5.md`](json5.md) を参照:

- [`env`](json5.md#env): per-package env ファイル名のマッピング
- [`binpkg_excludes`](json5.md#binpkg_excludes): usepkg と buildpkg 両方の exclude として作用
- [`profile`](json5.md#profile): 本体と揃えると問題の再現性が高い

### ソースリファレンス

- [wbrxcorp/genpack](https://github.com/wbrxcorp/genpack)
- 実装サンプル: `genpack-artifacts/grd-b580-debug/`
