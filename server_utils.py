"""
server_utils.py
ローカルHTTPサーバーの起動・ファイル同期ユーティリティ

preview_generator.py と index_generator.py から共通で使う。
配信ディレクトリは /tmp/bunkyo_preview/（Dropboxサブプロセス制限を回避するため）
"""

import json
import os
import shutil
import socket
import subprocess
import time
import urllib.request

PROJECT_DIR  = os.path.dirname(os.path.abspath(__file__))
SERVE_DIR    = "/tmp/bunkyo_preview"
PREVIEW_PORT = 8765
HEALTH_MARKER = ".server_health.txt"  # サーバーが正しいディレクトリを配信しているか確認するマーカー
SERVER_API_VERSION = "3"              # api_server.py のバージョン（更新のたびに上げる）


def _port_is_open() -> bool:
    s = socket.socket()
    s.settimeout(0.5)
    try:
        s.connect(("localhost", PREVIEW_PORT))
        s.close()
        return True
    except Exception:
        return False


def _server_serves_correct_dir() -> bool:
    """正しい配信ディレクトリ（SERVE_DIR）を配信しているかHTTPで確認する。

    SERVE_DIR に一意のマーカーファイルを置き、HTTP経由で取得できるかで判定する。
    旧サーバーが別ディレクトリを配信している場合は404になる。
    """
    marker_path = os.path.join(SERVE_DIR, HEALTH_MARKER)
    expected = f"ok-{os.getpid()}-{time.time()}"
    try:
        os.makedirs(SERVE_DIR, exist_ok=True)
        with open(marker_path, "w") as f:
            f.write(expected)
        req = urllib.request.Request(f"http://localhost:{PREVIEW_PORT}/{HEALTH_MARKER}")
        with urllib.request.urlopen(req, timeout=1.0) as resp:
            body = resp.read().decode("utf-8", errors="ignore").strip()
        return body == expected
    except Exception:
        return False


def _server_api_version_ok() -> bool:
    """サーバーの API バージョンが現行版かどうかを確認する。

    旧バージョンのサーバー（api_server.py更新前に起動したもの）を検出するために使う。
    /api/version が存在しない、またはバージョンが一致しない場合は False を返す。
    """
    try:
        req = urllib.request.Request(
            f"http://localhost:{PREVIEW_PORT}/api/version",
            headers={"Cache-Control": "no-cache"},
        )
        with urllib.request.urlopen(req, timeout=1.0) as resp:
            data = json.loads(resp.read())
        return data.get("version") == SERVER_API_VERSION
    except Exception:
        return False


def _kill_stale_server() -> None:
    """ポート8765を占有している古いサーバープロセスをkillする"""
    try:
        out = subprocess.check_output(["lsof", "-ti", f":{PREVIEW_PORT}"], text=True).strip()
        for pid in out.splitlines():
            if pid.strip():
                subprocess.run(["kill", pid.strip()], check=False)
        time.sleep(0.8)
    except Exception:
        pass


def is_server_running() -> bool:
    """ローカルサーバーが起動中かつ正しいディレクトリを配信しているか確認する"""
    if not _port_is_open():
        return False
    return _server_serves_correct_dir()


def _safe_copy(src, dst, retries=4, delay=0.25):
    """Dropboxの一時ロック（Operation not permitted / EPERM）に強いコピー。

    DropboxのCloudStorageフォルダはバックグラウンド同期中に
    一瞬ファイルをロックし、copy2が [Errno 1] Operation not permitted を返すことがある。
    数回リトライし、それでも失敗したら例外を投げずにスキップする
    （1ファイルのコピー失敗で更新処理全体を止めないため）。
    """
    if not os.path.exists(src):
        return False
    for attempt in range(retries):
        try:
            shutil.copy2(src, dst)
            return True
        except (PermissionError, OSError) as e:
            if attempt < retries - 1:
                time.sleep(delay)
                continue
            # 最終的に失敗 → 例外を投げずにログだけ残してスキップ
            print(f"⚠️ コピーをスキップ（Dropboxロック）: {os.path.basename(src)} / {e}")
            return False
    return False


def sync_to_serve_dir():
    """プロジェクトのHTMLファイルを配信ディレクトリにコピーする（Dropboxロック耐性あり）"""
    os.makedirs(SERVE_DIR, exist_ok=True)
    articles_dst = os.path.join(SERVE_DIR, "articles")
    os.makedirs(articles_dst, exist_ok=True)

    # article_preview.html
    _safe_copy(os.path.join(PROJECT_DIR, "article_preview.html"),
               os.path.join(SERVE_DIR, "article_preview.html"))

    # article_preview_version.json
    _safe_copy(os.path.join(PROJECT_DIR, "article_preview_version.json"),
               os.path.join(SERVE_DIR, "article_preview_version.json"))

    # article_index.html
    _safe_copy(os.path.join(PROJECT_DIR, "article_index.html"),
               os.path.join(SERVE_DIR, "article_index.html"))

    # articles/*.html
    articles_src = os.path.join(PROJECT_DIR, "articles")
    if os.path.isdir(articles_src):
        for f in os.listdir(articles_src):
            if f.endswith(".html"):
                _safe_copy(os.path.join(articles_src, f), os.path.join(articles_dst, f))


def start_background_server():
    """バックグラウンドでAPIサーバーを起動する（静的配信 + POST /api/update_status）"""
    sync_to_serve_dir()
    api_server = os.path.join(PROJECT_DIR, "api_server.py")
    subprocess.Popen(
        ["python3", api_server],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    time.sleep(0.8)


def ensure_server():
    """サーバーが起動していなければ起動し、起動済みならファイルを同期する。

    以下のいずれかを検出した場合、killして新しいサーバーを立ち上げる：
    - 別ディレクトリを配信している「幽霊サーバー」
    - APIバージョンが古いサーバー（仕様変更前に起動したもの）
    """
    if _port_is_open():
        stale = not _server_serves_correct_dir()
        outdated = not stale and not _server_api_version_ok()
        if stale:
            print(f"⚠️ 古いサーバーを検出（port {PREVIEW_PORT}）。再起動します...")
            _kill_stale_server()
        elif outdated:
            print(f"⚠️ 旧バージョンのサーバーを検出（port {PREVIEW_PORT}）。最新版で再起動します...")
            _kill_stale_server()

    if not _port_is_open():
        print(f"🚀 ローカルサーバーを起動しています（port {PREVIEW_PORT}）...")
        start_background_server()
    else:
        sync_to_serve_dir()
