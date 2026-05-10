# ADR-0001: Gentoo ミラーを distfiles.gentoo.org CDN に切り替える

- 日付: 2026-05-10
- ステータス: 採用

## 背景

`genpack.py` は Gentoo の stage3 tarball および portage スナップショットの取得先として
IIJ のミラー (`http://ftp.iij.ad.jp/pub/linux/gentoo/`) を使用していた。

2026-05-10 に IIJ 側の IPv6 接続に障害が発生し、`requests.get()` がタイムアウト設定なしで
IPv6 接続を試み続けるため、stage3 URL の取得処理が長時間スタックする問題が確認された。

- curl は Happy Eyeballs (RFC 6555) により IPv4 へ即座にフォールバックするため影響を受けない
- Python の `requests` ライブラリは `getaddrinfo` の返す順に逐次接続を試みるため、
  IPv6 が詰まると OS の TCP タイムアウトまで待ち続ける

## 決定

`base_url` を `https://distfiles.gentoo.org/` に変更する。

`distfiles.gentoo.org` は Gentoo 公式の CDN (CDN77) であり、以下の特性を持つ。

- エンドユーザーに地理的に近い PoP からコンテンツを配信する
- HTTP/2 対応
- ETag・Last-Modified・Content-Length ヘッダをすべて返す（既存のキャッシュ判定ロジックと互換）

特定ミラーへの依存をなくすことで、単一障害点を排除できる。

## 検討した代替案

- **タイムアウト追加 + ミラーフォールバック**: `url_readlines` にタイムアウトを設定し、
  IIJ が失敗したら別ミラーへ切り替える。ただし複雑さが増す割に、CDN への一本化で
  同等以上の可用性が得られるため採用しなかった。

## 影響

- `src/genpack.py` の `base_url` 1行のみの変更。
- stage3 tarball・portage スナップショットの取得先が変わる。
- キャッシュ判定ヘッダ (ETag, Last-Modified, Content-Length) は distfiles.gentoo.org でも
  すべて提供されており、既存の再ダウンロード判定ロジックへの影響はない。
