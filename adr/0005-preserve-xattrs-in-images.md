# ADR 0005: システムイメージで拡張属性(xattr)を保存する

## ステータス

**Accepted**（2026-07-03）

## コンテキスト

genpack のシステムイメージ(SquashFS)は現状 xattr を保存している。その結果、
xattr を持つシンボリックリンクは SquashFS の **extended symlink inode (type 10)** として
書き出される。

genpack-install-gui（インストーラ）が `/.genpack/{arch,artifact,...}` を読むために
pure-Rust の SquashFS リーダ `backhand` を試したところ、backhand 0.25.1 は
extended symlink 以降の inode(type 10〜14)が未実装(ソース上 TODO)で、これを含む
genpack イメージを `from_reader` の時点でパースできなかった
(`Deku(Parse("ID 10 not found on InodeId"))`)。

ここで「イメージ生成時に xattr を剥がせば basic inode だけになり、pure-Rust リーダで
ループマウント無し・root 無しに読める」という誘惑が生じる。本 ADR はこれを**採らない**
ことを明文化する。

## 決定

**システムイメージ生成時に xattr を剥がさない。イメージ形式はカーネルが書き出すものを
忠実に保持し、読み取りツール側を形式に合わせる。**

## 理由

1. **xattr は既に荷重がかかっている**
   - `security.capability`（ファイルケーパビリティ）は setuid-root を避けた権限付与の要。
     剥がすと該当バイナリが黙って壊れる。
   - POSIX ACL(`system.posix_acl_access`)、`security.selinux` も同様にパーミッション/
     アクセス制御の実体。

2. **immutable OS ほど将来 xattr 依存が増える**
   読み取り専用イメージの完全性検証(IMA/EVM の `security.ima`・`security.evm`、
   fs-verity の署名)はいずれも xattr ベース。measured boot / appraisal を将来導入する
   なら xattr は必須になる。今剥がす設計にすると、その将来を自ら塞ぐ。
   （※ dm-verity はブロック単位で xattr を使わないが、それでも capability の分は残る。）

3. **レイヤリングとして正しい**
   イメージ形式は「OS が必要とするメタデータを忠実に保持する」ものであり、特定の
   ユーザ空間パーサの実装都合に合わせて内容を削るのは本末転倒。参照実装(カーネルの
   SquashFS ドライバ)は当然フル対応している。

## 検討した代替案

- **xattr を全部剥がす** — capability 等が壊れ、完全性検証の将来を塞ぐ。却下。
- **symlink の xattr だけ剥がす** — extended symlink を避けられるが、場当たり的で
  「なぜ symlink だけ？」という不透明な特殊処理が残る。却下。
- **backhand に type 10〜14 を実装して上流へ** — 筋は良い(TODO が明示されている)。
  ただしイメージ側の判断とは独立。将来 pure-Rust 読みが必要になったら検討する。

## 結果

- genpack イメージは pure-Rust の no-root SquashFS 読みができない（extended inode 対応
  パーサが現れるまで）。
- 当面 `/.genpack/*` メタデータの読み取りはカーネルのループマウント経由で行う
  （genpack-install-gui の `read_genpack_metadata`。インストーラは root なので可）。
- capability・ACL・将来の完全性検証(IMA/EVM/fs-verity)がイメージ側で保証され続ける。
