# ADR-0003: `buildtime_packages_first` フラグで buildtime_packages の先行 emerge をオプトイン可能にする

- 日付: 2026-06-17
- ステータス: 採用

## 背景

`buildtime_packages` の本来の意味は「**最終イメージ（Upper）には含めないが、アーティファクトの
build に必要なパッケージ**」である。ここでの "build" は emerge による個々のパッケージのビルドを
指すのではなく、もっと広く**アーティファクトの build** を指す。具体的には Upper フェーズの
`execute-artifact-build-scripts` が持ち込みプログラムをビルドする際に必要だが、最終 squashfs には
要らないツール（Go や CMake など）を Lower 層へ入れておくための機構である。`buildtime_packages` は
runtime packages と同じ Lower の emerge（`@world @genpack-runtime @genpack-buildtime` の一括 emerge）で
インストールされ、両者の順序は portage が**宣言された依存関係**から解決する。

ここで例外的なユースケースに遭遇した。`clang-kernel` アーティファクト（clang ビルドのカーネル検証）
では、`sys-kernel/gentoo-kernel` を package.env（`env` フィールド）で clang/LLVM ツールチェーンに
差し替えてソースビルドする。このとき:

- `gentoo-kernel` の ebuild は**コンパイラを一切 BDEPEND していない**（gcc すら `@system` 前提で、
  ebuild に依存宣言は無い）。clang を使わせているのは package.env であって portage の依存グラフ上の
  関係ではない。
- したがって portage には「`llvm-core/clang` → `sys-kernel/gentoo-kernel`」という**依存エッジが
  存在せず、ビルド順序を保証できない**。`--parallel`（`--jobs`）時は両者が並行ビルドされ、kernel の
  コンパイルフェーズに clang のマージが間に合わずに `clang: command not found` で失敗しうる。
- clang を `buildtime_packages` に入れているのは「最終イメージから除外する」という*本来の意味*には
  合致している（ビルド専用ツールで squashfs には不要）。問題は、ここに**順序の保証まで期待できない**
  点である。

なお別問題として「clang はマージ済みだが `/usr/lib/llvm/<slot>/bin` が走行中 emerge プロセスの PATH に
反映されない（env-update ラグ）」があるが、これはアーティファクト側（package.env での PATH 前置、
`llvm-utils.eclass` の `llvm_prepend_path` と同型）で対処する別レイヤの話で、本 ADR の対象ではない。

## 決定

`genpack.json5` に **`buildtime_packages_first`（bool, デフォルト `false`）** を追加する。`true` の
とき、`@genpack-buildtime` セットを**メインの emerge より前に、独立した emerge パスで**先に流す。

- 別 emerge プロセスなので、メインパス開始時点で buildtime_packages は**完全にマージ済み**であり、
  かつ env-update を経た `profile.env` を新プロセスが読むため**PATH も更新済み**になる（env-update
  ラグも副次的に解消する）。
- 先行パス完了後（`check=True`）にメインパスが走るので、**`--parallel` でもレースしない**ハードな
  順序保証になる。
- `buildtime_packages` が空、またはフラグ未指定（既定 `false`）の場合は no-op で、従来どおりの
  一括 emerge のまま。既存アーティファクトの挙動・ビルド速度に影響しない。

## なぜ「デフォルト挙動の変更」や「新フィールド新設」ではなく「オプトインのフラグ」か

- **デフォルトで先行 emerge にしない**: `buildtime_packages` の意味は「最終像からの除外（配置）」で
  あって「順序」ではない。全アーティファクトの一括 emerge を先行2パスに変えると、buildtime↔runtime
  間の並列オーバーラップを失い、かつ `buildtime_packages` に**暗黙の順序意味**を後付けすることになる。
  機能に暗黙の意味を持たせるのは保守上よくない。
- **専用フィールド（例 `buildenv_packages`）を新設しない**: clang のように「最終像から除外したい」
  AND「先に焼きたい」を併せ持つパッケージは、2つの list に**重複記載**することになる。フラグ方式なら
  list は `buildtime_packages` 1つで、*いつ焼くか*だけを切り替えるので重複が出ない。
- **オプトインのフラグにする**: 「`buildtime_packages` を“半目的外”に使う（＝先行 emerge の足場にも
  する）」ことを、事故やデフォルト変更ではなく**明示的に名付けたオプトイン**として提供する。名前は
  *理由*（toolchain）ではなく*挙動*（順序）で付け、暗黙性を排除する。

## 検討した代替案

- **genpack 側で常に buildtime を先行パス化**: 上記のとおりデフォルト挙動の変更＋暗黙意味の付与に
  なるため不採用。
- **`gentoo-kernel` を overlay でフォークし BDEPEND に LLVM を足す**: portage から見て最も正しいが、
  カーネルのバージョンごとに ebuild を追従保守する必要があり重い。不採用。
- **アーティファクト手順で `genpack bash emerge <toolchain>` を先に手動実行**: genpack 改修不要だが、
  手順の記憶に依存し、ハードな保証にならない。フラグによる自動・確実な先行パスを優先。

## 影響

- `src/genpack.py`: `merge_genpack_json` に bool プロパティ `buildtime_packages_first` を追加（merge 可能
  フィールドにも登録）。Lower の emerge 直前に、フラグ ON かつ buildtime_packages 非空なら
  `@genpack-buildtime` の先行 emerge パスを実行。
- `docs/json5.md`: プロパティ説明とマージ表を追記。
- 既定 `false` のため**既存アーティファクトは無変更**。
- 初出の利用者は `clang-kernel` アーティファクト（`buildtime_packages_first: true`）。これにより
  stage3 からのファーストビルドでも clang が kernel より先に確実に揃い、`clang: command not found` の
  再試行が不要になる。
