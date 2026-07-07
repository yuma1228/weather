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

WBGT_LEVEL = [
    (31.0, "danger"),
    (28.0, "severe"),
    (25.0, "warning"),
    (21.0, "caution"),
    (float("-inf"), "safe"),
]



def compute_wbgt(
    temp: float | None,
    humidity: float | None,
    solar: float | None,
    wind_speed: float | None,
) -> float | None:
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


def risk_of(wbgt: float | None) -> str:
    if wbgt is None:
        return "unknown"
    for threshold, key in WBGT_LEVEL:
        if wbgt >= threshold:
            return key
    return "unknown"


def annotate(obs: dict) -> dict:
    wbgt = compute_wbgt(
        obs.get("temp"), obs.get("humidity"),
        obs.get("solar"), obs.get("wind_speed"),
    )
    return {**obs, "wbgt": wbgt, "risk_level": risk_of(wbgt)}


def process(snapshot: dict) -> dict:
    obs = [annotate(o) for o in snapshot.get("observations", [])]

    risk_counts = {key: 0 for _, key in WBGT_LEVEL}
    risk_counts["unknown"] = 0
    hottest = None
    wettest = None
    raining_count = 0
    for o in obs:
        risk_counts[o["risk_level"]] = risk_counts.get(o["risk_level"], 0) + 1
        w = o.get("wbgt")
        if w is not None and (hottest is None or w > hottest["wbgt"]):
            hottest = o
        p = o.get("precip")
        if p is not None:
            if p >= 0.1:
                raining_count += 1
            if wettest is None or p > wettest["precip"]:
                wettest = o

    return {
        "datetime": snapshot.get("datetime"),
        "index": snapshot.get("index"),
        "total": snapshot.get("total"),
        "step_interval_sec": snapshot.get("step_interval_sec"),
        "count": len(obs),
        "risk_counts": risk_counts,
        "hottest": {
            "station_id": hottest["station_id"],
            "name": hottest["name"],
            "wbgt": hottest["wbgt"],
            "risk_level": hottest["risk_level"],
        } if hottest else None,
        "raining_count": raining_count,
        "wettest": {
            "station_id": wettest["station_id"],
            "name": wettest["name"],
            "precip": wettest["precip"],
        } if wettest else None,
        "observations": obs,
    }


class Poller:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._payload: dict | None = None
        self._version = 0
        self._alive = True
        self._sess = requests.Session()
        self._sess.trust_env = False

    def run(self) -> None:
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
                print(f"[poller] {ex}")
            time.sleep(POLL_INTERVAL_SEC)

    def snapshot(self) -> tuple[dict | None, int]:
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
            await asyncio.sleep(config.STREAM_CHECK_SEC)

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


if __name__ == "__main__":
    uvicorn.run(app, host=config.CLIENT_HOST, port=config.CLIENT_PORT)
