"""
sheets_index.py
Google Sheetsを記事インデックスのSingle Source of Truthとして使う

- load_from_sheets() : Sheetsから全記事を取得してarticle_index.jsonに同期
- append_article()   : Sheetsに新規記事を1行追加
- update_article()   : Sheetsの既存行を更新（gdocs_url・statusなど）
"""

import os
import json
import warnings
warnings.filterwarnings("ignore")

from dotenv import load_dotenv
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

load_dotenv(override=True)

PROJECT_DIR    = os.path.dirname(os.path.abspath(__file__))
CLIENT_SECRETS = os.path.join(PROJECT_DIR, "client_secrets.json")
TOKEN_FILE     = os.path.join(PROJECT_DIR, "token.json")
INDEX_JSON     = os.path.join(PROJECT_DIR, "article_index.json")
SPREADSHEET_ID = os.environ.get("SHEETS_INDEX_ID", "")
SHEET_NAME     = "記事一覧"

SCOPES = [
    "https://www.googleapis.com/auth/documents",
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/spreadsheets",
]

HEADERS = ["id", "date", "title", "gdocs_url", "status", "saved_at", "html_file", "json_file", "writer"]


def _get_service():
    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRETS, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_FILE, "w") as f:
            f.write(creds.to_json())
    return build("sheets", "v4", credentials=creds)


def _rows_to_articles(rows):
    """Sheetsの行データ（リスト）を記事辞書のリストに変換する"""
    if not rows or len(rows) < 2:
        return []
    header = rows[0]
    articles = []
    for row in rows[1:]:
        # 列が足りない場合は空文字で補完
        padded = row + [""] * (len(header) - len(row))
        a = {header[i]: padded[i] for i in range(len(header))}
        # idは整数に変換
        try:
            a["id"] = int(a["id"])
        except (ValueError, KeyError):
            pass
        articles.append(a)
    return articles


def load_from_sheets():
    """SheetsからデータをfetchしてローカルのJSONキャッシュを更新する"""
    if not SPREADSHEET_ID:
        # SHEETS_INDEX_IDが未設定の場合はローカルJSONをそのまま使う（後方互換）
        if os.path.exists(INDEX_JSON):
            with open(INDEX_JSON, encoding="utf-8") as f:
                return json.load(f)
        return []

    try:
        service = _get_service()
        result = service.spreadsheets().values().get(
            spreadsheetId=SPREADSHEET_ID,
            range=f"{SHEET_NAME}!A:I",
        ).execute()
        rows = result.get("values", [])
        articles = _rows_to_articles(rows)

        # ローカルJSONキャッシュを更新
        with open(INDEX_JSON, "w", encoding="utf-8") as f:
            json.dump(articles, f, ensure_ascii=False, indent=2)

        return articles
    except Exception as e:
        print(f"⚠️ Sheets読み込み失敗（ローカルキャッシュを使用）: {e}")
        if os.path.exists(INDEX_JSON):
            with open(INDEX_JSON, encoding="utf-8") as f:
                return json.load(f)
        return []


def append_article(article: dict):
    """Sheetsに新規記事を1行追加する。ローカルJSONも更新する。"""
    if not SPREADSHEET_ID:
        return  # Sheets未設定時はスキップ

    row = [str(article.get(h, "")) for h in HEADERS]
    try:
        service = _get_service()
        service.spreadsheets().values().append(
            spreadsheetId=SPREADSHEET_ID,
            range=f"{SHEET_NAME}!A:I",
            valueInputOption="RAW",
            insertDataOption="INSERT_ROWS",
            body={"values": [row]},
        ).execute()
    except Exception as e:
        print(f"⚠️ Sheets追加失敗: {e}")


def update_article(article_id: int, updates: dict):
    """Sheetsの指定IDの行を更新する。ローカルJSONも更新する。"""
    if not SPREADSHEET_ID:
        return

    try:
        service = _get_service()
        # 全行を取得して対象行を探す
        result = service.spreadsheets().values().get(
            spreadsheetId=SPREADSHEET_ID,
            range=f"{SHEET_NAME}!A:I",
        ).execute()
        rows = result.get("values", [])
        if not rows:
            return

        header = rows[0]
        for i, row in enumerate(rows[1:], start=2):  # Sheetsは1始まり、ヘッダーが1行目
            padded = row + [""] * (len(header) - len(row))
            try:
                if int(padded[0]) == article_id:
                    # 更新する列だけ書き換え
                    for key, val in updates.items():
                        if key in header:
                            col_idx = header.index(key)
                            padded[col_idx] = str(val)
                    # 該当行を上書き
                    service.spreadsheets().values().update(
                        spreadsheetId=SPREADSHEET_ID,
                        range=f"{SHEET_NAME}!A{i}:I{i}",
                        valueInputOption="RAW",
                        body={"values": [padded]},
                    ).execute()
                    return
            except (ValueError, IndexError):
                continue
        print(f"⚠️ ID {article_id} の行がSheetsに見つかりませんでした")
    except Exception as e:
        print(f"⚠️ Sheets更新失敗: {e}")
