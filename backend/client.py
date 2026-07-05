import asyncio
import json
import threading
import time
from contextlib import asynccontextmanager

import requests
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
import uvicorn

import config


SOURCE = config.SOURCE
POLL_INTERVAL_SEC = config.POLL_INTERVAL_SEC


# ---------------------------------------------------------------------------
# WBGT(暑さ指数)の推定
#
# 屋外WBGTの実測には黒球温度が要るが、ここでは気象官署が観測する
# 気温・相対湿度・全天日射量・平均風速から推定する小野・登内(2014)の回帰式:
#
#   WBGT = 0.735*Ta + 0.0374*RH + 0.00292*Ta*RH
#          + 7.619*SR - 4.557*SR**2 - 0.0572*WS - 4.064
#
#   Ta: 気温[℃] / RH: 相対湿度[%] / SR: 全天日射量[kW/m^2] / WS: 平均風速[m/s]
#
# obsdl の時別値は日射量が「1時間積算[MJ/m^2]」なので kW/m^2 へ換算する。
# ---------------------------------------------------------------------------

# 環境省「熱中症予防情報サイト」の指針に沿った区分
RISK_LEVELS = [
    (31.0, "danger",  "危険"),
    (28.0, "severe",  "厳重警戒"),
    (25.0, "warning", "警戒"),
    (21.0, "caution", "注意"),
    (float("-inf"), "safe", "ほぼ安全"),
]


def compute_wbgt(temp, humidity, solar, wind_speed):
    """要素から推定WBGT[℃]を返す。必須要素が欠けていれば None。"""
    if temp is None or humidity is None or solar is None:
        return None
    ta = temp
    rh = humidity
    sr = solar * 1000.0 / 3600.0
    ws = wind_speed if wind_speed is not None else 0.0
    wbgt = (
        0.735 * ta
        + 0.0374 * rh
        + 0.00292 * ta * rh
        + 7.619 * sr
        - 4.557 * sr * sr
        - 0.0572 * ws
        - 4.064
    )
    return round(wbgt, 1)


def risk_of(wbgt):
    """WBGT値から (level_key, label) を返す。None は ("unknown", "―")。"""
    if wbgt is None:
        return "unknown", "―"
    for threshold, key, label in RISK_LEVELS:
        if wbgt >= threshold:
            return key, label
    return "unknown", "―"


def annotate(obs):
    """観測レコードに wbgt / risk_level / risk_label を付与して返す。"""
    wbgt = compute_wbgt(
        obs.get("temp"), obs.get("humidity"),
        obs.get("solar"), obs.get("wind_speed"),
    )
    level, label = risk_of(wbgt)
    return {**obs, "wbgt": wbgt, "risk_level": level, "risk_label": label}


def process(snapshot):
    """server の /now レスポンスを受け取り、各観測に WBGT を付けて返す。

    併せてこの時刻の統計(最大WBGT地点・危険度別カウント)も付ける。
    """
    obs = [annotate(o) for o in snapshot.get("observations", [])]

    counts = {key: 0 for _, key, _ in RISK_LEVELS}
    counts["unknown"] = 0
    hottest = None
    for o in obs:
        counts[o["risk_level"]] = counts.get(o["risk_level"], 0) + 1
        w = o.get("wbgt")
        if w is not None and (hottest is None or w > hottest["wbgt"]):
            hottest = o

    return {
        "datetime": snapshot.get("datetime"),
        "index": snapshot.get("index"),
        "total": snapshot.get("total"),
        "step_interval_sec": snapshot.get("step_interval_sec"),
        "count": len(obs),
        "risk_counts": counts,
        "hottest": {
            "station_id": hottest["station_id"],
            "name": hottest["name"],
            "wbgt": hottest["wbgt"],
            "risk_label": hottest["risk_label"],
        } if hottest else None,
        "observations": obs,
    }


# ---------------------------------------------------------------------------
# server をポーリングして最新の加工済みスナップショットを保持する
# ---------------------------------------------------------------------------

class Poller:
    def __init__(self):
        self._lock = threading.Lock()
        self._payload = None      # 最新の加工済みスナップショット
        self._version = 0         # index が変わるたびに増える
        self._alive = True
        self._sess = requests.Session()
        self._sess.trust_env = False

    def run(self):
        last_index = None
        while self._alive:
            try:
                clk = self._sess.get(f"{SOURCE}/clock", timeout=10).json()
                if clk.get("index") != last_index:
                    last_index = clk.get("index")
                    snap = self._sess.get(f"{SOURCE}/now", timeout=30).json()
                    payload = process(snap)
                    with self._lock:
                        self._payload = payload
                        self._version += 1
            except Exception as ex:
                # server 未起動などは黙ってリトライ
                print(f"[poller] {ex}")
            time.sleep(POLL_INTERVAL_SEC)

    def snapshot(self):
        with self._lock:
            return self._payload, self._version


poller = Poller()


@asynccontextmanager
async def lifespan(app: FastAPI):
    threading.Thread(target=poller.run, daemon=True).start()
    yield


app = FastAPI(
    title="Weather Processing Layer",
    description="WBGT加工 + SSE配信",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)


@app.get("/")
def index():
    return {
        "role": "processing layer (server.py → WBGT加工 → SSE)",
        "source": SOURCE,
        "endpoints": {
            "/now": "最新の加工済みスナップショット(1回)",
            "/stream": "SSE。時刻が進むたび加工済みスナップショットを push",
        },
    }


@app.get("/now")
def get_now():
    payload, _ = poller.snapshot()
    return payload or {"observations": [], "count": 0}


@app.get("/stream")
async def stream():
    """SSE。ポーラの version が上がる(=新しい時刻)たびに push。"""

    async def gen():
        last_version = -1
        while True:
            payload, version = poller.snapshot()
            if payload is not None and version != last_version:
                last_version = version
                yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
            await asyncio.sleep(0.5)

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


if __name__ == "__main__":
    uvicorn.run(app, host=config.CLIENT_HOST, port=config.CLIENT_PORT)
