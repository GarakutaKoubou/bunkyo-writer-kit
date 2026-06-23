"""
server_utils.py
ローカルHTTPサーバーの起動・ファイル同期ユーティリティ

preview_generator.py と index_generator.py から共通で使う。
配信ディレクトリは /tmp/bunkyo_preview/（Dropboxサブプロセス制限を回避するため）
"""

import fcntl
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
LOCK_FILE    = "/tmp/bunkyo_preview/.server.lock"  # ensure_server() のプロセス間排他ロック（/tmp＝同一マシン内で共有）
SERVER_API_VERSION = "9"              # api_server.py のバージョン（更新のたびに上げる）


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
    タイムアウトは3秒（サーバーがPOST処理でビジー状態でも誤検知しないよう余裕を持たせる）。
    """
    marker_path = os.path.join(SERVE_DIR, HEALTH_MARKER)
    expected = f"ok-{os.getpid()}-{time.time()}"
    try:
        os.makedirs(SERVE_DIR, exist_ok=True)
        with open(marker_path, "w") as f:
            f.write(expected)
        req = urllib.request.Request(f"http://localhost:{PREVIEW_PORT}/{HEALTH_MARKER}")
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            body = resp.read().decode("utf-8", errors="ignore").strip()
        return body == expected
    except Exception:
        return False


def _version_int(v) -> int:
    """バージョン文字列を整数に変換する（比較用）。失敗時は -1。"""
    try:
        return int(str(v).strip())
    except (TypeError, ValueError):
        return -1


def _running_server_version():
    """稼働中サーバーが報告するAPIバージョンを返す（取得できなければ None）。

    タイムアウトは3秒（サーバーがPOST処理でビジー状態でも誤検知しないよう余裕を持たせる）。
    """
    try:
        req = urllib.request.Request(
            f"http://localhost:{PREVIEW_PORT}/api/version",
            headers={"Cache-Control": "no-cache"},
        )
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            data = json.loads(resp.read())
        return data.get("version")
    except Exception:
        return None


def _server_is_healthy_and_current() -> bool:
    """稼働中サーバーが「正しいディレクトリを配信」かつ「自分以上のバージョン」かを判定する。

    【ピンポン防止の核心】
    稼働中サーバーのバージョンが自分（このコード）と同じ or それより新しい場合は
    「健全」とみなし、絶対にkillしない。
    複数セッションが異なるコード版を持っていても、最も新しい版のサーバーが生き残り、
    古い版のセッションはそれを尊重するため、kill合戦（ピンポン）が起きない。
    """
    if not _server_serves_correct_dir():
        return False
    rv = _running_server_version()
    if rv is None:
        return False
    return _version_int(rv) >= _version_int(SERVER_API_VERSION)


def _pids_on_port() -> list:
    """ポートを占有しているPID一覧を返す。"""
    try:
        out = subprocess.check_output(["lsof", "-ti", f":{PREVIEW_PORT}"], text=True).strip()
        return [p.strip() for p in out.splitlines() if p.strip()]
    except Exception:
        return []


def _wait_port_free(timeout=5.0) -> bool:
    """ポートが解放される（誰も握っていない）まで待つ。解放されたら True。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not _port_is_open():
            return True
        time.sleep(0.2)
    return not _port_is_open()


def _wait_server_up(timeout=8.0) -> bool:
    """サーバーが起動し /api/version に応答するまで待つ。応答したら True。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if _running_server_version() is not None:
            return True
        time.sleep(0.3)
    return _running_server_version() is not None


def _kill_server_on_port() -> None:
    """ポートを占有しているプロセスを確実にkillする（TERM→効かなければKILL）。

    旧実装は kill(TERM) して 0.8 秒待つだけで、プロセスが残ったまま次の bind が
    Address already in use で失敗していた。TERM後にポート解放を確認し、
    残っていれば KILL（-9）して、ポートが空くまで待つ。
    """
    pids = _pids_on_port()
    if not pids:
        return
    for pid in pids:
        subprocess.run(["kill", pid], check=False)        # SIGTERM
    if _wait_port_free(timeout=3.0):
        return
    # まだ残っている → 強制終了
    for pid in _pids_on_port():
        subprocess.run(["kill", "-9", pid], check=False)  # SIGKILL
    _wait_port_free(timeout=3.0)


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

    # articles/*.html（os.listdir自体もDropboxロックでEPERMしうるのでリトライ）
    articles_src = os.path.join(PROJECT_DIR, "articles")
    names = None
    for attempt in range(4):
        try:
            names = os.listdir(articles_src) if os.path.isdir(articles_src) else []
            break
        except (PermissionError, OSError) as e:
            if attempt < 3:
                time.sleep(0.25)
                continue
            print(f"⚠️ articles/ の一覧取得をスキップ（Dropboxロック）: {e}")
            names = []
    for f in (names or []):
        if f.endswith(".html"):
            _safe_copy(os.path.join(articles_src, f), os.path.join(articles_dst, f))


LOG_FILE = "/tmp/api_server.log"

def start_background_server():
    """バックグラウンドでAPIサーバーを起動する（静的配信 + POST /api/update_status）"""
    sync_to_serve_dir()
    api_server = os.path.join(PROJECT_DIR, "api_server.py")
    log_fh = open(LOG_FILE, "a")
    subprocess.Popen(
        ["python3", api_server],
        stdout=log_fh,
        stderr=log_fh,
        cwd=PROJECT_DIR,
    )
    time.sleep(0.8)


def ensure_server():
    """サーバーが起動していなければ起動し、起動済みならファイルを同期する。

    【複数セッション安全設計】
    全セッションがこの関数を呼ぶため、kill/再起動を排他制御しないと
    「同時kill→同時bind→Address already in use」「kill合戦（ピンポン）」が起き、
    その間ステータス更新POSTが Connection refused / 500 で失敗する。

    対策：
    1. 高速パス：健全かつ自分以上のバージョンなら、ロックも取らず同期だけして即return
    2. 再起動が必要なときだけ flock（プロセス間排他）を取得 → 1セッションずつ処理
    3. ロック取得後に再判定（他セッションが直前に直したかもしれない）
    4. kill→ポート解放確認→起動→応答確認、まで見届ける（中途半端な状態を残さない）
    5. 自分以上のバージョンのサーバーは絶対killしない（ピンポン根絶）
    """
    # ── 高速パス：健全なら何もしない（ロック不要・最も頻繁な経路）──
    if _port_is_open() and _server_is_healthy_and_current():
        sync_to_serve_dir()
        return

    # ── 再起動 or 新規起動が必要 → プロセス間ロックで直列化 ──
    os.makedirs(SERVE_DIR, exist_ok=True)
    lock_fd = open(LOCK_FILE, "w")
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX)   # 他セッションが処理中なら待つ

        # ロック取得までの間に別セッションが直していないか再判定
        if _port_is_open() and _server_is_healthy_and_current():
            sync_to_serve_dir()
            return

        if _port_is_open():
            # 何かが動いている → killすべきか判定
            running_ver = _running_server_version()
            stale_dir   = not _server_serves_correct_dir()
            old_version = (running_ver is None) or \
                          (_version_int(running_ver) < _version_int(SERVER_API_VERSION))
            if stale_dir:
                print(f"⚠️ 別ディレクトリを配信する古いサーバーを検出。再起動します...")
                _kill_server_on_port()
            elif old_version:
                print(f"⚠️ 旧バージョン({running_ver})のサーバーを検出。最新版({SERVER_API_VERSION})で再起動します...")
                _kill_server_on_port()
            else:
                # 自分以上のバージョンで健全 → 触らない（ピンポン防止）
                sync_to_serve_dir()
                return

        # ポートが空いている（or kill済み）→ 新規起動して応答を確認
        if not _port_is_open():
            print(f"🚀 ローカルサーバーを起動しています（port {PREVIEW_PORT}）...")
            start_background_server()
            if not _wait_server_up(timeout=8.0):
                print(f"⚠️ サーバーの起動確認に失敗しました（応答なし）。ログ: {LOG_FILE}")
        sync_to_serve_dir()
    finally:
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
        except Exception:
            pass
        lock_fd.close()
