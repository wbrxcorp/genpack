# genpack-install-gui（GUI インストーラ）

## 概要

`genpack-install-gui` は、genpack で生成したシステムイメージをディスクへ導入するための全画面 GUI インストーラです。Wayland コンポジタも X も無い環境で動くよう、KMS/DRM へ直接描画します（Slint の `backend-linuxkms`）。

- GitHub: [wbrxcorp/genpack-install-gui](https://github.com/wbrxcorp/genpack-install-gui)

[`genpack-install`](cli-install.md) CLI と同じ仕事をしますが、CLI を呼び出しているわけではなく、パーティション作成からブートローダ導入までを Rust で実装し直したものです（`parted` / `mkfs.vfat` / `mkfs.btrfs` / `grub-bios-setup` といった外部コマンドを使う点は同じで、ブートローダのバイナリも同じ `genpack/genpack-install` パッケージが配置したものを読みます）。したがって**出来上がるディスクの構成は CLI と同一**です。

| | `genpack-install`（CLI） | `genpack-install-gui`（GUI） |
|---|---|---|
| 操作 | コマンドライン | 全画面ウィザード（キーボード / マウス） |
| 想定する場面 | 手元での作業、自動化、SSH 越し | 現場でモニタとキーボードだけがある機体 |
| インストール先の構成 | ブートパーティション(FAT32) + データパーティション(Btrfs)、またはスーパーフロッピー | 同左（同一） |
| セルフアップデート | あり（`--disk` なし） | 無し |
| ISO / ZIP 生成 | `genpack-mkiso` / `genpack-mkzip` | 無し |

アプリ自体の詳細（画面構成、実行時の依存、開発・モック、VM での検証）はリポジトリの README を参照してください。このドキュメントは「そういうものがある」ことと、実際に使うまでの道筋だけを扱います。

## インストーラアーティファクト `genpack-install`

GUI を載せたブートメディアは、アーティファクト `genpack-install`（genpack-artifacts リポジトリ）としてビルドします。

- プロファイルは `baremetal`
- GUI バイナリは `files/build.d/genpack-install-gui.sh` が GitHub から clone して `cargo build --release` し `/usr/bin` へ導入します。ビルドツール（`dev-lang/rust-bin` / `dev-vcs/git` / `virtual/pkgconfig`）は [`buildtime_packages`](json5.md) で Lower にだけ入るため、最終イメージには残りません
- 実行時に必要なもの（`libdrm` / `mesa`(gbm,egl,gles2) / `libinput` / `fontconfig` / `seatd` / `libxkbcommon`、日本語グリフの `noto-cjk`、UI 装飾の `noto-emoji`）と、インストール処理が使う `genpack/genpack-install`（ブートローダ一式と `parted` / `dosfstools` / `btrfs-progs` を推移的に導入）が入っています
- `services` に `genpack-install-gui` と `seatd` を指定しており、GUI は tty1 を占有して自動起動します（`--wait-for-display` 付き。ディスプレイの認識完了を待ってから Slint を初期化するため、EDID 認識前に起動して落ちるのを防ぎます）

ビルドすると [`{name}-{arch}.squashfs` と `{name}-{arch}.img`](cli.md#pack) が出来ます。後者は EFI スーパーフロッピー（パーティションテーブルを持たない FAT32 全面）で、そのまま UEFI で起動できます。

```bash
cd ~/projects/genpack-artifacts/genpack-install
genpack build
```

### 起動メニュー

アーティファクト内の `/boot/grub/grub.cfg` が 2 つのエントリを出します（タイムアウト 5 秒、既定は上）。

| エントリ | 挙動 |
|---|---|
| Graphical installer | 既定の `graphical.target` で起動し、`genpack-install-gui.service` が自動起動する |
| Text mode (no installer) | `systemd.unit=multi-user.target` で止まる。GUI は起動しない（`WantedBy=graphical.target` のため） |

Text mode は、GUI が起動しない機体の調査や、手元でビルドしたバイナリを試すときの入口になります。

## ブートメディアの作り方

インストーラは**自分が起動したブートメディア**（`/run/initramfs/boot`）だけをスキャンして、インストールできるイメージの一覧を作ります。したがって媒体には、インストーラ自身（`system.img` と `EFI/`）と、**インストールしたいアーティファクトの squashfs** を同居させる必要があります。

```
/run/initramfs/boot/
  ├── EFI/BOOT/bootx64.efi   … インストーラの起動
  ├── system.img             … インストーラ自身の OS
  └── owncloud-x86_64.squashfs … インストール対象（複数置ける）
```

媒体の作り方は 3 通りあります。

### 1. `genpack-mkiso` で ISO にまとめる

姉妹コマンドの [`genpack-mkiso`](cli-install.md#genpack-mkiso) にインストーラのイメージを渡し、インストール対象を [`--add`](cli-install.md#--adddestsrc) で同梱します。出来た ISO は光学メディアにも書けますし、USB メモリに `dd` しても起動します（BIOS / UEFI 両対応）。

```bash
genpack-mkiso --label=INSTALLER installer.iso genpack-install-x86_64.squashfs \
    --add=owncloud-x86_64.squashfs=./owncloud-x86_64.squashfs
```

インストーラ自身は ISO 内の `/system.img` に入り、`--add` したファイルは ISO のルートに並ぶので、そのまま一覧に出ます。読み取り専用の媒体になるため、[postinstall スクリプト](#現場ごとのカスタマイズ-postinstall-スクリプト)を使う場合も `--add` で一緒に焼き込みます。

### 2. `genpack-mkzip` の ZIP を FAT32 の媒体に展開する

[`genpack-mkzip`](cli-install.md#genpack-mkzip) が出力する ZIP を、FAT32 でフォーマットした USB メモリや MicroSD に展開します。書き込み可能な媒体になるので、対象イメージや postinstall スクリプトを後から置き換えられるのが ISO との違いです。

ZIP には Raspberry Pi / U-Boot(extlinux) のブートファイルは入りますが、**EFI ブートローダは意図的に含まれません**（それは `genpack-install --disk` が作るブートパーティションの役目という整理です）。x86 の UEFI で起動する媒体にする場合は、`.img` の中にある `EFI/` を併せて置いてください。

### 3. `.img` をそのまま書く

`genpack build` が出力する `{name}-{arch}.img` を `dd` で書けば、インストーラ自体はすぐ起動します。ただしこのイメージはインストーラ自身でほぼ埋まっており（空きは数十 MB）、対象イメージを足す余地はありません。動作確認や、対象イメージを別途足した媒体を作るための土台として使います。genpack-install-gui の `tools/vm.py mkimage` は、十分な大きさの FAT32 を作って `.img` の中身（`EFI/` と `system.img`）を移し、対象イメージを置く、という手順を VM 検証用に自動化しています。

いずれの方法でも、FAT32 を使う場合は **1 ファイル 4GiB 未満**という制約がかかります（ISO9660 にはこの制限はありません）。

## 使い方

1. ブートメディアから UEFI で起動する（Graphical installer）
2. インストール先ディスクを選ぶ。マウント中のデバイスとその親は候補から除外されるので、起動媒体自身を誤って選ぶことはありません
3. インストールするイメージを選ぶ。`.genpack/` のメタデータ（アーティファクト名、バナー、ビルド情報）が表示され、実行環境と arch が違う場合は警告が出ます（別アーキテクチャ向けに書き込む用途は妨げません）
4. オプションを設定する — ホスト名 / タイムゾーン / ロケール、インストーラ環境の root の SSH 公開鍵の引き継ぎ、スーパーフロッピーモード（イメージが 4GiB 未満のときのみ）。これらは [`system.ini`](boot-sequence.md) としてブートパーティションに書かれ、初回起動時に [genpack-init](genpack-init-scripts.md) が適用します
5. 実行して再起動

GUI から離れずにシェルを触りたい場合は、メニュー（F10）の Terminal を使います。

## 現場ごとのカスタマイズ: postinstall スクリプト

`system.ini` に載る項目だけでは足りない設定（例: 個体ごとに違う固定 IP）のために、ブートメディアに置いたシェルスクリプトを、ターゲットをアンマウントする直前に実行できます。

```sh
sh -e <script> <boot_mnt> [<data_mnt>]
```

`<イメージ名から拡張子を除いたもの>.postinstall.sh` → `postinstall.sh` の順で探されます。インストール先のルートは SquashFS で書き換えられないため、ファイルの差し替えはデータパーティションの `root/`（起動時に overlayfs の upper 層になる場所）へ置く形で行います。

契約の詳細（引数と環境変数、失敗の扱い、whiteout、例）は genpack-install-gui リポジトリの `docs/postinstall.md` を参照してください。

## インストール先の構成

パーティション構成、ブートローダの配置、システムイメージの置き場所（4GiB 以上ならデータパーティションの `system`）は CLI と同一です。[genpack-install CLI リファレンスのパーティション構成](cli-install.md#パーティション構成)を参照してください。

## 開発版を試すとき

アーティファクトに焼き込まれている `/usr/bin/genpack-install-gui` は、**そのアーティファクトをビルドした時点のバイナリ**です。手元で直した版を試す場合は、ブートメディアにバイナリを置いて手動で起動します（自動起動している古い方は Text mode で起動するか `systemctl stop genpack-install-gui` で止めます）。

```bash
LIBSEAT_BACKEND=builtin SLINT_BACKEND=linuxkms /run/initramfs/boot/genpack-install-gui
```

QEMU 上で一通り検証する手順は genpack-install-gui リポジトリの `tools/vm.py` にまとまっています（ホスト root 不要）。

## ソースリファレンス

このドキュメントは以下のスナップショットに基づいて作成されました:

- [wbrxcorp/genpack-install-gui](https://github.com/wbrxcorp/genpack-install-gui)
- genpack-artifacts リポジトリの `genpack-install`（`genpack.json5`、`files/build.d/genpack-install-gui.sh`、`files/boot/grub/grub.cfg`、`files/usr/lib/systemd/system/genpack-install-gui.service`）
