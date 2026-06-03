"""
post_to_gdocs.py
記事・メール文をGoogle Docsに保存する（OAuth2認証）
"""

import warnings
warnings.filterwarnings("ignore")

import os
import io
import re
from datetime import datetime
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
from dotenv import load_dotenv

URL_PATTERN = re.compile(r'https?://[^\s　]+')

load_dotenv(override=True)

SCOPES = [
    'https://www.googleapis.com/auth/documents',
    'https://www.googleapis.com/auth/drive',
    'https://www.googleapis.com/auth/spreadsheets',
]

CLIENT_SECRETS      = os.path.join(os.path.dirname(__file__), 'client_secrets.json')
TOKEN_FILE          = os.path.join(os.path.dirname(__file__), 'token.json')
FOLDER_ID              = os.environ.get("GDOCS_FOLDER_ID", "")
COMPLETED_FOLDER_ID    = os.environ.get("COMPLETED_FOLDER_ID", "")
YEAR_FOLDERS_PARENT_ID = os.environ.get("YEAR_FOLDERS_PARENT_ID", "")


def get_service():
    """Google Drive サービスをOAuth2認証で取得する"""
    creds = None

    # 保存済みトークンがあれば読み込む
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

    # トークンがない or 期限切れの場合はブラウザで認証
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRETS, SCOPES)
            creds = flow.run_local_server(port=0)
        # トークンを保存（次回以降はブラウザ不要）
        with open(TOKEN_FILE, 'w') as f:
            f.write(creds.to_json())

    drive_service = build('drive', 'v3', credentials=creds)
    docs_service  = build('docs',  'v1', credentials=creds)
    return docs_service, drive_service


def format_article_content(article: dict) -> str:
    """
    記事データをドキュメント用テキストにフォーマットする
    添付テンプレート準拠

    写真スロット（7箇所）：
      1. ■写真キャプション + top_photo_url  ← トップ写真（最重要）
      ※ ■フォトフラッシュタイトルはセクション見出しのみ（コンテンツなし）
      2. （リンク画像）link_image_text + link_image_url  ← Yahoo!ニュース等リンク（2番目に重要）
      3〜7. （1）〜（5）photos配列  ← サブ写真
    """
    date_str    = article.get("generated_at", datetime.now().strftime("%Y%m%d"))
    title_short = article.get("title", "")[:10].replace("　", "")

    top_photo_url   = article.get("top_photo_url", "")
    link_image_text = article.get("link_image_text", "")
    link_image_url  = article.get("link_image_url", "")
    photos          = article.get("photos", [])  # （1）〜（5）用サブ写真のみ
    address         = article.get("address", "文京区")
    related_links   = article.get("related_links", [])  # {"url": "...", "text": "..."} のリスト

    # （1）〜（5）セクション：写真URLとキャプションを展開（最大5枚）
    photo_lines = []
    for i in range(5):
        num = f"（{i + 1}）"
        if i < len(photos):
            cap = photos[i].get("caption", "")
            url = photos[i].get("url", "")
            photo_lines.append(f"{num}{cap}\n{url}")
        else:
            photo_lines.append(num)
    photos_block = "\n\n".join(photo_lines)

    # 記事下リンクブロック：テキストがあれば「テキスト\nURL」、なければURLのみ
    link_lines = []
    for link in related_links[:5]:  # 最大5件
        url  = link.get("url", "")
        text = link.get("text", "")
        if text:
            link_lines.append(f"{text}\n{url}")
        else:
            link_lines.append(url)
    related_links_block = "\n\n".join(link_lines)

    content = f"""ファイル名：{date_str}_文京経済新聞_{title_short}

設定：フォント＝MSPゴシック、サイズ＝10.5

■タイトル（35字以内目安）
{article.get('title', '')}

■写真キャプション
{article.get('caption', '')}
{top_photo_url}

■本文（段落文頭１字下げ：文頭～初出「。」までリード）
{article.get('body', '')}

■フォトフラッシュタイトル

（リンク画像）{link_image_text}
{link_image_url}

{photos_block}

■記事下リンク（最大5件：関連画像含む）
{related_links_block}

■住所（管理画面入力用）
{address}
"""
    return content


def apply_url_links(docs_service, doc_id: str) -> None:
    """ドキュメント内のURL文字列すべてにハイパーリンクを設定する"""
    doc = docs_service.documents().get(documentId=doc_id).execute()
    requests = []

    for elem in doc.get("body", {}).get("content", []):
        if "paragraph" not in elem:
            continue
        for pe in elem["paragraph"].get("elements", []):
            if "textRun" not in pe:
                continue
            text = pe["textRun"].get("content", "")
            start_idx = pe.get("startIndex", 0)
            for m in URL_PATTERN.finditer(text):
                url = m.group(0).rstrip("。、.,）」』")
                link_start = start_idx + m.start()
                link_end   = start_idx + m.start() + len(url)
                requests.append({
                    "updateTextStyle": {
                        "range": {"startIndex": link_start, "endIndex": link_end},
                        "textStyle": {"link": {"url": url}},
                        "fields": "link",
                    }
                })

    if requests:
        docs_service.documents().batchUpdate(
            documentId=doc_id,
            body={"requests": requests}
        ).execute()
        print(f"✅ {len(requests)} 件のURLにハイパーリンクを設定しました")


def create_google_doc(title: str, content: str) -> str:
    """
    Google Docsにドキュメントを新規作成し、指定フォルダに配置する
    Returns: 作成したドキュメントのURL
    """
    docs_service, drive_service = get_service()

    file_metadata = {
        "name": title,
        "mimeType": "application/vnd.google-apps.document",
    }
    if FOLDER_ID:
        file_metadata["parents"] = [FOLDER_ID]

    media = MediaIoBaseUpload(
        io.BytesIO(content.encode("utf-8")),
        mimetype="text/plain",
        resumable=False
    )
    file = drive_service.files().create(
        body=file_metadata,
        media_body=media,
        fields="id"
    ).execute()
    doc_id = file["id"]

    apply_url_links(docs_service, doc_id)

    url = f"https://docs.google.com/document/d/{doc_id}/edit"
    print(f"✅ Google Docsに新規作成しました: {url}")
    return url


def update_google_doc(doc_id: str, title: str, content: str) -> str:
    """
    既存のGoogle Docsドキュメントの内容を上書き更新する
    Returns: 更新したドキュメントのURL
    """
    docs_service, drive_service = get_service()

    # ファイル名を更新
    drive_service.files().update(
        fileId=doc_id,
        body={"name": title}
    ).execute()

    # 内容を上書き（plain textをGoogle Docsとしてアップロード）
    media = MediaIoBaseUpload(
        io.BytesIO(content.encode("utf-8")),
        mimetype="text/plain",
        resumable=False
    )
    drive_service.files().update(
        fileId=doc_id,
        media_body=media
    ).execute()

    apply_url_links(docs_service, doc_id)

    url = f"https://docs.google.com/document/d/{doc_id}/edit"
    print(f"✅ Google Docsを更新しました: {url}")
    return url


def get_or_create_year_folder(year: str) -> str:
    """指定年のフォルダIDを返す。なければ自動作成する。"""
    if not YEAR_FOLDERS_PARENT_ID:
        return COMPLETED_FOLDER_ID  # フォールバック
    _, drive_service = get_service()
    folder_name = f"{year}年"
    # 既存フォルダを検索
    query = (
        f"'{YEAR_FOLDERS_PARENT_ID}' in parents "
        f"and name = '{folder_name}' "
        f"and mimeType = 'application/vnd.google-apps.folder' "
        f"and trashed = false"
    )
    results = drive_service.files().list(q=query, fields="files(id, name)").execute()
    files = results.get("files", [])
    if files:
        print(f"📂 既存の「{folder_name}」フォルダを使用: {files[0]['id']}")
        return files[0]["id"]
    # なければ作成
    metadata = {
        "name": folder_name,
        "mimeType": "application/vnd.google-apps.folder",
        "parents": [YEAR_FOLDERS_PARENT_ID]
    }
    folder = drive_service.files().create(body=metadata, fields="id").execute()
    print(f"✅ 「{folder_name}」フォルダを新規作成しました: {folder['id']}")
    return folder["id"]


def move_to_completed(doc_id: str, date_str: str = "") -> None:
    """ドキュメントを該当年の完成フォルダに移動する"""
    # 年をdate_strから取得（例：20270315 → 2027）
    year = date_str[:4] if date_str and len(date_str) >= 4 else ""
    if year and year != "2026":
        target_folder_id = get_or_create_year_folder(year)
    else:
        target_folder_id = COMPLETED_FOLDER_ID
    if not target_folder_id:
        print("⚠️  完成フォルダが未設定のためスキップします")
        return
    _, drive_service = get_service()
    # 現在の親フォルダとファイル名を取得
    file = drive_service.files().get(fileId=doc_id, fields="name, parents").execute()
    current_parents = ",".join(file.get("parents", []))
    # プレフィックスを除去したファイル名を作成（本番フォルダはプレフィックスなし）
    current_name = file.get("name", "")
    new_name = current_name
    for prefix in ["【完成】", "【下書き】"]:
        if current_name.startswith(prefix):
            new_name = current_name[len(prefix):]
            break
    # 完成フォルダに移動 + ファイル名更新
    drive_service.files().update(
        fileId=doc_id,
        addParents=target_folder_id,
        removeParents=current_parents,
        body={"name": new_name},
        fields="id, name, parents"
    ).execute()
    print(f"📁 完成フォルダに移動しました: https://docs.google.com/document/d/{doc_id}/edit")


def delete_old_docs_in_folder(date_str: str, folder_id: str) -> None:
    """同じ日付プレフィックスを持つ既存ドキュメントをフォルダから削除する"""
    if not folder_id:
        return
    _, drive_service = get_service()
    query = f"'{folder_id}' in parents and name contains '{date_str}' and mimeType = 'application/vnd.google-apps.document' and trashed = false"
    results = drive_service.files().list(q=query, fields="files(id, name)").execute()
    files = results.get("files", [])
    for f in files:
        # 自分たちが作成したファイルのみ削除（他の担当者のファイルは一切触らない）
        # ・下書き/完成フォルダ内：「【下書き】」「【完成】」プレフィックス付き
        # ・本番フォルダ内：move_to_completed()でプレフィックスを除去するため「YYYYMMDD_」形式
        name = f["name"]
        is_our_file = (
            name.startswith("【下書き】" + date_str + "_")
            or name.startswith("【完成】" + date_str + "_")
            or name.startswith(date_str + "_")  # 完成フォルダ内のプレフィックスなし形式
        )
        if not is_our_file:
            print(f"⏭️  スキップ（他担当者のファイル）: {name}")
            continue
        try:
            drive_service.files().delete(fileId=f["id"]).execute()
            print(f"🗑️  古いファイルを削除しました: {name}")
        except Exception as e:
            print(f"⚠️  削除をスキップしました（権限なし）: {name} / {e}")


def _extract_doc_id(gdocs_url: str) -> str:
    """Google DocsのURLからドキュメントIDを取り出す。失敗時は空文字。"""
    if not gdocs_url or "/d/" not in gdocs_url:
        return ""
    try:
        return gdocs_url.split("/d/")[1].split("/")[0]
    except (IndexError, AttributeError):
        return ""


def save_article(article: dict, has_comment: bool, gdocs_url: str = "") -> str:
    """記事をGoogle Docsに保存する。

    【重要】日付マッチの一括削除は廃止した。
    日付はかぶる（同日に複数記事）ため、日付で既存ファイルを削除すると
    同日付の別記事のドキュメントまで巻き込み削除してしまう重大バグになる。

    新方式：
      - gdocs_url（その記事固有のドキュメントURL）があれば、そのドキュメントを
        ピンポイントで上書き更新する（他記事には一切触れない）
      - gdocs_url が無ければ新規作成する
    """
    date_str  = article.get("generated_at", datetime.now().strftime("%Y%m%d"))
    title     = article.get("title", "無題")
    prefix = "【完成】" if has_comment else "【下書き】"
    doc_title = f"{prefix}{date_str}_{title}"
    content   = format_article_content(article)

    # 既存のドキュメントがあれば、それだけをピンポイントで上書き更新する
    doc_id = _extract_doc_id(gdocs_url)
    if doc_id:
        try:
            return update_google_doc(doc_id, doc_title, content)
        except Exception as e:
            print(f"⚠️ 既存ドキュメントの更新に失敗しました。新規作成にフォールバックします: {e}")

    # 既存URLが無い or 更新失敗 → 新規作成
    return create_google_doc(doc_title, content)


def save_mail(article: dict, mail_text: str, mail_type: str = "comment_only") -> str:
    """依頼メール文をGoogle Docsに保存する

    mail_type:
        "comment_only"       → 【メール：コメント依頼】
        "photo_only"         → 【メール：写真依頼】
        "comment_and_photo"  → 【メール：コメント＆写真依頼】
    """
    date_str = article.get("generated_at", datetime.now().strftime("%Y%m%d"))
    title    = article.get("title", "無題")

    prefix_map = {
        "comment_only":      "【メール：コメント依頼】",
        "photo_only":        "【メール：写真依頼】",
        "comment_and_photo": "【メール：コメント＆写真依頼】",
    }
    prefix    = prefix_map.get(mail_type, "【メール依頼】")
    doc_title = f"{prefix}{date_str}_{title}"
    return create_google_doc(doc_title, mail_text)
