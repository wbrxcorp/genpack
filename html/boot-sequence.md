# genpack イメージの起動機序

## 概要

genpack で生成された SquashFS イメージは、ディスクにインストールされた実機環境と、`vm` コマンドによる QEMU/KVM 準仮想化環境の 2 つの方法で起動できます。いずれの場合も共通の initramfs（dracut-genpack）が overlayfs ルートを構成し、genpack-init が system.ini に基づいて初期設定を行った後に systemd へ制御を渡す、という流れは同じです。

本ドキュメントでは両方式の起動シーケンスを詳細に解説します。

## system.img 方式（ディスクインストール）

### ディスクレイアウト

`genpack-install` でディスクにインストールすると、以下のパーティション構成が作られます。

| パーティション | ファイルシステム | 内容 |
|---|---|---|
| 1: ブートパーティション | FAT32 | EFI ブートローダー、カーネル、initramfs、system.img（4GiB 未満の場合）、system.ini |
| 2: データパーティション | Btrfs | overlayfs upper 層、system（4GiB 以上の場合） |

ブートパーティションのサイズはイメージサイズから自動計算されます。`--superfloppy` オプションを指定すると、パーティションテーブルを作成せずディスク全体を FAT32 として使用します（データパーティションなし）。

MBR と GPT はディスクサイズに応じて自動選択されます（2TiB 以下かつ 512 バイトセクタなら MBR、それ以外は GPT）。

### 起動シーケンス

```
UEFI/BIOS
  → GRUB (efi/boot/bootx64.efi 等)
    → Linux カーネル (root=systemimg:<UUID> or root=systemimg:auto)
      → initramfs (dracut-genpack)
        → overlayfs ルート構成
          → genpack-init (PID 1)
            → Python プラグインで初期設定
              → exec /sbin/init (systemd)
```

### initramfs の処理（dracut-genpack）

dracut-genpack は 2 つのフックで構成されます。

**cmdline フック（check-systemimg-root.sh）:**

カーネルコマンドラインの `root=` パラメータを確認します。`root=systemimg:...` 形式であれば、genpack のブートシーケンスを開始します。

**mount フック（mount-genpack.sh）:**

1. **ブートパーティションの検出とマウント**
   - `root=systemimg:<UUID>` の場合: 指定 UUID のパーティションをマウント
   - `root=systemimg:auto` の場合: 全 FAT パーティションを走査し、`system.img` を含むものを検出
   - FAT の場合は `fsck.fat -aw` で自動修復後にマウント
   - マウントポイント: `/run/initramfs/boot`

2. **データパーティションの検出とマウント**
   - ブートパーティションの UUID を基にラベル `data-<UUID>` で検索
   - フォールバック: `d-<UUID>`, `wbdata-<UUID>`、またはブートパーティションの次のパーティション番号 [^2]
   - 見つからない場合は virtiofs (`fs` タグ) を試行 [^3]
   - それでもマウントできない場合は tmpfs にフォールバック（トランジェントモード）
   - `genpack.transient` カーネルパラメータで明示的にトランジェントモードを指定可能
   - マウントポイント: `/run/initramfs/rw`

3. **SquashFS イメージのマウント**
   - ブートパーティション上の `/run/initramfs/boot/system.img` を検索
   - 見つからない場合はデータパーティション上の `/run/initramfs/rw/system` を使用
   - read-only で `/run/initramfs/ro` にマウント

4. **overlayfs の構成**
   - lowerdir: `/run/initramfs/ro`（SquashFS、読み取り専用）
   - upperdir: `/run/initramfs/rw/root`（Btrfs または tmpfs） [^5]
   - workdir: `/run/initramfs/rw/work`
   - `$NEWROOT` に overlay をマウント
   - lower 層の `/usr` タイムスタンプを upper 層に同期 [^4]

5. **シャットダウンプログラムの配置**
   - `/run/initramfs/ro/usr/libexec/genpack-shutdown` を `/run/initramfs/shutdown` にコピー
   - シャットダウン時に overlayfs と SquashFS を安全にアンマウントするために使用

### genpack-init

dracut の initramfs 処理が完了すると、`$NEWROOT` にルートが切り替わり、`/usr/bin/genpack-init` が PID 1 として起動します（`init=/usr/bin/genpack-init` が dracut モジュールにより cmdline に追加される）。

genpack-init は C++ + pybind11 で実装されており、以下の処理を行います。

1. `/run/initramfs/boot/system.ini`（ブートパーティション経由）または `/run/initramfs/rw/system.ini`（データパーティション経由）を読み込む
2. `/usr/lib/genpack-init/*.py` 内の全 Python モジュールをファイル名順にロード
3. 各モジュールの `configure(ini)` 関数を実行（タイムゾーン、ロケール、バナー表示、マシン ID 生成など）
4. `exec /sbin/init` で systemd に制御を引き渡す

## パラバーチャル方式（vm コマンド）

### vm コマンドの概要

`vm` コマンドは genpack イメージを QEMU/KVM で直接起動するためのツールです。ディスクへのインストールは不要で、SquashFS ファイルをそのまま指定して起動できます。

### 起動シーケンス

```
vm run system.squashfs
  → SquashFS からカーネルと initramfs を抽出 (memfd)
    → qemu-system-<arch> -kernel <kernel> -initrd <initramfs>
       -append "root=/dev/vda ro ..."
       -drive file=system.squashfs,...,serial=system  (virtio-blk)
       -drive file=data,...,serial=data  (virtio-blk, あれば)
      → initramfs (dracut-genpack)
        → overlayfs ルート構成
          → genpack-init (PID 1)
            → Python プラグインで初期設定
              → exec /sbin/init (systemd)
```

### カーネルと initramfs の抽出

vm コマンドは squashfuse ライブラリを使用して、SquashFS イメージの `/boot/` ディレクトリからカーネルと initramfs を直接読み出します。ディスクに展開する必要はなく、`memfd_create` で作成したメモリ上のファイルディスクリプタに書き出して QEMU に渡します。

検索順序:
1. `boot/kernel` または `boot/vmlinuz`（固定名）
2. `boot/kernel-*` または `boot/vmlinuz-*`（タイムスタンプが最新のもの）

initramfs も同様に `boot/initramfs`, `boot/initramfs.img`, `boot/initrd.img` の順で検索されます。

カーネルバイナリの ELF ヘッダまたは PE ヘッダからアーキテクチャ（x86_64, aarch64, riscv64 等）を自動判定し、対応する `qemu-system-<arch>` を起動します。

### QEMU の起動構成

vm コマンドは QEMU のダイレクトカーネルブート（`-kernel`, `-initrd`, `-append`）を使用します。ブートローダーは介在しません。

**カーネルコマンドライン:**

```
root=/dev/vda ro net.ifnames=0 systemd.firstboot=0 systemd.hostname=<vmname> console=...
```

- `root=/dev/vda`: SquashFS イメージが virtio-blk デバイスとして提供される
- virtiofs モードの場合は `root=fs rootfstype=virtiofs rw`

**ディスクの提供:**

| virtio デバイス | シリアル | 内容 |
|---|---|---|
| vda | system | SquashFS イメージ（読み取り専用） |
| vdb | data | データディスク（あれば） |
| vdc | swap | スワップファイル（あれば） |

SquashFS イメージは `virtio-blk-pci` デバイスとして read-only で接続されます。initramfs の `mount-genpack.sh` は `root=block:*` ではなくカーネルコマンドラインの `root=/dev/vda` を参照し、`/dev/vda` を直接 SquashFS として `/run/initramfs/ro` にマウントします。

**virtiofs モード:**

vm コマンドは virtiofs もサポートしています。virtiofsd を起動してホストのディレクトリをゲストに共有し、overlayfs の upper 層として使用できます。virtiofs 使用時、initramfs は `root=fs rootfstype=virtiofs rw` に基づいて virtiofs をルートとしてマウントします。

### vm サービスモード

`vm` コマンドには `vm.ini` ファイルを読み取るサービスモードがあります。各 VM のディレクトリ構成は以下の通りです。

```
/var/vm/<vmname>/
├── vm.ini        # VM 設定（メモリ、CPU、ネットワーク等）
├── system        # SquashFS イメージ（シンボリックリンク可）
├── data          # データディスク（オプション）
├── swapfile      # スワップ（オプション）
├── fs/           # virtiofs 共有ディレクトリ
├── docker        # Docker 用ディスク（オプション、serial=docker）
└── mysql         # MySQL 用ディスク（オプション、serial=mysql）
```

`vm.ini` の `type=genpack`（デフォルト）でダイレクトカーネルブートが使用されます。

### system.img 方式との共通点と相違点

| 項目 | system.img 方式 | パラバーチャル方式 |
|---|---|---|
| ブートローダー | GRUB (EFI/BIOS) | なし（ダイレクトカーネルブート） |
| カーネル格納場所 | ブートパーティション上のファイル | SquashFS 内から memfd に抽出 |
| root= パラメータ | `systemimg:<UUID>` or `systemimg:auto` | `/dev/vda` |
| SquashFS の提供 | ブート/データパーティション上のファイル | virtio-blk デバイス |
| データ永続化 | Btrfs パーティション | data ディスクファイルまたは virtiofs |
| トランジェントモード | `genpack.transient` カーネルパラメータ | data ディスクを指定しなければ自動 |
| system.ini | FAT32 パーティション上 | virtiofs 経由または fw_cfg |
| initramfs の動作 | 共通（dracut-genpack） | 共通（dracut-genpack） |
| genpack-init の動作 | 共通 | 共通 |

## シャットダウン

genpack イメージのシャットダウンは通常の systemd シャットダウンプロセスの後、dracut の initramfs に制御が戻り、`/run/initramfs/shutdown`（genpack-shutdown）が実行されます。genpack-shutdown は以下を行います。

1. `/oldroot` 以下の全マウントポイントを逆順にアンマウント
2. `/run/initramfs/rw`（データパーティション）と `/run/initramfs/boot`（ブートパーティション）を安全に移動・アンマウント
3. ブートパーティション上の `boottime.txt` を削除 [^1]
4. `reboot(2)` または `poweroff` を実行

---

[^1]: boottime.txt はブート時に作成されます。clean shutdown 時に削除されるため、次回ブート時にこのファイルが残存していれば前回の unclean shutdown（クラッシュや電源断）の証拠となります。

[^2]: `d-<UUID>` が現在の正式なラベルフォーマットです（Btrfs のラベル長制限のため短縮形を使用）。`data-<UUID>` および `wbdata-<UUID>` は Walbrix（genpack の前身）時代の互換性のために残されています。

[^3]: systemimg 方式は実機専用ではなく、vm フロントエンドを介さずに QEMU 上で直接実行される場合もあります。このフォールバックにより、baremetal プロファイルのイメージも準仮想化環境で起動可能です。baremetal プロファイルが systemimg の特化として存在するのもこの理由です。

[^4]: systemd は `/usr` のタイムスタンプを参照して `ld.so.cache` の再生成が必要かを判定します。overlayfs では upper 層が存在すると lower 層のタイムスタンプが隠されるため、lower 層の `/usr` タイムスタンプを明示的に upper 層に伝播させる必要があります。

[^5]: 旧バージョンでは upperdir が `rw/rw/root` という冗長なパスでした。`rw/root` に簡略化されましたが、既存環境との互換性のため initramfs は旧パス `rw/rw/root` も引き続き認識します。

## ソースリファレンス

このドキュメントは以下のリポジトリのスナップショットに基づいて作成されました:

- [wbrxcorp/genpack-install @ HEAD](https://github.com/wbrxcorp/genpack-install)
- [wbrxcorp/genpack-overlay @ HEAD](https://github.com/wbrxcorp/genpack-overlay) (sys-kernel/dracut-genpack, genpack/base)
- [wbrxcorp/genpack-init @ HEAD](https://github.com/wbrxcorp/genpack-init)
- [shimarin/vm @ HEAD](https://github.com/shimarin/vm)
