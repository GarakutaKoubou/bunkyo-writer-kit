"""
preview_generator.py
記事プレビューをHTMLファイルとして生成してブラウザで表示する

使い方:
  python3 preview_generator.py --json /tmp/article_preview.json --open
    → HTMLを生成してブラウザで開く（初回）

  python3 preview_generator.py --json /tmp/article_preview.json
    → HTMLだけ更新（ブラウザは変更を検知して自動リフレッシュ）

  python3 preview_generator.py --json /tmp/article_preview.json --save-article 20260302
    → 記事固有HTMLとして articles/20260302.html にも保存する（承認後に実行）

ブラウザURL: http://localhost:8765/article_preview.html
"""

import json
import argparse
import os
import time
import webbrowser
from datetime import datetime

from server_utils import PROJECT_DIR, PREVIEW_PORT, ensure_server, sync_to_serve_dir

OUTPUT_HTML  = os.path.join(PROJECT_DIR, "article_preview.html")
VERSION_FILE = os.path.join(PROJECT_DIR, "article_preview_version.json")
INDEX_JSON   = os.path.join(PROJECT_DIR, "article_index.json")
PREVIEW_URL  = f"http://localhost:{PREVIEW_PORT}/article_preview.html"


# ── article_index.json 自動更新 ────────────────────────────────────────────

def update_article_index(article_id, title, gdocs_url, html_file, json_file, date_fallback=None):
    """
    --save-article 実行時に article_index.json の該当エントリを自動更新する。
    html_file / json_file / gdocs_url / title を上書きする。

    検索順序:
      1. id が一致するエントリ（article_id が None でない場合）
      2. date が一致するエントリ（date_fallback が指定されている場合）
      3. 見つからない場合は新規エントリを自動作成する
    """
    if not os.path.exists(INDEX_JSON):
        print("⚠️  article_index.json が見つかりません。手動で更新してください。")
        return
    with open(INDEX_JSON, encoding="utf-8") as f:
        articles = json.load(f)

    updated = False
    for a in articles:
        # article_id が判明している場合は id のみで厳密に検索する。
        # date による曖昧マッチは article_id が None の場合のみ許可する。
        # （同じ日付の別記事を誤って上書きするバグを防ぐ）
        if article_id is not None:
            matched = (str(a.get("id", "")) == str(article_id))
        elif date_fallback:
            matched = (a.get("date") == str(date_fallback))
        else:
            matched = False

        if matched:
            if html_file:
                a["html_file"] = html_file
            if json_file:
                a["json_file"] = json_file
            if gdocs_url:
                a["gdocs_url"] = gdocs_url
            if title:
                a["title"] = title
            updated = True
            article_id = a.get("id", article_id)  # ログ用にidを取得
            break

    if not updated:
        from datetime import date as _date
        if article_id is not None:
            # article_id は判明しているがローカルJSONにない（claim_article.py 直後など）。
            # max+1 で別IDを作ると既存Sheetsエントリを破壊するため、指定IDで追加する。
            new_entry = {
                "id": int(article_id),
                "date": date_fallback or "",
                "title": title or "",
                "gdocs_url": gdocs_url or "",
                "status": "writing",
                "saved_at": str(_date.today()),
                "html_file": html_file or "",
                "json_file": json_file or "",
            }
            articles.append(new_entry)
            print(f"📋 article_index.json に新規エントリを作成しました（id={article_id}, date={date_fallback}）")
        else:
            # article_id が不明な場合のみ max+1 で採番する（レアケース）
            existing_ids = [a.get("id", 0) for a in articles if isinstance(a.get("id"), int)]
            new_id = max(existing_ids) + 1 if existing_ids else 1
            new_entry = {
                "id": new_id,
                "date": date_fallback or "",
                "title": title or "",
                "gdocs_url": gdocs_url or "",
                "status": "draft",
                "saved_at": str(_date.today()),
                "html_file": html_file or "",
                "json_file": json_file or "",
            }
            articles.append(new_entry)
            article_id = new_id
            print(f"📋 article_index.json に新規エントリを作成しました（id={new_id}, date={date_fallback}）")

    with open(INDEX_JSON, "w", encoding="utf-8") as f:
        json.dump(articles, f, ensure_ascii=False, indent=2)
    print(f"📋 article_index.json を自動更新しました（id={article_id}）")

    # Sheets にも同期（writing ステータスを上書きするため）
    if article_id is not None:
        import os as _os
        if _os.environ.get("SHEETS_INDEX_ID"):
            try:
                from sheets_index import update_article as _su
                sync = {k: v for k, v in {
                    "html_file": html_file,
                    "json_file": json_file,
                    "gdocs_url": gdocs_url,
                    "title":     title,
                }.items() if v}
                if sync:
                    _su(int(article_id), sync)
                    print(f"📋 Sheets も更新しました（id={article_id}）")
            except Exception as e:
                print(f"⚠️ Sheets 同期スキップ: {e}")


# ── バージョンファイル更新 ──────────────────────────────────────────────────

def write_version():
    """変更検知用のバージョンファイルを更新する"""
    with open(VERSION_FILE, "w", encoding="utf-8") as f:
        json.dump({"version": datetime.now().isoformat()}, f)


# ── HTML生成 ───────────────────────────────────────────────────────────────

MAIL_TYPE_LABELS = {
    "comment_only":        "コメント依頼メール",
    "photo_only":          "写真依頼メール",
    "comment_and_photo":   "コメント＆写真依頼メール",
    "interview_questions": "取材質問リスト",
}

def build_received_comment_section(received_comment) -> str:
    """受け取ったコメントセクションのHTML"""
    if not received_comment:
        return ""
    text = received_comment.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return f"""
      <!-- 受け取ったコメント -->
      <div class="section received-comment-section">
        <div class="label received-comment-label">💬 受け取ったコメント（担当者より）</div>
        <pre class="received-comment-body">{text}</pre>
      </div>
"""


def build_mail_section(mail) -> str:
    """メールセクションのHTML（mail.jsonがない場合は空文字）"""
    if not mail:
        return ""
    mail_type  = mail.get("mail_type", "")
    mail_text  = mail.get("mail_text", "")
    label      = MAIL_TYPE_LABELS.get(mail_type, "依頼メール")
    mail_lines = mail_text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return f"""
      <!-- コメント依頼メール -->
      <div class="section mail-section">
        <div class="label mail-label">✉ {label}</div>
        <pre class="mail-body">{mail_lines}</pre>
      </div>
"""


def build_next_steps_section(next_steps) -> str:
    """次のステップセクションのHTML"""
    if not next_steps:
        return ""

    step_type   = next_steps.get("type", "")
    comment_req = next_steps.get("comment_request", {})
    photo_req   = next_steps.get("photo_request", {})
    missing     = next_steps.get("missing_info", [])

    blocks = ""

    # 不足情報（最優先で表示）
    if missing:
        items = "".join(
            f"<li>{m.replace('&','&amp;').replace('<','&lt;').replace('>','&gt;')}</li>"
            for m in missing
        )
        blocks += f"""
        <div class="ns-block ns-missing">
          <div class="ns-block-title">⚠️ 記事に必要な情報が不足しています</div>
          <ul class="ns-list">{items}</ul>
        </div>"""

    # コメント依頼
    if comment_req:
        target = comment_req.get("target", "担当者")
        questions = comment_req.get("questions", [])
        q_items = "".join(
            f"<li>{q.replace('&','&amp;').replace('<','&lt;').replace('>','&gt;')}</li>"
            for q in questions
        )
        blocks += f"""
        <div class="ns-block ns-comment">
          <div class="ns-block-title">💬 コメントを依頼してください</div>
          <div class="ns-target">依頼先：{target.replace('&','&amp;').replace('<','&lt;').replace('>','&gt;')}</div>
          <div class="ns-q-heading">質問案：</div>
          <ol class="ns-questions">{q_items}</ol>
        </div>"""

    # 写真依頼
    if photo_req:
        suggestions = photo_req.get("suggestions", [])
        s_items = "".join(
            f"<li>{s.replace('&','&amp;').replace('<','&lt;').replace('>','&gt;')}</li>"
            for s in suggestions
        )
        blocks += f"""
        <div class="ns-block ns-photo">
          <div class="ns-block-title">📸 写真を依頼してください</div>
          <ul class="ns-list">{s_items}</ul>
        </div>"""

    if not blocks:
        return ""

    return f"""
      <!-- 次のステップ -->
      <div class="section next-steps-section">
        <div class="label ns-label">▶ 次のステップ</div>
        {blocks}
      </div>
"""


def build_advice_section(advice) -> str:
    """編集アドバイスセクションのHTML（editorial_adviceがない場合は空文字）"""
    if not advice:
        return ""
    if isinstance(advice, str):
        text = advice.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        return f"""
      <!-- 編集アドバイス -->
      <div class="section advice-section">
        <div class="label advice-label">📋 編集アドバイス（あるとよい情報・写真）</div>
        <pre class="advice-body">{text}</pre>
      </div>
"""
    elif isinstance(advice, dict):
        info_items  = advice.get("info_needed", [])
        photo_items = advice.get("photos_needed", [])
        info_html   = "".join(f"<li>{item.replace('&','&amp;').replace('<','&lt;').replace('>','&gt;')}</li>" for item in info_items)
        photo_html  = "".join(f"<li>{item.replace('&','&amp;').replace('<','&lt;').replace('>','&gt;')}</li>" for item in photo_items)
        info_block  = f"<div class='advice-category'>◆ 追加情報があると記事が充実します</div><ul class='advice-list'>{info_html}</ul>" if info_items else ""
        photo_block = f"<div class='advice-category'>◆ 欲しい写真</div><ul class='advice-list'>{photo_html}</ul>" if photo_items else ""
        return f"""
      <!-- 編集アドバイス -->
      <div class="section advice-section">
        <div class="label advice-label">📋 編集アドバイス（あるとよい情報・写真）</div>
        <div class="advice-body">{info_block}{photo_block}</div>
      </div>
"""
    return ""


def build_html(article: dict, has_comment: bool, mail=None, gdocs_url="", received_comment="", article_id=None, advice=None, next_steps=None, include_auto_reload: bool = True) -> str:
    # 静的記事HTML（articles/YYYYMMDD.html）にはポーリングスクリプトを含めない
    # article_preview.html（ライブプレビュー）のみ auto-reload を有効にする
    if include_auto_reload:
        auto_reload_script = (
            "<!-- 変更検知：バージョンファイルをポーリングして変更時だけリロード -->\n"
            "  <script>\n"
            "    let currentVersion = null;\n"
            "    async function checkVersion() {\n"
            "      try {\n"
            "        const r = await fetch('/article_preview_version.json?_=' + Date.now());\n"
            "        const data = await r.json();\n"
            "        if (currentVersion === null) {\n"
            "          currentVersion = data.version;\n"
            "        } else if (currentVersion !== data.version) {\n"
            "          location.href = location.pathname + '?t=' + Date.now();\n"
            "        }\n"
            "      } catch(e) {}\n"
            "    }\n"
            "    setInterval(checkVersion, 1000);\n"
            "  </script>"
        )
    else:
        auto_reload_script = "<!-- auto-reload disabled: static article snapshot -->"

    title        = article.get("title", "（タイトルなし）")
    caption      = article.get("caption", "")
    top_url      = article.get("top_photo_url", "")
    body         = article.get("body", "")
    link_text    = article.get("link_image_text", "")
    link_url     = article.get("link_image_url", "")
    photos       = article.get("photos", [])
    address      = article.get("address", "")
    rel_links    = article.get("related_links", [])
    generated_at = article.get("generated_at", datetime.now().strftime("%Y%m%d"))
    status       = "✅ 完成" if has_comment else "📝 下書き（コメント待ち）"
    status_class = "status-done" if has_comment else "status-draft"

    # 本文：\n を <br> + 段落に変換
    body_html = ""
    for para in body.split("\n\n"):
        para = para.strip()
        if para:
            body_html += f'<p>{para.replace(chr(10), "<br>")}</p>\n'

    # トップ写真
    top_img_html = ""
    if top_url:
        top_img_html = f'<img src="{top_url}" class="top-img" alt="トップ写真" referrerpolicy="no-referrer">'

    # リンク画像
    link_img_html = ""
    if link_url:
        link_img_html = f'<img src="{link_url}" class="sub-img" alt="リンク画像" referrerpolicy="no-referrer">'

    # サブ写真 (1)〜(最大10)
    sub_photos_html = ""
    num_slots = max(5, len(photos))
    for i in range(num_slots):
        num = f"（{i + 1}）"
        if i < len(photos):
            cap = photos[i].get("caption", "")
            url = photos[i].get("url", "")
            sub_photos_html += f"""
            <div class="photo-row">
              <span class="photo-num">{num}</span>
              <div class="photo-content">
                {"<img src='" + url + "' class='sub-img' alt='" + num + "' referrerpolicy='no-referrer'>" if url else "<span class='no-photo'>（写真なし）</span>"}
                <p class="photo-caption">{cap if cap else "（キャプションなし）"}</p>
              </div>
            </div>"""
        else:
            sub_photos_html += f"""
            <div class="photo-row empty">
              <span class="photo-num">{num}</span>
              <div class="photo-content"><span class="no-photo">（空欄）</span></div>
            </div>"""

    # 記事下リンク
    links_html = ""
    for link in rel_links:
        url  = link.get("url", "")
        text = link.get("text", "")
        if url:
            if text:
                links_html += f'<li><span class="link-label">{text}</span><br><a href="{url}" target="_blank">{url}</a></li>'
            else:
                links_html += f'<li><a href="{url}" target="_blank">{url}</a></li>'
    if not links_html:
        links_html = "<li class='empty'>（なし）</li>"

    # Google Docs ボタン（URLがある場合のみ）
    docs_btn = ""
    if gdocs_url:
        docs_btn = f'<a class="docs-btn" href="{gdocs_url}" target="_blank">📄 Google Docs を開く</a>'

    # 記事ID表示
    id_badge = f'<span class="article-id">No.{article_id}</span>' if article_id else ""

    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="UTF-8">
  <meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate">
  <meta http-equiv="Pragma" content="no-cache">
  <meta http-equiv="Expires" content="0">
  <title>📰 記事プレビュー｜{title[:20]}</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ font-family: "Hiragino Kaku Gothic ProN", "Meiryo", sans-serif; font-size: 14px;
            background: #f5f5f5; color: #333; }}
    .container {{ max-width: 720px; margin: 0 auto; padding: 16px; }}
    .back-bar {{ padding: 8px 0 4px; display: flex; align-items: center; gap: 12px; }}
    .back-bar a.back-link {{ font-size: 12px; color: #0066cc; text-decoration: none; }}
    .back-bar a.back-link:hover {{ text-decoration: underline; }}
    .docs-btn {{ font-size: 12px; background: #1a73e8; color: #fff !important; padding: 4px 12px;
                 border-radius: 4px; text-decoration: none !important; margin-left: auto; white-space: nowrap; }}
    .docs-btn:hover {{ background: #1557b0; }}
    .header {{ background: #1a1a2e; color: #fff; padding: 12px 16px; border-radius: 6px 6px 0 0;
               display: flex; justify-content: space-between; align-items: center; }}
    .header h1 {{ font-size: 13px; opacity: 0.8; }}
    .status {{ font-size: 12px; padding: 3px 8px; border-radius: 3px; font-weight: bold; }}
    .status-done  {{ background: #43a047; color: #fff; }}
    .status-draft {{ background: #e65100; color: #fff; }}
    .card {{ background: #fff; border-radius: 0 0 6px 6px; padding: 20px; box-shadow: 0 2px 8px rgba(0,0,0,.08); }}
    .section {{ margin-bottom: 20px; padding-bottom: 20px; border-bottom: 1px solid #eee; }}
    .section:last-child {{ border-bottom: none; margin-bottom: 0; }}
    .label {{ font-size: 11px; font-weight: bold; color: #888; text-transform: uppercase;
              letter-spacing: .05em; margin-bottom: 6px; }}
    .title-text {{ font-size: 18px; font-weight: bold; line-height: 1.5; color: #111; }}
    .char-count {{ font-size: 11px; color: #aaa; margin-top: 4px; }}
    .top-img {{ width: 100%; max-height: 320px; object-fit: cover; border-radius: 4px;
                display: block; margin-bottom: 8px; }}
    .caption {{ font-size: 13px; color: #555; line-height: 1.6; }}
    .body-text p {{ font-size: 14px; line-height: 1.85; margin-bottom: 12px; text-indent: 1em; }}
    .photo-row {{ display: flex; gap: 12px; margin-bottom: 12px; align-items: flex-start; }}
    .photo-row.empty {{ opacity: .4; }}
    .photo-num {{ font-size: 13px; font-weight: bold; color: #666; min-width: 32px; padding-top: 4px; }}
    .photo-content {{ flex: 1; }}
    .sub-img {{ width: 100%; max-height: 200px; object-fit: cover; border-radius: 4px;
                display: block; margin-bottom: 6px; }}
    .photo-caption {{ font-size: 12px; color: #666; line-height: 1.5; }}
    .link-img-block {{ display: flex; gap: 12px; align-items: flex-start; }}
    .link-img-label {{ font-size: 12px; font-weight: bold; color: #e04; min-width: 80px; padding-top: 4px; }}
    .link-img-content {{ flex: 1; }}
    .link-text {{ font-size: 13px; font-weight: bold; color: #e04; margin-bottom: 6px; }}
    .no-photo {{ font-size: 12px; color: #bbb; font-style: italic; }}
    .address {{ font-size: 13px; color: #555; }}
    .links-list {{ list-style: none; }}
    .links-list li {{ font-size: 13px; margin-bottom: 4px; }}
    .links-list a {{ color: #0066cc; text-decoration: none; }}
    .links-list a:hover {{ text-decoration: underline; }}
    .links-list .empty {{ color: #bbb; font-style: italic; }}
    .link-label {{ font-size: 13px; color: #333; font-weight: bold; }}
    .mail-section {{ background: #fff8e1; border-left: 4px solid #e65100; border-radius: 0 4px 4px 0; padding: 14px 16px; }}
    .mail-label {{ color: #e65100 !important; }}
    .mail-body {{ font-size: 13px; line-height: 1.8; white-space: pre-wrap; color: #444; margin: 0; }}
    .received-comment-section {{ background: #e8f5e9; border-left: 4px solid #2e7d32; border-radius: 0 4px 4px 0; padding: 14px 16px; }}
    .received-comment-label {{ color: #2e7d32 !important; }}
    .received-comment-body {{ font-size: 13px; line-height: 1.8; white-space: pre-wrap; color: #444; margin: 0; }}
    .advice-section {{ background: #f3e5f5; border-left: 4px solid #7b1fa2; border-radius: 0 4px 4px 0; padding: 14px 16px; }}
    .advice-label {{ color: #7b1fa2 !important; }}
    .advice-body {{ font-size: 13px; line-height: 1.8; color: #444; margin: 0; }}
    .advice-body pre {{ white-space: pre-wrap; }}
    .advice-category {{ font-weight: bold; color: #7b1fa2; margin: 10px 0 4px; font-size: 13px; }}
    .advice-category:first-child {{ margin-top: 0; }}
    .advice-list {{ list-style: disc; padding-left: 20px; margin: 0; }}
    .advice-list li {{ font-size: 13px; line-height: 1.7; margin-bottom: 3px; color: #444; }}
    .article-id {{ font-size: 11px; font-weight: bold; background: #555; color: #fff; padding: 2px 7px; border-radius: 3px; letter-spacing: .05em; }}
    .next-steps-section {{ background: #e3f2fd; border-left: 4px solid #1565c0; border-radius: 0 4px 4px 0; padding: 14px 16px; }}
    .ns-label {{ color: #1565c0 !important; font-size: 13px !important; }}
    .ns-block {{ margin-bottom: 14px; padding: 10px 14px; background: #fff; border-radius: 4px; }}
    .ns-block:last-child {{ margin-bottom: 0; }}
    .ns-block-title {{ font-size: 13px; font-weight: bold; color: #333; margin-bottom: 6px; }}
    .ns-target {{ font-size: 13px; color: #555; margin-bottom: 4px; }}
    .ns-q-heading {{ font-size: 12px; color: #888; margin-bottom: 2px; }}
    .ns-questions {{ padding-left: 20px; margin: 0; }}
    .ns-questions li {{ font-size: 13px; line-height: 1.7; margin-bottom: 3px; color: #444; }}
    .ns-list {{ list-style: disc; padding-left: 20px; margin: 0; }}
    .ns-list li {{ font-size: 13px; line-height: 1.7; margin-bottom: 3px; color: #444; }}
    .ns-missing {{ background: #fff3e0; border-left: 3px solid #e65100; }}
    .ns-missing .ns-block-title {{ color: #bf360c; }}
    .ns-comment {{ background: #f1f8e9; border-left: 3px solid #2e7d32; }}
    .ns-photo {{ background: #fce4ec; border-left: 3px solid #c62828; }}
  </style>
</head>
<body>
  <div class="container">
    <div class="back-bar">
      <a class="back-link" href="/article_index.html">← 記事インデックスへ戻る</a>
      {id_badge}
      {docs_btn}
    </div>
    <div class="header">
      <h1>📰 文京経済新聞｜記事プレビュー｜{generated_at}</h1>
      <span class="status {status_class}">{status}</span>
    </div>
    <div class="card">

      <!-- タイトル -->
      <div class="section">
        <div class="label">■ タイトル</div>
        <div class="title-text">{title}</div>
        <div class="char-count">{len(title)}字</div>
      </div>

      <!-- トップ写真 + キャプション -->
      <div class="section">
        <div class="label">■ 写真キャプション（トップ写真）</div>
        {top_img_html if top_img_html else '<span class="no-photo">（写真なし）</span>'}
        <div class="caption">{caption}</div>
      </div>

      <!-- 本文 -->
      <div class="section">
        <div class="label">■ 本文</div>
        <div class="body-text">{body_html}</div>
      </div>

      <!-- フォトフラッシュ -->
      <div class="section">
        <div class="label">■ フォトフラッシュ</div>

        <!-- リンク画像 -->
        <div class="link-img-block" style="margin-bottom:16px;">
          <div class="link-img-label">（リンク画像）</div>
          <div class="link-img-content">
            <div class="link-text">{link_text if link_text else "（テキストなし）"}</div>
            {link_img_html if link_img_html else '<span class="no-photo">（写真なし）</span>'}
          </div>
        </div>

        <!-- サブ写真 (1)〜(5) -->
        {sub_photos_html}
      </div>

      <!-- 記事下リンク -->
      <div class="section">
        <div class="label">■ 記事下リンク</div>
        <ul class="links-list">{links_html}</ul>
      </div>

      <!-- 住所 -->
      <div class="section">
        <div class="label">■ 住所（管理画面入力用）</div>
        <div class="address">{address if address else "（未設定）"}</div>
      </div>

{build_next_steps_section(next_steps)}
{build_advice_section(advice)}
{build_received_comment_section(received_comment)}
{build_mail_section(mail)}
    </div>
  </div>

  {auto_reload_script}
</body>
</html>"""


# ── メイン ─────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="記事プレビューHTMLを生成する")
    parser.add_argument("--json",              required=True, help="article_preview.json のパス")
    parser.add_argument("--open",              action="store_true", help="生成後にブラウザで開く")
    parser.add_argument("--out",               default=OUTPUT_HTML, help="出力HTMLのパス")
    parser.add_argument("--save-article",      metavar="YYYYMMDD",
                        help="記事固有HTMLとして articles/YYYYMMDD.html にも保存する（承認後に実行）")
    parser.add_argument("--article-only",      action="store_true",
                        help="articles/YYYYMMDD.html のみ保存し article_preview.html は更新しない（過去記事の再生成用）")
    args = parser.parse_args()

    # --article-only 時は article_preview.html を上書きしないよう出力先を一時ファイルに変更
    if args.article_only:
        args.out = "/tmp/article_regen_temp.html"

    with open(args.json, encoding="utf-8") as f:
        data = json.load(f)

    article           = data.get("article", data)
    has_comment       = data.get("has_comment", False)
    gdocs_url         = data.get("gdocs_url", "")
    received_comment  = data.get("received_comment", "")
    article_id        = data.get("id", None)
    advice            = data.get("editorial_advice", None)
    next_steps        = data.get("next_steps", None)

    # article_id がない場合、同フォルダの claim_id.txt から補完する
    # （claim_article.py で登録した執筆中エントリのIDを引き継ぐ）
    if article_id is None:
        claim_file = os.path.join(os.path.dirname(os.path.abspath(args.json)), "claim_id.txt")
        if os.path.exists(claim_file):
            with open(claim_file) as cf:
                article_id = cf.read().strip()
            print(f"📋 claim_id.txt から article_id={article_id} を取得しました")

    # mail.json を読み込む（article_preview.json と同じディレクトリを探す）
    # ※ has_comment: true の記事ではメール依頼は不要なので読み込まない
    mail_data = None
    if not has_comment:
        mail_path = os.path.join(os.path.dirname(os.path.abspath(args.json)), "mail.json")
        if os.path.exists(mail_path):
            with open(mail_path, encoding="utf-8") as f:
                mail_data = json.load(f)

    # HTML生成
    html = build_html(article, has_comment, mail=mail_data, gdocs_url=gdocs_url, received_comment=received_comment, article_id=article_id, advice=advice, next_steps=next_steps)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"✅ プレビューHTMLを生成しました: {args.out}")

    # 記事固有HTMLとして articles/ に保存（承認後に --save-article で実行）
    if args.save_article:
        articles_dir = os.path.join(PROJECT_DIR, "articles")
        os.makedirs(articles_dir, exist_ok=True)
        named_path = os.path.join(articles_dir, f"{args.save_article}.html")
        # 静的スナップショットにはポーリングスクリプトを含めない
        # （article_preview_version.json の更新で過去記事が誤ってリロードされるのを防ぐ）
        static_html = build_html(article, has_comment, mail=mail_data, gdocs_url=gdocs_url, received_comment=received_comment, article_id=article_id, advice=advice, next_steps=next_steps, include_auto_reload=False)
        with open(named_path, "w", encoding="utf-8") as f:
            f.write(static_html)
        print(f"📁 記事HTMLを保存しました: {named_path}")

        # JSON も articles/ に保存（過去記事の修正時に再構築不要にする）
        json_named_path = os.path.join(articles_dir, f"{args.save_article}.json")
        with open(json_named_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"📋 記事JSONを保存しました: {json_named_path}")

        # article_index.json を自動更新（html_file / json_file / gdocs_url / title）
        # ※ これにより「インデックスにリンクが表示されない」問題を構造的に防止する
        update_article_index(
            article_id=article_id,
            title=article.get("title", ""),
            gdocs_url=gdocs_url,
            html_file=f"articles/{args.save_article}.html",
            json_file=f"articles/{args.save_article}.json",
            date_fallback=article.get("generated_at", args.save_article),
        )

    # バージョンファイル更新（変更検知トリガー）
    write_version()

    # サーバー起動 or ファイル同期
    ensure_server()

    if args.open:
        open_url = PREVIEW_URL + f"?t={int(time.time())}"
        webbrowser.open(open_url)
        print(f"🌐 ブラウザで開きました: {PREVIEW_URL}")


if __name__ == "__main__":
    main()
