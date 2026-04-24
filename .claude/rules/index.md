# 記事インデックス管理

- インデックスデータ：`article_index.json`（Dropboxフォルダ内・永続保存）
- インデックスHTML：`http://localhost:8765/article_index.html`（ローカルサーバー経由）
- 記事プレビューの上部に「← 記事インデックスへ戻る」リンクが表示される

## インデックス更新の必須タイミング（省略禁止）

以下のフェーズ変化が起きたら、**必ずその場で** article_index.json を更新して `python3 index_generator.py` を実行する：

| タイミング | 行う操作 |
|-----------|---------|
| **新規記事のプレビュー生成（初回）** | article_index.json にエントリを追加（status: draft）|
| **Google Docs に下書き保存** | gdocs_url・saved_at を更新 |
| **コメント組み込み後に再保存** | status を draft → completed に更新 |
| **本番フォルダへ移動（--move-completed）** | status を completed → done に更新 |
| **GDocs URL が変わった** | gdocs_url を最新のURLに更新 |

> **⚠️ preview_generator.py の --save-article は、article_index.json に既存エントリ（id付き）がないと自動更新されない。新規記事は必ず手動でエントリを追加してから実行すること。**

## ファイル保存ルール

| ファイル | 場所 | タイミング |
|---------|------|----------|
| 記事JSON | `articles/YYYYMMDD.json` | Google Docs保存後 |
| 記事HTML | `articles/YYYYMMDD.html` | Google Docs保存後（--save-article で生成） |
| インデックスJSON | `article_index.json` | フェーズ変化のたびに必ず更新（上表参照）|
| インデックスHTML | `article_index.html` | `python3 index_generator.py` で再生成 |

## article_index.json のエントリー形式

```json
{
  "date": "YYYYMMDD",
  "title": "記事タイトル",
  "gdocs_url": "https://docs.google.com/document/d/...",
  "status": "interview | draft | review | completed | done",
  "saved_at": "YYYY-MM-DD",
  "html_file": "articles/YYYYMMDD.html",
  "json_file": "articles/YYYYMMDD.json"
}
```
※ html_file・json_file を空にするとインデックスのリンクが切れるため注意

## 過去記事のコメントが届いた場合

1. article_index.json で該当記事の `json_file` パスを確認
2. 作業フォルダを作成し、JSONをコピー
   ```bash
   mkdir -p /tmp/bunkyo_YYYYMMDD
   cp articles/YYYYMMDD.json /tmp/bunkyo_YYYYMMDD/article.json
   ```
3. あとは通常の「コメントが届いた場合のフロー」と同じ

## 記事ステータス

| ステータス | 表示ラベル | 意味 |
|-----------|-----------|------|
| `interview` | 取材中 | 取材・情報収集の段階 |
| `writing` | 執筆中 | ライターが執筆を開始した（claim_article.py で登録）|
| `draft` | 下書き | コメント・写真待ち（執筆中） |
| `review` | 確認待ち | 記事一旦完成・関係者に確認中 |
| `completed` | 完成 | 関係者からOK・Google Docs保存済み |
| `done` | 完了 | Google Driveの完成フォルダへ移動済み |
