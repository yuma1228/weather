import json
import os
import urllib.request
from collections.abc import Iterable, Sequence
from datetime import datetime
from decimal import Decimal
from typing import Any, TypedDict

import boto3

BASE = "https://www.jma.go.jp/bosai/amedas/data"
HEADERS = {"User-Agent": "weather/1.0 (https://github.com/yuma1228/weather)"}
ELEMENTS = ("temp", "precipitation10m", "precipitation1h", "humidity", "wind", "windDirection")


# アメダス JSON の値は [観測値, 品質フラグ]。欠測の要素はキー自体が無い
Observation = dict[str, Sequence[float] | None]


class Result(TypedDict):
    observed_at: str
    written: int
    skipped: int


s3 = boto3.client("s3")
dynamodb = boto3.resource("dynamodb")


def fetch_text(path: str) -> str:
    req = urllib.request.Request(f"{BASE}/{path}", headers=HEADERS)
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read().decode("utf-8")


def pick(obs: Observation, elements: Iterable[str] = ELEMENTS) -> dict[str, float]:
    result: dict[str, float] = {}
    for k in elements:
        v = obs.get(k)
        if v is not None and v[1] == 0:
            result[k] = v[0]
    return result


def handler(event: dict[str, Any], context: Any) -> Result:
    s3_bucket_name = os.environ["S3_BUCKET_NAME"]
    table = dynamodb.Table(os.environ["DYNAMODB_TABLE_NAME"])
    ttl_days = int(os.environ["TTL_DAYS"])

    observed_at = fetch_text("latest_time.txt").strip()
    observed = datetime.fromisoformat(observed_at)
    stamp = observed.strftime("%Y%m%d%H%M%S")
    observations_raw = fetch_text(f"map/{stamp}.json")
    observations_dict = json.loads(observations_raw)

    s3.put_object(
        Bucket=s3_bucket_name,
        Key=f"amedas/{observed:%Y/%m/%d}/{stamp}.json",
        Body=observations_raw,
        ContentType="application/json",
    )

    expires_at = int(observed.timestamp()) + ttl_days * 24 * 60 * 60
    written = 0
    skipped = 0
    with table.batch_writer() as batch:
        for station_id, observation in observations_dict.items():
            values = pick(observation)
            if not values:
                skipped += 1
                continue

            item: dict[str, str | int | Decimal] = {
                "station_id": station_id,
                "datetime": observed_at,
                "ttl": expires_at,
            }
            for element, value in values.items():
                item[element] = Decimal(str(value))

            batch.put_item(Item=item)
            written += 1

    print(f"{observed_at} written={written} skipped={skipped}")
    return {"observed_at": observed_at, "written": written, "skipped": skipped}

