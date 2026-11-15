import os

# poll_weather_data はモジュール直下で boto3 クライアントを作るため、
# import する前にリージョンが要る（未設定の環境では NoRegionError になる）
os.environ.setdefault("AWS_DEFAULT_REGION", "ap-northeast-1")

from poll_weather_data import pick


def test_品質フラグ0の要素だけ採用する():
    obs = {"temp": [12.3, 0], "precipitation10m": [0.5, 0]}
    assert pick(obs) == {"temp": 12.3, "precipitation10m": 0.5}


def test_品質フラグが0以外の要素は弾く():
    assert pick({"temp": [12.3, 1]}) == {}


def test_値がない要素は弾く():
    assert pick({"wind": None}) == {}


def test_ELEMENTSにない要素は拾わない():
    assert pick({"sun10m": [10.0, 0]}) == {}


def test_要素が1つもない観測所は空を返す():
    assert pick({}) == {}
