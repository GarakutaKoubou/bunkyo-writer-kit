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


def sync_to_serve_dir():
    """プロジェクトのHTMLファイルを配信ディレクトリにコピーする"""
    os.makedirs(SERVE_DIR, exist_ok=True)
    articles_dst = os.path.join(SERVE_DIR, "articles")
    os.makedirs(articles_dst, exist_ok=True)

    # article_preview.html
    preview_html = os.path.join(PROJECT_DIR, "article_preview.html")
    if os.path.exists(preview_html):
        shutil.copy2(preview_html, os.path.join(SERVE_DIR, "article_preview.html"))

    # article_preview_version.json
    version_json = os.path.join(PROJECT_DIR, "article_preview_version.json")
    if os.path.exists(version_json):
        shutil.copy2(version_json, os.path.join(SERVE_DIR, "article_preview_version.json"))

    # article_index.html
    index_html = os.path.join(PROJECT_DIR, "article_index.html")
    if os.path.exists(index_html):
        shutil.copy2(index_html, os.path.join(SERVE_DIR, "article_index.html"))

    # articles/*.html
    articles_src = os.path.join(PROJECT_DIR, "articles")
    if os.path.isdir(articles_src):
        for f in os.listdir(articles_src):
            if f.endswith(".html"):
                shutil.copy2(os.path.join(articles_src, f), os.path.join(articles_dst, f))


def start_background_server():
    """バックグラウンドでHTTPサーバーを起動する"""
    sync_to_serve_dir()
    subprocess.Popen(
        ["python3", "-m", "http.server", str(PREVIEW_PORT), "--directory", SERVE_DIR],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    time.sleep(0.8)


def ensure_server():
    """サーバーが起動していなければ起動し、起動済みならファイルを同期する。

    ポートは開いているが間違ったディレクトリを配信している「幽霊サーバー」を検出すると、
    killしてから新しいサーバーを立ち上げる。
    """
    if _port_is_open() and not _server_serves_correct_dir():
        print(f"⚠️ 古いサーバーを検出（port {PREVIEW_PORT}）。再起動します...")
        _kill_stale_server()
    if not _port_is_open():
        print(f"🚀 ローカルサーバーを起動しています（port {PREVIEW_PORT}）...")
        start_background_server()
    else:
        sync_to_serve_dir()
