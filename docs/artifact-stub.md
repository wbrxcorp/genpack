# stub — VM 用マルチディストリビューションインストーラ兼 kexec ブートローダー

[GitHub: genpack-artifacts/stub](https://github.com/genpack-artifacts/stub)

## 概要

stub は genpack ツールチェーンで構築されるアーティファクトの一つで、**他の Linux ディストリビューションを QEMU/KVM 仮想マシン上にインストールするための使い捨てブート環境**です。

genpack イメージとして動作しつつも、最終的な目的は genpack 以外の OS を立ち上げることにあります。初回起動時はインストーラとして、2 回目以降は kexec を使ったブートローダーとして振る舞う、二段階構成のプロビジョニングツールです。

## 使い方

[vm](https://github.com/shimarin/vm) コマンドと組み合わせて使用します。

```bash
# 1. データ用仮想ディスクを作成 (8GiB)
vm allocate debian12.img 8

# 2. stub をシステムイメージ、debian12.img をデータディスクとして VM 起動
vm run -d debian12.img stub-$(uname -m).squashfs

# 3. VM 内で自動ログイン後、目的のディストリビューションのスクリプトを実行
./debian12.sh

# 4. インストール完了後に reboot → 以降は Debian 12 が直接起動する
```

## 動作の流れ

```
stub 起動 (genpack イメージ、コンソール自動ログイン)
  │
  ├── /root/ 以下にディストリビューションインストールスクリプトが用意されている
  │
  ├── ユーザーがスクリプトを実行
  │     1. /dev/vdb (データ用仮想ディスク) にファイルシステム作成
  │     2. debootstrap / rpmbootstrap でディストリビューションをブートストラップ
  │     3. SSH, ネットワーク, ホスト名, ロケール等を設定
  │     4. dracut で initramfs 生成
  │     5. reboot
  │
  └── 次回起動時: genpack-init の kexec プラグイン (00kexec.py)
        データディスク上のカーネルを検出
        → kexec でインストール済み OS のカーネルに直接遷移
        → stub は役目を終え、以降はインストールした OS が起動
```

## 対応ディストリビューション

### Debian / Ubuntu 系 (debootstrap 使用)

| スクリプト | ディストリビューション |
|---|---|
| `debian12.sh` | Debian 12 (Bookworm) |
| `debian13.sh` | Debian 13 (Trixie) |
| `ubuntu2004.sh` | Ubuntu 20.04 (Focal) |
| `ubuntu2204.sh` | Ubuntu 22.04 (Jammy) |
| `ubuntu2404.sh` | Ubuntu 24.04 (Noble) |
| `ubuntu2604.sh` | Ubuntu 26.04 (Resolute) |

### RHEL / RPM 系 (rpmbootstrap 使用)

| スクリプト | ディストリビューション |
|---|---|
| `centos6.sh` | CentOS 6 |
| `centos7.sh` | CentOS 7 |
| `centos8stream.sh` | CentOS Stream 8 |
| `centos9stream.sh` | CentOS Stream 9 |
| `centos10stream.sh` | CentOS Stream 10 |
| `almalinux9.sh` | AlmaLinux 9 |
| `rocky8.sh` | Rocky Linux 8 |
| `miraclelinux8.sh` | MIRACLE LINUX 8 |
| `fedora42.sh` | Fedora 42 |

### その他

| スクリプト | ディストリビューション |
|---|---|
| `gentoo.sh` | Gentoo Linux (stage3 tarball から構築) |

## 主要コンポーネント

### kexec ブートプラグイン (`files/usr/lib/genpack-init/00kexec.py`)

genpack-init のプラグインとして毎回起動時に実行される Python スクリプトです。データディスク (`/dev/vdb`) または virtiofs 上にインストール済み OS のカーネルと initramfs が存在するかを検出し、見つかった場合は kexec でそのカーネルをロードして遷移します。

これにより、stub は初回のインストール作業後は透過的なブートローダーとして機能し、VM の起動フローは以下のようになります:

```
QEMU 起動 → stub カーネル → genpack-init → kexec → インストール済み OS カーネル → OS 起動
```

### ディストリビューションインストールスクリプト (`files/root/*.sh`)

各スクリプトは以下の共通パターンに従います:

1. `systemd-networkd-wait-online` でネットワーク接続を待機
2. データディスクにファイルシステムを作成 (XFS / Btrfs)
3. `debootstrap` または `rpmbootstrap` でベースシステムをブートストラップ
4. ホスト名、ネットワーク、SSH、タイムゾーンを設定
5. SSH 公開鍵、LLMNRD (Link-Local Name Resolution)、QEMU ゲストエージェントを配置
6. dracut で initramfs を生成 (virtiofs / 暗号化サポート含む)
7. reboot

インストール直後から SSH によるリモート管理が可能な状態になります。

### 自動ログイン (`files/build.d/autologin.sh`)

hvc0 (virtio コンソール) と ttyS0 (シリアルコンソール) の両方で root の自動ログインを設定します。`vm console` でコンソール接続すると、ログインプロンプトなしで即座にシェルが使えます。

### LLMNRD (`files/build.d/build-llmnrd.sh`)

Link-Local Multicast Name Resolution Daemon をソースからスタティックビルドします。インストール先の OS に配置され、DNS サーバーなしでのホスト名解決を可能にします。

## 含まれるパッケージ

| パッケージ | 用途 |
|---|---|
| `genpack/paravirt` | 準仮想化カーネルとベースシステム |
| `sys-kernel/gentoo-kernel` | ソースからビルドされた最小カーネル |
| `sys-apps/kexec-tools` | OS カーネルへの遷移に使用 |
| `dev-util/debootstrap` | Debian / Ubuntu 系のブートストラップ |
| `dev-util/rpmbootstrap` | RPM 系のブートストラップ |
| `sys-fs/cryptsetup` | ディスク暗号化サポート |
| `sys-devel/binutils` | バイナリユーティリティ |

## カーネル最小化

stub は使い捨てのブート環境であり広範なハードウェアサポートが不要なため、`kernel/config.d/unset.config` で 1,755 のカーネルオプションを無効化しています。

無効化される主な機能:
- Hibernation / Suspend / 電源管理
- XEN / NUMA / SGX
- デバッグ、プロファイリング、トレーシング機能全般
- 不要なカーネル圧縮アルゴリズム
- カーネル署名検証 (`KEXEC_SIG` — kexec の柔軟性のために無効化)

逆に、最小化しすぎて壊した過去がある以下は意図的に有効のままにしています (`unset.config` 内に碑文コメントを残し、再発を防いでいます):

- **`CONFIG_EFI=y`** — genpack の paravirt VM は QEMU q35 + OVMF (UEFI ファームウェア) で起動します。UEFI では ACPI の RSDP が EFI システムテーブル経由でしか得られないため、EFI を無効化すると ACPI 全体が無効になり、`poweroff` が機能せず QEMU が終了しなくなります (`reboot: Power off not available: System halted instead`)。paravirt では EFI は必須です。
- **`CONFIG_VSOCKETS=y` / `CONFIG_VIRTIO_VSOCKETS=y`** (`kernel/config.d/vsock.config`) — ホストから `ssh root@vsock%$(vm cid …)` でゲストへ接続するための AF_VSOCK ゲストサポートです。Fedora ベース構成ではこれらは標準でモジュール (`=m`) として有効ですが、ブート初期から確実に効かせるためモジュールではなく `=y` (組み込み) に格上げしています。

## 対応アーキテクチャ

| アーキテクチャ | カーネル設定 | 出力ファイル |
|---|---|---|
| x86_64 | `kernel/config.d/` (unset.config + vsock.config) | `stub-x86_64.squashfs` |
| aarch64 | `kernel/config.d/` (unset.config + vsock.config) | `stub-aarch64.squashfs` |
| riscv64 | `kernel/config.d/` (unset.config + vsock.config) | `stub-riscv64.squashfs` |

以前は aarch64 / riscv64 でアーキテクチャごとの `savedconfig`（ホワイトリスト方式の完全な設定ファイル）を併用していましたが、保守性のため全アーキテクチャで `kernel/config.d/`（ブラックリスト方式のフラグメント）に一本化しました。`savedconfig` は廃止されています。

## 想定シナリオ — 新しい SBC への先行投資

stub がマルチアーキテクチャ (x86_64 / aarch64 / riscv64) に対応していることには、単なる移植性以上の実利的な狙いがあります。典型的なのは新しいシングルボードコンピュータ (SBC) への先行対応です。

どこかのベンダが革新的な RISC-V SBC を発表したとしましょう。この種のボードの公式 OS は、たいていベンダが独自にカスタマイズした Debian や Ubuntu です。しかし実機はまだ手元に届いていない — あるいは入手した後でも、開発作業そのものは使い慣れた手元の x86 ワークステーションで進めたい。そんなとき、ソフトウェア環境だけでも実機になるべく寄せて先行調査・開発を始めたい、という需要が生まれます。

ここで riscv64 版 stub が効いてきます。手元の x86 マシンで riscv64 stub を QEMU (TCG エミュレーション) の VM として起動し、`debian13.sh` のようなスクリプトで `debootstrap --arch=riscv64` を実行すれば、そのベンダ系統のディストリビューションを **riscv64 アーキテクチャのまま** VM 内に構築し、kexec で起動できます。実機がなくても (あるいは実機とは別に)、SBC の OS 環境を近似的に再現できるわけです。

これが成立するのは、stub の役割が「ブートストラッパ」だからです。`debootstrap` は自分が動作しているアーキテクチャ向けにターゲットを構築し、kexec もそのカーネルへ遷移します。**ブートストラッパは、インストールしたいターゲットと同じアーキテクチャ上で動いていなければならない。** したがって aarch64 / riscv64 のディストリビューションを立ち上げるには、stub 自身がそのアーキテクチャで動く必要があります。マルチアーキテクチャ対応は「テストカバレッジが広がる」といった副次的なものではなく、stub が本来の仕事を各アーキテクチャで果たすための機能的な前提条件なのです。

TCG エミュレーションのため CPU 性能は実機に及ばず (foreign アーキテクチャのカーネルビルドにはかなりの時間がかかります)、純粋な性能評価には向きません。しかし ABI やアーキテクチャ依存の挙動、ビルドの通り方、パッケージの揃い具合といったソフトウェア面の先行検証には十分実用的です。

## 設計上の位置づけ

stub は genpack エコシステムの中では異色の存在です。genpack イメージとして構築・起動されますが、目的は genpack 以外の OS を立ち上げることにあります。genpack-init のプラグイン機構 (pybind11 + Python) と vm コマンドの仮想ディスク管理を活用し、QEMU/KVM 環境で多数の異なるディストリビューションの VM を共通の手順でプロビジョニングする統一的な環境を提供しています。

## ソースリファレンス

このドキュメントは以下のリポジトリのスナップショットに基づいて作成されました:

- [genpack-artifacts/stub @ 54470f6](https://github.com/genpack-artifacts/stub/tree/54470f6d961a2422f3af228a5e1de005458b07e4)
