// バックエンド(処理系 client.py)の接続先。
// ページが増えても API URL はここ1か所で管理する。
export const API_BASE = "http://localhost:8001";

export const STREAM_URL = `${API_BASE}/stream`;

export const MAX_WINDOW_HOURS = 24;
