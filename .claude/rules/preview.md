# プレビュー表示フォーマット

> トークン効率化モード：チャット上に画像は表示しない。ブラウザプレビューで確認する。

## プレビューの仕組み
- 記事データを `/tmp/bunkyo_YYYYMMDD/article.json` に書き出す
- `python3 preview_generator.py` がHTMLを生成してブラウザで表示
- ブラウザはJSONが更新されたときだけ自動リフレッシュ
- チャットにはテキスト情報のみ表示（画像のcurl・Read不要）

---

## 初回プレビュー手順

```
1. /tmp/bunkyo_YYYYMMDD/article.json に記事データを書き出す
   ⚠️ has_comment: false の場合は next_steps を必ず設定する（詳細 → json-format.md）
   　 next_steps がないと「次のアクション」欄がプレビューに表示されない
2. python3 article_check.py --json /tmp/bunkyo_YYYYMMDD/article.json（チェック必須）
3. python3 preview_generator.py --json /tmp/bunkyo_YYYYMMDD/article.json --open
   → ブラウザが開く
4. チャットには以下のテキストサマリーだけ表示する：
```

```
## 記事プレビュー（ブラウザで確認してください）

■タイトル（N字）：[タイトル]
■トップ写真：[選定理由1行]
■リンク画像：[選定理由1行] ／ テキスト：[link_image_text]
■（1）〜使用枚数：[各キャプション1行ずつ]
■住所：[住所]
■リンク：[URL]

修正があればご指示ください。OKであれば「OK」とお返事ください。
```

---

## 修正ループ手順（2回目以降）

```
1. 変更フィールドのみ /tmp/bunkyo_YYYYMMDD/article.json を更新（JSONの部分書き換え）
2. python3 article_check.py --json /tmp/bunkyo_YYYYMMDD/article.json（チェック必須・毎回）
3. python3 preview_generator.py --json /tmp/bunkyo_YYYYMMDD/article.json --open
   （--open あり：必ずブラウザを開き直す）
   ※ --save-article は使わない（まだ承認前のため articles/ は更新しない）
4. チャットには変更箇所のテキストのみ表示：
```

```
変更しました：
  ■タイトル → 「新しいタイトル（XX字）」
  ■トップ写真 → Photo3に変更（理由：〇〇）

ブラウザのプレビューをご確認ください。
```

---

## 最終承認後の手順

```
ユーザーが「OK」
  → python3 save_to_gdocs.py --json /tmp/bunkyo_YYYYMMDD/article.json を実行
  → Google DocsのURLをチャットに返す
```

### コメントが届いた場合のフロー
1. ユーザーがコメント素材を貼り付ける
2. コメントを本文の「【担当者様コメント（取得待ち）】」と差し替え、has_comment: true に更新
3. /tmp/bunkyo_YYYYMMDD/mail.json を削除する（メール欄がHTMLプレビューから消える）
4. /tmp/bunkyo_YYYYMMDD/article.json を更新
5. python3 article_check.py → python3 preview_generator.py --open
6. プレビュー確認 → 修正ループ → ユーザーが「OK」→ Google Docs に【完成】として保存
7. gdocs_url 更新 → --save-article → index_generator.py

### 完成フォルダへの移動
ユーザーが「完成フォルダに移動して」と指示したとき（OK後のみ）：
```bash
python3 save_to_gdocs.py --json /tmp/bunkyo_YYYYMMDD/article.json --move-completed
```
