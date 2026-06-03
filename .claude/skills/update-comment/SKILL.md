---
name: update-comment
description: 取材先からのコメントを記事本文に組み込む。「コメントが届いた」「コメントを組み込んで」「コメントが来た」等で自動起動。
allowed-tools: Read, Write, Edit, Bash, Glob, Grep
---

# コメント組み込みフロー

取材先からコメントが届いたとき、以下のフローで記事を更新する。

## 手順

1. **該当記事を特定する**
   - Sheets（正規データ）で該当記事の `id` と `json_file` パスを確認
   - 作業フォルダを作成：`mkdir -p /tmp/bunkyo_YYYYMMDD`
   - 既存JSONをコピー：`cp articles/{id}.json /tmp/bunkyo_YYYYMMDD/article.json`（{id}は記事のユニークID）
   - claim_id.txt にIDを保存：`echo {id} > /tmp/bunkyo_YYYYMMDD/claim_id.txt`
     （--save-article がこのIDからファイル名を解決するため）

2. **コメントを組み込む**
   - ユーザーが貼り付けたコメント素材を確認
   - 本文の「【担当者様コメント（取得待ち）】」部分をコメントに差し替え
   - `has_comment: true` に更新
   - コメントは原文の「ですます」調を「である」調に変換する
   - **コメント語順ルール**：必ず「主語＋は」を先に、コメントを後に
     - ✅ 白井会長は「○○したい」と話す。
     - ❌ 「○○したい」と白井会長は話す。

3. **mail.json を削除する**
   - `/tmp/bunkyo_YYYYMMDD/mail.json` を削除（メール欄がHTMLプレビューから消える）

4. **チェック＆プレビュー**
   ```bash
   python3 article_check.py --json /tmp/bunkyo_YYYYMMDD/article.json
   python3 preview_generator.py --json /tmp/bunkyo_YYYYMMDD/article.json --open
   ```

5. **修正ループ**
   - ユーザーの修正指示があれば修正 → 再チェック → 再プレビュー

6. **ユーザーが「OK」→ Google Docs に【完成】として保存**
   ```bash
   python3 save_to_gdocs.py --json /tmp/bunkyo_YYYYMMDD/article.json
   ```

7. **インデックスを更新**
   - gdocs_url を article.json に追記
   - `python3 preview_generator.py --json ... --save-article`（ファイル名はIDから自動解決）
   - `python3 check_index_link.py --json /tmp/bunkyo_YYYYMMDD/article.json`
   - `python3 index_generator.py`
