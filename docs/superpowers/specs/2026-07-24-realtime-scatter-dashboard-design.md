# リアルタイム散布図ダッシュボード 設計

作成日: 2026-07-24

## 目的

全観測地点の「気温 × 積算降水量」を地域別に色分けした散布図を、`/rain` ページの左側に
常設し、仮想時計の進行に合わせてリアルタイムに更新する。地域ごとの傾向差を一目で
比較できるようにする。

## 決定事項

| 項目 | 決定 |
|---|---|
| 点の意味 | 現在時刻の全地点スナップショット(点 = 観測地点1つ、約1300点) |
| X軸 | 気温(℃)、線形、−10〜40 固定 |
| Y軸 | 直近 `windowHours` の積算降水量(mm)、対数、0.05〜1000 固定 |
| 色分け | 6地域(prid から導出) |
| 配置 | `/rain` の地図の左に固定サイドパネル(折り畳み可) |
| 連動 | 凡例クリックによる地域フィルタのみ |
| 描画 | ECharts(`echarts` 本体のみ、React ラッパは自前 20行) |

## アーキテクチャ

```
client.py  ── GET /window?hours=N ──→ {"datetime": ..., "points": [
                                          {station_id, name, region, temp, precip_sum}, ...]}
                  (リングバッファを全地点ぶん集計。既存 /history の全地点版)
                        │
frontend   useWindowPrecip(datetime, windowHours)   ← datetime が進むたび再取得
                        │
              RainScatter.tsx  (echarts.init / setOption)
                        │
              RainMap の flex 左カラムに常設
```

### なぜバックエンドに新エンドポイントが要るか

SSE (`/stream`) のペイロードは全地点の**瞬間値のみ**。積算値を返す `/history` は
`station_id` 1つずつしか受け付けない。1300地点ぶんの積算をフロント側で組み立てる
手段が現状ないため、サーバ側に全地点版を1本足す。サーバはすでに全地点のリング
バッファを持っているので、集計はループ1つで済む。

## コンポーネント

| ファイル | 変更 | 役割 |
|---|---|---|
| `backend/client.py` | 追加 | `GET /window` と `prid → 地域` の対応表 |
| `frontend/hooks/useWindowPrecip.ts` | 新規 | `/window` を叩くだけ。`useWindowAvg` と同じ形 |
| `frontend/components/rain/RainScatter.tsx` | 新規 | ECharts の初期化・更新・折り畳み |
| `frontend/components/rain/RainMap.tsx` | 変更 | 左カラムに `RainScatter` を差し込む |
| `frontend/package.json` | 変更 | `echarts` 追加 |

### 地域の対応表

`prid`(府県コード)の範囲で決まる。

| 地域 | prid |
|---|---|
| 北海道・東北 | 11–36 |
| 関東 | 40–46 |
| 中部 | 48–57 |
| 近畿 | 60–65 |
| 中国・四国 | 66–74 |
| 九州・沖縄 | 81–91 |

`prid=99`(昭和基地、1地点)は対象外として除外する。

### `GET /window?hours=N`

- レスポンス: `{"datetime": str | null, "hours": int, "points": [{station_id, name, region, temp, precip_sum}]}`
- `temp` は現在時刻の瞬間値、`precip_sum` は直近 `hours` の積算
- `region` は静的だが毎回同梱する。1300点で約 30KB、localhost 前提なので
  地点メタ用のエンドポイントを別に立てるより安い
- `temp` が欠測(null)の点は返さない(散布図に置けないため)

## 表示仕様

- 軸レンジは固定。毎フレーム軸が動くと目で傾向を追えなくなるため
- Y軸は対数なので 0 を置けない。積算 0mm の地点は **0.05 にクランプ**し、
  軸の最下段ラベルを「0」と表記する。クランプは表示だけで、値の解釈は
  「降っていない」で一貫する
- 凡例は ECharts 標準(地域 = 系列)。クリックでその地域を表示/非表示
- ヘッダに現在時刻と表示点数、`windowHours` の表示。`windowHours` は
  既存 `RainHeader` のスライダを共有する(新しい操作子は増やさない)
- 折り畳みトグル付き。閉じると地図が全幅に戻る
- パネル幅は 360px 固定、`sm` 未満では非表示(地図優先)

## データフロー

1. `RainMap` が `windowHours` state を持つ(既存)
2. `useWindowPrecip(payload?.datetime, windowHours)` が、時刻または時間幅が変わるたび
   `/window` を fetch
3. `RainScatter` が結果を地域ごとの系列に振り分けて `setOption`
4. ECharts のインスタンスは初回のみ `init`、以降は `setOption` のみ(再生成しない)

## エラー処理

- `client.py` 未起動 / fetch 失敗: 既存 `useWindowAvg` と同じく握りつぶし、
  直前のデータを表示したまま。パネルに「更新待ち」を出す
- リングバッファがまだ `hours` ぶん溜まっていない起動直後: サーバは持っている
  ぶんだけで積算を返し、レスポンスに実際の集計時間数を含めない(表示は
  「直近Nh」のまま)。過小評価になるが起動直後の一過性であり、実害はない
- `temp` 欠測の点はサーバ側で除外済み。`precip_sum` の欠測は 0 とみなす

## 検証

- `backend/client.py` に `assert` ベースの自己チェックを1つ:
  prid → 地域の分類が境界値(36/40, 46/48, 57/60, 65/66, 74/81, 91/99)で
  正しいこと、および既知のリングバッファ入力に対する積算が期待値になること
- フロントは目視確認(点が出る・凡例トグルが効く・時計進行で動く)

## やらないこと

- 点クリックからの地点詳細表示(既存の右パネルとの連動)
- 軸のオートスケール
- 点の軌跡・残像・時系列蓄積
- 地点検索、地域以外のグルーピング(クラスタ)

必要になった時点で足す。
