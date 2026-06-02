"""
index_generator.py
記事インデックスHTMLを生成してブラウザで表示する

使い方:
  python3 index_generator.py         → HTMLを生成（ブラウザは自動更新）
  python3 index_generator.py --open  → HTMLを生成してブラウザで開く

ブラウザURL: http://localhost:8765/article_index.html
"""

import json
import argparse
import os
import subprocess
import time
import webbrowser
from datetime import datetime

from server_utils import PROJECT_DIR, PREVIEW_PORT, ensure_server
from sheets_index import load_from_sheets, append_article as sheets_append, update_article as sheets_update

INDEX_JSON   = os.path.join(PROJECT_DIR, "article_index.json")
OUTPUT_HTML  = os.path.join(PROJECT_DIR, "article_index.html")
PREVIEW_URL  = f"http://localhost:{PREVIEW_PORT}/article_index.html"


# ── インデックスJSON操作 ──────────────────────────────────────────────────

def load_index():
    """Sheetsから取得してローカルJSONを更新、記事リストを返す"""
    return load_from_sheets()


def append_article(title, gdocs_url, date, status="draft", html_file="", json_file=""):
    """記事をインデックスに追加する（Sheets優先・article_index.jsonは出力キャッシュのみ）"""
    articles = load_index()

    # 同じGDocsURLがあれば更新（Sheetsを直接更新）
    for a in articles:
        if a.get("gdocs_url") == gdocs_url:
            a["title"]     = title
            a["date"]      = date
            a["status"]    = status
            a["html_file"] = html_file
            a["json_file"] = json_file
            a["saved_at"]  = datetime.now().strftime("%Y-%m-%d")
            sheets_update(a["id"], {
                "title": title, "date": date, "status": status,
                "html_file": html_file, "json_file": json_file,
                "saved_at": a["saved_at"],
            })
            break
    else:
        # 新規追加：IDはsheets_appendが行番号から採番する（複数セッション競合防止）
        writer = os.environ.get("WRITER_NAME", "")
        new_article = {
            "date":      date,
            "title":     title,
            "gdocs_url": gdocs_url,
            "status":    status,
            "saved_at":  datetime.now().strftime("%Y-%m-%d"),
            "html_file": html_file,
            "json_file": json_file,
            "writer":    writer,
            # id は sheets_append が返す値を使う
        }
        new_id = sheets_append(new_article)
        if new_id:
            new_article["id"] = new_id
            articles.append(new_article)

    # article_index.json は出力専用キャッシュとして更新（インプットには使わない）
    with open(INDEX_JSON, "w", encoding="utf-8") as f:
        json.dump(articles, f, ensure_ascii=False, indent=2)
    return articles


def update_status(gdocs_url, status):
    """記事のステータスを更新する（Sheets + ローカルJSON）"""
    articles = load_index()
    for a in articles:
        if a.get("gdocs_url") == gdocs_url:
            a["status"] = status
            sheets_update(a["id"], {"status": status})
            break
    with open(INDEX_JSON, "w", encoding="utf-8") as f:
        json.dump(articles, f, ensure_ascii=False, indent=2)


# ── HTML生成 ───────────────────────────────────────────────────────────────

STATUS_BADGES = {
    # ── 対応中 ──
    "writing":               ("✏️ 執筆中",   "badge-writing"),    # 制作中・コメント/写真待ち
    "review":                ("👀 確認中",   "badge-review"),     # ドラフト完成・取材先確認中
    "completed":             ("📨 申請中",   "badge-completed"),  # 完了フォルダ移動済み・本部確認中
    # ── 完了（月別タブ） ──
    "done":                  ("🌐 公開済み", "badge-done"),       # 記事公開済み
    "hold":                  ("⏸️ 保留",    "badge-hold"),       # 現時点では記事化しない
    "closed":                ("🗑️ ボツ",    "badge-closed"),     # 記事化ならず
    # ── 旧ステータス（後方互換） ──
    "draft":                 ("✏️ 執筆中",   "badge-writing"),
    "interview":             ("✏️ 執筆中",   "badge-writing"),
    "photo_pending":         ("✏️ 執筆中",   "badge-writing"),
    "comment_photo_pending": ("✏️ 執筆中",   "badge-writing"),
    "published":             ("🌐 公開済み", "badge-done"),
}


def build_rows(articles):
    if not articles:
        return "<tr><td colspan='5' class='empty-row'>記事がまだありません</td></tr>"
    rows = ""
    # 作成日（saved_at）降順 → 同日はdate降順（作った順に上から表示）
    sorted_articles = sorted(articles,
                             key=lambda x: (x.get("saved_at", ""), x.get("date", "")),
                             reverse=True)
    for row_num, a in enumerate(sorted_articles, 1):
        date_raw   = a.get("saved_at", a.get("date", ""))
        # saved_at は YYYY-MM-DD 形式
        date_fmt   = date_raw if "-" in date_raw else (
            f"{date_raw[:4]}/{date_raw[4:6]}/{date_raw[6:]}" if len(date_raw) >= 8 else date_raw
        )
        title      = a.get("title", "（タイトルなし）")
        gdocs_url  = a.get("gdocs_url", "")
        html_file  = a.get("html_file", "")
        status     = a.get("status", "draft")
        article_id = a.get("id", "?")   # JSONに保存された永久固定idを使う

        badge_label, badge_class = STATUS_BADGES.get(status, ("📝 下書き", "badge-draft"))
        writer     = a.get("writer", "")

        # タイトルリンク → HTMLがあればHTML、なければGDocsへ、それもなければテキストのみ
        if html_file:
            title_html = f'<a class="title-link" href="/{html_file}">{title}</a>'
        elif gdocs_url:
            title_html = f'<a class="title-link gdocs-link" href="{gdocs_url}" target="_blank">{title}</a>'
        else:
            title_html = f'<span class="title-nolink">{title}</span>'

        # Google Docs ボタン（URLがある場合のみ）
        docs_btn = ""
        if gdocs_url:
            docs_btn = f'<a class="docs-btn" href="{gdocs_url}" target="_blank">📄 Google Docs</a>'

        # 公開済み記事は公開URLへのリンクも表示
        published_url = a.get("published_url", "")
        if status == "published" and published_url:
            docs_btn = f'<a class="docs-btn published-btn" href="{published_url}" target="_blank">🌐 公開記事</a>'

        id_cell     = f'<span class="article-id-cell">No.{article_id}</span>'
        writer_cell = f'<span class="writer-cell">{writer}</span>' if writer else ""

        # ステータスバッジ：クリックでドロップダウンを開く
        badge_html = (
            f'<span class="badge {badge_class} badge-clickable" '
            f'onclick="openStatusMenu(event, {article_id}, \'{status}\')" '
            f'title="クリックでステータス変更">{badge_label} ▾</span>'
        )

        rows += f"""          <tr class="row-{status}" id="row-{article_id}">
            <td class="id-cell">{id_cell}</td>
            <td class="date-cell">{date_fmt}</td>
            <td class="title-cell">{title_html}</td>
            <td class="writer-col">{writer_cell}</td>
            <td>{badge_html}</td>
            <td class="action-cell">{docs_btn}</td>
          </tr>
"""
    return rows


def _month_key(saved_at):
    """saved_at（YYYY-MM-DD）から月キー文字列を返す（例: '2026-04-23' → '2026年04月'）"""
    digits = "".join(c for c in str(saved_at) if c.isdigit())
    if len(digits) >= 6:
        return f"{digits[:4]}年{digits[4:6]}月"
    return "不明"


def _month_sort_key(month_str):
    """'2026年04月' → '202604'（降順ソート用）"""
    digits = "".join(c for c in month_str if c.isdigit())
    return digits if digits else "0"


TABLE_HEADER = """\
          <table>
            <thead>
              <tr>
                <th style="width:56px;text-align:center;">No.</th>
                <th style="width:100px;">日付</th>
                <th>タイトル（クリックでHTMLプレビューを開く）</th>
                <th style="width:72px;text-align:center;">担当</th>
                <th style="width:160px;">ステータス</th>
                <th style="width:130px;"></th>
              </tr>
            </thead>
            <tbody>
"""


def build_html(articles):
    import re
    from collections import defaultdict

    count     = len(articles)
    generated = datetime.now().strftime("%Y/%m/%d %H:%M")

    # ── 対応中（固定表示）と月別アーカイブに分離 ──
    # 月別タブ（カレンダー）に表示するのは done のみ。公開前は表示しない。
    # 対応中：公開前のすべての作業中ステータス
    ACTIVE_STATUSES = {"writing", "review", "completed",
                       "draft", "interview", "photo_pending", "comment_photo_pending"}
    # 完了（月別タブ）：公開済み・保留・ボツ
    ARCHIVE_STATUSES = {"done", "hold", "closed", "published"}
    active   = [a for a in articles if a.get("status") in ACTIVE_STATUSES]
    archived = [a for a in articles if a.get("status") in ARCHIVE_STATUSES]

    # 月別グループ（archived のみ）
    month_groups: dict = defaultdict(list)
    for a in archived:
        month_groups[_month_key(a.get("saved_at", ""))].append(a)

    sorted_months = sorted(month_groups.keys(), key=_month_sort_key, reverse=True)
    first_month_id = re.sub(r"\D", "", sorted_months[0]) if sorted_months else ""

    # ── 対応中セクション HTML ──
    active_section = ""
    if active:
        active_rows = build_rows(active)
        active_section = f"""\
    <div class="active-section">
      <div class="active-header">📋 対応中の記事（{len(active)}件）</div>
      {TABLE_HEADER}{active_rows}            </tbody>
          </table>
    </div>
"""

    # ── 月タブボタン HTML ──
    tab_buttons = ""
    for month in sorted_months:
        mid = re.sub(r"\D", "", month)
        cnt = len(month_groups[month])
        active_class = "tab-active" if mid == first_month_id else ""
        tab_buttons += f'<button class="tab-btn {active_class}" onclick="switchTab(\'{mid}\')" id="tab-{mid}">{month}（{cnt}件）</button>\n        '

    # ── 月別セクション HTML ──
    month_sections = ""
    for month in sorted_months:
        mid = re.sub(r"\D", "", month)
        display = "block" if mid == first_month_id else "none"
        rows = build_rows(month_groups[month])
        month_sections += f"""\
      <div class="month-section" id="section-{mid}" style="display:{display}">
        {TABLE_HEADER}{rows}            </tbody>
          </table>
      </div>
"""

    archived_block = ""
    if sorted_months:
        archived_block = f"""\
    <div class="card" style="margin-top:12px;">
      <div class="tab-bar">
        {tab_buttons}
      </div>
      {month_sections}
    </div>
"""

    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="UTF-8">
  <meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate">
  <meta http-equiv="Pragma" content="no-cache">
  <meta http-equiv="Expires" content="0">
  <title>📰 文京経済新聞｜記事インデックス</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ font-family: "Hiragino Kaku Gothic ProN", "Meiryo", sans-serif; font-size: 14px;
            background: #f5f5f5; color: #333; }}
    .container {{ max-width: 820px; margin: 0 auto; padding: 16px; }}
    .header {{ background: #1a1a2e; color: #fff; padding: 12px 16px; border-radius: 6px 6px 0 0;
               display: flex; justify-content: space-between; align-items: center; }}
    .header h1 {{ font-size: 14px; }}
    .header .meta {{ font-size: 11px; opacity: 0.7; }}
    .reload-btn {{ font-size: 12px; background: rgba(255,255,255,.15); color: #fff; padding: 4px 10px;
                   border-radius: 4px; text-decoration: none; border: none; cursor: pointer; }}
    .reload-btn:hover {{ background: rgba(255,255,255,.25); }}
    /* 対応中セクション */
    .active-section {{ background: #fff; border-radius: 0 0 6px 6px;
                       box-shadow: 0 2px 8px rgba(0,0,0,.08); overflow: hidden; }}
    .active-header {{ background: #fff3e0; border-left: 4px solid #e65100;
                      padding: 10px 16px; font-size: 13px; color: #bf360c; font-weight: bold; }}
    /* 月タブエリア */
    .card {{ background: #fff; border-radius: 6px;
             box-shadow: 0 2px 8px rgba(0,0,0,.08); overflow: hidden; }}
    .tab-bar {{ display: flex; flex-wrap: wrap; gap: 6px; padding: 12px 14px;
                background: #f0f0f5; border-bottom: 1px solid #ddd; }}
    .tab-btn {{ font-size: 12px; padding: 5px 12px; border-radius: 16px; border: 1px solid #ccc;
                background: #fff; color: #555; cursor: pointer; white-space: nowrap; }}
    .tab-btn:hover {{ background: #e8e8f0; }}
    .tab-btn.tab-active {{ background: #1a1a2e; color: #fff; border-color: #1a1a2e; font-weight: bold; }}
    /* テーブル共通 */
    table {{ width: 100%; border-collapse: collapse; }}
    th {{ background: #f0f0f5; font-size: 11px; color: #666; padding: 10px 14px;
          text-align: left; border-bottom: 2px solid #ddd; font-weight: bold; }}
    td {{ padding: 12px 14px; border-bottom: 1px solid #eee; vertical-align: middle; }}
    tr:last-child td {{ border-bottom: none; }}
    tr.row-done td {{ background: #f1f8e9; }}
    tr.row-done:hover td {{ background: #e6f4d7; }}
    tr.row-published td {{ background: #e8f5e9; }}
    tr.row-published:hover td {{ background: #d4edda; }}
    tr.row-closed td {{ background: #f5f5f5; color: #9e9e9e; }}
    tr.row-closed:hover td {{ background: #eeeeee; }}
    tr.row-completed td {{ background: #e8f5e9; }}
    tr.row-completed:hover td {{ background: #d4edda; }}
    tr.row-review td {{ background: #fff8e1; }}
    tr.row-review:hover td {{ background: #fff0c0; }}
    tr.row-interview td {{ background: #e3f2fd; }}
    tr.row-interview:hover td {{ background: #d0e8f9; }}
    tr.row-draft td {{ background: #fffde7; }}
    tr.row-draft:hover td {{ background: #fff9c4; }}
    tr.row-photo_pending td {{ background: #fffde7; }}
    tr.row-photo_pending:hover td {{ background: #fff9c4; }}
    tr.row-comment_photo_pending td {{ background: #fffde7; }}
    tr.row-comment_photo_pending:hover td {{ background: #fff9c4; }}
    .id-cell {{ width: 56px; text-align: center; }}
    .article-id-cell {{ font-size: 11px; color: #888; font-weight: bold; }}
    .date-cell {{ font-size: 12px; color: #888; white-space: nowrap; width: 100px; }}
    .title-cell {{ line-height: 1.5; }}
    .title-link {{ color: #0066cc; text-decoration: none; font-size: 14px; }}
    .title-link:hover {{ text-decoration: underline; }}
    .title-nolink {{ font-size: 14px; color: #555; }}
    .action-cell {{ width: 130px; text-align: right; white-space: nowrap; }}
    .badge {{ font-size: 11px; padding: 3px 8px; border-radius: 10px; white-space: nowrap; }}
    .badge-done      {{ background: #c8e6c9; color: #1b5e20; font-weight: bold; }}
    .badge-published {{ background: #c8e6c9; color: #1b5e20; font-weight: bold; }}
    .badge-closed    {{ background: #eeeeee; color: #757575; }}
    .badge-hold      {{ background: #fff3e0; color: #e65100; }}
    .badge-completed {{ background: #e3f2fd; color: #1565c0; font-weight: bold; }}
    .badge-review    {{ background: #fff8e1; color: #f57f17; font-weight: bold; }}
    .badge-interview {{ background: #e3f2fd; color: #1565c0; font-weight: bold; }}
    .badge-draft     {{ background: #fffde7; color: #827717; }}
    .badge-writing   {{ background: #e8f4fd; color: #0066cc; border: 1px solid #99ccee; font-weight: bold; }}
    .row-writing     {{ background: #f5faff; }}
    .published-btn   {{ background: #388e3c; color: #fff; border: none; }}
    .writer-col      {{ text-align: center; white-space: nowrap; }}
    .writer-cell     {{ font-size: 11px; color: #555; background: #f0f0f0; border-radius: 8px;
                        padding: 2px 7px; display: inline-block; }}
    .docs-btn {{ font-size: 11px; background: #1a73e8; color: #fff; padding: 3px 10px;
                 border-radius: 4px; text-decoration: none; }}
    .docs-btn:hover {{ background: #1557b0; }}
    .empty-row {{ text-align: center; color: #aaa; padding: 32px; font-style: italic; }}
    /* ── ステータス変更ドロップダウン ── */
    .badge-clickable {{ cursor: pointer; user-select: none; transition: opacity .15s; }}
    .badge-clickable:hover {{ opacity: .75; }}
    #status-menu {{
      display: none; position: fixed; z-index: 9999;
      background: #fff; border: 1px solid #ccc; border-radius: 8px;
      box-shadow: 0 4px 16px rgba(0,0,0,.18); padding: 6px 0; min-width: 150px;
    }}
    #status-menu .menu-item {{
      display: flex; align-items: center; gap: 8px;
      padding: 8px 16px; cursor: pointer; font-size: 13px;
      transition: background .1s;
    }}
    #status-menu .menu-item:hover {{ background: #f0f4ff; }}
    #status-menu .menu-item.current {{ font-weight: bold; background: #e8f0fe; }}
    #status-menu .menu-sep {{
      border: none; border-top: 1px solid #eee; margin: 4px 0;
    }}
    #status-toast {{
      display: none; position: fixed; bottom: 28px; left: 50%; transform: translateX(-50%);
      background: #323232; color: #fff; padding: 10px 22px; border-radius: 6px;
      font-size: 13px; z-index: 10000; pointer-events: none;
    }}
  </style>
</head>
<body>
  <div class="container">
    <div class="header">
      <h1>📰 文京経済新聞｜記事インデックス（{count}件）</h1>
      <div style="display:flex;align-items:center;gap:10px;">
        <span class="meta">更新：{generated}</span>
        <button class="reload-btn" onclick="location.href=location.pathname+'?t='+Date.now()">🔄 更新</button>
      </div>
    </div>
    {active_section}
    {archived_block}
  </div>
  <!-- ステータス変更ドロップダウン -->
  <div id="status-menu"></div>
  <div id="status-toast"></div>

  <script>
    function switchTab(monthId) {{
      document.querySelectorAll('.month-section').forEach(s => s.style.display = 'none');
      document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('tab-active'));
      document.getElementById('section-' + monthId).style.display = 'block';
      document.getElementById('tab-' + monthId).classList.add('tab-active');
    }}

    /* ── ステータス変更メニュー ── */
    const STATUS_OPTIONS = [
      {{ value: 'writing',   label: '✏️ 執筆中',   group: 'active' }},
      {{ value: 'review',    label: '👀 確認中',   group: 'active' }},
      {{ value: 'completed', label: '📨 申請中',   group: 'active' }},
      {{ value: 'done',      label: '🌐 公開済み', group: 'archive' }},
      {{ value: 'hold',      label: '⏸️ 保留',    group: 'archive' }},
      {{ value: 'closed',    label: '🗑️ ボツ',    group: 'archive' }},
    ];

    function openStatusMenu(event, articleId, currentStatus) {{
      event.stopPropagation();
      const menu = document.getElementById('status-menu');
      let html = '';
      let lastGroup = null;
      STATUS_OPTIONS.forEach(opt => {{
        if (lastGroup && opt.group !== lastGroup) html += '<hr class="menu-sep">';
        lastGroup = opt.group;
        const cur = opt.value === currentStatus;
        html += `<div class="menu-item${{cur ? ' current' : ''}}"
          onclick="applyStatus(${{articleId}}, '${{opt.value}}')"
        >${{opt.label}}${{cur ? ' ✓' : ''}}</div>`;
      }});
      menu.innerHTML = html;

      const rect = event.currentTarget.getBoundingClientRect();
      menu.style.display = 'block';
      const mw = menu.offsetWidth;
      const mh = menu.offsetHeight;
      // 左右：はみ出す場合は右端に寄せる
      let left = rect.left;
      if (left + mw > window.innerWidth - 8) left = window.innerWidth - mw - 8;
      if (left < 8) left = 8;
      menu.style.left = left + 'px';
      // 上下：position:fixed なので scrollY は不要。下にはみ出す場合は上に表示
      const spaceBelow = window.innerHeight - rect.bottom - 4;
      if (spaceBelow >= mh || spaceBelow >= rect.top) {{
        menu.style.top = (rect.bottom + 4) + 'px';
      }} else {{
        menu.style.top = (rect.top - mh - 4) + 'px';
      }}
    }}

    function applyStatus(articleId, newStatus) {{
      document.getElementById('status-menu').style.display = 'none';
      showToast('⏳ 更新中…');
      fetch('/api/update_status', {{
        method: 'POST',
        headers: {{ 'Content-Type': 'application/json' }},
        body: JSON.stringify({{ id: articleId, status: newStatus }}),
      }})
      .then(r => r.json())
      .then(data => {{
        if (data.success) {{
          showToast('✅ ステータスを更新しました');
          setTimeout(() => location.reload(), 900);
        }} else {{
          showToast('❌ 更新失敗: ' + (data.error || '不明なエラー'));
        }}
      }})
      .catch(e => showToast('❌ 通信エラー: ' + e));
    }}

    function showToast(msg) {{
      const t = document.getElementById('status-toast');
      t.textContent = msg;
      t.style.display = 'block';
      clearTimeout(t._timer);
      t._timer = setTimeout(() => {{ t.style.display = 'none'; }}, 3500);
    }}

    document.addEventListener('click', (e) => {{
      const menu = document.getElementById('status-menu');
      if (!menu.contains(e.target)) menu.style.display = 'none';
    }});

    /* ── Sheets自動ポーリング（30秒ごとに更新確認） ── */
    let _knownHash = null;
    let _pollActive = true;

    async function pollSheetsHash() {{
      if (!_pollActive) return;
      try {{
        const r = await fetch('/api/sheets_hash?t=' + Date.now());
        if (!r.ok) return;
        const data = await r.json();
        if (_knownHash === null) {{
          _knownHash = data.hash;   // 初回：現在のハッシュを記憶
        }} else if (_knownHash !== data.hash) {{
          // ハッシュが変わった → 他のユーザーが更新した
          showToast('🔄 他のユーザーが更新しました。再読み込みします…');
          _pollActive = false;
          setTimeout(() => location.reload(), 1500);
        }}
      }} catch (e) {{
        // APIサーバーが起動していない場合は無視
      }}
    }}

    pollSheetsHash();                          // 起動直後に初回実行
    setInterval(pollSheetsHash, 30000);        // 以降30秒ごと
  </script>
</body>
</html>"""


# ── メイン ─────────────────────────────────────────────────────────────────

def assign_missing_ids(articles):
    """idがない記事にSheetsへのappendで採番する（既存idは絶対に変更しない）

    IDはsheets_appendが行番号から採番する。
    これにより複数セッションが同時に実行しても衝突しない。
    """
    no_id = sorted([a for a in articles if "id" not in a or a.get("id") == ""],
                   key=lambda x: (x.get("saved_at", ""), x.get("date", "")))

    if not no_id:
        return articles

    for a in no_id:
        new_id = sheets_append(a)
        if new_id:
            a["id"] = new_id
            print(f"📋 IDなし記事にID={new_id}を採番しました: {a.get('title','')[:30]}")

    # article_index.json は出力専用キャッシュとして更新
    with open(INDEX_JSON, "w", encoding="utf-8") as f:
        json.dump(articles, f, ensure_ascii=False, indent=2)
    return articles


def _auto_git_pull():
    """GitHubから最新コードを自動取得する（失敗しても処理は続行）"""
    try:
        result = subprocess.run(
            ["git", "pull", "--ff-only", "--quiet"],
            cwd=PROJECT_DIR,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.stdout.strip() and "Already up to date" not in result.stdout:
            print(f"🔄 コードを最新版に更新しました")
    except Exception:
        pass  # ネットワーク不通・git未設定でも処理を止めない


def main():
    parser = argparse.ArgumentParser(description="記事インデックスHTMLを生成する")
    parser.add_argument("--open", action="store_true", help="生成後にブラウザで開く")
    parser.add_argument("--no-pull", action="store_true", help="git pullをスキップする")
    args = parser.parse_args()

    # GitHubから最新コードを自動取得（--no-pull で無効化可能）
    if not args.no_pull:
        _auto_git_pull()

    # idがない記事にだけ新しいidを割り当てる（既存idは絶対に変更しない）
    articles = assign_missing_ids(load_index())
    html = build_html(articles)
    with open(OUTPUT_HTML, "w", encoding="utf-8") as f:
        f.write(html)

    draft_cnt = sum(1 for a in articles if a.get("status") not in ("done", "closed"))
    print(f"✅ インデックスHTMLを生成しました（{len(articles)}件・うち対応中{draft_cnt}件）")

    # サーバー起動 or ファイル同期
    ensure_server()

    if args.open:
        open_url = PREVIEW_URL + f"?t={int(time.time())}"
        webbrowser.open(open_url)
        print(f"🌐 ブラウザで開きました: {PREVIEW_URL}")

    # Notion同期（バックグラウンド実行・失敗してもHTML生成には影響しない）
    try:
        notion_sync = os.path.join(PROJECT_DIR, "notion_sync.py")
        if os.path.exists(notion_sync):
            subprocess.Popen(
                ["python3", notion_sync],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            print("📡 Notion同期を開始しました")
    except Exception:
        pass  # Notion同期の失敗はHTML生成に影響させない

    # CONTEXT.md を自動更新
    try:
        update_ctx = os.path.join(PROJECT_DIR, "update_context.py")
        if os.path.exists(update_ctx):
            subprocess.run(
                ["python3", update_ctx],
                cwd=PROJECT_DIR,
                check=False,
            )
    except Exception:
        pass  # CONTEXT.md 更新の失敗はHTML生成に影響させない


if __name__ == "__main__":
    main()
