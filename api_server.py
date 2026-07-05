#!/usr/bin/env python3
"""
api_server.py
静的ファイル配信 + ステータス更新API を提供するローカルHTTPサーバー

ThreadingHTTPServer を使用してリクエストを並列処理する。
（シングルスレッドだとPOST処理中に別接続がタイムアウトする）

エンドポイント:
  POST /api/update_status   {"id": 32, "status": "done"}
  → Google Sheets を更新 → index_generator.py 実行 → HTML を再生成
"""

import json
import os
import subprocess
import sys
from http.server import SimpleHTTPRequestHandler
from socketserver import ThreadingMixIn
from http.server import HTTPServer

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_DIR)

# .env はサーバー起動時に1回だけ読み込む（Dropboxのファイルロック回避）
from dotenv import load_dotenv
load_dotenv(dotenv_path=os.path.join(PROJECT_DIR, ".env"), override=False)


class ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
    """並列リクエスト処理に対応したHTTPサーバー"""
    daemon_threads = True  # メインプロセス終了時にスレッドも終了


class APIHandler(SimpleHTTPRequestHandler):
    """静的ファイル配信 + POST /api/update_status を処理するハンドラ"""

    # クラス変数としてserve_dirを保持（サブクラスで上書き）
    serve_dir = "."

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=self.serve_dir, **kwargs)

    # ── POST ──────────────────────────────────────────────────────────────────

    def do_GET(self):
        if self.path == "/api/version":
            from server_utils import SERVER_API_VERSION
            self._send_json(200, {"version": SERVER_API_VERSION})
        elif self.path.startswith("/api/sheets_hash"):
            self._handle_sheets_hash()
        else:
            super().do_GET()

    def do_POST(self):
        if self.path == "/api/update_status":
            self._handle_update_status()
        else:
            self._send_json(404, {"success": False, "error": "Not found"})

    def do_OPTIONS(self):
        self.send_response(200)
        self._cors_headers()
        self.end_headers()

    # ── 内部処理 ──────────────────────────────────────────────────────────────

    def _handle_sheets_hash(self):
        """Sheetsの最終更新ハッシュを返す（INDEXページのポーリングに使用）。

        【重要】fetch_articles_readonly を使い、ファイルI/Oを一切しない。
        常駐サーバーはDropbox内ファイルへのアクセス権を失うことがある（macOS TCC）ため、
        Dropbox内のキャッシュ読み書きに依存すると恒久的な500エラーになる（実際に発生）。
        """
        try:
            from sheets_index import fetch_articles_readonly
            articles = fetch_articles_readonly()
            # last_modified の最大値をハッシュ代わりに使う
            last_mods = [a.get("last_modified", "") for a in articles if a.get("last_modified")]
            latest = max(last_mods) if last_mods else str(len(articles))
            import hashlib
            h = hashlib.md5(latest.encode()).hexdigest()[:8]
            self._send_json(200, {"hash": h, "count": len(articles)})
        except Exception as e:
            self._send_json(500, {"hash": "error", "error": str(e)})

    def _handle_update_status(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            body   = self.rfile.read(length)
            data   = json.loads(body)

            article_id = int(data["id"])
            new_status = str(data["status"])

            allowed = {"writing", "review", "completed", "done", "hold", "closed"}
            if new_status not in allowed:
                self._send_json(400, {"success": False,
                                      "error": f"不正なステータス: {new_status}"})
                return

            # Sheets を更新（失敗したら例外が飛ぶ → 下の except で 500 を返す）
            from sheets_index import update_article
            update_article(article_id, {"status": new_status})
            print(f"[api_server] Sheets更新成功: id={article_id} status={new_status}", flush=True)

            # index_generator.py を実行して HTML を再生成（ブロッキング）
            # ※ HTMLの一次出力先は /tmp の配信フォルダ（Dropbox非依存）なので、
            #   Dropboxの権限問題があっても再生成は成功する
            # ※ --no-pull：ステータス更新のたびにgit pullしない（高速・安定）
            # ※ --no-server：サーバー自身のサブプロセスなので ensure_server() は呼ばない
            html_ok = True
            html_err = ""
            try:
                result = subprocess.run(
                    [sys.executable, os.path.join(PROJECT_DIR, "index_generator.py"),
                     "--no-pull", "--no-server"],
                    cwd=PROJECT_DIR,
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
                if result.returncode != 0:
                    html_ok = False
                    html_err = (result.stderr or result.stdout or "")[-300:]
                    print(f"[api_server] index_generator 失敗: {html_err}", flush=True)
            except Exception as e:
                html_ok = False
                html_err = str(e)
                print(f"[api_server] index_generator 実行エラー: {e}", flush=True)

            # 配信ディレクトリへ同期（best-effort・記事HTML等のため）
            try:
                from server_utils import sync_to_serve_dir
                sync_to_serve_dir()
            except Exception as e:
                print(f"[api_server] sync_to_serve_dir 失敗（無視）: {e}", flush=True)

            # 【失敗を隠さない】Sheets更新は成功。HTML再生成の結果も正直に返す
            payload = {
                "success": True,
                "id":      article_id,
                "status":  new_status,
            }
            if not html_ok:
                payload["warning"] = f"Sheetsは更新済みですが画面の再生成に失敗しました: {html_err[:120]}"
            self._send_json(200, payload)

        except (KeyError, ValueError) as e:
            self._send_json(400, {"success": False, "error": f"不正なリクエスト: {e}"})
        except subprocess.TimeoutExpired:
            self._send_json(500, {"success": False, "error": "HTML再生成がタイムアウトしました"})
        except Exception as e:
            self._send_json(500, {"success": False, "error": str(e)})

    def _send_json(self, code, payload):
        body = json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self._cors_headers()
        self.end_headers()
        self.wfile.write(body)

    def _cors_headers(self):
        self.send_header("Access-Control-Allow-Origin",  "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def log_message(self, fmt, *args):
        """API 呼び出しのみログ出力（静的ファイルは抑制）"""
        if args and "/api/" in str(args[0]):
            print(f"[api_server] {fmt % args}", flush=True)


def make_handler_class(serve_dir: str):
    """serve_dir を束縛したハンドラクラスを返す"""
    return type("BoundAPIHandler", (APIHandler,), {"serve_dir": serve_dir})


SELF_RESTART_SEC = 24 * 3600  # 24時間ごとに自分自身を再起動する


def _schedule_self_restart():
    """24時間後に os.execv で自分自身を最新コードで再起動する。

    【なぜ必要か】
    週単位で生き続けた常駐プロセスは、macOS（TCC）にDropboxフォルダへの
    アクセス権を剥奪されたり、更新前の古いコードを抱え込んだりする（実際に発生）。
    execv はプロセスを丸ごと入れ替えるため、コードもメモリ状態も毎日リフレッシュされる。
    listenソケットはPythonがCLOEXEC付きで作るため exec 時に自動で閉じ、
    新プロセスが同じポートに bind し直せる（ダウンタイムは1秒未満）。
    """
    import threading

    def _restart():
        print(f"[api_server] 定期セルフリスタート（起動から24時間経過）", flush=True)
        os.chdir(PROJECT_DIR)
        os.execv(sys.executable, [sys.executable, os.path.abspath(__file__)])

    t = threading.Timer(SELF_RESTART_SEC, _restart)
    t.daemon = True
    t.start()


def run(port: int, serve_dir: str):
    os.makedirs(serve_dir, exist_ok=True)
    HandlerClass = make_handler_class(serve_dir)
    server = ThreadingHTTPServer(("localhost", port), HandlerClass)
    _schedule_self_restart()
    server.serve_forever()


if __name__ == "__main__":
    from server_utils import PREVIEW_PORT, SERVE_DIR, SERVER_API_VERSION
    print(f"🚀 API server v{SERVER_API_VERSION}: http://localhost:{PREVIEW_PORT}/  (dir={SERVE_DIR})", flush=True)
    run(PREVIEW_PORT, SERVE_DIR)
