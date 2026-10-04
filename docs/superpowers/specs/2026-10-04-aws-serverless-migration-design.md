# AWS サーバーレス移行 設計書

- 作成日: 2026-10-04
- 対象: 気象データ可視化プロジェクト（`univ/weather`）
- 範囲: データパイプライン + 全地点の事前推論 + 過去データ閲覧 + フロント公開 + CI/CD

## 1. 目的

CSV 再生による擬似リアルタイムを気象庁アメダスの実データに置き換え、常時起動のサーバーを持たない構成へ移行する。個人製作のため、**月額をほぼ $0 に収めることを最優先の制約**とする。

### 達成条件

| | |
|---|---|
| データ | 気象庁アメダスの実データが10分ごとに更新される |
| 予測 | 全地点の LightGBM 予測が毎時更新され、クリック時に即表示される |
| 過去 | 任意の地点・期間の観測と、その時点で出した予測を閲覧できる |
| 公開 | フロントが URL で閲覧できる |
| コスト | 月額 $1 未満。常時起動するサーバーを持たない |
| 再現性 | インフラが Terraform で定義され、`terraform apply` で再構築できる |
| 自動化 | `main` への push でインフラ・Lambda・フロントが反映される |

### 範囲外

- WBGT・熱中症リスク機能（廃止済み。bosai API に日射が無く計算不可）
- モデルの再学習（手元で実行する運用を継続）
- 独自ドメイン（CloudFront のデフォルトドメインで運用）

## 2. 現状

```
server.py (:8000)   CSV 642MB を VirtualClock で毎時1ステップ再生
    ↓ 0.5秒ごとにポーリング
client.py (:8001)   加工 + LightGBM 予測 + 24フレームをメモリ保持 + SSE 配信
    ↓ EventSource
Next.js (:3000)     完全クライアントサイド
```

両者は `backend/local/` へ退避済み。ローカル開発用モックとして残す。

### 廃止するもの

| | 理由 |
|---|---|
| SSE 配信 | 実データは10分更新。常時接続する意味がない |
| `Poller` のメモリ履歴（`deque(maxlen=24)`） | Lambda はインスタンスを保持しない |
| WBGT 計算（`compute_wbgt`） | bosai API に日射（solar）が無く計算不可 |

### 再利用するもの

| | 行き先 |
|---|---|
| `ml/inference.py` | 書き込み Lambda がそのまま使う（pandas 除去の改修あり） |
| `ml/models/*.txt`（8個・計8MB） | 書き込み Lambda の zip に同梱 |
| `data/stations*.csv` | 地点メタ（lat/lon/elev）と近隣探索の供給元 |
| `client.py` の `region_of` | 散布図の地域分類に使う |

## 3. 調査結果（検証済み）

実際に API を叩き、ベンチマークを実行して確認した事実を記録する。推測は含まない。

### 3.1 データソース

```
https://www.jma.go.jp/bosai/amedas/data/latest_time.txt
  → 2026-10-04T17:00:00+09:00

https://www.jma.go.jp/bosai/amedas/data/map/{yyyyMMddHHmmss}.json
  → 1286地点を1リクエストで取得

https://www.jma.go.jp/bosai/amedas/const/amedastable.json
  → 地点マスタ 1286件（type / elems / lat[度,分] / lon[度,分] / alt / kjName）
```

更新間隔は10分。全国分が1リクエストで揃うため、地点ごとに叩く必要はない。

### 3.2 取得できるフィールド

値は `[値, 品質フラグ]` の形で返る。

```json
{"temp": [12.7, 0], "humidity": [62, 0], "precipitation1h": [0.0, 0],
 "precipitation10m": [0.0, 0], "precipitation3h": [0.0, 0],
 "precipitation24h": [3.0, 0], "wind": [4.7, 0], "windDirection": [11, 0],
 "sun10m": [7, 0], "sun1h": [1.0, 0], "snow1h": [0, null], ...}
```

**日射（solar）は存在しない。** WBGT は計算不可。廃止方針と一致するため問題なし。

### 3.3 学習データは毎時

`backend/local/server.py` を起動して確認した。

```
stations: 1287
times: 721          ← 721 = 30日 × 24時間 + 1
```

観測は**毎時**である。`ml/inference.py` の `timedelta(hours=lag)` も毎時前提。推論に必要なのは**24個の毎時値**であり、10分刻みの144個ではない。

地点数の `1287` はCSVの全行数であり、本設計で以降用いる `1286` は緯度経度が有効な地点数である。差の1件は `stations.csv` の緯度経度欠落行（昭和基地と推定、14節参照）。

### 3.4 推論の実測値

`ml/models/*.txt` を実際にロードして計測した（ローカル PC）。

```
8モデルのロード             :  176.6 ms
一括推論 1286地点 x 8モデル :   39.9 ms
1地点のみ x 8モデル         :    1.3 ms

一括は1地点あたり           :    0.031 ms
```

**モデルのロード（177ms）が支配的で、推論自体は無視できる。** 1286倍のデータに対して30倍しかかからない。

この結果が「全地点を事前計算する」判断の根拠になる。全地点やる追加コストは 39ms であり、オンデマンドにして計算を節約する意味がない。

### 3.5 パッケージサイズ

```
lightgbm     4.7 MB
numpy       31.1 MB
scipy      109.5 MB   ← lightgbm が basic.py:30 で import scipy.sparse
pandas      61.9 MB
requests     0.5 MB
```

zip Lambda の上限は展開後 250MB。

| Lambda | 構成 | サイズ | 判定 |
|---|---|---|---|
| 書き込み | lightgbm + numpy + scipy + requests | **145.9 MB** | OK |
| 読み出し | 依存なし（boto3 はランタイム同梱） | **約10 KB** | OK |
| （参考）pandas 込み | 上記 + pandas | 207.8 MB | 収まるが不要 |

`inference.py` の pandas 使用は3箇所（12行目の import、35行目の型注釈、52行目の `read_csv`）のみ。`csv` モジュールに置き換えて 62MB を削る。

**両方 zip Lambda に収まるため、ECR と Docker が不要になる。** CI から docker build が消える。

### 3.6 地点IDの突き合わせ

**形式が異なる。** 手元 CSV は obsdl 用コード、bosai は独自採番。

```
手元CSV:  station_id = a0002   name = 沓形
bosai:    キー        = 11001   kjName = 宗谷岬
```

bosai の地点マスタに obsdl の ID は含まれない。名前と緯度経度で突き合わせるスクリプトを実行した結果：

```
[amedas] CSV=1131  name一致=1131  緯度経度一致=1131  両方一致=1131  不一致=0
[kansho] CSV=155   name一致=152   緯度経度一致=155   両方一致=152   不一致=0
```

1131 + 155 = **1286** で bosai と完全一致。名前で引き、一致しない3地点は緯度経度（0.02度以内の最近傍）で解決できる。bosai の緯度経度は `[度, 分]` 形式なので `度 + 分/60` で十進に変換する。

### 3.7 フロントが実際に使っているフィールド

`lib/types.ts` の定義のうち、参照されているものだけを grep で特定した。

**`WeatherPayload`**: `datetime` / `observations` / `wettest` / `raining_count`
**未使用**: `risk_counts` / `hottest`

**`Observation`**: `datetime` / `station_id` / `name` / `temp` / `precip` / `wind_dir` / `wind_speed` / `lat` / `lon` / `elev` / `type`
**未使用**: `humidity` / `solar` / `cloud` / `vapor_pressure` / `dew_point` / `wbgt` / `risk_level`

JSON スキーマは使用中のフィールドのみとする。

## 4. アーキテクチャ

Lambda を**書き込みと読み出し**で2つに分ける。

```
┌─ EventBridge Scheduler (rate: 10 minutes) ───────────────────┐
│                                                               │
│   Lambda W: write   (zip 145.9MB / 1024MB / 120秒)            │
│     1. latest_time.txt で最新時刻を取得                        │
│     2. 前回の latest.json を読む（冪等チェック）                │
│     3. map/{t}.json で1286地点を一括取得                       │
│     4. 正規化（bosai → 既存スキーマ）＋ 地点メタ結合             │
│     5. S3 へ latest.json を PUT                   ← 毎回        │
│     6. 毎時のみ:                                               │
│          history.json を読み更新（24時間 × 3変数）              │
│          全1286地点を一括推論（実測 40ms）                      │
│          S3 へ forecast.json / history.json を PUT             │
│     7. DynamoDB へ BatchWriteItem（毎時は予測も同じアイテムに）  │
└───────────────────────────────────────────────────────────────┘
          ↓                                    ↓
   S3 (data バケット)                    DynamoDB
     latest.json    ブラウザ向け          PK=station_id / SK=datetime
     forecast.json  ブラウザ向け          観測 +（毎時）予測
     history.json   Lambda 専用           プロビジョンド 25 WCU / 25 RCU
          ↓                                    ↑ Query
     CloudFront                                │
          ↓                                    │
       ブラウザ ─────── Function URL ──→ Lambda R: read
          ↑                              (zip 約10KB / 256MB / 10秒)
          │                                1. DynamoDB Query
   S3 (frontend バケット)                   2. 観測の時系列 + 保存済み予測を返す
     静的エクスポートした Next.js
```

### 4.1 なぜ書き込みと読み出しで分けるか

| | 理由 |
|---|---|
| 依存が全く違う | 書き込みは scipy 込みで 146MB、読み出しは依存ゼロ |
| 公開範囲が違う | 読み出しは Function URL で外部に晒す。書き込みは晒さない |
| 権限が違う | 読み出しに書き込み権限を与えない |
| コールドスタートが違う | 読み出しが約200ms で済む。146MB をロードしない |
| 障害が分離する | 読み出しが壊れても取得パイプラインは止まらない |

**ブラウザから DynamoDB は直接叩けない**（AWS の認証情報が必要で、ブラウザに置けない）。過去データ閲覧のために読み出し Lambda が必須になる。

### 4.2 なぜ全地点を事前計算するか

実測で追加コストが 39ms と判明したため（3.4節）、計算を節約する動機がない。事前計算して保存することで次の利点が得られる。

| | 事前計算 + 保存 | オンデマンド推論 |
|---|---|---|
| クリック時の待ち時間 | **0ms**（CloudFront キャッシュ） | 1〜2秒（コールドスタート） |
| 読み出し Lambda の依存 | **約10KB** | 146MB |
| 過去の予測の閲覧 | **できる** | できない（都度計算は過去を再現しない） |
| 予測 vs 実測の精度検証 | **できる** | できない |

最後の2つが決定的である。予測を保存すると、`based_at` 時点で出した予測と実際にその時刻に観測された値が同じテーブルに並ぶ。**後から予測精度を検証できる。**

### 4.3 ストレージの役割

| 置き場所 | 中身 | 読む人 | 更新 |
|---|---|---|---|
| S3 `latest.json` | 全地点の最新観測 + 24時間の降水量配列 | ブラウザ | 10分ごと |
| S3 `forecast.json` | 全地点の予測 | ブラウザ | 毎時 |
| S3 `history.json` | 24時間 × 3変数 × 全地点（推論の入力） | **Lambda W のみ** | 毎時 |
| DynamoDB | 全期間の観測 + 予測 | Lambda R | 10分ごと |

**S3 と DynamoDB は役割が違い、どちらも必要である。**

- S3 + CloudFront: 全員が同じものを見るデータ。エッジキャッシュが効き、閲覧者が1000人でもオリジンへの取得は10分に1回
- DynamoDB: 人によって違うクエリ（この地点の、この期間）。S3 では配れない

最新値を DynamoDB に移すと、ページを開くたびに1286件の読み取りが走り、エッジキャッシュも効かない。遅くなって高くなる。

`history.json` をブラウザに配らず Lambda 専用にする理由は、内部形式を自由に変更できるようにするためである。散布図が必要とする降水量は `latest.json` に `precip_24h` として重複して持たせる。200KB の重複はキャッシュ効率と引き換えに許容する。

## 5. コスト設計

月額をほぼ $0 に収めることが本設計の制約である。

### 5.1 DynamoDB — ここが唯一の実質的なコスト

```
観測: 1286件 × 144回/日 × 30日 = 月 5,560,000 write
予測: 毎時の観測アイテムの属性として書く  → 追加の書き込みは 0
```

**予測を別アイテムにしない。** 毎時の観測アイテムに `forecast` 属性として載せる。DynamoDB は 1KB までが 1 WCU であり、観測＋予測4件で約300バイトに収まるため、**アイテム数も WCU も増えない。**

| 課金モード | 月額 |
|---|---|
| オンデマンド | 約 $8 |
| **プロビジョンド 25 WCU** | **$0**（無料枠） |

プロビジョンドを採用する。負荷が10分ごとに1286件で完全に予測可能であり、オンデマンドの「突発的な負荷に追従する」利点が効かない。

**無料枠の性質（有効化前に請求ダッシュボードで確認する）**

| 対象 | 無料枠 | 本プロジェクトの使用 |
|---|---|---|
| プロビジョンド書き込み | 25 WCU（月 64,800,000 write） | 5,560,000 write（**8.6%**） |
| プロビジョンド読み込み | 25 RCU | 1% 未満 |
| ストレージ | 25 GB | 約 10 GB/年（約2.5年で到達） |

- 12か月の期限がない「Always Free」枠である
- **プロビジョンドのみが対象。オンデマンドのリクエストは1件目から課金される**
- **アカウント単位でありテーブル単位ではない。** 同一アカウントに他の DynamoDB テーブルがあると 25 WCU を分け合う。既存テーブルがある場合は前提が崩れるため、事前に確認する

### 5.1.1 PITR は無料枠の対象外

`point_in_time_recovery` はテーブルサイズに応じて別課金される（約 $0.20/GB・月）。

| 時期 | テーブルサイズ | PITR の月額 |
|---|---|---|
| 1か月目 | 約 0.8 GB | 約 $0.2 |
| 12か月目 | 約 10 GB | 約 $2 |

目標の「月 $0.05 未満」に対して40倍になり、設計上の最大コストになる。**初期構築では PITR を無効にする。**

無効にして安全と判断する根拠：

1. **破壊的な書き込みパターンが無い。** このテーブルは10分ごとに追記するのみで、既存アイテムの更新や削除を行わない。PITR が守る「誤った上書き・削除からの復旧」が起きる余地が構造的に無い
2. **`prevent_destroy` が Terraform 経由の事故を塞いでいる**（10.2節）
3. **後から設定変更だけで有効化できる**

バックアップが必要になった場合、PITR より S3 へのエクスポートが安い。

| 方式 | 単価の目安 |
|---|---|
| PITR | 約 $0.20 / GB・月 |
| S3 へエクスポート | 約 $0.023 / GB・月（約 1/9） |

```
平均書き込み: 1286 ÷ 600秒 = 2.14 write/秒        (25 WCU の 8.6%)
バースト:     毎時 2572件（観測1286 + 予測1286）
バースト容量: 300秒分 = 25 × 300 = 7500 WCU を蓄積
```

バースト容量が吸収し、約103秒の待機で補充される。スロットリング時は `BatchWriteItem` の `UnprocessedItems` を指数バックオフでリトライする（9節）。バックグラウンド処理であり利用者に影響しない。

読み込みは1地点 × 期間指定の Query。24時間分で約29KB、結果整合性読み取りで約4 RCU。25 RCU の範囲に十分収まる。

### 5.2 その他

| サービス | 使用量 | 月額 |
|---|---|---|
| Lambda W | 約 13,000 GB-s（無料枠 400,000 GB-s） | $0 |
| Lambda R | 約 40 GB-s | $0 |
| S3 | PUT 約 5,800回 + 保存 2MB 未満 | 約 $0.04 |
| CloudFront | 無料枠 1TB/月・1000万リクエスト | $0 |
| DynamoDB 書き込み | プロビジョンド 25 WCU（無料枠の 8.6%） | $0 |
| DynamoDB 保存 | 約 10GB/年（無料枠 25GB） | $0（約2.5年間） |
| DynamoDB PITR | **無効にする**（5.1.1節） | $0 |
| ECR | **使用しない** | $0 |
| **合計** | | **月 $0.05 未満** |

DynamoDB の保存量が 25GB を超えるのは約2.5年後。以降は約 $0.25/GB・月（14節参照）。

本節の単価は変動する。有効化の前に料金ページと請求ダッシュボードで確認し、予算アラートを設定する。

## 6. データ設計

### 6.1 `latest.json`（ブラウザ向け・10分更新）

```json
{
  "datetime": "2026-10-04 17:00:00",
  "raining_count": 123,
  "wettest": { "station_id": "a0002", "name": "沓形", "precip": 12.5 },
  "precip_24h_times": ["2026-10-03 18:00:00", "...", "2026-10-04 17:00:00"],
  "observations": [
    {
      "datetime": "2026-10-04 17:00:00",
      "station_id": "a0002",
      "name": "沓形",
      "temp": 12.7,
      "precip": 0.0,
      "wind_dir": "11",
      "wind_speed": 4.7,
      "lat": 45.1783,
      "lon": 141.1383,
      "elev": 14.0,
      "type": "アメダス",
      "precip_24h": [0.0, 0.5, null, "...24個..."]
    }
  ]
}
```

`station_id` は **obsdl 形式**（`a0002`）で統一する。モデルの学習時と一致させる必要があるため。

概算サイズ 320KB、gzip 70KB。

**`precip_24h` を含める理由。** 散布図（`useWindowPrecip`）は全1286地点の「直近N時間の平均降水量」を必要とし、`N` は利用者がスライダーで変更できる。DynamoDB で全地点分を引くと1286回の Query になり現実的でない。生の24時間配列を配り、**窓の平均はクライアントで計算する**。スライダー操作時の再取得も不要になる。

`precip_24h_times` は配列のインデックスに対応する時刻。欠測は `null`。

### 6.2 `forecast.json`（ブラウザ向け・毎時更新）

```json
{
  "based_at": "2026-10-04 17:00:00",
  "model": "LightGBM",
  "stations": {
    "a0002": [
      { "hours": 1,  "datetime": "2026-10-04 18:00:00", "temperature": 12.4, "rain_probability": 0.08 },
      { "hours": 6,  "...": "..." },
      { "hours": 12, "...": "..." },
      { "hours": 24, "...": "..." }
    ]
  }
}
```

予測不能な地点（緯度経度欠落、現在気温が欠測など）はキーごと省略する。フロントは存在しない地点を「予測なし」として扱う。

概算サイズ 400KB、gzip 80KB。毎時しか変わらないため `latest.json` と分離し、CloudFront の TTL を長く取る。

### 6.3 `history.json`（Lambda W 専用・毎時更新）

推論の入力専用。ブラウザには配らない。

```json
{
  "times": ["2026-10-03 18:00:00", "...", "2026-10-04 17:00:00"],
  "stations": {
    "a0002": {
      "temp":       [12.1, 12.3, null, "...24個..."],
      "precip":     [0.0, 0.5, 0.0, "..."],
      "wind_speed": [4.2, 4.7, 3.9, "..."]
    }
  }
}
```

`times` は昇順で最大24件。各配列は `times` と同じ長さ。欠測は `null`。概算サイズ 700KB。

DynamoDB から全地点分の履歴を引くと1286回の Query になるため、S3 の1ファイルで持つ。1時間あたり 1 GET + 1 PUT で済む。

### 6.4 DynamoDB

| | |
|---|---|
| テーブル名 | `weather-observations` |
| パーティションキー | `station_id` (S) — obsdl 形式 |
| ソートキー | `datetime` (S) — `YYYY-MM-DD HH:MM:SS` |
| 課金モード | **プロビジョンド 25 WCU / 25 RCU** |
| PITR | **無効**（5.1.1節参照。無料枠の対象外で月約$2かかる） |
| `prevent_destroy` | 有効 |

**アイテムの構造**

```
PK: station_id = "a0002"
SK: datetime   = "2026-10-04 17:00:00"
    temp        : N
    precip      : N
    wind_speed  : N
    wind_dir    : S
    humidity    : N
    forecast    : L   ← 毎時（分==0）のアイテムにのみ付く
                      [{hours, datetime, temperature, rain_probability} × 4]
```

欠測の属性は書かない（DynamoDB は `null` を属性として持てるが、容量を無駄にする）。

`PK=station_id, SK=datetime` を選ぶ理由は、読み出しが全て「特定地点の期間指定」であるため。

- 過去の観測の時系列: 1地点 × N時間 → 1 Query
- 過去の予測: 同じ Query で `forecast` 属性が付いてくる
- 予測 vs 実測の検証: 同じ Query 結果の中で突き合わせられる

GSI は作らない。全地点を横断する集計は `history.json` と `latest.json` が担当する。

## 7. Lambda W: 書き込み

```python
def handler(event, context):
    t = fetch_latest_time()                      # latest_time.txt
    prev = read_s3_json("latest.json")            # 無ければ None

    if prev and prev["datetime"] == fmt(t):
        return {"skipped": True}                  # 冪等性: 同じ時刻なら何もしない

    raw = fetch_map(t)                            # map/{t}.json → 1286地点
    obs = normalize(raw, station_map, station_meta)

    forecasts = {}
    if t.minute == 0:
        history = read_s3_json("history.json") or empty_history()
        history = append_frame(history, obs, t)   # 追加し、24件を超えたら先頭を捨てる
        forecasts = predict_all(history, station_meta)   # 実測 40ms

        put_s3_json("history.json", history)
        put_s3_json("forecast.json", build_forecast_payload(forecasts, t))

    put_s3_json("latest.json", build_latest_payload(obs, t, history_or_prev))
    batch_write_dynamodb(obs, forecasts, t)       # 毎時は forecast 属性も載せる

    return {"datetime": fmt(t), "stations": len(obs), "forecasts": len(forecasts)}
```

### 7.1 正規化の対応表

| 既存スキーマ | bosai | 変換 |
|---|---|---|
| `station_id` | JSON のキー | 対応表で bosai ID → obsdl ID |
| `temp` | `temp[0]` | そのまま |
| `precip` | `precipitation1h[0]` | **毎時降水量。学習時と一致させる** |
| `wind_speed` | `wind[0]` | そのまま |
| `wind_dir` | `windDirection[0]` | 文字列化 |
| `humidity` | `humidity[0]` | DynamoDB にのみ保存 |
| `name` `lat` `lon` `elev` `type` | — | `stations*.csv` から結合 |

品質フラグ（配列の2番目）が `0` 以外は欠測として `null` にする。フィールド自体が無い場合も `null`。

`precip` に `precipitation1h` を使うことが最重要である。学習データは obsdl の毎時降水量であり、`precipitation10m` を誤って使うと値が約 1/6 になる。モデルは動くが予測だけが静かに狂う。

### 7.2 推論のバッチ化

現在の `ForecastService.predict()` は1地点ずつ呼ぶ設計であり、`_features()` が地点ごとに `observation_at` を呼ぶ。1286地点では約9.3万回の辞書参照が発生する。

`predict_all(history, station_meta)` を新設し、特徴量行列を一括で構築する。

```
1. 近隣5地点を全地点分あらかじめ解決（_nearest_station_ids をループ、結果をキャッシュ）
2. history から (1286, 92) の float32 行列を構築
3. 8モデルそれぞれに1回 predict() を呼ぶ       ← 実測 40ms
4. 地点ID × 時間帯の辞書に展開
```

**既存の `predict()` は残す。** `test_feature_order.py`（13節）が両経路で同じ特徴量を作ることを検証し、バッチ化による退行を検出する。

### 7.3 地点IDの対応表

実行時に名前や緯度経度で突き合わせると、失敗が静かに混入する。**事前に生成してコミットする。**

```
backend/data/station_id_map.json
  { "11001": "a0002", ... }   bosai ID → obsdl ID
```

生成スクリプト `backend/data/build_station_map.py` を用意し、以下を満たさない場合はエラーで停止させる。

- 対応件数が 1286 件
- obsdl ID に重複がない
- 名前一致しなかった地点について、緯度経度の距離が 0.02 度以内

## 8. Lambda R: 読み出し

Function URL で公開する。API Gateway を使わない（不要な層とコストを避ける）。依存は無く、`boto3` は Lambda ランタイムに同梱されている。

```python
def handler(event, context):
    station_id = query_param(event, "station_id")
    hours      = int(query_param(event, "hours", default=24))
    end        = query_param(event, "end")        # 省略時は最新

    items = table.query(
        KeyConditionExpression=Key("station_id").eq(station_id)
            & Key("datetime").between(start_of(end, hours), end),
    )

    return {
        "station_id": station_id,
        "points": [to_point(i) for i in items],      # 観測の時系列
        "forecasts": [to_fc(i) for i in items if "forecast" in i],  # 保存済み予測
    }
```

1回の Query で観測と予測の両方が返る。同じアイテムに同居しているため。

### 8.1 CORS

Function URL の CORS 設定で、CloudFront のドメインのみを許可する。

```hcl
cors {
  allow_origins = ["https://<cloudfront-domain>"]
  allow_methods = ["GET"]
  max_age       = 86400
}
```

### 8.2 入力検証

Function URL は認証なしで公開するため、入力を検証する。

| パラメータ | 検証 |
|---|---|
| `station_id` | 地点マスタに存在するIDのみ許可。存在しなければ 404 |
| `hours` | 1〜720（30日）に制限。超える値は 400 |
| `end` | `YYYY-MM-DD HH:MM:SS` 形式のみ。不正なら 400 |

`hours` に上限を設ける理由は、巨大な期間を要求されて RCU を使い切られるのを防ぐため。プロビジョンド容量は共有資源である。

## 9. エラーハンドリング

| 事象 | 対応 |
|---|---|
| bosai API が 5xx / タイムアウト | 指数バックオフで3回リトライ。失敗時は例外で終了し、**`latest.json` を更新しない**（古いデータが残る方が空より良い） |
| 一部地点が欠測 | `null` のまま流す。`inference.py` の `_number` が NaN に変換し、LightGBM が欠損として扱う |
| 対応表に無い bosai ID | 観測をスキップし CloudWatch に警告。件数が10を超えたら異常として例外 |
| 推論が失敗 | `forecast.json` を更新せず、`latest.json` と DynamoDB の観測書き込みは実行する |
| `BatchWriteItem` の `UnprocessedItems` | 指数バックオフでリトライ。3回失敗で例外 |
| DynamoDB のスロットリング | 上記と同じ経路で吸収。プロビジョンド容量のため想定内 |
| Lambda R に不正な入力 | 400 / 404 を返す。例外にしない |
| Lambda が例外終了 | CloudWatch アラームで通知。次回10分後の起動で自動回復 |

**処理順序が復旧性を決める。** 表示に必要な `latest.json` を先に書き、重い推論と DynamoDB 書き込みを後に置く。推論が失敗しても地図の表示は最新のままになる。

### 監視

`terraform apply` を自動化するため、異常に気づく仕組みを必須とする。

- Lambda W / R の `Errors` が5分間に1回以上 → SNS 通知
- Lambda W が30分間1回も成功しない → SNS 通知
- DynamoDB の `ThrottledRequests` が継続 → SNS 通知（プロビジョンド容量の見直し判断に使う）
- **AWS Budgets で月額 $1 を超えたら通知**（無料枠を外れたことに気づくため。予算2件までは無料）

月額をほぼ $0 に収めることが本設計の制約であるため、最後の予算アラートは必須とする。無料枠の前提が崩れた場合（アカウント内の他テーブルが 25 WCU を消費していた、単価が変わった等）、これが唯一の検知手段になる。

## 10. Terraform 構成

```
infra/
├─ main.tf              provider / backend (S3 + DynamoDB ロック)
├─ s3_data.tf           データバケット（prevent_destroy）
├─ s3_frontend.tf       フロントバケット（OAC のみ許可）
├─ cloudfront.tf        ディストリビューション + OAC + キャッシュポリシー
├─ dynamodb.tf          観測テーブル（プロビジョンド 25/25 / prevent_destroy）
├─ lambda_write.tf      Lambda W（zip / EventBridge Scheduler）
├─ lambda_read.tf       Lambda R（zip / Function URL / CORS）
├─ iam_lambda.tf        各 Lambda の実行ロール（権限を分ける）
├─ iam_github.tf        GitHub OIDC プロバイダ + 2つのロール
├─ monitoring.tf        CloudWatch アラーム + SNS + AWS Budgets（月額 $1 で通知）
└─ variables.tf
```

リージョンは `ap-northeast-1`。**ECR は作成しない。**

### 10.1 Lambda の実行ロールを分ける

| Lambda | 必要な権限 |
|---|---|
| W: write | S3 の `GetObject`/`PutObject`（データバケットのみ）、DynamoDB `BatchWriteItem` |
| R: read | DynamoDB `Query` のみ |

**読み出し Lambda に書き込み権限を与えない。** Function URL で公開する面であり、攻撃対象になる。

### 10.2 データ保護

`terraform apply` を CI に任せるため、誤った変更でデータが消えない仕組みを入れる。

```hcl
# DynamoDB テーブル / データバケット
lifecycle {
  prevent_destroy = true
}

# PITR は有効にしない（5.1.1節: 無料枠の対象外で月約$2）
point_in_time_recovery { enabled = false }
```

リソース名を誤って変更した場合、`destroy` が阻止され apply が失敗する。データが消えるより apply が失敗する方が安全である。

PITR を使わないため、`prevent_destroy` が唯一のデータ保護機構になる。DynamoDB テーブルとデータバケットの両方に必ず付ける。

### 10.3 キャッシュ設定

| パス | TTL | 理由 |
|---|---|---|
| `latest.json` | 300秒 | 10分更新なので半分の値にする |
| `forecast.json` | 1800秒 | 毎時更新 |
| `history.json` | **配信しない** | Lambda 専用。CloudFront のビヘイビアから除外する |
| 静的アセット（`_next/static/*`） | 1年 | ファイル名にハッシュが入る |
| `index.html` | 60秒 | デプロイ後に早く切り替わるように |

Lambda R は Function URL を直接叩くため CloudFront を経由しない。

## 11. CI/CD

GitHub Actions + OIDC。長期のアクセスキーは置かない。

```
.github/workflows/
├─ terraform.yml   infra/**        PR → plan をコメント / main → apply
├─ lambda.yml      backend/**      zip 作成 → 両 Lambda を更新
└─ frontend.yml    frontend/**     next build → S3 sync → CF invalidation
```

`paths` フィルタで変更範囲に応じたワークフローのみを走らせる。

**Docker ビルドが不要なため、`lambda.yml` は zip の作成と `update-function-code` のみで完結する。** 依存は `pip install -t` でディレクトリに展開して zip に固める。Lambda R は依存が無いため zip が数十KBで済む。

### 11.1 IAM ロールを2つに分ける

| ロール | 権限 | 使うワークフロー |
|---|---|---|
| `gh-actions-deploy` | Lambda 更新 / S3 sync / CF invalidation | `lambda.yml` `frontend.yml` |
| `gh-actions-terraform` | インフラ管理に必要な広い権限 | `terraform.yml` |

デプロイ用の弱いロールとインフラ用の強いロールを分ける。デプロイのワークフローが侵害されてもインフラを壊せない。

### 11.2 フロントのビルド時変数

`NEXT_PUBLIC_CARTO_KEY` を GitHub Secrets から注入する。

**注意:** `NEXT_PUBLIC_` 接頭辞の変数は JS バンドルに埋め込まれ、閲覧者から見える。これは秘密を守る仕組みではなく、リポジトリにキーを置かないための措置である。CARTO 側でリファラ制限をかけることを推奨する。

## 12. フロントエンドの変更

| ファイル | 変更 |
|---|---|
| `next.config.mjs` | `output: "export"` を追加 |
| `lib/config.ts` | `API_BASE` を CloudFront の URL、`READ_API_URL` を Function URL に。環境変数から読む |
| `providers/WeatherStreamProvider.tsx` | `EventSource` → `fetch` + 10分間隔のポーリング |
| `hooks/useStationForecast.ts` | `/forecast` API → `forecast.json` から該当地点を引く |
| `hooks/useWindowPrecip.ts` | `/window` をやめ、`latest.json` の `precip_24h` から窓の平均をクライアントで計算 |
| `hooks/useWindowAvg.ts` | 同上（`precip_24h` と `temp` から算出） |
| `hooks/useStationHistory.ts` | `/history_series` → `READ_API_URL` を叩く |
| `lib/types.ts` | 未使用フィールドを削除（`wbgt` `risk_level` `risk_counts` `hottest` `solar` `cloud` `vapor_pressure` `dew_point` `humidity` および `RiskLevel` `Hottest` 型） |

`WeatherStreamProvider` の外側は変更不要。`useWeatherStream()` のインターフェースを保つ。

### 12.1 ポーリングへの置き換え

```ts
useEffect(() => {
  let alive = true;
  const load = async () => {
    try {
      const res = await fetch(`${API_BASE}/latest.json`, { cache: "no-store" });
      if (!alive) return;
      setConnected(res.ok);
      if (res.ok) setPayload(await res.json());
    } catch {
      if (alive) setConnected(false);
    }
  };
  load();
  const id = setInterval(load, 10 * 60 * 1000);
  return () => { alive = false; clearInterval(id); };
}, []);
```

`connected` の意味は「SSE が接続中」から「直近の取得が成功」に変わる。[NavBar.tsx:37](frontend/components/layout/NavBar.tsx#L37) の表示はそのまま使える。

## 13. テスト方針

フレームワークは導入せず、`py -m pytest` で動く最小のテストのみ置く。

| テスト | 何が壊れたら落ちるか |
|---|---|
| `test_normalize.py` | bosai JSON の正規化。固定サンプルを入力し、期待する `Observation` と比較 |
| `test_station_map.py` | 対応表が1286件、obsdl ID に重複なし、双方向に解決できる |
| `test_feature_order.py` | **最重要。** 特徴量ベクトルの順序が学習時と一致し、かつ `predict()` と `predict_all()` が同じ行を作る |

3つ目を最重要とする理由は、ここが壊れても**エラーが出ない**ためである。`inference.py:80` の `num_feature()` チェックは個数しか見ないため、順序が入れ替わっても通過し、モデルは動いたまま予測だけが狂う。既知の入力に対する既知の出力を固定値で assert する。

このテストは2つの退行を同時に検出する。

- pandas 除去（`csv` モジュールへの置き換え）による地点メタの読み違い
- `predict_all()` のバッチ化による特徴量の並び違い

## 14. 段階と残課題

### 実装順

| | 内容 |
|---|---|
| 1 | 事前準備（15節） |
| 2 | 地点ID対応表の生成とテスト |
| 3 | `inference.py` の pandas 除去 + `predict_all()` + 特徴量順序テスト |
| 4 | Terraform の土台（S3 / DynamoDB / IAM / OIDC） |
| 5 | Lambda W（書き込み）+ EventBridge |
| 6 | DynamoDB と `history.json` の24時間分バックフィル |
| 7 | Lambda R（読み出し）+ Function URL |
| 8 | フロントの静的エクスポート + CloudFront 公開 |
| 9 | CI/CD 3ワークフロー |

### 初回バックフィル

デプロイ直後は履歴が無く、予測が出せない。`map/{t}.json` を過去24時間分（24リクエスト）取得して埋める。**ローカルスクリプトとして実装する**（Lambda のタイムアウトを気にせず、書き込み速度を自分で制御できる）。

DynamoDB への書き込みは 24時刻 × 1286地点 = 30,864件になる。プロビジョンド 25 WCU を超えないよう、スクリプト側で **20 write/秒に自己制限**する。所要約26分。

### 残課題

- **`ml/dataset.py` と `inference.py` の特徴量順序の一致確認。** 両者がコードを共有していない場合、共有モジュールへの切り出しを検討する
- **`stations.csv` の緯度経度欠落行（155/156）。** 昭和基地と推定。除外して問題ないか確認する
- **DynamoDB の保存量。** 約2.5年で無料枠 25GB に到達する。TTL 属性で古い10分データのみ削除し毎時データを残す、または S3 へアーカイブする方針を後日判断する
- **バックアップ方針。** PITR を無効にしている（5.1.1節）。追記のみのテーブルであり `prevent_destroy` で保護されるため初期は不要と判断した。データが蓄積して価値が上がった時点で、S3 へのエクスポート（PITR の約 1/9 の単価）を検討する
- **予測精度の可視化。** `forecast` 属性と実測が同じテーブルに揃うため、精度検証の画面を後から追加できる。本設計の範囲外とするが、データ構造はそれを前提にしている

## 15. 事前準備（リポジトリ側）

実装前に片付ける。

| | 作業 | 状態 |
|---|---|---|
| 1 | `git gc --prune=now` — 到達不能な blob 5.4GB（圧縮後679MB）を回収 | 未実施 |
| 2 | `backend/lambda/` を削除 — `lambda` は Python の予約語で import 不可 | 未実施 |
| 3 | `stations*.csv` をコミット — `inference.py` に必須の実行資産（68KB） | 完了 |
| 4 | `station_id_map.json` を生成しコミット | 実装フェーズ 2 |
| 5 | `git switch -c aws` — `main` を動く状態で保全 | 完了 |

`.gitignore` は本設計の作成時に修正済み。

- `backend/data/*.csv` → `backend/data/observations*.csv`（地点マスタを追跡対象に）
- `docs/` → `docs/*` + `!docs/superpowers/`（卒研の成果物 4.4MB は除外を維持し、設計書のみ追跡）

Lambda のディレクトリ構成は予約語を避けて次のようにする。

```
backend/
├─ handlers/
│  ├─ write.py        Lambda W（取得 + 推論 + 書き込み）
│  └─ read.py         Lambda R（DynamoDB 読み出し）
├─ processing.py      正規化・集計（client.py から移動）
├─ config.py
├─ ml/                inference.py / models/
├─ data/              地点マスタ / 対応表 / 取得スクリプト / バックフィル
└─ local/             server.py / client.py（ローカル開発用モック）
```
