# ADR-0007: アーティファクト定義のコミット ID を `include_commit_id` でイメージに記録する

- 日付: 2026-08-09
- ステータス: 採用

## 背景

稼働中のイメージが「いつのアーティファクト定義から作られたものか」を知る手段が無かった。
`/.genpack/` のメタデータは `arch` / `profile` / `artifact` / `variant` / `packages` /
`timestamp.commit` で、アーティファクト定義のリビジョンを示すものはひとつも無い。素性を知るには
システムの起動時刻から推測するしかなく、再起動を挟むと当てにならず、同じ日に複数回ビルドした
ものは区別できない。

`timestamp.commit` はコミット ID を含むため紛らわしいが、これは
`/var/db/repos/gentoo/metadata/timestamp.commit` をそのままコピーしたもので、**どの時点の Gentoo
Portage ツリーでビルドしたか**を示す。アーティファクトとは無関係で、`genpack/base` の
`glsa-check.py` が GLSA データの鮮度判定に使っている。

## 決定

`genpack.json5` に **`include_commit_id`（bool, デフォルト `false`）** を追加する。`true` のとき、
アーティファクトディレクトリの git リビジョンを `/.genpack/commit-id` に 1 行で書き出す。

```
33f4562a1b9e8c7d6f5a4b3c2d1e0f9a8b7c6d5e
33f4562a1b9e8c7d6f5a4b3c2d1e0f9a8b7c6d5e (with local changes)
```

経路は既存の `ARTIFACT` / `PROFILE` / `VARIANT` とまったく同じで、新しい仕組みは要らない。
ホスト側の `genpack.py` が git を実行し、nspawn の `-E COMMIT_ID=...` でコンテナへ渡し、
`genpack-generate-metadata` がメタデータとして書き出す。

## なぜ git の実行をホスト側に置くか

コンテナ内で git を呼ぶ実装にはしない。理由が 3 つある。

1. **ビルドコンテナに git が無い。** `genpack/base` にも `genpack/genpack-progs` にも
   `dev-vcs/git` への依存は無く、たまたま入っているアーティファクトでしか動かない実装になる
2. **`.git` が見えるとは限らない。** コンテナにバインドされるのは `--bind=.:/mnt/host`、すなわち
   カレントディレクトリのみで、モノレポのサブディレクトリ構成では `.git` はマウント範囲の外にある
3. **所有者が違う。** 非 root ビルドでは `rootidmap` が効くため、git の `dubious ownership` 検査に
   引っかかる

ホスト側の `genpack.py` はアーティファクトのディレクトリで、ユーザー権限のまま動いているので、
これらの問題がすべて無い。

## なぜ書式を `<sha> (with local changes)` にするか

既存の `timestamp.commit` が空白区切りのフィールド形式（`<sha> <unixtime> <iso8601>`）なので、
それに倣う。この形なら追記があっても第 1 フィールドは常に SHA であり、
`cut -d' ' -f1 /.genpack/commit-id` で取り出せる。git 標準の `--dirty` が付ける `<sha>-dirty` は
SHA と連結してしまうため、同じ切り出しが壊れる。

自然言語の括弧書きは機械可読性の観点で不安に見えるが、これは表記ではなく契約の定め方の問題である。
判定規則を「**空白区切りでちょうど 1 トークン、かつそれが期待長の 16 進文字列**」と定めれば、パーサは
括弧の中身を一切解釈しない。

| ファイルの状態 | 判定 |
|---|---|
| `<sha>` のみ | clean |
| `<sha>` に後続がある | clean でない |
| ファイルが存在しない | clean でない |
| 未知の形式 | clean でない |

最後の行が重要で、安全ゲートとしては fail-closed が正しい。機械向けの表記（`dirty` というトークンや
`key=value` 形式）に寄せると、かえって「未知の形式を clean と誤判定する」余地が生まれる。
引き換えに**このファイルは 1 フィールドに凍結される**。将来ブランチ名や日時を持たせたくなった場合は、
このファイルを拡張するのではなく別ファイルを設けること。

dirty マーカー自体は省略できない。コミット ID だけでは「コミット後に手元で書き換えてビルドした
イメージ」を見分けられず、開発中はそれが常態だからである。

## なぜオプトインか

- **git 管理下とは限らない。** いずれにせよ「取れなければどうするか」の処理は必要になる。オプトイン
  なら「取れるはずなのに書かれていない」異常に気付きやすい
- **イメージ内容が git の状態に依存するようになる。** 同一ツリーからのビルドでも、コミットが違えば
  イメージのバイト列が変わる。この副作用を全アーティファクトへ暗黙に及ぼすのは避けたい
- **リポジトリの活動状況が成果物に載る。** 配布物からコミット ID が読めることを望まないケースがある

明示的に要求されている以上、`include_commit_id: true` なのに取得できなければ**ビルドをエラーで
止める**。意図が満たされないまま成果物ができるのを防ぐほうが一貫する（`genpack archive` で配布された
定義には `.git` が無いので、そこでは指定しないことになる）。

## メタデータ生成を Upper フェーズの最後へ移す

当初、メタデータは `genpack-exec-package-scripts` がパッケージスクリプト実行と同時に生成していた。
しかし Upper フェーズはその**後**に `cp -rdv /mnt/host/files/. /` で `files/` をマージし、続いて
`/build`・`/build.d/*`・`setup_commands` を実行する。**メタデータが記述しているはずのイメージが、
メタデータを書いた後にまだ変化する**ということであり、これは順序として単純に誤っている。ファイルを
書き終える前にチェックサムを計算しないのと同じ理由である。一体になっていたのは、両者がパッケージ
一覧を必要とするという実装上の都合にすぎない。

具体的な害としては、**他イメージのメタデータを持ち込む事故が通る**ことがある。`files/` を既存
イメージの rootfs から組むと、そのイメージの `/.genpack/` が一緒に入り、別アーティファクトを名乗る
イメージができる。最後に生成すれば打ち消される。

`packages` については、Upper フェーズで runtime set やプロファイルが変化した場合にそれを反映できる
ようになる。現時点でそれを行うアーティファクトは無いので、実際の差は今のところ無い。

> **`packages` の限界（本 ADR の範囲外）**
> `packages` は `@profile` / `@genpack-runtime`（devel 時は `@genpack-devel`）を起点に依存関係を
> たどって列挙される（`genpack_pkg.py` の `get_runtime_packages()`）。`@world` や VDB は見ない。
> したがってビルドスクリプトが `emerge foo` で追加したパッケージは、set を書き換えない限り**列挙の
> 起点に入らず、一覧にも載らない**。生成のタイミングを後ろへ移してもこれは変わらない。
> 一方でそのパッケージのファイルはイメージに入るため、起動後の `glsa-check.py` による勧告照合から
> 静かに漏れる。これは `packages` の導出方法の問題であり、メタデータ生成の順序とは別の課題である。
> Lower にしか残らない buildtime パッケージを混ぜないようにしつつ最終イメージの実体を列挙する方法が
> 要るので、直すなら独立した設計判断として扱う。

したがって**メタデータ生成そのものを最後に移す**。genpack-progs のコマンドを 2 つに分ける。

- `genpack-package-scripts` — パッケージスクリプトの実行のみ。アーティファクトのビルドスクリプト
  より前に走る必要があるため、この位置は動かせない
- `genpack-generate-metadata` — メタデータ生成のみ。イメージへ書き込む処理がすべて終わった後に走る

列挙のコストは stub で 0.2 秒、gnome（1029 パッケージ）で 0.8 秒であり、遅らせる代償は無い。
ビルド中に `/.genpack/` を読む処理は存在しない（`glsa-check` も `01banner` も起動後のイメージ内で
動く）ので、生成を遅らせて困るものも無い。

副次的に、`files/.genpack/commit-id` のようなものを置いても最後の生成で打ち消される。これは順序を
正した結果として得られるものであって、**この効果を保証として謳うことはしない**（後述）。

### `/.genpack/` を予約領域にはしない

`files/.genpack/` をビルドエラーとして拒否する案も検討したが、採らない。`/.genpack/` は genpack
専用ではなく、既存アーティファクトが自前のバージョン情報を置く場所として既に使っている
（owncloud の `owncloud-version`、walbrix の `version`）。また `banner` はパッケージスクリプトが
生成するものなので、`files/.genpack/banner` で差し替えられることには意味がある。genpack が所有
するのはディレクトリではなく**特定のファイル名**であり、それらは最後に生成することで守られる。

### 所有ファイルは「書く」ではなく「正規化する」

最後に生成するだけでは、書く値がある名前しか揃わない。genpack 所有の名前は毎回**置き換えるか消すか**
する。

1. **値が無い名前は unlink する。** `include_commit_id: false` なら `COMMIT_ID` は渡らないので、
   何もしなければ持ち込まれた `commit-id` がそのまま残る。前述の「他イメージの `/.genpack/` ごと
   持ち込む」事故では、`commit-id` / `variant` / `profile` が別イメージの値のまま最終イメージに残る
   ことになる。「生成されない」は「存在しない」でなければ、記録として意味を持たない
2. **書く前に既存パスを除去する。** `files/` のマージは `cp -rd` で symlink を保持するため、
   `/.genpack/artifact` が symlink になっている状態がありうる。`open(..., "w")` はこれを辿るので、
   除去せずに書くとメタデータ生成が**自分のディレクトリの外へ書く**。防御というより、genpack が
   自分の担当範囲の外に手を出さないための衛生である。`/.genpack` 自体がディレクトリでない場合も
   同様に置き換える

対象は genpack 所有の名前だけなので、`banner` やアーティファクト独自のファイルには影響しない。

## 信頼境界

この機能が防ぐのは**取り違えと思い違い**である。`system.img` のようなありふれた名前のファイルを
間違えて本番に書き込む、手元の未コミット変更が混じったイメージを配ってしまう、といった事故を、
イメージ自身に素性を持たせることで減らす。

**敵対的なアーティファクト定義に対する防御ではない。** genpack の設計にはそもそも「信頼できない
アーティファクト」という概念が無い。`build.d` と `setup_commands` はコンテナ内で root として動き、
最終イメージの中身は完全にアーティファクトが決める。実際、`files/usr/bin/genpack-generate-metadata`
を置けば、メタデータを書く当のコマンドを差し替えられる（`genpack-copyup` も同様）。これは PATH 解決
の問題ではなく、可変なイメージの中の実行ファイルを信頼しているという構造の問題であり、塞ぐには
Upper 構築後の全処理をホスト側へ移す必要がある。

そこまでしても意味は薄い。commit-id には署名が無く、イメージを作れる者はそれを書き換えたイメージも
作れる（`unsquashfs` して詰め直すだけでよい）。**署名の無いメタデータで偽装を防ぐことはできない。**
将来 `--require-clean-commit` を実装するときも、これは運用上のガードレールであってセキュリティ
コントロールではない、という位置付けを保つ。

### 旧コマンドは凍結して残す

`genpack-exec-package-scripts` は変更せずそのまま残す。分離前の genpack は新コマンドを呼ばないため、
これを削ると `/.genpack/` が空のイメージができてしまう。スクリプト先頭に凍結の理由を書き、ebuild の
後方互換セクションへ移した。

2 世代前の `exec-package-scripts-and-generate-metadata`（と対になる `list-pkg-files`）も残す。これらを
最後に使う genpack は `a6ea03c` の直前、2026-05-19 のものであり、削るには近すぎる。またその削除は本 ADR
の主題とは無関係で、混ぜると「旧世代のサポートをいつ終了したか」を後から追えなくなる。切るならそれ自体を
独立した判断として扱う。代わりに、どの genpack コミットから使われなくなったかを各スクリプトと ebuild に
書き、将来の削除候補であることを明示した。

なお `genpack upper` は `genpack build` と違って lower を作り直さないため、分離前の lower に対して
新しい genpack で `upper` を実行すると新コマンドが無い。Upper フェーズの冒頭で存在確認し、高価な処理に
入る前に「先に `genpack lower` が必要」と伝える。

## dirty の判定範囲

`git status --porcelain` はリポジトリ全体を見るため、イメージに影響しないファイル（README など）の
変更でも dirty になる。ビルド入力に絞れば精度は上がるが、判定が複雑になるうえ、**誤って clean と
表示するほうが害が大きい**（イメージの素性を誤認する）。過剰に dirty と出るのは安全側の誤りなので、
リポジトリ全体を見て保守的に dirty とする。

未追跡ファイルも dirty に含める。`files/` に未追跡ファイルがあればイメージに入ってしまうためである
（`git status --porcelain` は既定で `??` を出すので、追加の指定は要らない）。

ただし `git status` は**gitignore されたファイルを出力しない**。一方 genpack は git の ignore 状態と
無関係にビルド入力を読む（`files/` は `cp -rdv /mnt/host/files/. /` で丸ごとイメージへ入る）。
`files/` 以下を gitignore しているアーティファクトでは、その内容を書き換えてイメージのバイト列が
変わっても status は空のままで、**上記の保守性がそこだけ破れる**。したがって repo 全体の status に
加えて、ビルド入力パスに限定して ignored ファイルの有無も見る。

```sh
git ls-files --others --ignored --exclude-standard -- <ビルド入力>
```

リポジトリ全体に単純に `--ignored` を付けるのでは駄目で、genpack 自身が生成して gitignore する
`work/` や `*.squashfs` のせいで常時 dirty になる。pathspec をビルド入力に限定することで、
「入力は漏らさない」と「生成物では汚さない」を両立させる。

ここで言うビルド入力の範囲は `src/genpack.py` の `BUILD_INPUT_DIRS` / `GENPACK_JSON_FILES` を
権威的な定義とし、`genpack archive` の対象と Lower 層の再ビルド判定もこれを共有する。三者が別々の
リストを持つと、ディレクトリが増えたときに片方だけ更新されて静かにずれる。人間向けの説明は
`docs/subdirectories.md`。

## 影響

- `src/genpack.py`: `get_artifact_commit_id()` を追加し、Upper フェーズの `env_opts` 組み立てで
  `-E COMMIT_ID=...` を渡す。値に空白が含まれるが、genpack-helper は execvp で systemd-nspawn を
  起動するため argv 要素として保たれる。`include_commit_id` が bool でなければ、Lower ビルドを
  何時間も進めてから落ちないよう genpack.json 読み込み直後に `ValueError` とする。
- `src/genpack.py`: ビルド入力の定義を `BUILD_INPUT_DIRS_LOWER` / `BUILD_INPUT_DIRS_UPPER` /
  `GENPACK_JSON_FILES` に集約し、`create_archive()` と Lower の陳腐化判定を移行した（従来は
  それぞれが独自にディレクトリ名を並べていた）。
- genpack-overlay: `genpack-package-scripts` と `genpack-generate-metadata` を新設し、後者に
  `COMMIT_ID` → `commit-id` の対応を含めた。`genpack-exec-package-scripts` は凍結。
- `src/genpack.py`: Upper フェーズの冒頭で、lower イメージが新コマンドを持つか確認する。`genpack
  upper` は `genpack build` と違って lower を作り直さないため、分離前の lower に対して実行すると
  途中で command not found になる。高価な処理の前に理由を伝えて止める。
- `docs/json5.md`, `docs/overlay-genpack-progs.md`: 記述を追加。
- 既定 `false` のため**既存アーティファクトは無変更**。

## 積み残し

genpack-install 側の対応（`/.genpack/commit-id` の常時表示と、デプロイ時ゲートとしての
`--require-clean-commit`）は本 ADR の範囲外とし、genpack-install / genpack-mkiso / genpack-mkzip の
3 つを対象に別途実装した。前章のとおり、運用上のガードレールとして設計してある。
仕様は [genpack-install CLI リファレンス](../docs/cli-install.md#--require-clean-commit)を参照。
