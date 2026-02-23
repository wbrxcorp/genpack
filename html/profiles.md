# genpack-overlay プロファイルリファレンス

## 概要

genpack-overlay のプロファイルは、genpack イメージのベース環境を定義します。`genpack.json5` で `profile: "paravirt"` のように指定すると、そのプロファイルが持つパッケージ群、USE フラグ、キーワード設定などが自動的に適用されます。

プロファイルは Gentoo の Portage プロファイル機構を使って構成されており、階層的な継承関係を持ちます。

## プロファイル階層

全てのプロファイルは `genpack` ルートプロファイルを継承し、さらにアーキテクチャ固有の層を経由します。

```
genpack (ルート: 全環境共通の基本設定)
├── genpack/paravirt (仮想マシン向け)
├── genpack/systemimg (ディスクイメージ向け)
│   └── genpack/systemimg/baremetal (物理マシン向け)
├── genpack/weston (Wayland デスクトップ)
└── genpack/gnome (GNOME デスクトップ)
```

実際のプロファイル選択時には、アーキテクチャ層が自動的に挿入されます:

```
genpack.json5: profile: "paravirt"
  → genpack/amd64/paravirt  (x86_64 の場合)
  → genpack/arm64/paravirt  (aarch64 の場合)
```

## 利用可能なプロファイル

### paravirt

**用途**: QEMU/KVM 仮想マシン向け

`systemimg` と排他的です。仮想化環境に特化したパッケージ（ゲストエージェント、virtio 対応）を含み、物理ハードウェア向けのドライバ類を含みません。

**追加されるパッケージ** (genpack/paravirt メタパッケージ):

| パッケージ | 用途 |
|---|---|
| `genpack/base` | ベースシステム（後述） |
| `app-emulation/qemu-guest-agent` | QEMU ゲストエージェント |
| `sys-libs/liburing` | 非同期 I/O サポート |
| `net-misc/socat` | 多目的リレーツール |

**USE フラグ設定**:

```
media-libs/mesa video_cards_zink video_cards_lavapipe
```

仮想マシンではソフトウェアレンダリング (lavapipe) と Zink (OpenGL on Vulkan) が使用されます。

### systemimg

**用途**: ディスクイメージベースのインストール向け（genpack-install で書き込む形式）

`paravirt` と排他的です。genpack-install によるディスク書き込みとブートローダー設置に必要なパッケージを含みます。

**追加されるパッケージ** (genpack/systemimg メタパッケージ):

| パッケージ | 用途 |
|---|---|
| `genpack/base` | ベースシステム |
| `genpack/genpack-install` | ディスク書き込み・セルフアップデートツール |
| `sys-apps/kbd` | キーボードユーティリティ |

**USE フラグ設定**:

```
sys-libs/zlib minizip
```

### baremetal (systemimg/baremetal)

**用途**: 物理マシン向け（`systemimg` を継承）

`profile: "baremetal"` で指定します。物理ハードウェアの検出・管理に必要なツール群を追加します。

**追加されるパッケージ** (`genpack/systemimg` の `baremetal` USE フラグで有効化):

| パッケージ | 用途 |
|---|---|
| `sys-kernel/linux-firmware` | ハードウェアファームウェア |
| `sys-fs/lsscsi` | SCSI デバイス列挙 |
| `sys-apps/lshw` | ハードウェア情報表示 |
| `sys-apps/hwloc` | ハードウェアトポロジ |
| `sys-apps/usbutils` | USB デバイス管理 |
| `sys-apps/pciutils` | PCI デバイス管理 |
| `sys-apps/dmidecode` | DMI/SMBIOS 情報 |
| `sys-apps/lm-sensors` | ハードウェアモニタリング |
| `sys-apps/usb_modeswitch` | USB モード切替 |
| `sys-power/cpupower` | CPU 周波数管理 |
| `sys-apps/smartmontools` | S.M.A.R.T. 監視 |
| `sys-apps/nvme-cli` | NVMe 管理 |
| `sys-apps/hdparm` | ディスクパラメータ |
| `sys-apps/ethtool` | ネットワーク設定 |

x86_64 固有:

| パッケージ | 用途 |
|---|---|
| `app-misc/beep` | ビープ音 |
| `sys-apps/msr-tools` | MSR レジスタアクセス |
| `sys-apps/memtest86+` | メモリテスト |

### gnome/baremetal

**用途**: 物理マシン + GNOME デスクトップ

`profile: "gnome/baremetal"` で指定します。`baremetal` の全パッケージに加えて GNOME デスクトップ環境を含みます。

**追加されるパッケージ** (genpack/gnome メタパッケージ):

| パッケージ | 用途 |
|---|---|
| `gnome-base/gnome` | GNOME デスクトップ環境一式 |
| `media-fonts/noto-cjk` | CJK フォント |
| `media-fonts/noto-emoji` | 絵文字フォント |
| `x11-apps/mesa-progs` | OpenGL テストツール |
| `dev-util/vulkan-tools` | Vulkan テストツール |
| `net-libs/libnsl` | NIS サポートライブラリ |
| `app-misc/evtest` | 入力イベントテスト |
| `net-misc/gnome-remote-desktop` | リモートデスクトップ |
| `app-i18n/mozc` | 日本語入力（デフォルト有効） |

**継承元**: `gentoo:targets/desktop/gnome` プロファイルを含むため、GNOME に必要な広範な USE フラグが自動設定されます。

### weston/paravirt

**用途**: 仮想マシン + Wayland (Weston) デスクトップ

`profile: "weston/paravirt"` で指定します。Weston コンポジタをベースとした軽量なデスクトップ環境を提供します。

**追加されるパッケージ** (genpack/weston メタパッケージ):

| パッケージ | 用途 |
|---|---|
| `dev-libs/weston` | Wayland コンポジタ |
| `app-misc/wayland-utils` | Wayland ユーティリティ |
| `app-i18n/mozc` | 日本語入力 |
| `app-i18n/fcitx-gtk` | 入力メソッドフレームワーク |
| `gui-apps/wl-clipboard` | Wayland クリップボード |
| `gui-apps/tuigreet` | ログイングリーター（デフォルト有効） |
| `media-fonts/noto-cjk` | CJK フォント |
| `media-fonts/noto-emoji` | 絵文字フォント |
| `x11-apps/mesa-progs` | OpenGL テストツール |
| `dev-util/vulkan-tools` | Vulkan テストツール |

**グローバル USE フラグ**:

```
USE="wayland -X"
```

X11 を無効化し、Wayland を優先する設定です。

**パッケージ別 USE フラグ** (74 項目、主要なもの):

```
sys-apps/systemd policykit
media-libs/mesa X vulkan vaapi
app-i18n/mozc fcitx5
dev-qt/qtbase opengl vulkan
```

Chrome、VS Code、Ghostty、GIMP、Evolution、LibreOffice、VLC など多数のアプリケーション向けの USE フラグが設定されています。

**仮想マシン向けビデオドライバ**:

```
VIDEO_CARDS="-intel -nouveau -radeon -radeonsi virgl"
```

### raspberrypi

**用途**: Raspberry Pi 向け（arm64 のみ）

`profile: "raspberrypi"` で指定します（arm64 アーキテクチャ専用）。`baremetal` を継承し、Raspberry Pi 固有のカーネルとファームウェアを追加します。

**追加されるパッケージ**:

| パッケージ | 用途 |
|---|---|
| `sys-kernel/raspberrypi-image` | Raspberry Pi カーネル |
| `sys-firmware/raspberrypi-wifi-ucode` | Wi-Fi ファームウェア |

## ルートプロファイル (genpack)

全プロファイルが継承する共通設定です。

**パッケージ**:

| パッケージ | 用途 |
|---|---|
| `genpack/genpack-progs` | genpack ビルドユーティリティ（常に含まれる） |
| `genpack/base` | ベースシステム |

**グローバル USE フラグ**:

```
sys-libs/glibc audit
sys-kernel/installkernel dracut
sys-fs/squashfs-tools lz4 lzma lzo xattr zstd
app-crypt/libb2 -openmp
dev-lang/perl minimal
app-editors/vim minimal
```

**パッケージマスク**:

```
>=dev-lang/python-3.14
```

## ベースシステム (genpack/base)

全プロファイルを通じて含まれるベースパッケージです。

**常に含まれるパッケージ**:

| カテゴリ | パッケージ |
|---|---|
| カーネル | `gentoo-kernel-bin` または `gentoo-kernel` (initramfs 付き) |
| 初期化 | `dracut-genpack`, `genpack-init`, `gentoo-systemd-integration` |
| 基本ツール | `timezone-data`, `net-tools`, `gzip`, `unzip`, `grep`, `coreutils`, `procps`, `which` |
| ネットワーク | `rsync`, `iputils`, `iproute2` |
| ランタイム | `python`, `requests`, `ca-certificates` |

**USE フラグで制御可能なパッケージ** (全てデフォルト有効):

| USE フラグ | パッケージ | 用途 |
|---|---|---|
| `sshd` | `net-misc/openssh` | SSH サーバー |
| `vi` | `app-editors/vim` | テキストエディタ |
| `strace` | `dev-debug/strace` | システムコールトレース |
| `wireguard` | `net-vpn/wireguard-tools`, `net-vpn/wg-genconf` | VPN |
| `btrfs` | `sys-fs/btrfs-progs` | Btrfs ファイルシステムツール |
| `xfs` | `sys-fs/xfsprogs` | XFS ファイルシステムツール |
| `cron` | `sys-process/cronie` | cron デーモン |
| `audit` | `sys-process/audit` | 監査フレームワーク |
| `logrotate` | `app-admin/logrotate` | ログローテーション |
| `tcpdump` | `net-analyzer/tcpdump` | パケットキャプチャ |
| `banner` | (genpack バナー表示) | ログインバナー |

## その他のメタパッケージ

プロファイルとは独立して `genpack.json5` の `packages` に追加できるメタパッケージです。

### genpack/wireless

無線ネットワークサポート:

| パッケージ | 用途 |
|---|---|
| `net-wireless/wpa_supplicant_any80211` | WPA サプリカント |
| `net-wireless/iw` | 無線 LAN 設定 |
| `net-wireless/wireless-tools` | 無線ツール |
| `net-wireless/bluez` | Bluetooth スタック |
| `net-wireless/hostapd` | アクセスポイント |

### genpack/devel

開発ツール:

| パッケージ | 用途 |
|---|---|
| `sys-devel/binutils` | バイナリユーティリティ |
| `sys-devel/gcc` | C/C++ コンパイラ |
| `dev-debug/gdb` | デバッガ |

### genpack/devlauncher

AI エージェント向け開発環境 (`genpack/devel` を含む):

| パッケージ | 用途 |
|---|---|
| `www-client/google-chrome` | Web ブラウザ |
| `gui-apps/waypipe` | Wayland リモート表示 |
| `dev-util/claude-code` | AI コーディングアシスタント |
| `app-editors/vscode` | コードエディタ |
| `x11-terms/ghostty` | ターミナルエミュレータ |
| `app-containers/docker` | コンテナランタイム |
| その他 | jq, fd, bat, pip, pytest, pylint 等 |

## プロファイルの選択ガイド

| ユースケース | プロファイル | 備考 |
|---|---|---|
| QEMU/KVM 仮想マシン | `paravirt` | 最も一般的 |
| 物理マシン (サーバー) | `baremetal` | ハードウェア検出ツール付き |
| 物理マシン + GNOME デスクトップ | `gnome/baremetal` | フルデスクトップ |
| 仮想マシン + GUI | `weston/paravirt` | 軽量 Wayland デスクトップ |
| Raspberry Pi | `raspberrypi` | arm64 専用 |
| プロファイルなし | (なし) | `genpack/base` のみ。最小構成から独自に構築する場合 |

## アーキテクチャ固有の差異

| アーキテクチャ | 対応プロファイル | 備考 |
|---|---|---|
| x86_64 (amd64) | 全プロファイル | GRUB EFI-32 サポート付き |
| aarch64 (arm64) | paravirt, baremetal, raspberrypi | Raspberry Pi 専用プロファイルあり |
| i686 (x86) | base, systemimg | デスクトッププロファイルなし |
| riscv64 | base 相当 | 限定的サポート |

## ソースリファレンス

このドキュメントは以下のリポジトリのスナップショットに基づいて作成されました:

- [wbrxcorp/genpack-overlay @ 45a7e1e](https://github.com/wbrxcorp/genpack-overlay/tree/45a7e1e7440104f6592150261858c4ddd498d15b)
