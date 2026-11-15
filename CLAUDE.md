# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

アメダスの観測データから降水を予測して可視化する個人プロジェクト。日本語でやりとりする。
`backend/local/` の3プロセス構成（server / client / frontend）は AWS サーバーレスへ移行中で、いずれ廃止する。

## 進め方

- 無断でコミット・push・マージしない
- コードにコメントを書かない。理由はコミットメッセージと PR に書く
- 使っていないコード・変数・output を足さない。見つけたら消す
- 作ったら動かして確かめる。テストは実データの fixture で書く

```bash
py -m pytest backend/lambda -v
bash backend/lambda/poll_weather_data/build.sh
terraform fmt -recursive infra/    # CI が -check で落とす
```

## 踏みやすい罠

- **データが2系統で非互換** — 学習用は obsdl CSV（ID `a0002`、列 `precip`）、リアルタイムは bosai JSON（ID `44132`、`precipitation10m`、値が `[観測値, 品質フラグ]`）。**ID 変換表は未着手**
- **品質フラグ** — `0` 正常 / `1` 準正常 / `6` 欠測（値が `null`）/ `null` 積雪系
- **`feature_order_test.py` を DRY にしない** — 学習時の定数をリテラルで持つのは意図的。import すると期待値も動きテストが永久に通る
- **DynamoDB に float を渡せない** — `Decimal(str(value))`
- **`batch_writer()` は `BatchWriteItem`** — `dynamodb:PutItem` の許可では通らない
- **Lambda の zip は git にコミットする** — Terraform が参照している。コード変更時は `build.sh` も実行
- **S3 には加工前の生データを置く** — 絞るのは読み出し側
- **観測データの CSV は gitignore** — 数GB。`stations*.csv` と `ml/models/*.txt` はコミット対象
