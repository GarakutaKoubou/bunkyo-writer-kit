---
name: upload-gdocs
description: 記事をGoogle Docsに保存、または完成フォルダに移動する。「アップして」「保存して」「本番にアップ」「完成フォルダに移動」等で自動起動。
allowed-tools: Read, Write, Edit, Bash
---

# Google Docs 保存・移動フロー

## 下書き保存

```bash
# 1. チェック実行
python3 article_check.py --json /tmp/bunkyo_YYYYMMDD/article.json

# 2. Google Docsに保存（【下書き】フォルダ）
# → save_to_gdocs.py が article.json の gdocs_url を自動更新する
python3 save_to_gdocs.py --json /tmp/bunkyo_YYYYMMDD/article.json

# 3. インデックスを更新（articles/{id} に HTML・JSON を保存）
python3 preview_generator.py --json /tmp/bunkyo_YYYYMMDD/article.json --save-article
python3 check_index_link.py --json /tmp/bunkyo_YYYYMMDD/article.json
python3 index_generator.py
```

## 本番アップロード（完成フォルダへ移動）

```bash
# 1. チェック実行
python3 article_check.py --json /tmp/bunkyo_YYYYMMDD/article.json

# 2. 完成フォルダに保存＆移動
# → save_to_gdocs.py が article.json の gdocs_url を自動更新する
python3 save_to_gdocs.py --json /tmp/bunkyo_YYYYMMDD/article.json --move-completed

# 3. インデックスを更新（status → "done"）
python3 preview_generator.py --json /tmp/bunkyo_YYYYMMDD/article.json --save-article
python3 check_index_link.py --json /tmp/bunkyo_YYYYMMDD/article.json
python3 index_generator.py
```

## 保存後の必須表示

```
📁 保存先：【下書き】フォルダ OR 【完成】フォルダ
🔗 [https://docs.google.com/document/d/...](https://docs.google.com/document/d/...)
```

URL表示は必ずURLテキストそのものをリンクにする形式で。
