# genpack-init スクリプト ガイド

## 概要

genpack-init は genpack システムイメージの起動プロセスで PID 1 として動作する C++ + pybind11 製の初期化プログラムです。dracut-genpack が構築した overlayfs ルートに切り替わった直後に実行され、`/usr/lib/genpack-init/*.py` に配置された Python スクリプトを順次呼び出してシステムを設定した後、`/sbin/init`（systemd）に制御を引き渡します。

このドキュメントでは、genpack-init スクリプトの書き方・使える API・配布方法・注意点を解説します。

## 実行タイミングと文脈

```
dracut-genpack (initramfs)
  ↓ overlayfs ルート構築完了
genpack-init (PID 1)
  ↓ /usr/lib/genpack-init/*.py を順に実行
exec /sbin/init (systemd)
```

スクリプトが実行される時点での状態:

- ルートは overlayfs（lowerdir = SquashFS, upperdir = データパーティションまたは tmpfs）
- `/run/initramfs/boot/` にブートパーティション（FAT32）がマウント済み
- `/run/initramfs/ro/` に SquashFS が読み取り専用でマウント済み
- `/run/initramfs/rw/` にデータパーティション（またはフォールバックの tmpfs）がマウント済み
- UID 0（root）、ネットワーク未起動、systemd 未起動

## スクリプトの配置と命名

スクリプトは `/usr/lib/genpack-init/` に `.py` 拡張子で配置します。genpack では通常、ebuild の `files/` に置いて `FILESDIR` 経由でインストールします。

```
/usr/lib/genpack-init/
  ├── 10timezone.py
  ├── 20locale.py
  ├── 50sshd.py
  └── 99default-network.py
```

**ロード順序**: `std::filesystem::directory_iterator` で列挙されます。SquashFS はディレクトリエントリをアルファベット順で格納するため、実際にはファイル名の辞書順に読み込まれます。実行順序を明示したい場合は `10-`, `20-`, `99-` のような数値プレフィックスを使ってください。

## 基本構造

各スクリプトは `configure()` 関数を定義します。この関数が genpack-init から呼び出されます。

### configure() の引数

引数なし（system.ini にアクセス不要な場合）:

```python
import logging

def configure():
    logging.info("Hello from my script")
```

引数あり（system.ini にアクセスする場合）:

```python
import logging

def configure(ini):
    value = ini.get("_default", "mykey", fallback=None)
    if value is None:
        return
    logging.info(f"mykey = {value}")
```

`configure` 関数が存在しないスクリプトはスキップされます（情報ログが出力されます）。引数が 2 つ以上の `configure` はエラーになります。

## system.ini とini オブジェクト

`configure(ini)` に渡される `ini` は Python 標準の `configparser.ConfigParser` インスタンスです。

genpack-init は `system.ini` の読み込み時に先頭へ `[_default]` セクションヘッダを自動付加します。そのため、`system.ini` でセクション指定なしに書かれたキーはすべて `[_default]` セクションとしてアクセスできます。

**system.ini の例:**

```ini
timezone=Asia/Tokyo
locale=ja_JP.UTF-8
ssh_pubkey=ssh-ed25519 AAAA...
debug=false

[myapp]
data_dir=/data/myapp
```

**スクリプトからのアクセス例:**

```python
def configure(ini):
    # セクションなし（_default）のキー
    timezone = ini.get("_default", "timezone", fallback=None)

    # boolean 値
    debug = ini.getboolean("_default", "debug", fallback=False)

    # 名前付きセクション
    data_dir = ini.get("myapp", "data_dir", fallback="/var/lib/myapp")

    # セクションの存在確認
    if ini.has_section("myapp"):
        pass
```

system.ini が存在しない場合や解析に失敗した場合でも、空の ConfigParser オブジェクトが渡されて実行は継続します（`fallback` 引数は必ず指定してください）。

### debug モード

`system.ini` に `debug=true` を記載するとログレベルが DEBUG に昇格します。

## genpack_init モジュール

`from genpack_init import ...` または `import genpack_init` でアクセスできる専用モジュールが提供されています。

### パス補助関数

ファイルシステム上の各パスに対応する `pathlib.PosixPath` を返します。

| 関数 | 対応するパス |
|---|---|
| `root_path(*args)` | `/` （overlayfs ルート） |
| `ro_path(*args)` | `/run/initramfs/ro/` （SquashFS、読み取り専用） |
| `rw_path(*args)` | `/run/initramfs/rw/` （データパーティションまたは tmpfs） |
| `boot_path(*args)` | `/run/initramfs/boot/` （FAT32 ブートパーティション） |

引数を渡すとパスを連結します。先頭の `/` は自動的に除去されます。

```python
from genpack_init import root_path, rw_path, boot_path

# /etc/systemd/network/ (overlayfs ルート上)
network_dir = root_path("/etc/systemd/network")
network_dir.mkdir(parents=True, exist_ok=True)

# /run/initramfs/rw/mydata/
data_dir = rw_path("mydata")

# /run/initramfs/boot/system.ini
ini_path = boot_path("system.ini")
```

overlayfs ルートはスクリプト実行時点で既に `/` になっているため、`root_path()` を使わず直接絶対パスで書くことも可能です。`root_path()` は `pathlib.PosixPath` を返すので、ファイル存在確認などに便利です。

### プラットフォーム判定

```python
from genpack_init import is_raspberry_pi, is_qemu, read_qemu_firmware_config

if is_raspberry_pi():
    # Raspberry Pi 固有の設定
    pass

if is_qemu():
    # QEMU/KVM 環境固有の設定
    pass

# QEMU fw_cfg からデータを読み込む
data = read_qemu_firmware_config("opt/mykey")  # bytes | None
```

### systemd サービス操作

```python
from genpack_init import enable_systemd_service, disable_systemd_service

enable_systemd_service("myapp.service")
disable_systemd_service("unneeded.service")
```

### ファイル権限操作

```python
from genpack_init import chown, chgrp, chmod

chown("www-data", "/var/www/html", group="www-data", recursive=True)
chgrp("docker", "/var/lib/docker", recursive=True)
chmod("0700", "/root/.ssh")
```

### ディスク操作

初期化スクリプトが追加のディスク設定を行う場合に使用します。

```python
from genpack_init import (
    coldplug, get_block_device_info, get_partition_info,
    parted, mkfs, mkswap, mount, umount
)

# udev コールドプラグ（デバイスの検出）
coldplug()

# ブロックデバイス情報
info = get_block_device_info("/dev/sda")
# -> {"name": ..., "logical_sector_size": 512, "physical_sector_size": 512, "num_logical_sectors": ...}
# デバイスが存在しない場合は None

# パーティション情報
part = get_partition_info("/dev/sda1")
# -> {"name": ..., "uuid": "...", "type": "..."} または None

# parted コマンド実行
parted("/dev/sdb", "mklabel gpt")
parted("/dev/sdb", "mkpart primary 1MiB 100%")

# ファイルシステム作成
mkfs("/dev/sdb1", "ext4", label="mydata")   # label は省略可
mkswap("/dev/sdb2", label="swap")

# マウント・アンマウント
mount("/dev/sdb1", "/mnt/mydata", fstype="ext4", options="noatime")
umount("/mnt/mydata")
```

## ログ出力

Python 標準の `logging` モジュールが genpack-init により設定済みです。スクリプト内で直接使用できます。

```python
import logging

def configure(ini):
    logging.debug("デバッグ情報")
    logging.info("通常の処理ログ")
    logging.warning("警告")
    logging.error("エラー（続行可能）")
```

ログは `/var/log/genpack-init.log` とコンソール（stderr）の両方に出力されます。`system.ini` に `debug=true` が設定されている場合は DEBUG レベルも記録されます。

## エラーハンドリング

あるスクリプトで例外が発生しても、genpack-init はその例外をキャッチして `logging.error()` に記録し、**次のスクリプトの実行を継続します**。全スクリプトの実行が終わると、問題の有無にかかわらず `/sbin/init` へ exec します。

したがって:

- **致命的なエラーでもブートは止まりません**（意図的な設計）
- スクリプト内での例外はログに残りますが、スタックトレースも記録されます
- 前提条件が満たされていない場合は例外を投げるよりも早期 `return` が推奨されます

```python
import logging

def configure(ini):
    # 前提条件のチェックは早期 return で行う
    if not os.path.isdir("/var/lib/myapp"):
        logging.warning("myapp のデータディレクトリが存在しません。スキップします。")
        return
    # 以降の処理...
```

## 実装例

### タイムゾーン設定

```python
import os, logging

def configure(ini):
    timezone = ini.get("_default", "timezone", fallback=None)
    if timezone is None:
        return
    zoneinfo = f"/usr/share/zoneinfo/{timezone}"
    try:
        os.symlink(zoneinfo, "/etc/localtime")
    except FileExistsError:
        os.remove("/etc/localtime")
        os.symlink(zoneinfo, "/etc/localtime")
    logging.info(f"Timezone set to {timezone}")
```

### データディレクトリのバインドマウント

SquashFS は読み取り専用のため、書き込みが必要なデータディレクトリはデータパーティション（`/run/initramfs/rw/`）にコピーしてバインドマウントします。

```python
import os, shutil, subprocess, logging

def configure():
    orig = "/var/lib/myapp"
    if not os.path.isdir(orig):
        logging.warning("myapp data directory not found")
        return

    work = "/run/initramfs/rw/myapp"
    if not os.path.exists(work):
        shutil.copytree(orig, work)
        logging.info("myapp data directory copied to rw layer")

    if os.path.exists(work) and not os.path.ismount(orig):
        if subprocess.call(["mount", "--bind", work, orig]) == 0:
            logging.info("myapp data directory bind-mounted")
        else:
            logging.error("Bind-mounting myapp data directory failed")
```

### systemd ネットワーク設定ファイルの生成

```python
import logging
from genpack_init import root_path

CONFIG = """[Match]
Type=ether

[Network]
DHCP=yes
"""

def configure():
    network_dir = root_path("/etc/systemd/network")
    # 既存の設定があればスキップ
    if any(network_dir.glob("*.network")):
        return
    network_dir.mkdir(parents=True, exist_ok=True)
    (network_dir / "50-default.network").write_text(CONFIG)
    logging.info("Default systemd-networkd config generated")
```

## ベストプラクティス

- **`fallback` を必ず指定する**: `ini.get()` / `ini.getboolean()` に `fallback=` を与えておくと、system.ini が空でも安全に動作します。
- **べき等に書く**: スクリプトは複数回実行されることがあります（開発時やテスト時）。ファイルの存在確認やマウント状態の確認を行い、二重処理を避けてください。
- **前提条件は早期 return で処理する**: 対象ファイルやディレクトリが存在しない場合は `logging.warning()` を出して早期 `return` してください。
- **ファイル名プレフィックスで順序を制御する**: 他のスクリプトの結果に依存する場合は `10-`, `50-`, `99-` のような数値プレフィックスで実行順序を明示してください。
- **ログを残す**: 何をしたか・しなかったかを `logging.info()` / `logging.warning()` で記録しておくと、起動時のトラブルシューティングが容易になります。
