# genpack-install CLI リファレンス

## 概要

`genpack-install` は genpack で生成した SquashFS システムイメージを物理ディスク、ISO イメージ、ZIP アーカイブにデプロイするためのツールです。

- GitHub: [wbrxcorp/genpack-install](https://github.com/wbrxcorp/genpack-install)

```bash
genpack-install [オプション] [system_image]
```

**root 権限が必要です。**

## オプション

### 位置引数

| 引数 | 必須 | 説明 |
|---|---|---|
| `system_image` | 動作モードによる | システムイメージファイル（SquashFS） |

セルフアップデートモードでは必須です。`--disk`、`--cdrom`、`--zip` モードでは省略可能で、省略時は現在インストールされているシステムイメージが使用されます。

### 名前付きオプション

| オプション | 型 | デフォルト | 説明 |
|---|---|---|---|
| `--disk <PATH>` | 文字列 | (なし) | ディスクデバイスパス。`list` を指定するとインストール可能なディスクの一覧を表示 |
| `--cdrom <PATH>` | 文字列 | (なし) | 作成する ISO9660 イメージのパス |
| `--zip <PATH>` | 文字列 | (なし) | 作成する ZIP アーカイブのパス |
| `--system-cfg <PATH>` | パス | (なし) | 指定した system.cfg ファイルをインストール |
| `--system-ini <PATH>` | パス | (なし) | 指定した system.ini ファイルをインストール |
| `--label <NAME>` | 文字列 | (なし) | ブートパーティションまたは ISO イメージのボリュームラベル |
| `--gpt` | フラグ | false | MBR の代わりに常に GPT を使用 |
| `--superfloppy` | フラグ | false | パーティショニングせずディスク全体を使用 |
| `--no-esp` | フラグ | false | ブートパーティションを ESP としてマークしない |
| `--additional-boot-files <PATH>` | パス | (なし) | 追加のブートファイルを含む ZIP アーカイブ |
| `-y` | フラグ | false | 確認プロンプトをスキップ |
| `--debug` | フラグ | false | デバッグメッセージを表示 |

## 動作モード

genpack-install は引数の組み合わせにより 4 つの動作モードを持ちます。

### セルフアップデート（引数のみ、オプションなし）

```bash
genpack-install <system_image>
```

稼働中のシステムのシステムイメージをアトミックに更新します。`--disk`、`--cdrom`、`--zip` のいずれも指定しない場合にこのモードで動作します。

**更新手順:**

1. 現在のシステムイメージのパスを特定（ブートパーティションの `system.img` またはデータパーティションの `system`）
2. 新しいシステムイメージを検証
3. ブートファイル（カーネル、initramfs、ブートローダー）を更新
4. アトミックなリネーム操作で切り替え:
   - 既存の `system.old` を削除（存在する場合）
   - 新しいイメージを `system.new` としてコピー
   - 現在のイメージを `system.cur` にリネーム（ロールバック用に保持）
   - `system.new` を本来のイメージパスにリネーム
   - `sync` を実行

失敗時は `system.cur` から自動復旧を試みます。

### ディスクインストール（--disk）

```bash
genpack-install --disk=<デバイスパス> [オプション] [system_image]
genpack-install --disk=list
```

物理ディスクにシステムイメージをインストールします。

`--disk=list` を指定すると、インストール可能なディスクの一覧を表示します。読み取り専用デバイス、マウント済みデバイス、4GiB 未満のデバイスは除外されます。

**パーティショニング:**

- **MBR/GPT の自動選択**: ディスクが 2TiB 以下かつ論理セクタサイズが 512 バイトの場合は MBR、それ以外は GPT が選択されます
- `--gpt`: 条件に関わらず GPT を強制使用
- `--superfloppy`: パーティションテーブルを作成せず、ディスク全体を FAT32 としてフォーマット（4GiB 未満のイメージのみ）

**通常モード（パーティショニングあり）のレイアウト:**

1. **ブートパーティション**（FAT32）: カーネル、initramfs、ブートローダー、4GiB 未満のシステムイメージを格納
2. **データパーティション**（Btrfs）: 4GiB 以上のシステムイメージを格納。ラベルは `data-{ブートパーティションUUID}`

`--no-esp` を指定すると、ブートパーティションに ESP（EFI System Partition）フラグを付与しません。一部のブートローダーが ESP フラグを嫌う場合に使用します（MBR 時のみ有効）。

インストール前に確認プロンプトが表示されます。`-y` で確認をスキップできます。

### ISO イメージ作成（--cdrom）

```bash
genpack-install --cdrom=<出力パス> [--label=<ラベル>] [system_image]
```

ブータブル ISO9660 イメージを作成します。xorriso（libisoburn）がインストールされている必要があります。

- **BIOS ブート**: El Torito（`eltorito-bios.img` が存在する場合）
- **EFI ブート**: EFI パーティション付加（`eltorito-efi.img` が存在する場合）
- 両方のイメージが存在する場合はデュアルブート ISO が生成されます

`--label` を省略した場合、ボリュームラベルは `GENPACK` になります。

### ZIP アーカイブ作成（--zip）

```bash
genpack-install --zip=<出力パス> [system_image]
```

システムイメージとブートファイルを含む ZIP アーカイブを作成します。

**ZIP に含まれるファイル:**

- `system.img` — システムイメージ
- `system.cfg` — システム設定（`--system-cfg` 指定時）
- `system.ini` — システム設定（`--system-ini` 指定時）
- Raspberry Pi のブートファイル（Raspberry Pi イメージの場合）

## ブートローダー

genpack-install は GRUB をブートローダーとして使用します。ブートローダーファイルは以下の順序で検索されます:

1. システムイメージ内の `/usr/lib/genpack-install/`
2. ホスト側の `/usr/local/lib/genpack-install/`
3. ホスト側の `/usr/lib/genpack-install/`

**インストールされるファイル:**

- **EFI ブートローダー**: `boot*.efi` ファイルが `efi/boot/` にコピーされます
- **BIOS ブートローダー**: `boot.img`、`core.img`、`grub.cfg` が存在し `grub-bios-setup` が利用可能な場合にインストールされます

**対応アーキテクチャ:**

| アーキテクチャ | BIOS | UEFI |
|---|---|---|
| x86_64 | boot.img + core.img | bootx64.efi |
| i386 | boot.img + core.img | bootia32.efi |
| aarch64 | — | bootaa64.efi |
| riscv64 | — | bootriscv64.efi |

**Raspberry Pi のサポート:**

システムイメージに `boot/bootcode.bin` が含まれる場合、Raspberry Pi イメージとして扱われます。`boot/` ディレクトリの全ファイルがブートパーティションにコピーされ、`cmdline.txt` の `root=` パラメータが `root=systemimg:auto` に書き換えられます。

**grub.cfg の system.img 検索ロジック:**

1. ブートパーティションに `system.img` が存在すればそれを使用
2. 存在しない場合、`data-{ブートパーティションUUID}` ラベルのパーティションを検索
3. さらに `d-{ブートパーティションUUID}` ラベルを検索
4. 最終手段としてブートパーティション番号から推測（パーティション 1 → パーティション 2 を試行）

## パーティション構成

### ブートパーティション（FAT32）

- ブートローダー（GRUB EFI ファイル、BIOS イメージ）
- カーネル（`boot/kernel`）と initramfs（`boot/initramfs`）
- `grub.cfg`
- `system.cfg` / `system.ini`（指定時）
- **4GiB 未満のシステムイメージ**: `system.img` として格納

ブートパーティションサイズは、システムイメージが 4GiB 未満の場合は `max(4, image_size_gib * 3 + 1)` GiB、4GiB 以上の場合は 1 GiB です。

### データパーティション（Btrfs）

- `--superfloppy` 使用時は作成されません
- ラベル: `data-{ブートパーティションUUID}`
- **4GiB 以上のシステムイメージ**: `system` として格納

## システムイメージの検証

genpack-install はインストール前にシステムイメージの検証を行います:

1. `.genpack/` ディレクトリが存在すること
2. 以下のいずれかを満たすこと:
   - `boot/kernel` と `boot/initramfs` が存在する（通常のイメージ）
   - `boot/bootcode.bin` が存在する（Raspberry Pi イメージ）

検証に通過すると、`.genpack/artifact` と `.genpack/variant` の内容が表示されます。

## ソースリファレンス

このドキュメントは以下のリポジトリのスナップショットに基づいて作成されました:

- [wbrxcorp/genpack-install @ 4246185](https://github.com/wbrxcorp/genpack-install/tree/4246185bb8c5b32f809fa482a28aa5c39caf5b3e)
