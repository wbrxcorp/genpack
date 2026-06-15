# exec-guard — 実行保護機能

## 概要

exec-guard は、overlayfs の upper layer（書き込み可能層）に持ち込まれたバイナリや共有ライブラリの実行を eBPF LSM でブロックする genpack-init のオプション機能です。

genpack イメージのルートファイルシステムは SquashFS（lower layer、読み取り専用）と書き込み可能な upper layer の overlayfs で構成されています。exec-guard は「SquashFS イメージに含まれていないバイナリは実行させない」という信頼境界を、署名検証なしにカーネルレベルで強制します。

```
SquashFS (lower layer)  ←── 信頼済み。exec-guard が許可
書き込み可能層 (upper)  ←── 不審なバイナリが持ち込まれても実行・ロード不可
```

## 有効化

`genpack.json5` の `use` セクションに `exec-guard` を指定します。

```json5
{
    profile: "paravirt",
    packages: [
        "genpack/paravirt",
    ],
    use: {
        "sys-apps/genpack-init": "exec-guard",
    },
}
```

ビルド時に clang と bpftool が必要です（`genpack-overlay` の ebuild が自動的に依存関係として追加します）。

## 動作の仕組み

genpack-init が PID 1 として起動した直後に以下を実行します。

1. **eBPF LSM プログラムのロード**: `/sys/kernel/btf/overlay` の BTF 情報を使い、overlayfs の内部構造（`ovl_inode.__upperdentry`）を解釈できる BPF プログラムをカーネルにロード
2. **信頼済みデバイスの登録**: `/run/initramfs/ro`（SquashFS のマウントポイント）の `st_dev` を BPF マップに登録
3. **BPF リンクのピン留め**: `execl(systemd)` 後も BPF プログラムが有効であり続けるよう `/sys/fs/bpf/exec_guard/` にリンクをピン留め
4. **`/usr` の読み取り専用マウント**: `touch /usr/bin/bash` のような誤操作で上書きコピーが発生し exec-guard が自分自身をブロックしてしまう事態を防ぐため、`/usr` を read-only bind mount

これ以降のすべての `execve()`、`mmap(PROT_EXEC)`、`mprotect(+PROT_EXEC)` に対し、以下のルールが適用されます。

| ファイルの出所 | exec / dlopen |
|---|---|
| SquashFS lower layer 由来 | 許可 |
| upper layer 由来（持ち込みファイル） | `EPERM` で拒否 |

### ELF バイナリのみが対象

`execve()` のチェックは ELF バイナリ（マジックバイト `\x7fELF`）に限定しています。シェバン（`#!/bin/bash`）付きスクリプトを `bash ./script.sh` のようにインタープリタ経由で実行する操作は制限されません（管理者による通常のスクリプト作業を妨げないための設計です）。

`dlopen()` 経由の共有ライブラリロードは `mmap(PROT_EXEC)` フックで捕捉し、ELF ファイルに関わらずチェックされます。

### mmap→mprotect の 2 段バイパスへの対応

ファイルを `mmap(PROT_READ)` で一旦マップして `mmap(PROT_EXEC)` フックを回避し、あとから `mprotect(+PROT_EXEC)` で実行属性を付け足す W^X バイパスは、`file_mprotect` フックで捕捉します。対象 VMA がファイルバックで、その実ファイルが upper layer 由来であれば `EPERM` を返します。

overlayfs は mmap 時に VMA の参照先を実ファイル（lower の SquashFS ファイル、または copy-up された upper のファイル）に差し替えるため、`file_mprotect` フックでは overlay 経由ではなく実ファイルの `s_dev` で判定します。lower の SquashFS は信頼済みデバイスとして登録されているため許可され、upper（tmpfs 等）由来は拒否されます。ファイルを持たない匿名マッピング（JIT 等の正当な用途。後述の「対応しない範囲」）は判定対象外で、従来どおり許可されます。

## system.ini での制御

`system.ini` に以下を記載すると exec-guard を無効化できます。

```ini
exec_guard = false
```

この設定は `/usr` の read-only mount も含めてすべての exec-guard の動作を無効化します。

## 監査ログ（audit）

exec-guard を有効にしたイメージには `/etc/audit/rules.d/exec_guard.rules` が自動的にインストールされます。auditd が起動するとこのルールが読み込まれ、ブロックされた `execve()`、`mmap()`、`mprotect()` が `key=exec_guard_deny` でログに記録されます。

```bash
# 今回のブート分のみ表示
ausearch -k exec_guard_deny --interpret -ts boot | grep -v "^type=CONFIG_CHANGE"
```

出力例（exec ブロック）:
```
type=SYSCALL ... syscall=execve success=no exit=-1 comm="bash" key="exec_guard_deny"
type=PATH ... name="/root/ls_copy" inode=84 dev=00:1c ...
```

出力例（dlopen ブロック）:
```
type=SYSCALL ... syscall=mmap success=no exit=-1 comm="python3" key="exec_guard_deny"
type=MMAP fd=4 flags=0x812
```

`key=exec_guard_deny` のログが出た時点で upper layer への不審なバイナリ持ち込みが試みられたと判断できます。通常の運用ではこのキーのログはほぼ発生しないため、誤検知が少ない検知シグナルとして機能します。

## セキュリティ上の位置づけ

exec-guard は「完全な防壁」ではなく、**検知トラップ**として捉えるのが適切です。

`execve()` が `EPERM` で失敗する時点で、攻撃者には他の手段（シェルスクリプト実行、シグナル送信など）がすでにある可能性があります。exec-guard の価値は、攻撃ツールが自動的に試みる ELF バイナリの持ち込み実行を即座に audit ログに記録する点にあります。

exec-guard 自体を知らない攻撃者が一般的な Linux 環境を想定した手法で動作すると、高確率で `exec_guard_deny` の痕跡が残ります。

### 防御範囲

| 攻撃手法 | 対応 |
|---|---|
| upper layer への ELF バイナリ持ち込み → `execve` | ブロック＋audit ログ |
| upper layer への `.so` 持ち込み → `dlopen` | ブロック＋audit ログ |
| `memfd_create` + `fexecve` によるファイルレス実行 | ブロック＋audit ログ |
| upper layer ファイルの `mmap(PROT_READ)` → `mprotect(+PROT_EXEC)`（2段 W^X バイパス） | ブロック＋audit ログ |
| `touch /usr/bin/bash` 等による誤コピーアップ | `/usr` の ro mount で防止 |
| シェバンスクリプトの直接 `execve` | ブロック＋audit ログ |

`memfd_create` でディスクに痕跡を残さず ELF を実行する手法は、攻撃ツールが検知回避のために好んで用いるものですが、exec-guard はこれをブロックします。memfd は内部 tmpfs 上の無名ファイルであり、その `s_dev` は `trusted_devs` マップに登録されていないため、`bprm_check_security` フック（ELF マジック判定後の `check_file()`）が `EPERM` を返します。匿名 `mmap(PROT_EXEC)` へのシェルコード（後述の「対応しない範囲」）とは異なり、こちらはファイルバックのマッピングを経由するため捕捉できます。検証用のテストスクリプトは `genpack-stencils` の `exec-guard/files/usr/bin/test-memfd-exec` に収録しており、ブロックは実機で確認済みです。mmap→mprotect の 2 段バイパスについても同様に `exec-guard/files/usr/bin/test-mprotect-exec` で検証でき、upper layer ファイルのみブロック・lower layer ファイルと匿名マッピングは許可されることを確認済みです。

### 対応しない範囲

| 攻撃手法 | 理由 |
|---|---|
| `bash ./evil.sh` 等インタープリタ経由のスクリプト実行 | スクリプトは `execve` されない（意図的な設計） |
| カーネル脆弱性によるページキャッシュ改ざん | カーネル自体の信頼が前提 |
| anonymous `mmap(PROT_EXEC)` へのシェルコード書き込み・実行（および匿名マッピングへの `mprotect(+PROT_EXEC)`） | ファイルを持たない匿名マッピングは `mmap_file`/`file_mprotect` いずれのファイルベース判定の対象にもならない。塞ぐことは技術的には可能（プロセス単位の W^X 強制）だが、Python・Java・Node.js 等の JIT コンパイラが同じ仕組みを正当な用途で使っており、どのパッケージが JIT を使うか実行前に把握することが難しいため、現実的ではない |

## 適用できないアーティファクト

以下のようなソフトウェアを含むアーティファクトには exec-guard を適用できません。

- **プラグインシステムで ELF バイナリをダウンロードするもの**: VS Code の拡張機能（ネイティブ拡張）、一部の IDE やエディタが実行時にバイナリプラグインをダウンロード・実行するケース
- **セルフアップデート機能を持つもの**: アプリケーションが新バージョンのバイナリを自分でダウンロードして差し替えるケース
- **パッケージマネージャを動作させるもの**: npm、pip 等がネイティブ拡張（`.so`）をビルド・インストールするケース

これらは exec-guard の仕組みそのものと根本的に相容れません。exec-guard は「イメージ外から持ち込まれた ELF バイナリは信頼しない」という原則で動作しているため、正規の動作としてバイナリを外部から取り込むソフトウェアは必然的にブロックされます。

スクリプト（シェルスクリプト、Python スクリプトなど）をダウンロードして実行するだけであれば exec-guard の制約を受けないため、そのようなアーティファクトには適用可能です。

## リカバリー

exec-guard が有効な状態で誤操作によりシステムが起動不能になった場合、`/usr` が read-only マウントされているため通常の操作による新たな問題の発生は防がれています。

それでも起動に問題が生じた場合は、ブートパーティション（FAT32）上の `system.ini` に `exec_guard = false` を追記してください。ブートパーティションは他の OS や Live 環境からマウントできるため、システムが起動しない状態でも編集可能です。

```ini
# system.ini に追記
exec_guard = false
```

## 必要なカーネル設定

以下のカーネルオプションが必要です。Gentoo の標準カーネルでは通常すべて有効になっています。

| オプション | 用途 |
|---|---|
| `CONFIG_BPF_LSM=y` | BPF LSM サポート |
| `CONFIG_LSM="...,bpf"` | BPF を LSM リストに含める |
| `CONFIG_DEBUG_INFO_BTF=y` | BTF（BPF 型情報）生成 |
| `CONFIG_DEBUG_INFO_BTF_MODULES=y` | カーネルモジュールの BTF（overlay BTF に必要） |
| `CONFIG_OVERLAY_FS=m` または `=y` | overlayfs（genpack の動作要件） |
