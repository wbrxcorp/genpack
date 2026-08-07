# console-passwd — コンソールログインパスワードの管理

## 概要

console-passwd は、コンソールログイン用のパスワードを **OS イメージに焼き込まずに、稼働中のシステム側で設定する**ための `genpack/base` のオプション機能です。

genpack のルートファイルシステムは SquashFS（lower layer、読み取り専用）と書き込み可能な upper layer の overlayfs です。ここで通常の `passwd` を実行すると、**overlayfs の copy-up はファイル単位**であるため `/etc/shadow` がファイルごと upper layer へコピーされ、以降は lower 側が完全に隠れます。その結果、次にイメージ側でユーザーを追加しても `/etc/passwd`（lower のまま）には現れるのに `/etc/shadow`（upper に固定）には現れない、という不整合が起きます。**イメージ更新でシステムを更新できる**という genpack の利点が、パスワードまわりについてだけ失われるわけです。

console-passwd は `pam_userdb` を「独立した認証データベース」ではなく **`/etc/shadow` に対するユーザー単位の override 層**として使うことで、この問題を回避します。

```
コンソールログイン
       |
       v
  pam_userdb          (/etc/console-passwd.db … 永続層。ユーザーごとの override)
       |
       +-- DBにあり・一致 ------> 認証成功
       +-- DBにあり・不一致 ----> 即座に失敗（shadow へ落とさない）
       +-- DBに無い ------------> pam_unix (/etc/shadow … イメージ側の値で判定)
```

- アカウントの定義そのもの（`/etc/passwd`、`/etc/group`、`/etc/shadow`）は**引き続きイメージ側が正**です
- 上書きしたいユーザーのパスワードだけが永続層のデータベースに入ります
- **`/etc/shadow` は読まれるだけで書かれない**ため copy-up が起こらず、イメージ更新によるユーザーの追加・削除・ロック状態の変更がそのまま反映され続けます

なお、この機能を使わない場合の genpack イメージのコンソール root は**パスワード無し**です（ビルド時に `/etc/shadow` の root エントリが空にされます）。console-passwd の実際の効能は、この空パスワードを「イメージを書き換えずに」塞ぐことにあります。

## 有効化

`genpack.json5` の `use` セクションで `genpack/base` に `console-passwd` を指定します。既定は無効です。

```json5
{
    profile: "paravirt",
    packages: [
        "genpack/paravirt",
    ],
    use: {
        "genpack/base": "console-passwd",
    },
}
```

ビルド時に `sys-libs/pam[-berkdb]` と `dev-lang/python[gdbm]` が要求されます（ebuild が USE 依存として自動的に追加します）。`sys-libs/pam` に `berkdb` を立てるとデータベースの形式が変わって読めなくなるため、**両立できません**。この組み合わせはビルド時にエラーになります。

## 使い方

イメージを起動した後、root で次のように実行します。

```sh
# root のコンソールパスワードを設定・変更する
console-passwd root

# override を解除し、イメージ側 /etc/shadow の値に戻す
console-passwd --reset root

# override されているユーザーを一覧する（ハッシュは表示しない）
console-passwd --list

# イメージ更新で消えたユーザーのエントリが残っていないか調べる
console-passwd --check
```

| コマンド | 動作 |
|---|---|
| `console-passwd <user>` | パスワードを対話的に 2 回入力させ、override を設定・更新する |
| `console-passwd --reset <user>` | override を削除する。以降はイメージ側のパスワードで認証される |
| `console-passwd --list` | override されているユーザー名を表示する |
| `console-passwd --check` | 存在しないユーザーのエントリ（orphan）を検出する。見つかれば終了コード 1 |

対象ユーザーは**イメージ側に実在している必要があります**。データベースが持てるのは「ユーザー名 → ハッシュ」だけで、UID・GID・ホームディレクトリ・シェルは持てないため、存在しないユーザーを登録してもログインは成立しません。存在しないユーザーを指定した場合はその場で拒否されます。

パスワードはシステム標準と同じ方式（yescrypt）でハッシュ化されます。

### `passwd` を使ってはいけない

override 済みのユーザーに対して通常の `passwd` を実行すると、単に無効なのではなく **データベース側と `/etc/shadow` 側の両方のパスワードで認証が通る状態**になります。同時に `/etc/shadow` が copy-up されるため、この機能で回避したはずのピン留め問題も再発します。

パスワードの変更は必ず `console-passwd` で行ってください。

## 適用範囲

**コンソールログイン（`/etc/pam.d/login`）だけ**が対象です。

| 経路 | override の適用 |
|---|---|
| シリアルコンソール（`serial-getty@`） | **される** |
| ローカル仮想端末 tty1-6（`getty@`） | **される** |
| SSH（`sshd`） | されない（`/etc/shadow` のまま） |
| `su` / `sudo` | されない |
| ディスプレイマネージャ（GDM、greetd 等） | されない |

意図的にこのスコープに限定しています。理由は 2 つあります。

- **失敗モードを復旧可能にするため。** 共通の `system-auth` に手を入れると、この仕組みに問題があったときに SSH ごと締め出され、イメージの焼き直し以外に復旧手段がなくなります。コンソール限定であれば、最悪コンソールが死んでも SSH は生きています
- **用途と一致するため。** 本機能の主目的は「SSH が壊れたときの最後の復旧手段」であり、そもそもリモートから使えてはいけない資格情報です。万一ハッシュが漏れてもリモートからは一切使えません

「`console-passwd` でパスワードを変えたのに GUI ログインでは通らない」という状況はこの設計どおりの動作です。

## 制限事項

- **`pam_faillock` が効きません。** override 済みユーザーは認証の成功・失敗とも faillock のカウント対象外になり、試行回数による一時ロックが働きません。コンソール（＝物理アクセス相当）限定という前提のもとで許容しています
- **パスワードの有効期限（aging）と整合しません。** `/etc/shadow` の last change は更新されないため、aging を使うアーティファクトでは齟齬が出る可能性があります
- **ユーザーの追加・削除は対象外です。** 本機能が解決するのは `/etc/shadow` のピン留めだけで、`/etc/passwd` や `/etc/group` をローカルで書き換えれば従来どおり copy-up されます。「アカウントの定義はイメージ側で管理し、稼働後に変えたいのは主にパスワードである」システムに向いた仕組みです
- **トランジェント構成では再起動で消えます。** データパーティションを持たないアーティファクトでは upper layer が tmpfs になるため、設定したパスワードは再起動で失われます

## 稼働中のシステムへ適用する場合

**すでに稼働しているシステムでは `/etc/shadow` が upper layer にコピーアップ済みである可能性が高い**点に注意してください。過去に一度でも `passwd` を実行していればこの状態になっています。

このまま本機能を有効にしても、upper 側の古い `/etc/shadow` が lower を隠し続けるため、**ピン留め問題は解消しません**。次の手順が必要です。

1. upper layer に `/etc/shadow` があるか確認する

   ```sh
   ls -l /run/initramfs/rw/root/etc/shadow
   ```

2. ある場合は、イメージ側（`/run/initramfs/ro/etc/shadow`）との差分を取り、ローカルで変更されたパスワードを把握する
3. 残したいパスワードを `console-passwd` で設定し直す
4. **upper 側の `/etc/shadow` を削除**し、lower layer の `/etc/shadow` が再び見えるようにする
5. 再起動して、イメージ側のユーザー構成が正しく反映されることを確認する

## 動作の仕組み

有効にすると、ビルド時に `/etc/pam.d/login` へ次の 2 行が挿入されます（`sys-auth/pambase` の所有ファイルなので、package-script が挿入します）。

```
auth  required  pam_env.so                                                       # ← 挿入される
auth  [success=done auth_err=die user_unknown=ignore default=die]  pam_userdb.so db=/etc/console-passwd.db crypt=crypt  # ← 挿入される
auth  include   system-local-login                                               # 元からある行
```

`pam_env` を先頭に置いているのは、`success=done` で後続の `include` ごと飛ばされる際に環境変数の設定が漏れないようにするためです。

| 制御 | 意味 |
|---|---|
| `success=done` | 認証成立。以降の auth スタックを飛ばす |
| `auth_err=die` | データベースにあるのに不一致なら**即座に失敗**。`pam_unix` へ落とさない |
| `user_unknown=ignore` | データベースに無いユーザーは無視して `pam_unix` へ継続 |
| `default=die` | データベースの異常やモジュール不在は fail closed |

`auth_err=die` が本機能の肝です。ここでフォールバックさせると、**イメージ側 `/etc/shadow` に残っている古いパスワード（既定では空パスワード）でも認証が通ってしまい**、override した意味がなくなります。

データベース `/etc/console-passwd.db` は gdbm 形式で、`root:root` の 0600 です。実質的にパスワードハッシュの集合であり、`/etc/shadow` と同等の機密情報として扱ってください。

**空のデータベースがイメージに同梱されます。** `default=die` の副作用として、データベースのファイル自体が存在しないと全ユーザーがログイン不能になるためです。エントリが 0 件であれば全ユーザーが `pam_unix` へフォールバックし、有効化前と同じ挙動になります。

## リカバリー

コンソールからログインできなくなった場合、**SSH は影響を受けていません**。SSH で入って次のいずれかを行ってください。

データベースが壊れた・消えた場合は、空のデータベースを作り直せば全ユーザーがイメージ側のパスワードで入れる状態に戻ります。

```sh
python3 -c 'import dbm.gnu, os; dbm.gnu.open("/etc/console-passwd.db", "n", 0o600).close(); os.chmod("/etc/console-passwd.db", 0o600)'
```

機能そのものを止めたい場合は、`/etc/pam.d/login` から上記 2 行を削除します（このファイルが upper layer へ copy-up されますが、緊急時には問題になりません）。

`exec_guard` のようにブートパーティションの `system.ini` から無効化する経路は用意されていません。**SSH を持たないアーティファクトでこの機能を使う場合は、復旧手段がイメージの再書き込みだけになる**点に留意してください。
