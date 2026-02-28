# genpack — Gentoo ベースの不変システムイメージビルドツールチェーン

## はじめに

genpack は、Gentoo Linux をベースとして用途特化型の **不変 (immutable) システムイメージ** を宣言的に生成・配布・起動するための一連のツール群です。従来の「OS をインストールしてからカスタマイズする」アプローチとは異なり、**設計図 (JSON5) から OS イメージ全体をビルドする**というイメージファクトリの考え方に基づいています。

Docker がアプリケーションコンテナの世界で実現したことを、**OS 全体のレベル**で、しかも**ベアメタル・仮想マシン・組み込み機器を横断して**実現することを目指しています。

## ツールチェーンの構成

```
  設計・定義層             ビルド層               配布・実行層
 ┌───────────────┐    ┌───────────────┐    ┌───────────────────────┐
 │genpack-overlay │    │    genpack     │    │    genpack-install     │
 │ (Gentooオーバー│───▶│  (イメージ     │───▶│  (ディスク書込/ISO/    │
 │  レイ: プロファ│    │   ビルダー)    │    │   セルフアップデート)  │
 │  イル・ebuild) │    └──────┬────────┘    └───────────────────────┘
 └───────────────┘           │                       │
                             │ .squashfs / .img      │
 ┌───────────────┐           ▼                       ▼
 │ genpack-       │    ┌───────────────┐    ┌───────────────────────┐
 │ artifacts      │    │  genpack-init  │    │          vm            │
 │ (各イメージの  │───▶│ (毎回起動時の  │    │  (QEMU/KVMで仮想マシン │
 │  設定定義集)   │    │  プロビジョニ  │    │   として実行)          │
 └───────────────┘    │  ング)         │    └───────────────────────┘
                      └───────────────┘
```

### 各コンポーネント一覧

| コンポーネント | 言語 | 役割 | リポジトリ |
|---|---|---|---|
| **genpack** | Python + C++ | JSON5 設定から SquashFS イメージを生成 | [wbrxcorp/genpack](https://github.com/wbrxcorp/genpack) |
| **genpack-overlay** | Gentoo ebuild/profile | パッケージ定義・プロファイル階層・初期化スクリプト群 | [wbrxcorp/genpack-overlay](https://github.com/wbrxcorp/genpack-overlay) |
| **genpack-init** | C++ + Python (pybind11) | 毎回起動時に system.ini に基づきシステムを構成 | [wbrxcorp/genpack-init](https://github.com/wbrxcorp/genpack-init) |
| **genpack-install** | C++ | イメージをディスク/ISO/ZIP にデプロイ、セルフアップデート | [wbrxcorp/genpack-install](https://github.com/wbrxcorp/genpack-install) |
| **vm** | C++ | genpack イメージを QEMU/KVM 上で実行・管理 | [shimarin/vm](https://github.com/shimarin/vm) |
| **genpack-artifacts** | JSON5 + シェルスクリプト | 具体的なイメージ定義の集合 | [genpack-artifacts](https://github.com/genpack-artifacts) (GitHub Organization) |

---

## genpack — イメージビルダー

[GitHub: wbrxcorp/genpack](https://github.com/wbrxcorp/genpack)

genpack はツールチェーンの中核をなすビルドエンジンです。`genpack.json5` という宣言的な設定ファイルを入力として受け取り、Gentoo Linux の stage3 + Portage を使って最適化された SquashFS イメージを生成します。

### ビルドの仕組み: レイヤードアーキテクチャ

genpack は **lower/upper の 2 層構造** でビルドを行います。

1. **Lower 層**: Gentoo stage3 をベースに、全パッケージを `systemd-nspawn` コンテナ内でコンパイル・インストールする完全なビルド環境
2. **Upper 層**: Lower 層から実行時に必要なファイルだけを選択的にコピーし、ユーザー作成・サービス有効化・カスタムファイル配置などの仕上げを実行
3. **パック**: Upper 層を SquashFS に圧縮して最終イメージを生成

この設計により、コンパイラやヘッダファイルなどビルド時にしか使わないファイルは Lower 層に残り、最終イメージには含まれません。最小限のランタイムイメージが自然に得られます。

### 宣言的な設定

```json5
{
  name: "nextcloud",
  profile: "paravirt",
  packages: [
    "www-apps/nextcloud",
    "dev-db/mysql",
    "dev-lang/php",
    "net-misc/redis"
  ],
  services: ["apache2", "mysqld", "redis"],
  users: [{ name: "nextcloud", uid: 1000 }],
  use: {
    "dev-lang/php": "+mysql +curl +gd +xml +zip"
  },
  compression: "xz"
}
```

パッケージリスト、有効にするサービス、ユーザー定義、USE フラグ、カーネル設定まで、全てがこの 1 ファイルに集約されます。これにより手作業によるシステム構築を排除し、**完全に再現可能なビルド**を実現しています。

### 主要コマンド

| コマンド | 機能 |
|---|---|
| `genpack build` | フルビルド (lower → upper → pack) |
| `genpack lower` | Lower 層のビルド/リビルド |
| `genpack upper` | Upper 層のビルド/リビルド |
| `genpack pack` | SquashFS イメージの生成 |
| `genpack bash [command...]` | Lower 層内の対話シェル / コマンド実行 |
| `genpack archive` | 設定の tar.gz アーカイブを作成 |

### 対応アーキテクチャ

x86_64, aarch64 (ARM64), i686, riscv64 に対応しています。アーキテクチャ固有の設定は `genpack.json5` の `arch` セクションで管理できます。

---

## genpack-overlay — Gentoo オーバーレイ

[GitHub: wbrxcorp/genpack-overlay](https://github.com/wbrxcorp/genpack-overlay)

genpack-overlay は Gentoo のパッケージ管理システム (Portage) を拡張するオーバーレイです。genpack でビルドするイメージの「部品」となるメタパッケージ群と、デプロイ先の違いを吸収するプロファイル階層を提供します。

### プロファイル階層

```
genpack/base (全環境共通: カーネル, init, 基本ツール)
  ├── genpack/systemimg (ベアメタル: ハードウェア検出, ストレージツール)
  │     └── systemimg/baremetal (BIOS/UEFI, デバイスドライバ)
  ├── genpack/paravirt (仮想化: QEMU ゲストエージェント, virtio)
  ├── genpack/gnome (GNOME デスクトップ)
  └── genpack/weston (Wayland コンポジタ)
```

イメージ定義側は `profile: "paravirt"` や `profile: "gnome/baremetal"` を指定するだけで、適切なベース環境が自動的に選択されます。

### パッケージスクリプト

各パッケージは `/usr/lib/genpack/package-scripts/` 以下に初期化スクリプトを配置できます。MySQL のデータディレクトリ初期化、Docker のストレージ設定、SSH ホスト鍵の生成など、パッケージ固有の構成処理がここに定義されています。

---

## genpack-init — 起動時プロビジョニングシステム

[GitHub: wbrxcorp/genpack-init](https://github.com/wbrxcorp/genpack-init)

genpack-init は C++ と Python (pybind11) のハイブリッドで構成された初期化システムです。PID 1 として起動し、**毎回の起動時に** ブートパーティション上の `system.ini` を読み取って Python スクリプト群を実行し、システムを構成します。

### 動作の流れ

1. PID 1 として起動
2. `/run/initramfs/boot/system.ini` (FAT パーティション上) を読み込み
3. `/usr/lib/genpack-init/*.py` の各モジュールの `configure(ini)` 関数を実行
4. ホスト名、ネットワーク、ストレージ、サービス構成などを適用
5. 実際の init (`/sbin/init` = systemd) に exec で移行

### Python に公開されるネイティブ機能

genpack-init は pybind11 を通じて以下のような低レベル操作を Python スクリプトに公開します:

- **ディスク操作**: パーティション情報取得、parted、mkfs、mount/umount
- **プラットフォーム検出**: Raspberry Pi / QEMU の判定
- **ファイルシステム操作**: chown, chmod, chgrp
- **カーネルモジュール**: coldplug (modalias による自動ロード)
- **systemd サービス**: enable/disable

### system.ini 駆動アーキテクチャ

genpack-init の最も重要な設計上の特徴は、**FAT パーティション上の `system.ini` だけでシステム全体の動作をカスタマイズできる**点にあります。

```
ストレージレイアウト:
┌──────────────────────────────────────────────────┐
│ パーティション1: FAT32 (ブート)                   │
│  ├── EFI/                 (ブートローダー)        │
│  ├── system.img           (SquashFS OS イメージ)  │
│  └── system.ini  ← ユーザーが編集する唯一のファイル │
├──────────────────────────────────────────────────┤
│ パーティション2: データ [任意]                     │
└──────────────────────────────────────────────────┘
```

### ルートファイルシステムの構成: overlayfs による柔軟な永続性制御

genpack イメージの initramfs は、起動時にブートストレージ上のデータパーティション（QEMU の場合はデータ用仮想ディスク）の有無を検出し、overlayfs ルートファイルシステムの upper layer を動的に決定します:

- **データパーティションあり** → upper layer に永続ストレージを使用。実行中のファイル変更は再起動後も保持される
- **データパーティションなし** → upper layer に tmpfs を使用。実行中の変更は再起動で消失し、毎回クリーンな状態から開始される（トランジェントモード）

この仕組みにより、同一イメージでありながらデプロイ構成によって動作特性を使い分けることができます。データパーティションを設けない構成ではキオスク端末やデモ環境のような「毎回リセットされる」運用が、データパーティションを設ける構成ではサーバーのような永続的な運用がそれぞれ可能です。いずれの場合も、genpack-init は毎回起動時に system.ini を読んでシステムを構成するため、system.ini の変更は常に次回起動時に反映されます。

### system.ini がもたらす利点

- **誰でも設定変更できる**: FAT32 は Windows/macOS/Linux どの OS でも読み書き可能。INI 形式はメモ帳で編集できる。Linux の専門知識は不要
- **OS の不変性と設定の可変性の完全な分離**: SquashFS は読み取り専用、構成は system.ini に集約。設定が /etc 以下に散在することがない
- **毎回起動時の構成適用**: genpack-init は毎回起動時に system.ini を読んでシステムを構成する。system.ini の変更は必ず次回起動に反映される
- **同一イメージの多目的展開**: 同じイメージを異なる system.ini で異なる用途にデプロイできる
- **物理アクセスによるリカバリ**: ネットワーク設定を誤った場合でも、ストレージを取り出して FAT パーティション上の system.ini を修正するだけで復旧可能
- **OS 更新と設定の独立**: イメージを差し替えても system.ini はそのまま維持される。設定ファイルの上書き問題が発生しない

---

## genpack-install — イメージデプロイツール

[GitHub: wbrxcorp/genpack-install](https://github.com/wbrxcorp/genpack-install)

genpack-install は生成されたシステムイメージを物理ストレージに書き込み、ブート可能な状態にするツールです。

### 動作モード

| モード | 用途 |
|---|---|
| `--disk=<device>` | 物理ディスクへのインストール (パーティショニング + ブートローダー設置) |
| セルフアップデート | 稼働中のシステムのイメージをアトミックに入れ替え |
| `--cdrom=<file>` | ブータブル ISO 9660 イメージの作成 |
| `--zip=<file>` | ZIP アーカイブの作成 |

### マルチアーキテクチャブート対応

BIOS / UEFI (x86_64, i386, ARM64, RISC-V) / Raspberry Pi の各ブート方式に対応した GRUB ブートローダーを生成・配置します。El Torito によるCD/ISOブートもサポートしています。

### アトミックなセルフアップデート

稼働中のシステムのイメージ更新は、以下のアトミックなリネーム操作で実現されます:

```
system     → system.cur  (現在のイメージを退避)
system.new → system      (新しいイメージを有効化)
system.cur → system.old  (前世代を保持 = ロールバック可能)
```

---

## vm — 仮想マシン管理ツール

[GitHub: shimarin/vm](https://github.com/shimarin/vm)

vm は genpack で生成したシステムイメージを QEMU/KVM 上で仮想マシンとして実行・管理するためのコマンドラインツールです。

### 主要コマンド

| コマンド | 機能 |
|---|---|
| `vm run <image>` | システムイメージから VM を起動 |
| `vm service` | vm.ini に基づいて VM をサービスとして実行 |
| `vm console <name>` | VM のシリアルコンソールに接続 |
| `vm stop <name>` | QMP プロトコルによるグレースフルシャットダウン |
| `vm list` | 実行中の VM を一覧表示 |
| `vm ssh user@vm` | vsock 経由で VM に SSH 接続 |
| `vm usb` | USB デバイスの列挙 (XPath クエリ対応) |

### 主な機能

- **ネットワーク**: ユーザーモード / ブリッジ / TAP / MACVTAP / SR-IOV / VDE / マルチキャスト
- **ディスプレイ**: SPICE / VNC / egl-headless
- **GPU**: virtio-gpu 2D / QXL / OpenGL / Vulkan パススルー
- **デバイスパススルー**: USB (XPath フィルタリング) / PCI (VFIO)
- **ファイル共有**: virtiofs / 9pfs
- **通信**: vsock 経由の SSH/SCP

---

## genpack-artifacts — イメージ定義集

[GitHub Organization: genpack-artifacts](https://github.com/genpack-artifacts)

genpack-artifacts は、genpack ツールチェーンを使って構築する具体的なシステムイメージの定義集です。各アーティファクトは個別のリポジトリとして管理されています。

### アーティファクトの構造

各アーティファクトは統一されたディレクトリ構造を持ちます:

```
artifact-name/
├── genpack.json5          # 宣言的イメージ定義
├── files/                 # ルートファイルシステムにマージされるファイル
│   ├── build.d/           # ビルド時実行スクリプト
│   ├── etc/               # 設定ファイル
│   └── boot/              # ブート設定 (grub.cfg 等)
├── kernel/                # カーネルカスタマイズ (任意)
│   └── config.d/          # カーネル設定フラグメント
└── savedconfig/           # Portage savedconfig (アーキテクチャ別)
```

### アーティファクトの例

| カテゴリ | アーティファクト | 用途 |
|---|---|---|
| **デスクトップ** | [gnome](https://github.com/genpack-artifacts/gnome), [streamer](https://github.com/genpack-artifacts/streamer) | GNOME デスクトップ、OBS 配信ワークステーション |
| **ML/AI** | [torch](https://github.com/genpack-artifacts/torch) | PyTorch + ROCm/CUDA 機械学習環境 |
| **クラウド** | [nextcloud](https://github.com/genpack-artifacts/nextcloud), [owncloud](https://github.com/genpack-artifacts/owncloud) | セルフホストクラウドストレージ |
| **プロジェクト管理** | [redmine](https://github.com/genpack-artifacts/redmine) | Redmine プロジェクト管理 |
| **ネットワーク** | [vpnhub](https://github.com/genpack-artifacts/vpnhub), [walbrix](https://github.com/genpack-artifacts/walbrix) | VPN ゲートウェイ、ネットワークアプライアンス |
| **セキュリティ** | [suricata](https://github.com/genpack-artifacts/suricata), [borg](https://github.com/genpack-artifacts/borg) | IDS、バックアップサーバー |
| **組み込み** | [camera](https://github.com/genpack-artifacts/camera) | モーション検知カメラシステム |
| **ユーティリティ** | [rescue](https://github.com/genpack-artifacts/rescue), [stub](https://github.com/genpack-artifacts/stub) | システムリカバリ、最小ビルド環境 |

最小構成 (rescue: 十数パッケージ) からフルデスクトップ (gnome: 数百パッケージ) まで、全て同じ `genpack.json5` + `files/` のパターンで定義されています。

---

## 設計思想

### 1. 宣言的イメージ定義 (Infrastructure as Code)

全てのイメージは `genpack.json5` で宣言的に定義されます。パッケージ、USE フラグ、ユーザー、サービス、カーネル設定まで 1 ファイルに集約されており、手作業を排除した再現可能なビルドを実現しています。

### 2. 不変イメージと柔軟な永続性 (Immutable Image, Flexible Persistence)

最終成果物は読み取り専用の SquashFS です。システムの更新は既存環境の変更ではなく新しいイメージのビルドとアトミックな入れ替えで行われます。実行時のルートファイルシステムは overlayfs で構成され、データパーティションの有無により upper layer が永続ストレージか tmpfs かが自動的に決まります。データパーティションがない場合は毎回クリーンな状態から起動するため構成ドリフトが原理的に発生せず、データパーティションがある場合はサーバー用途に適した永続的な運用が可能です。

### 3. OS とユーザー設定の完全な分離

OS イメージ (SquashFS) は不変、ユーザー設定 (system.ini) は FAT パーティション上のテキストファイル。この 2 つが完全に分離されているため、OS の更新で設定が失われることがなく、設定変更に Linux の専門知識も不要です。

### 4. 毎回起動時の構成適用

genpack-init は初回だけでなく毎回の起動時に system.ini を読んでシステムを構成します。これにより、system.ini への変更は常に次回起動時に反映されます。さらに、データパーティションを設けないトランジェントモードでは overlayfs の upper layer が tmpfs となるため、実行中の変更は再起動で自動的に消失し、毎回クリーンな状態 + system.ini の設定で起動します。

### 5. レイヤードビルドによる最小イメージ

Lower 層 (ビルド環境) と Upper 層 (ランタイム) を分離し、実行時に不要なコンパイラやヘッダを自然に除外します。

### 6. Gentoo の選択

ベースに Gentoo を採用することで:
- **USE フラグ** によるパッケージ単位の機能制御で不要な依存を徹底排除
- **ソースビルド** でターゲットに最適化されたバイナリを生成
- **プロファイル階層** でデプロイ先の差異を体系的に管理
- **Portage のオーバーレイ機構** でカスタムパッケージを自然に統合

### 7. マルチアーキテクチャ・マルチターゲット

x86_64 / aarch64 / i686 / riscv64 のアーキテクチャと、BIOS / UEFI / Raspberry Pi のブート方式をツールチェーン全体で横断的にサポートしています。

---

## ワークフロー全体像

```
1. 設計: genpack.json5 を記述
   ↓
2. ビルド: genpack build
   ├── Lower層: stage3 + Portage でコンパイル (systemd-nspawn)
   ├── Upper層: ランタイムファイルのみ抽出 + カスタマイズ
   └── Pack: SquashFS 圧縮 → system-x86_64.squashfs
   ↓
3. デプロイ (いずれかを選択)
   ├── genpack-install --disk=/dev/sdX  (物理ディスク)
   ├── genpack-install --cdrom=out.iso  (ISO イメージ)
   └── vm run system-x86_64.squashfs   (仮想マシン)
   ↓
4. 起動時: genpack-init が system.ini を読んでシステムを構成
   ↓
5. 運用: system.ini を編集して再起動 = 設定変更
         新イメージでセルフアップデート = OS 更新
```

---

## genpack の独自性について

NixOS、Yocto、Buildroot、mkosi、OSTree など同様の目的を持つツールは数多く存在しますが、genpack は **「高度に最適化された Linux イメージを、非技術者でも運用できるアプライアンスとして配布する」** という独自の立ち位置を持っています。

その核となるのは、FAT32 上の INI ファイルという意図的に原始的な構成インターフェース、毎回起動時の構成適用とハードウェア検出による動作モードの自動決定、可変システムの代表である Gentoo の不変イメージへの転用、そして pybind11 によるプラグイン型 init といったアイディアの組み合わせです。

既存ツールとの詳しい比較については [genpackが提供する価値の独自性についての対話](uvp.md) を参照してください。

## ソースリファレンス

このドキュメントは以下のリポジトリのスナップショットに基づいて作成されました:

- [wbrxcorp/genpack @ 6aa1e82](https://github.com/wbrxcorp/genpack/tree/6aa1e8244e53499cacb3b15e78ba215c3a6a23a9)
- [wbrxcorp/genpack-overlay @ 45a7e1e](https://github.com/wbrxcorp/genpack-overlay/tree/45a7e1e7440104f6592150261858c4ddd498d15b)
- [wbrxcorp/genpack-init @ 721060c](https://github.com/wbrxcorp/genpack-init/tree/721060c832335b240e6bd6998779235e5185468a)
- [wbrxcorp/genpack-install @ 4246185](https://github.com/wbrxcorp/genpack-install/tree/4246185bb8c5b32f809fa482a28aa5c39caf5b3e)
- [shimarin/vm @ 2297086](https://github.com/shimarin/vm/tree/2297086ffe725a554e4577ad43d2a74e5e34d97a)
