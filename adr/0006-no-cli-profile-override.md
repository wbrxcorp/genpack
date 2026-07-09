# ADR-0006: CLI の `--profile` オーバーライドは追加せず、profile の出し分けは `variants` に任せる

- 日付: 2026-07-09
- ステータス: 採用（CLI `--profile` は不採用）

## 背景

`genpack.json5` の `profile` は genpack-overlay 上の Portage プロファイルを選び、パッケージ集合・
USE・キーワード・カーネル/ファームウェアまでを決める、Lower ビルドの根幹である。例として
同一 `aarch64` でも:

- `baremetal` … 一般的な物理マシン向け
- `raspberrypi` … `baremetal` を継承し、Raspberry Pi 固有のカーネルとファームウェアを追加

のように、**同じアーティファクト定義から profile だけ（あるいは主に profile）を切り替えて
ビルドし分けたい**場面がある。

これに対し、CLI に `--profile <NAME>` を足して `genpack.json5` の `profile` をアドホックに
上書きする案が検討された。`--arch` や `--compression` と同様の「ビルド時の一時オーバーライド」
として自然に見えるためである。

一方で、同一アーティファクトから構成差のあるイメージを出すための機構として、すでに
**`variants` + CLI `--variant`** が存在する。バリアント内では `profile` を含む大半の
トップレベルフィールドを上書きでき、work イメージもバリアント名ごとに分離される
（`lower-{name}.img` / `upper-{name}.img`）。本 ADR は、profile の出し分けを
`--profile` ではなく **`variants` に寄せる**ことを明文化する。

## 決定

**CLI に `--profile` オプションは追加しない。**

同一 `genpack.json5` から profile（およびそれに伴う差分）を切り替えてビルドし分ける場合は、
`variants` で名前付きバリアントを宣言し、`--variant` で選択する。

```json5
{
  name: "myapp",
  profile: "baremetal",
  packages: [ /* 共通 */ ],
  variants: {
    raspberrypi: {
      profile: "raspberrypi"
      // 必要なら packages / use / outfile もここで差分
    }
  }
}
```

```bash
genpack --arch aarch64 build                          # デフォルト profile（baremetal）
genpack --arch aarch64 --variant raspberrypi build    # RPi 向け
```

## なぜこの形か

1. **profile は work の中身を根幹から変える**  
   `--compression` のような pack 時だけの差し替えとは異なり、profile 変更は Portage プロファイル
   全体（`@profile` パッケージ集合、USE、カーネル/FW など）に効く。`Variant` はすでに
   `lower-{name}.img` などを分離しているが、素の `--profile` だけでは同一
   `work/{arch}/lower.img` を共有しやすく、前の profile の残骸と混ざる危険がある。

2. **再ビルド判定に CLI だけの変更が載らない**  
   Lower の outdated 判定は主に `genpack.json5` と Portage 関連サブディレクトリの mtime に
   依存する。CLI だけで profile を切り替えても `lower.done` が古く扱われず、意図せず
   前 profile の lower のまま upper/pack が進みうる。`--profile` を入れるなら work パスや
   outdated 判定に profile を含める必要があり、実質 variants と同等の隔離機構を二重実装する
   ことになる。

3. **「profile だけ違う」が長く続かない**  
   `baremetal` と `raspberrypi` のような分岐は、やがて packages / use / outfile / services など
   profile 以外の差分を伴いがちである。variants はその差分を同じ軸にまとめられるが、
   `--profile` 単体では足りなくなり、結局 variants が必要になる。

4. **設定軸を増やさない**  
   すでに「ベース → arch マージ → variant マージ」の優先順位があり、variant 内でも
   `profile` を上書きできる。ここに CLI `--profile` を足すと
   `CLI > variant > トップレベル` の三重になり、work キー（variant 名 vs profile 名）の
   取り方も曖昧になる。出し分けの**主軸を `--variant` に一本化**した方が、宣言が
   json5 に残り再現性も高い。

5. **既存 CLI オーバーライドとの役割分担**  

   | オプション | 影響範囲 | work 分離 |
   |---|---|---|
   | `--arch` | 全体 | `work/{arch}/` |
   | `--variant` | 設定一式（profile 含む） | `lower-{variant}` 等 |
   | `--compression` | pack 時のみ | 不要 |
   | `--devel` | 開発用フラグ | 既存の流れに乗る |
   | **`--profile`（不採用）** | Lower の根幹 | 現状なし／実装コスト大 |

## 検討した代替案

- **CLI `--profile` を追加し、json5 の `profile` を上書きする**  
  アドホックな試し切りには便利だが、上記の work 衝突・outdated 判定・軸の二重化が残る。
  隔離まで実装すると variants の再発明になる。**不採用**。

- **CLI `--profile` を実験専用とし、常に lower を無効化する／警告する**  
  事故は減るが、製品ビルドし分けの主経路としては向かず、利用者は結局 variants を使う。
  主経路を増やさない方針と矛盾するため**不採用**（将来、明確な実験用途が必要になれば
  別 ADR で再検討可）。

- **`arch.<arch>.profile` でアーキごとに profile を選ぶ**  
  `x86_64` と `aarch64` で profile を変える用途には有用かもしれないが、**同一 arch 内**の
  baremetal / raspberrypi 分岐には使えない。現状 `arch` マージの許可フィールドにも
  `profile` は含まれない。本 ADR の対象外とし、必要なら別途検討する。

- **アーティファクトをディレクトリごとフォークする**  
  共通 packages / scripts の二重保守になる。variants の方が軽い。**不採用**。

## 影響

- **コード変更なし**（現状の `variants` / `--variant` / `Variant` の work 分離をそのまま使う）。
- ドキュメント上の方針: profile の出し分けは [docs/json5.md](../docs/json5.md) の `variants` と
  [docs/cli.md](../docs/cli.md) の `--variant` を正とする。本 ADR は「なぜ CLI `--profile` を
  足さないか」の経緯記録である。
- 既存アーティファクト・CLI 互換性への影響はない。

## 利用例（推奨パターン）

同一 aarch64 アーティファクトから baremetal と Raspberry Pi 向けを出す場合:

```json5
{
  name: "appliance",
  profile: "baremetal",
  packages: ["app-misc/foo"],
  variants: {
    raspberrypi: {
      profile: "raspberrypi"
    }
  },
  // 任意: 未指定時のバリアント
  // default_variant: null のままならトップレベル profile が使われる
}
```

```bash
genpack --arch aarch64 build
genpack --arch aarch64 --variant raspberrypi build
```

出力はバリアント名が載る（例: `appliance-raspberrypi-aarch64.squashfs`）。outfile を
固定したい場合はバリアント内で `outfile` を指定する。
