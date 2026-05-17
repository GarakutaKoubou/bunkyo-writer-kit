# 記事インデックス管理

- **正規データ（Single Source of Truth）：Google Sheets**（SHEETS_INDEX_ID）
- ローカル `article_index.json` はSheetsのキャッシュ。参照・修正の起点にしてはならない
- インデックスHTML：`http://localhost:8765/article_index.html`（ローカルサーバー経由）
- 記事プレビューの上部に「← 記事インデックスへ戻る」リンクが表示される

## ⚠️ インデックスを参照・修正するときの必須手順

**ローカルの `article_index.json` を起点にしてはならない。必ずSheetsを先に確認する。**

```
1. SheetsをMCPツール（mcp__read_file_content fileId=SHEETS_INDEX_ID）で読み込む
2. Sheetsの内容を正規データとして確認・修正する
3. ローカル article_index.json とズレがあれば Sheets 側に合わせる（逆は禁止）
4. python3 index_generator.py で article_index.json と HTML を再生成する
```

## インデックス更新の必須タイミング（省略禁止）

以下のフェーズ変化が起きたら、**必ずその場で** article_index.json を更新して `python3 index_generator.py` を実行する：

| タイミング | 行う操作 |
|-----------|---------|
| **新規記事のプレビュー生成（初回）** | article_index.json にエントリを追加（status: draft）|
| **Google Docs に下書き保存** | gdocs_url・saved_at を更新 |
| **コメント組み込み後に再保存** | status を draft → completed に更新 |
| **本番フォルダへ移動（--move-completed）** | status を completed → done に更新 |
| **GDocs URL が変わった** | gdocs_url を最新のURLに更新 |
| **記事がサイトに公開された（thank-you-email スキル）** | status を done → published に更新・published_url を登録・index_generator.py を実行 |

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
  "status": "interview | draft | review | completed | done | published",
  "saved_at": "YYYY-MM-DD",
  "html_file": "articles/YYYYMMDD.html",
  "json_file": "articles/YYYYMMDD.json",
  "published_url": "https://bunkyo.keizai.biz/headline/NNN/"
}
```
※ `published_url` は公開後に登録。それ以前は省略可。
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

### 対応中（プレビュー上部に表示）
| ステータス | 表示ラベル | 意味 |
|-----------|-----------|------|
| `writing` | ✏️ 執筆中 | 最初に制作した状態。コメント・写真待ちも含む |
| `review` | 👀 確認中 | 記事ドラフト完成・取材先に確認中 |
| `completed` | 📨 申請中 | 完了フォルダに移動済み・本部への確認中 |

### 完了（月別タブに表示）
| ステータス | 表示ラベル | 意味 |
|-----------|-----------|------|
| `done` | 🌐 公開済み | 記事が公開された状態 |
| `hold` | ⏸️ 保留 | 現時点では記事化しない保留記事 |
| `closed` | 🗑️ ボツ | 記事化ならず |

> **旧ステータス（後方互換）**：`draft`・`interview`・`photo_pending`・`comment_photo_pending` → `writing` 扱い、`published` → `done` 扱い
