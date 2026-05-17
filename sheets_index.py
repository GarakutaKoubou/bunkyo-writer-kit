"""
sheets_index.py
Google Sheetsを記事インデックスのSingle Source of Truthとして使う

- load_from_sheets() : Sheetsから全記事を取得 → article_index.json（出力専用キャッシュ）を更新
- append_article()   : Sheetsに新規記事を1行追加。IDはSheets行番号から採番（競合防止）
- update_article()   : Sheetsの既存行を更新（last_modifiedを自動設定）

【競合防止の仕組み】
  ID採番に max(existing)+1 を使わず、Sheets API の append が返す行番号をIDとして使う。
  append 自体はSheets側でシリアライズされるため、複数セッション同時実行でも
  異なる行番号（=異なるID）が割り当てられ、ID衝突が発生しない。
"""

import os
import re
import json
import warnings
from datetime import datetime

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

# last_modified を10列目（J列）に追加
HEADERS    = ["id", "date", "title", "gdocs_url", "status", "saved_at",
              "html_file", "json_file", "writer", "last_modified"]
COL_RANGE  = "A:J"          # 全列取得範囲
ROW_FMT    = "A{r}:J{r}"   # 行単位の更新範囲フォーマット


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
        padded = row + [""] * (len(header) - len(row))
        a = {header[i]: padded[i] for i in range(len(header))}
        try:
            a["id"] = int(a["id"])
        except (ValueError, KeyError):
            pass
        articles.append(a)
    return articles


def load_from_sheets():
    """SheetsからデータをfetchしてローカルのJSONキャッシュを更新する。

    article_index.json は出力専用キャッシュ。直接編集・参照禁止。
    SHEETS_INDEX_ID が未設定の場合のみローカルJSONへフォールバック（後方互換）。
    """
    if not SPREADSHEET_ID:
        # SHEETS_INDEX_ID 未設定 → ローカルJSONで動作（後方互換）
        if os.path.exists(INDEX_JSON):
            with open(INDEX_JSON, encoding="utf-8") as f:
                return json.load(f)
        return []

    try:
        service = _get_service()
        result = service.spreadsheets().values().get(
            spreadsheetId=SPREADSHEET_ID,
            range=f"{SHEET_NAME}!{COL_RANGE}",
        ).execute()
        rows = result.get("values", [])
        articles = _rows_to_articles(rows)

        # article_index.json は出力専用キャッシュとして上書き（インプットには使わない）
        with open(INDEX_JSON, "w", encoding="utf-8") as f:
            json.dump(articles, f, ensure_ascii=False, indent=2)

        return articles

    except Exception as e:
        print(f"⚠️ Sheets読み込み失敗（ローカルキャッシュを使用）: {e}")
        if os.path.exists(INDEX_JSON):
            with open(INDEX_JSON, encoding="utf-8") as f:
                return json.load(f)
        return []


def append_article(article: dict) -> int:
    """Sheetsに新規記事を1行追加し、採番されたIDを返す。

    【競合防止】
    - IDフィールドを空にしてappend（アトミック操作）
    - Sheetsが返す行番号をそのままIDとして使用
    - 複数セッションが同時にappendしても行番号は必ず異なるため、ID衝突しない
    """
    if not SPREADSHEET_ID:
        return 0

    now = datetime.now().isoformat(timespec="seconds")
    row = [
        "",                               # id  ← 空で送信、行番号から後で採番
        str(article.get("date", "")),
        article.get("title", ""),
        article.get("gdocs_url", ""),
        article.get("status", ""),
        article.get("saved_at", ""),
        article.get("html_file", ""),
        article.get("json_file", ""),
        article.get("writer", ""),
        now,                              # last_modified
    ]

    try:
        service = _get_service()
        resp = service.spreadsheets().values().append(
            spreadsheetId=SPREADSHEET_ID,
            range=f"{SHEET_NAME}!{COL_RANGE}",
            valueInputOption="RAW",
            insertDataOption="INSERT_ROWS",
            body={"values": [row]},
        ).execute()

        # 追加された行番号を取得（例: "記事一覧!A39:J39" → 39）
        updated_range = resp.get("updates", {}).get("updatedRange", "")
        match = re.search(r"!A(\d+)", updated_range)
        if not match:
            print(f"⚠️ 行番号を取得できませんでした: {updated_range}")
            return 0

        new_row_num = int(match.group(1))
        # 行番号をそのままIDとして使用（append がシリアライズされるため一意）
        new_id = new_row_num

        # ID列（A列）に確定したIDを書き込む
        service.spreadsheets().values().update(
            spreadsheetId=SPREADSHEET_ID,
            range=f"{SHEET_NAME}!A{new_row_num}",
            valueInputOption="RAW",
            body={"values": [[str(new_id)]]},
        ).execute()

        print(f"📋 Sheetsに追加: ID={new_id}（行{new_row_num}）")
        return new_id

    except Exception as e:
        print(f"⚠️ Sheets追加失敗: {e}")
        return 0


def update_article(article_id: int, updates: dict):
    """Sheetsの指定IDの行を更新する。last_modifiedを自動設定する。"""
    if not SPREADSHEET_ID:
        return

    try:
        service = _get_service()
        result = service.spreadsheets().values().get(
            spreadsheetId=SPREADSHEET_ID,
            range=f"{SHEET_NAME}!{COL_RANGE}",
        ).execute()
        rows = result.get("values", [])
        if not rows:
            return

        header = rows[0]
        for i, row in enumerate(rows[1:], start=2):   # Sheetsは1-indexed、ヘッダーが1行目
            padded = row + [""] * (len(header) - len(row))
            try:
                if int(padded[0]) == article_id:
                    # 指定フィールドを更新
                    for key, val in updates.items():
                        if key in header:
                            padded[header.index(key)] = str(val)
                    # last_modified を自動更新（更新のたびに記録）
                    now = datetime.now().isoformat(timespec="seconds")
                    if "last_modified" in header:
                        padded[header.index("last_modified")] = now
                    # J列まで含めた行範囲で上書き
                    service.spreadsheets().values().update(
                        spreadsheetId=SPREADSHEET_ID,
                        range=f"{SHEET_NAME}!{ROW_FMT.format(r=i)}",
                        valueInputOption="RAW",
                        body={"values": [padded]},
                    ).execute()
                    return
            except (ValueError, IndexError):
                continue
        print(f"⚠️ ID {article_id} の行がSheetsに見つかりませんでした")

    except Exception as e:
        print(f"⚠️ Sheets更新失敗: {e}")
