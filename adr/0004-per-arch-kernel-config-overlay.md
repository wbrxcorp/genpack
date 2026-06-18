# ADR-0004: `kernel/arch-<arch>/` によるアーキテクチャ別カーネル設定オーバーレイ

- 日付: 2026-06-18
- ステータス: 採用

## 背景

genpack は単一の `genpack.json5`（と周辺サブディレクトリ）から複数アーキテクチャ
（`x86_64` / `aarch64` / `riscv64`）のイメージをビルドできる。カーネル設定のカスタマイズは
`kernel/config.d/*.config` を Lower フェーズで `/etc/kernel/` にコピーし、`kernel-build.eclass` が
配布 config の上に `merge_config.sh` でマージする仕組みである。

ここでアーキ依存の例外に遭遇した。`clang-kernel` アーティファクトの clang 専用堅牢化機能 kCFI
(`CONFIG_CFI`) は、x86_64 では問題なく動くが、**RISC-V では早期ブート（trap ベクタ `stvec` 設定前）で
CFI チェックを踏んでサイレントハングする**ことが切り分けで判明した（同一カーネル・clang で kCFI の
有無だけが分岐点。ThinLTO と素の clang+lld 自体は RISC-V でも正常）。つまり「**x86_64 では kCFI を
有効に保ちたいが、riscv64 でだけ無効化したい**」という、1アーティファクト内でのアーキ別の差分が必要に
なった。

しかし `kernel/config.d/*.config` は**アーキ横断**で全アーキに等しく適用される。`config.d` 内で
アーキ条件を表現する手段は無く、これまではアーキ別のカーネル設定を `savedconfig/`（CHOST 別サブ
ディレクトリ＋ `USE=savedconfig` の完全 config 持ち込み）でしか行えなかった。savedconfig は config 全体を
固定する重い方式で、`config.d` のフラグメント差分（「この1項目だけ上書き」）とは粒度が合わない。

## 決定

`kernel/arch-<arch>/` ディレクトリを設け、その中身を**対象アーキのビルド時だけ** `/etc/kernel/` の上に
**オーバーレイ rsync**（重ね書き、`--delete` なし）する。`<arch>` は genpack のアーキテクチャトークン
（`uname -m` 相当・`--arch` の値と同じ。`x86_64` / `aarch64` / `riscv64`）。

- アーキ非依存の第1段コピー（`kernel/` → `/etc/kernel`）は `--exclude=/arch-*` で `arch-*` を除外し、
  他アーキへ漏らさない。
- 続けて `kernel/arch-<arch>/` が存在すれば、その**中身**を `/etc/kernel` に重ね書きする。例として
  `kernel/arch-riscv64/config.d/zz-no-kcfi.config` は共有の `config.d/` に積み増しされる。
- 既存アーティファクトは `arch-*` を持たないので **no-op**（挙動・速度に影響なし）。

## なぜこの形か

- **`config.d` のフラグメント方式を活かす**: アーキ別でも「config 全体の固定（savedconfig）」ではなく
  「共有フラグメント＋アーキ差分」の重ね書きにすることで、共通設定（clang/kCFI/最小化）は1か所に保ち、
  アーキ固有の例外だけを小さく表現できる。差分の意図が diff で読める。
- **rsync オーバーレイ（`--delete` なし）**: 共有層を消さずに上書き・追加するだけなので、アーキ別
  ディレクトリは「例外の宣言」に徹する。全アーキの設定を各ディレクトリへ全コピーする必要がない。
- **genpack 駆動・portage 非依存**: savedconfig は CHOST 命名で portage の機構に乗るが、本オーバーレイは
  genpack が staging 時にアーキを見て撒くだけで、`config.d` のマージ機構（eclass）には手を入れない。
- **トークンは `arch-<uname>` 接頭辞**: `savedconfig/` の CHOST 命名（`riscv64-unknown-linux-gnu`）とは
  別系統だが、genpack の他所（`work/<arch>`、`--arch`、cache）と同じ短いアーキトークンに統一し、
  `arch-` 接頭辞で「アーキ別オーバーレイ」であることを名前から明示する。

## 注意（マージ順序の罠）

`kernel-build.eclass` は `config.d/*.config` を**ファイル名のアルファベット順**でマージし**後勝ち**。
ASCII では数字（`0`–`9`, 0x30–）が英字（`a`–, 0x61–）より前に来るため、`clang.config` のような英字始まりの
共通フラグメントを上書きしたいアーキ別 override を `90-...config` のような**数字始まり**にすると、共有
フラグメントより**前**にソートされて負ける。共有に確実に勝たせるには `zz-` のように後方へソートする
接頭辞を使う（例 `arch-riscv64/config.d/zz-no-kcfi.config`）。この点はドキュメントにも明記した。

## 検討した代替案

- **savedconfig でアーキ別に config 全体を持つ**: 既存機構で可能だが、`config.d` の差分粒度を捨てて
  config 全体を固定することになり、共通部分の重複保守が重い。不採用。
- **`config.d` ファイル内にアーキ条件構文を導入**: eclass のマージ機構（素の `# CONFIG_x is not set`
  行）に独自構文を足すことになり、上流フォーマットからの逸脱・パーサ保守が発生する。不採用。
- **アーキごとにアーティファクトをフォーク**: ツリー全体が分岐し、共通変更の二重保守になる。不採用。

## 影響

- `src/genpack.py`: kernel staging を2段化。第1段に `--exclude=/arch-*` を追加し、続けて
  `kernel/arch-<arch>/`（グローバル `arch`）が在れば `/etc/kernel` へオーバーレイ rsync。
  キャッシュ無効化（`get_latest_mtime`）は `kernel/` を再帰走査するため `arch-*` 配下の変更も自動で拾う。
  オーバーレイ側 rsync には **`--ignore-times` を付ける**。フルコピー方式で base と同名のファイル
  （例 `arch-riscv64/config.d/clang.config`）を重ねる際、rsync の既定 quick-check は「サイズ＋mtime
  一致でスキップ」であり、`git checkout` が全ファイルの mtime を揃えるため、同サイズだと overlay が
  黙ってスキップされ base が残る事故が起こりうる。`--ignore-times` で overlay を常に上書き勝ちにする
  （`--delete` は付けない＝base を消さず足す/上書きするだけ）。
- `docs/subdirectories.md`: `kernel/` 節に `arch-<arch>/` のサブセクションと命名注意を追記。
- 既定 no-op のため**既存アーティファクトは無変更**。
- 初出の利用者は `clang-kernel`（`arch-riscv64/config.d/zz-no-kcfi.config` で riscv64 のみ kCFI 無効化、
  x86_64 では kCFI 有効を維持）。
