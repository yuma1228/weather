import json
import os
import urllib.request
from datetime import datetime, timedelta, timezone
from collections.abc import Sequence, Iterable
from decimal import Decimal
from typing import TypedDict, Any

import boto3

BASE = "https://www.data.jma.go.jp/bosai/forecast/data"
JST = timezone(timedelta(hours=+9))
ELEMENTS = ("temp", "precipitation10m", "precipitation1h", "humidity", "wind", "windDirection")

s3 = boto3.client("s3")
dynamodb = boto3.resource("dynamodb")

def fetch_text(path: str) -> str:
    req = urllib.request.Request(f"{BASE}/{path}", headers={"User-Agent": "weather/1.0 (https://github.com/yuma1228/weather)"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read().decode("utf-8")
    
def pick(obs: dict[str, Sequence[float] | None], elements: Iterable[str] = ELEMENTS) -> dict[str, float]:
    result = {}
    for k in elements:
        v = obs.get(k)
        if v and v[1] == 0:
            result[k] = v[0]
    return result

def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    