# AWS サーバーレス移行 設計書

- 作成日: 2026-10-04
- 対象: 気象データ可視化プロジェクト（`univ/weather`）
- 範囲: フェーズ2（データパイプライン）+ フロント公開 + CI/CD

## 1. 目的

CSV 再生による擬似リアルタイムを、気象庁アメダスの実データに置き換え、常時起動のサーバーを持たない構成へ移行する。

### 達成条件

| | |
|---|---|
| データ | 気象庁アメダスの実データが10分ごとに更新される |
| 予測 | 全1286地点の LightGBM 予測が毎時更新される |
| 公開 | フロントが URL で閲覧できる |
| 運用 | 常時起動するサーバーが無く、月額が数ドル以内に収まる |
| 再現性 | インフラが Terraform で定義され、`terraform apply` で再構築できる |
| 自動化 | `main` への push でインフラ・Lambda・フロントが反映される |

### 範囲外

- DynamoDB の読み出し API（フェーズ3）。本設計では書き込みのみ行う
- WBGT・熱中症リスク機能（廃止済み）
- モデルの再学習（手元で実行する運用を継続）

## 2. 現状

```
server.py (:8000)   CSV 642MB を VirtualClock で毎時1ステップ再生
    ↓ 0.5秒ごとにポーリング
client.py (:8001)   加工 + LightGBM 予測 + 24フレームをメモリ保持 + SSE 配信
    ↓ EventSource
Next.js (:3000)     完全クライアントサイド
```

両者は `backend/local/` へ退避済み。ローカル開発用モックとして残す。

### 移行で廃止するもの

| | 理由 |
|---|---|
| SSE 配信 | 実データは10分更新。常時接続する意味がない |
| `Poller` のメモリ履歴（`deque(maxlen=24)`） | Lambda はインスタンスを保持しない |
| `/history` `/window` `/forecast` エンドポイント | 事前計算した JSON に置き換える |
| WBGT 計算（`compute_wbgt`） | bosai API に日射（solar）が無く、計算不可。廃止方針とも一致 |

### 再利用するもの

| | 行き先 |
|---|---|
| `ml/inference.py` | Lambda がそのまま使う（バッチ化の改修あり） |
| `ml/models/*.txt`（8個） | Lambda のイメージに同梱 |
| `data/stations*.csv` | 地点メタ（lat/lon/elev）の供給元 |
| `client.py` の `region_of` | 散布図の地域分類に使う |

## 3. 調査結果（検証済み）

実際に API を叩き、スクリプトを実行して確認した事実を記録する。推測は含まない。

### 3.1 データソース

```
https://www.jma.go.jp/bosai/amedas/data/latest_time.txt
  → 2026-10-04T17:00:00+09:00

https://www.jma.go.jp/bosai/amedas/data/map/{yyyyMMddHHmmss}.json
  → 1286地点を1リクエストで取得

https://www.jma.go.jp/bosai/amedas/const/amedastable.json
  → 地点マスタ 1286件（type / elems / lat[度,分] / lon[度,分] / alt / kjName）
```

更新間隔は10分。地点ごとに叩く必要はなく、全国分が1リクエストで揃う。

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

`backend/local/server.py` を起動し確認した。

```
stations: 1287
times: 721          ← 721 = 30日 × 24時間 + 1
```

`config.py` の `LOAD_RECENT_DAYS = 30` に対して721時刻。観測は**毎時**である。`ml/inference.py` の `timedelta(hours=lag)` も毎時前提。

なお地点数の `1287` はCSVの全行数であり、本設計で以降用いる `1286` は緯度経度が有効な地点数である。差の1件は `stations.csv` の緯度経度欠落行（昭和基地と推定、3.4節および14節を参照）。`inference.py` は緯度経度が無い地点を予測対象から除外するため、実質的な対象は1286地点となる。

この結果、**履歴は24フレームで足りる**（10分刻みの144フレームは不要）。

| | 当初の想定 | 確定 |
|---|---|---|
| 履歴フレーム数 | 144 | **24** |
| `history.json` のサイズ | 約3MB | **約700KB**（gzip 150KB） |

### 3.4 地点IDの突き合わせ

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

1131 + 155 = **1286** で bosai と完全一致。名前で引き、一致しない3地点は緯度経度（0.02度以内の最近傍）で解決できる。

緯度経度は bosai が `[度, 分]` 形式なので `度 + 分/60` で十進に変換する。

### 3.5 フロントが実際に使っているフィールド

`lib/types.ts` の定義のうち、参照されているものだけを grep で特定した。

**`WeatherPayload`**: `datetime` / `observations` / `wettest` / `raining_count`
**未使用**: `risk_counts` / `hottest`

**`Observation`**: `datetime` / `station_id` / `name` / `temp` / `precip` / `wind_dir` / `wind_speed` / `lat` / `lon` / `elev` / `type`
**未使用**: `humidity` / `solar` / `cloud` / `vapor_pressure` / `dew_point` / `wbgt` / `risk_level`

JSON スキーマは使用中のフィールドのみとする。

## 4. アーキテクチャ

```
┌─ EventBridge Scheduler (rate: 10 minutes) ──────────────┐
│                                                          │
│   Lambda: fetch  (コンテナイメージ / 1024MB / 300秒)      │
│     1. latest_time.txt で最新時刻を取得                   │
│     2. 前回時刻と同じならスキップ（冪等性）                 │
│     3. map/{t}.json で1286地点を一括取得                  │
│     4. 正規化（bosai → 既存スキーマ）＋ 地点メタ結合        │
│     5. S3 へ latest.json を PUT              ← 毎回       │
│     6. DynamoDB へ BatchWriteItem            ← 毎回       │
│     7. 毎時（分==0）のみ:                                 │
│          history.json 更新 → 全地点一括推論               │
│          → forecast.json を PUT                          │
└──────────────────────────────────────────────────────────┘
          ↓                              ↓
   S3 (data バケット)              DynamoDB
     latest.json                   PK=station_id
     history.json  (24フレーム)      SK=datetime
     forecast.json                 PITR 有効 / prevent_destroy
          ↓
     CloudFront ←──── ブラウザ
          ↑
   S3 (frontend バケット)
     静的エクスポートした Next.js
```

### 設計判断

**Lambda は1個にまとめる。** 10分ごとに起動し、毎時かどうかで推論の有無を分岐する。2個に分けると `ml/` の読み込みとコンテナイメージが二重になり、ビルドとデプロイが倍になる。

**ストレージの役割を分ける。**

| 置き場所 | 中身 | 読む人 | 更新 |
|---|---|---|---|
| S3 `latest.json` | 全地点の最新観測 | ブラウザ | 10分ごと |
| S3 `history.json` | 直近24時間（推論の入力） | Lambda のみ | 毎時 |
| S3 `forecast.json` | 全地点の予測 | ブラウザ | 毎時 |
| DynamoDB | 全期間の観測（追記のみ） | 現状なし（フェーズ3で開放） | 10分ごと |

最新スナップショットを S3 に置く理由はキャッシュである。全員が同じものを見るデータなので、CloudFront のエッジキャッシュが効き、閲覧者が増えてもオリジンへの取得は10分に1回で済む。DynamoDB にはエッジキャッシュが無く、閲覧者数に比例してクエリが走る。

**予測は全地点を事前計算する。** LightGBM は `1286 × 92` の行列を8回 `predict()` するだけで済み、ミリ秒で終わる。オンデマンド API を持つ必要がない。地点をクリックした際の待ち時間も無くなる。

## 5. データ設計

### 5.1 `latest.json`

```json
{
  "datetime": "2026-10-04 17:00:00",
  "raining_count": 123,
  "wettest": { "station_id": "a0002", "name": "沓形", "precip": 12.5 },
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
      "type": "アメダス"
    }
  ]
}
```

概算サイズ 190KB、gzip 40KB。`station_id` は **obsdl 形式**（`a0002`）で統一する。モデルの学習時と一致させる必要があるため。

### 5.2 `history.json`

推論の入力専用。地点ごとに配列で持ち、サイズを抑える。

```json
{
  "times": ["2026-10-03 18:00:00", "...", "2026-10-04 17:00:00"],
  "stations": {
    "a0002": {
      "temp":       [12.1, 12.3, null, ...],
      "precip":     [0.0, 0.5, 0.0, ...],
      "wind_speed": [4.2, 4.7, 3.9, ...]
    }
  }
}
```

`times` は昇順で最大24件。各配列は `times` と同じ長さ。欠測は `null`。

### 5.3 `forecast.json`

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

### 5.4 DynamoDB

| | |
|---|---|
| テーブル名 | `weather-observations` |
| パーティションキー | `station_id` (S) |
| ソートキー | `datetime` (S) |
| 課金モード | オンデマンド |
| PITR | 有効 |
| `prevent_destroy` | 有効 |

属性: `temp` / `precip` / `wind_speed` / `wind_dir` / `humidity`（数値は `N`、欠測は属性を書かない）

`PK=station_id, SK=datetime` を選ぶ理由は、フェーズ3で想定される読み出しが「特定地点の任意期間」であるため。本設計では読み出さないが、後から GSI を足す手戻りを避ける。

書き込み量は 1286件 / 10分 = 月約55.6万件。オンデマンドで月1ドル未満。

## 6. Lambda の処理フロー

```python
def handler(event, context):
    t = fetch_latest_time()                    # latest_time.txt
    prev = read_s3_json("latest.json")         # 無ければ None
    if prev and prev["datetime"] == fmt(t):
        return {"skipped": True}               # 冪等性: 同じ時刻なら何もしない

    raw = fetch_map(t)                         # map/{t}.json → 1286地点
    obs = normalize(raw, station_map, station_meta)

    put_s3_json("latest.json", build_payload(obs, t))
    batch_write_dynamodb(obs, t)

    if t.minute == 0:                          # 毎時のみ
        history = read_s3_json("history.json") or {"times": [], "stations": {}}
        history = backfill_if_short(history, t) # 24件未満なら過去を取得
        history = append_frame(history, obs, t) # 追加し、24件を超えたら先頭を捨てる
        put_s3_json("history.json", history)

        forecast = predict_all(history, station_meta)
        put_s3_json("forecast.json", forecast)

    return {"datetime": fmt(t), "stations": len(obs)}
```

### 6.1 正規化の対応表

| 既存スキーマ | bosai | 変換 |
|---|---|---|
| `station_id` | JSON のキー | 対応表で bosai ID → obsdl ID |
| `temp` | `temp[0]` | そのまま |
| `precip` | `precipitation1h[0]` | **毎時降水量。学習時と一致させる** |
| `wind_speed` | `wind[0]` | そのまま |
| `wind_dir` | `windDirection[0]` | 文字列化 |
| `name` `lat` `lon` `elev` `type` | — | `stations*.csv` から結合 |

品質フラグ（配列の2番目）が `0` 以外の値は欠測として `null` にする。フィールド自体が存在しない場合も `null`。

`precip` に `precipitation1h` を使うことが最重要である。学習データは obsdl の毎時降水量であり、`precipitation10m` を誤って使うと値が約1/6になり、モデルは動くが予測が静かに狂う。

### 6.2 履歴のブートストラップ

初回デプロイ時は `history.json` が存在せず、24時間分が揃うまで予測できない。`map/{t}.json` を過去24時間分（24リクエスト）取得して埋める。

```
history が N 件（N < 24）のとき、
  t-1h, t-2h, ..., t-(24-N)h の map/{t}.json を取得して先頭に追加
```

全国分が1リクエストで取れるため24リクエストで完了する。初回のみ数十秒かかるため Lambda のタイムアウトを300秒に設定する。

### 6.3 地点IDの対応表

実行時に名前や緯度経度で突き合わせると、失敗が静かに混入する。**事前に生成してコミットする。**

```
backend/data/station_id_map.json
  { "11001": "a0002", ... }   bosai ID → obsdl ID
```

生成スクリプト `backend/data/build_station_map.py` を用意し、以下を満たさない場合はエラーで停止させる。

- 対応件数が 1286 件
- obsdl ID に重複がない
- 名前一致しなかった地点について、緯度経度の距離が 0.02 度以内

## 7. エラーハンドリング

| 事象 | 対応 |
|---|---|
| bosai API が 5xx / タイムアウト | 指数バックオフで3回リトライ。失敗時は例外で終了し、**`latest.json` を更新しない**（古いデータが残る方が空より良い） |
| 一部地点が欠測 | `null` のまま流す。`inference.py` の `_number` が NaN に変換し、LightGBM が欠損として扱う |
| 対応表に無い bosai ID | 観測はスキップし、CloudWatch に警告を出す。件数が10を超えたら異常として例外 |
| 推論が失敗 | `forecast.json` を更新せず終了。`latest.json` と DynamoDB の更新は先に完了しているため維持される |
| `BatchWriteItem` の `UnprocessedItems` | 指数バックオフでリトライ。3回失敗で例外 |
| Lambda が例外終了 | CloudWatch アラームで通知。次回10分後の起動で自動回復する |

**処理順序が復旧性を決める。** 表示に必要な `latest.json` を最初に書き、重い推論を最後に置く。推論が失敗しても表示は最新のままになる。

### 監視

`terraform apply` を自動化するため、異常に気づく仕組みを必須とする。

- Lambda の `Errors` メトリクスが 5分間に1回以上 → SNS 通知
- Lambda が 30分間 1回も成功しない → SNS 通知

## 8. Terraform 構成

```
infra/
├─ main.tf              provider / backend (S3 + DynamoDB ロック)
├─ s3_data.tf           データバケット（prevent_destroy）
├─ s3_frontend.tf       フロントバケット（OAC のみ許可）
├─ cloudfront.tf        ディストリビューション + OAC + キャッシュポリシー
├─ dynamodb.tf          観測テーブル（PITR / prevent_destroy）
├─ ecr.tf               Lambda イメージのリポジトリ
├─ lambda.tf            関数定義（package_type = "Image"）
├─ scheduler.tf         EventBridge Scheduler（rate 10 minutes）
├─ iam_lambda.tf        Lambda 実行ロール
├─ iam_github.tf        GitHub OIDC プロバイダ + 2つのロール
├─ monitoring.tf        CloudWatch アラーム + SNS
└─ variables.tf
```

リージョンは `ap-northeast-1`。CloudFront の証明書が必要になった場合のみ `us-east-1` のプロバイダを別途定義する。

### データ保護

`terraform apply` を CI に任せるため、誤った変更でデータが消えない仕組みを入れる。

```hcl
# DynamoDB テーブル / データバケット
lifecycle {
  prevent_destroy = true
}

# DynamoDB
point_in_time_recovery { enabled = true }
```

リソース名を誤って変更した場合、`destroy` が阻止され apply が失敗する。データが消えるより apply が失敗する方が安全である。

### キャッシュ設定

| パス | TTL | 理由 |
|---|---|---|
| `latest.json` | 300秒 | 10分更新なので半分の値にする |
| `forecast.json` | 1800秒 | 毎時更新 |
| 静的アセット（`_next/static/*`） | 1年 | ファイル名にハッシュが入る |
| `index.html` | 60秒 | デプロイ後に早く切り替わるように |

## 9. CI/CD

GitHub Actions + OIDC。長期のアクセスキーは置かない。

```
.github/workflows/
├─ terraform.yml   infra/**        PR → plan をコメント / main → apply
├─ lambda.yml      backend/**      docker build → ECR push → 関数更新
└─ frontend.yml    frontend/**     next build → S3 sync → CF invalidation
```

`paths` フィルタで変更範囲に応じたワークフローのみを走らせる。

### IAM ロールを2つに分ける

| ロール | 権限 | 使うワークフロー |
|---|---|---|
| `gh-actions-deploy` | ECR push / Lambda 更新 / S3 sync / CF invalidation | `lambda.yml` `frontend.yml` |
| `gh-actions-terraform` | インフラ管理に必要な広い権限 | `terraform.yml` |

デプロイ用の弱いロールと、インフラ用の強いロールを分ける。デプロイのワークフローが侵害されてもインフラを壊せない。

### フロントのビルド時変数

`NEXT_PUBLIC_CARTO_KEY` を GitHub Secrets から注入する。

**注意:** `NEXT_PUBLIC_` 接頭辞の変数は JS バンドルに埋め込まれ、閲覧者から見える。これは秘密を守る仕組みではなく、リポジトリにキーを置かないための措置である。CARTO 側でリファラ制限をかけることを推奨する。

## 10. フロントエンドの変更

| ファイル | 変更 |
|---|---|
| `next.config.mjs` | `output: "export"` を追加 |
| `lib/config.ts` | `API_BASE` を CloudFront の URL に。環境変数から読む |
| `providers/WeatherStreamProvider.tsx` | `EventSource` → `fetch` + 10分間隔のポーリング |
| `hooks/useStationForecast.ts` | `/forecast` API → `forecast.json` から該当地点を引く |
| `hooks/useStationHistory.ts` | `history.json` から算出、またはフェーズ3まで非表示 |
| `hooks/useWindowAvg.ts` `useWindowPrecip.ts` | 同上 |
| `lib/types.ts` | 未使用フィールドを削除（`wbgt` `risk_level` `risk_counts` `hottest` `solar` `cloud` `vapor_pressure` `dew_point` `humidity` および `RiskLevel` `Hottest` 型） |

`WeatherStreamProvider` の外側は変更不要。`useWeatherStream()` のインターフェースを保つ。

### ポーリングへの置き換え

```ts
useEffect(() => {
  let alive = true;
  const load = async () => {
    const res = await fetch(`${API_BASE}/latest.json`, { cache: "no-store" });
    if (alive && res.ok) setPayload(await res.json());
    setConnected(res.ok);
  };
  load();
  const id = setInterval(load, 10 * 60 * 1000);
  return () => { alive = false; clearInterval(id); };
}, []);
```

`connected` の意味は「SSE が接続中」から「直近の取得が成功」に変わる。表示（`接続待ち…`）はそのまま使える。

## 11. テスト方針

フレームワークは導入せず、`py -m pytest` で動く最小のテストのみ置く。

| テスト | 何が壊れたら落ちるか |
|---|---|
| `test_normalize.py` | bosai JSON の正規化。固定サンプルを入力し、期待する `Observation` と比較 |
| `test_station_map.py` | 対応表が1286件、obsdl ID に重複なし、双方向に解決できる |
| `test_feature_order.py` | **最重要。** `inference.py` の特徴量ベクトルの順序が学習時（`ml/dataset.py`）と一致する |

3つ目を最重要とする理由は、ここが壊れても**エラーが出ない**ためである。`inference.py` の `num_feature()` チェックは個数しか見ないため、順序が入れ替わっても通過し、モデルは動いたまま予測だけが狂う。既知の入力に対する既知の出力を固定値で assert する。

## 12. 事前準備（リポジトリ側）

実装前に片付ける。

| | 作業 | 理由 |
|---|---|---|
| 1 | `git gc --prune=now` | 到達不能な blob 5.4GB（圧縮後679MB）が `.git` を占めている |
| 2 | `backend/lambda/` を削除 | `lambda` は Python の予約語で import 不可。`backend/handler.py` にする |
| 3 | `stations*.csv` をコミット | `inference.py` に必須の実行資産（68KB）。`.gitignore` は修正済み |
| 4 | `station_id_map.json` を生成しコミット | 実行時の推測を排除 |
| 5 | `git switch -c aws` | `main` を動く状態で保全する |

`.gitignore` は本設計の作成時に修正済み。

- `backend/data/*.csv` → `backend/data/observations*.csv`（地点マスタを追跡対象に）
- `docs/` の除外を解除（設計書を追跡対象に）

## 13. 段階

| フェーズ | 内容 | 本設計の範囲 |
|---|---|---|
| 2a | Terraform の土台 + Lambda + S3 + DynamoDB 書き込み | ○ |
| 2b | CI/CD 3ワークフロー | ○ |
| 2c | フロントの静的エクスポート + CloudFront 公開 | ○ |
| 3 | DynamoDB の読み出し API（任意期間のクエリ） | × |

## 14. 未確定事項

実装時に確認する。

- `ml/dataset.py` の特徴量構築順序と `inference.py` の `_features` が同一であることの確認方法。両者がコードを共有していない場合、共有モジュールへの切り出しを検討する
- `predict_all` のバッチ化。現在の `_features` は1地点ずつ `observation_at` を呼ぶため、1286地点では約9.3万回の辞書参照が発生する。実測して許容範囲か判断する
- `stations.csv` の1行が緯度経度の欠落で読み込まれない（155/156）。昭和基地と推定。除外して問題ないか確認する
