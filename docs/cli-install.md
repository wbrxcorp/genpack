# genpack-install CLI リファレンス

## 概要

genpack で生成した SquashFS システムイメージをデプロイするためのツール群です。目的ごとに 3 つのコマンドに分かれています。

- GitHub: [wbrxcorp/genpack-install](https://github.com/wbrxcorp/genpack-install)

| コマンド | 役割 | root 権限 |
|---|---|---|
| `genpack-install` | 物理ディスクへのインストール、稼働中システムのセルフアップデート | **必要** |
| `genpack-mkiso` | ブータブル ISO9660 イメージの作成 | 不要 |
| `genpack-mkzip` | システムイメージとブートファイルの ZIP アーカイブ作成 | 不要 |

`genpack-mkiso` / `genpack-mkzip` はシステムイメージを libsquashfs で直接読むため、ループバックマウントを行いません。ビルドホスト上で一般ユーザーとして実行できます。外部コマンドの起動も行いません（xorriso も unsquashfs も呼びません）。

これらは同一パッケージから提供されますが、ebuild の `install` / `iso` / `zip` USE フラグで個別に有効化できます。ISO や ZIP を生成しないアーティファクトでは `iso` / `zip` を外すことで、libisofs や minizip を持ち込まずに済みます。

---

## genpack-install

```bash
genpack-install [オプション] [system_image]
```

**root 権限が必要です。**

### 位置引数

| 引数 | 必須 | 説明 |
|---|---|---|
| `system_image` | 動作モードによる | システムイメージファイル（SquashFS） |

セルフアップデートモードでは必須です。`--disk` モードでは省略可能で、省略時は現在インストールされているシステムイメージが使用されます。

### 名前付きオプション

| オプション | 型 | デフォルト | 説明 |
|---|---|---|---|
| `--disk <PATH>` | 文字列 | (なし) | ディスクデバイスパス。`list` を指定するとインストール可能なディスクの一覧を表示 |
| `--system-cfg <PATH>` | パス | (なし) | 指定した system.cfg ファイルをインストール |
| `--system-ini <PATH>` | パス | (なし) | 指定した system.ini ファイルをインストール |
| `--label <NAME>` | 文字列 | (なし) | ブートパーティションのボリュームラベル |
| `--gpt` | フラグ | false | MBR の代わりに常に GPT を使用 |
| `--superfloppy` | フラグ | false | パーティショニングせずディスク全体を使用 |
| `--no-esp` | フラグ | false | ブートパーティションを ESP としてマークしない |
| `--additional-boot-files <PATH>` | パス | (なし) | 追加のブートファイルを含む ZIP アーカイブ |
| `-y` | フラグ | false | 確認プロンプトをスキップ |
| `--debug` | フラグ | false | デバッグメッセージを表示 |

### セルフアップデート（`--disk` なし）

```bash
genpack-install <system_image>
```

稼働中のシステムのシステムイメージをアトミックに更新します。

**更新手順:**

1. 現在のシステムイメージのパスを特定（ブートパーティションの `system.img` またはデータパーティションの `system`）
2. 新しいシステムイメージを検証
3. ブートファイル（ブートローダー）を更新
4. アトミックなリネーム操作で切り替え:
   - 既存の `system.old` を削除（存在する場合）
   - 新しいイメージを `system.new` としてコピー
   - 現在のイメージを `system.cur` にリネーム（ロールバック用に保持）
   - `system.new` を本来のイメージパスにリネーム
   - `sync` を実行

失敗時は `system.cur` から自動復旧を試みます。

### ディスクインストール（`--disk`）

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

1. **ブートパーティション**（FAT32）: ブートローダー、4GiB 未満のシステムイメージを格納
2. **データパーティション**（Btrfs）: 4GiB 以上のシステムイメージを格納。ラベルは `data-{ブートパーティションUUID}`

`--no-esp` を指定すると、ブートパーティションに ESP（EFI System Partition）フラグを付与しません。一部のブートローダーが ESP フラグを嫌う場合に使用します（MBR 時のみ有効）。

インストール前に確認プロンプトが表示されます。`-y` で確認をスキップできます。

---

## genpack-mkiso

```bash
genpack-mkiso [オプション] <出力ISOパス> <system_image>
```

ブータブル ISO9660 イメージを作成します。**root 権限は不要です。**

| オプション | 型 | デフォルト | 説明 |
|---|---|---|---|
| `--label <NAME>` | 文字列 | `GENPACK` | ISO9660 イメージのボリュームラベル |
| `--add <DEST=SRC>` | 文字列 | (なし) | ローカルファイル `SRC` を ISO 内の `DEST` として追加。複数指定可 |
| `--debug` | フラグ | false | デバッグメッセージを表示 |

```bash
genpack-mkiso --label=MYSYS out.iso ./myimage-x86_64.squashfs
genpack-mkiso --add=system.cfg=./mycfg out.iso ./myimage-x86_64.squashfs
```

**ISO の構成:**

| ISO 内パス | 内容 |
|---|---|
| `/system.img` | システムイメージ |
| `/boot/grub/grub.cfg` | ブートローダーの grub.cfg |
| `/boot/grub/i386-pc/eltorito.img` | BIOS ブート用 El Torito イメージ（`eltorito-bios.img` がある場合） |
| 追記パーティション 2 (0xEF) | EFI ブート用 FAT イメージ（`eltorito-efi.img` がある場合） |

- **BIOS ブート**: El Torito no-emulation + boot info table
- **EFI ブート**: 追記した FAT パーティションを El Torito の platform_id 0xEF エントリとして参照
- 両方のイメージが存在する場合はデュアルブート ISO が生成されます。どちらも存在しない場合は警告を表示し、起動不可能な ISO を生成します

ISO の生成には libisofs を直接使用します。xorriso（libisoburn）は不要です。

> **注意:** ISO に `system.cfg` を置いても、イメージ内に `/boot/grub/grub.cfg` を持つアーティファクトでは読まれません。ブートローダーの grub.cfg は `loopback` 直後にイメージ内 grub.cfg があれば `configfile` で処理を委譲してしまい、`source ($BOOT_PARTITION)/system.cfg` はその後ろにあるためです。

---

## genpack-mkzip

```bash
genpack-mkzip [オプション] <出力ZIPパス> <system_image>
```

システムイメージとブートファイルを ZIP アーカイブにまとめます。**root 権限は不要です。**

| オプション | 型 | デフォルト | 説明 |
|---|---|---|---|
| `--add <DEST=SRC>` | 文字列 | (なし) | ローカルファイル `SRC` をアーカイブ内の `DEST` として追加。複数指定可 |
| `--debug` | フラグ | false | デバッグメッセージを表示 |

**ZIP に含まれるファイル:**

- `system.img` — システムイメージ
- Raspberry Pi のブートファイル（Raspberry Pi イメージの場合、イメージ内 `boot/` 以下を再帰的に格納）
- `--add` で指定したファイル

ZIP64 は使用しません。格納対象ファイルの合計サイズが 4GiB 以上になる場合は、生成を開始せずエラーになります。

---

## `--add=DEST=SRC`

`genpack-mkiso` と `genpack-mkzip` に共通のオプションです。

- `DEST` はイメージ／アーカイブ内のパス、`SRC` はローカルファイルです。**最初の `=` で分割します**（`SRC` のパスに `=` が含まれていても構いません）
- 省略形（`--add=file` のような `=` なし）は認められません。常に `DEST=SRC` の形が必要です
- `SRC` は通常ファイルのみです。ディレクトリを指定するとエラーになります
- `DEST` にサブディレクトリを含めてよく、中間ディレクトリは自動生成されます
- `DEST` はパスを正規化してから重複判定されます。正規化後に同じ `DEST` となる指定は警告を表示して後勝ちになります
- `system.img` やブートファイルなど、ツールがあらかじめ配置するパスと重複した場合も警告を表示して後勝ちになります。必須ファイルを上書きして起動不能な成果物を作る可能性は利用者の責任です

旧 `genpack-install --cdrom` / `--zip` にあった `--system-cfg` / `--system-ini` は `--add` に一本化されています。

```bash
genpack-mkiso --add=system.cfg=./mycfg out.iso image.squashfs
genpack-mkzip --add=system.ini=./system.ini-for-thisvariant out.zip image.squashfs
```

## 出力ファイルの扱い

`genpack-mkiso` / `genpack-mkzip` は、出力先と同じディレクトリに一時ファイルを作ってそこに書き込み、すべての入力を読み終えて完全な成果物になってから rename で指定された出力先へ置き換えます。失敗時は一時ファイルを削除し、既存の出力ファイルには手を触れません。

出力先がシステムイメージまたは `--add` の `SRC` と同じファイル（シンボリックリンク／ハードリンク経由を含む）である場合は、入力を破壊しないよう生成開始前にエラーになります。

---

## ブートローダー

genpack-install / genpack-mkiso は GRUB をブートローダーとして使用します。ブートローダーファイルは以下の順序で検索されます:

1. システムイメージ内の `/usr/lib/genpack-install/`
2. ホスト側の `/usr/local/lib/genpack-install/`
3. ホスト側の `/usr/lib/genpack-install/`

**genpack-install がインストールするファイル:**

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

システムイメージに `boot/bootcode.bin` が含まれる場合、Raspberry Pi イメージとして扱われます。`boot/` ディレクトリの全ファイルがブートパーティション（`genpack-install --disk`）または ZIP アーカイブ（`genpack-mkzip`）に格納され、`cmdline.txt` の `root=` パラメータが `root=systemimg:auto` に書き換えられます。`rootfstype=` は除去されます。

`genpack-install --disk` では、既にブートパーティションに `cmdline.txt` / `config.txt` が存在する場合は上書きしません。

**grub.cfg の system.img 検索ロジック:**

1. ブートパーティションに `system.img` が存在すればそれを使用
2. 存在しない場合、`data-{ブートパーティションUUID}` ラベルのパーティションを検索
3. さらに `d-{ブートパーティションUUID}` ラベルを検索
4. 最終手段としてブートパーティション番号から推測（パーティション 1 → パーティション 2 を試行）

## パーティション構成

### ブートパーティション（FAT32）

- ブートローダー（GRUB EFI ファイル、BIOS イメージ）
- `grub.cfg`
- `system.cfg` / `system.ini`（指定時）
- **4GiB 未満のシステムイメージ**: `system.img` として格納

ブートパーティションサイズは、システムイメージが 4GiB 未満の場合は `max(4, image_size_gib * 3 + 1)` GiB、4GiB 以上の場合は 1 GiB です。

カーネル（`boot/kernel`）と initramfs（`boot/initramfs`）はブートパーティションには置かれません。GRUB が `loopback` でシステムイメージをマウントし、その中から直接読み込みます。

### データパーティション（Btrfs）

- `--superfloppy` 使用時は作成されません
- ラベル: `data-{ブートパーティションUUID}`
- **4GiB 以上のシステムイメージ**: `system` として格納

## システムイメージの検証

3 つのツールはいずれも処理前にシステムイメージの検証を行います:

1. `.genpack/` ディレクトリが存在すること
2. 以下のいずれかを満たすこと:
   - `boot/kernel` と `boot/initramfs` が存在する（通常のイメージ）
   - `boot/bootcode.bin` が存在する（Raspberry Pi イメージ）

検証に通過すると、`.genpack/artifact` と `.genpack/variant` の内容が表示されます。

## ソースリファレンス

このドキュメントは以下のリポジトリのスナップショットに基づいて作成されました:

- [wbrxcorp/genpack-install](https://github.com/wbrxcorp/genpack-install)（`isozip` ブランチ）
