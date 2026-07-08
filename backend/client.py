import asyncio
import json
import threading
import time
from collections import deque
from contextlib import asynccontextmanager
from datetime import datetime, timedelta

import requests
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
import uvicorn

import config


SOURCE = config.SOURCE
POLL_INTERVAL_SEC = config.POLL_INTERVAL_SEC
HISTORY_MAX = config.HISTORY_MAX
DT_FMT = "%Y-%m-%d %H:%M:%S"

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
        self._thread_lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._payload: dict | None = None
        self._version = 0
        self._history: deque[tuple[datetime, dict[str, dict[str, float | None]]]] = deque(
            maxlen=HISTORY_MAX
        )

    def start(self) -> None:
        with self._thread_lock:
            if self._thread and self._thread.is_alive():
                return
            self._stop.clear()
            self._thread = threading.Thread(
                target=self.run,
                daemon=True,
                name="weather-poller",
            )
            self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        thread = self._thread
        if thread and thread.is_alive():
            thread.join(timeout=3)

    def run(self) -> None:
        last_index = None
        sess = requests.Session()
        sess.trust_env = False
        try:
            while not self._stop.is_set():
                try:
                    clk = sess.get(f"{SOURCE}/clock", timeout=10).json()
                    if clk.get("index") != last_index:
                        last_index = clk.get("index")
                        snap = sess.get(f"{SOURCE}/now", timeout=30).json()
                        payload = process(snap)
                        metrics = {
                            o["station_id"]: {
                                "temp": o.get("temp"),
                                "precip": o.get("precip"),
                            }
                            for o in payload["observations"]
                        }
                        dt_text = payload.get("datetime")
                        dt = datetime.strptime(dt_text, DT_FMT) if dt_text else None
                        with self._lock:
                            self._payload = payload
                            self._version += 1
                            if dt is not None:
                                self._history.append((dt, metrics))
                except Exception as ex:
                    print(f"[poller] {ex}")
                self._stop.wait(POLL_INTERVAL_SEC)
        finally:
            sess.close()

    def snapshot(self) -> tuple[dict | None, int]:
        with self._lock:
            return self._payload, self._version

    def history_avg(self, station_id: str, field: str, hours: int) -> float | None:
        with self._lock:
            entries = list(self._history)
        if not entries:
            return None
        end = entries[-1][0]
        cutoff = end - timedelta(hours=hours)
        vals = []
        for dt, metrics in entries:
            if not (cutoff < dt <= end):
                continue
            station = metrics.get(station_id)
            if station is None:
                continue
            value = station.get(field)
            if value is not None:
                vals.append(value)
        return round(sum(vals) / len(vals), 1) if vals else None

    def history_series(self, station_id: str, hours: int) -> list[dict]:
        with self._lock:
            entries = list(self._history)
        if not entries:
            return []
        end = entries[-1][0]
        cutoff = end - timedelta(hours=hours)
        points = []
        for dt, metrics in entries:
            if not (cutoff < dt <= end):
                continue
            station = metrics.get(station_id)
            if station is None:
                continue
            points.append({
                "datetime": dt.strftime(DT_FMT),
                "temp": station.get("temp"),
                "precip": station.get("precip"),
            })
            
        print(f" points={points}")
        return points


poller = Poller()


@asynccontextmanager
async def lifespan(app: FastAPI):
    poller.start()
    yield
    poller.stop()


app = FastAPI(
    title="Weather Processing Layer",
    description="WBGT加工 + SSE配信",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)

@app.get("/history")
def get_history(station_id: str, hours: int = HISTORY_MAX) -> dict:
    hours = max(1, min(hours, HISTORY_MAX))
    return {
        "temp_avg": poller.history_avg(station_id, "temp", hours),
        "precip_avg": poller.history_avg(station_id, "precip", hours),
    }


@app.get("/history_series")
def get_history_series(station_id: str, hours: int = HISTORY_MAX) -> dict:
    hours = max(1, min(hours, HISTORY_MAX))
    return {
        "station_id": station_id,
        "hours": hours,
        "points": poller.history_series(station_id, hours),
    }


@app.get("/debug/poller")
def debug_poller() -> dict:
    return poller.status()


@app.get("/debug/threads")
def debug_threads() -> list[dict]:
    return [
        {
            "name": thread.name,
            "ident": thread.ident,
            "daemon": thread.daemon,
            "alive": thread.is_alive(),
        }
        for thread in threading.enumerate()
    ]


@app.get("/stream")
async def stream():

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
