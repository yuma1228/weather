"""fixtures/map_sample.json は 2026-11-15T20:00:00+09:00 の実データから 5 地点を抜いたもの。値は未加工。"""
import json
import os
from pathlib import Path

# poll_weather_data はモジュール直下で boto3 クライアントを作るため、
# import する前にリージョンが要る（未設定の環境では NoRegionError になる）
os.environ.setdefault("AWS_DEFAULT_REGION", "ap-northeast-1")

from poll_weather_data import pick

SAMPLE = json.loads((Path(__file__).parent / "fixtures" / "map_sample.json").read_text(encoding="utf-8"))


def test_観測所IDの1階層下が観測値():
    assert pick(SAMPLE) == {}
    assert pick(SAMPLE["11001"]) != {}


def test_4要素の観測所から6要素を取り出せる():
    assert pick(SAMPLE["11001"]) == {
        "temp": 4.3,
        "precipitation10m": 0.0,
        "precipitation1h": 0.0,
        "humidity": 75,
        "wind": 8.3,
        "windDirection": 4,
    }


def test_降水量のみの観測所は降水量だけ返す():
    assert pick(SAMPLE["12066"]) == {"precipitation10m": 0.0, "precipitation1h": 0.0}


def test_品質フラグ1の値は採用しない():
    assert "humidity" not in pick(SAMPLE["74447"])


def test_欠測のNoneは採用しない():
    assert None not in pick(SAMPLE["22391"]).values()
    assert None not in pick(SAMPLE["94001"]).values()
