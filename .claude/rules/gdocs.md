# Google Docs 保存・更新ルール

## ルール1：旧ファイルは必ず削除する
- `save_to_gdocs.py` 実行時、**下書きフォルダ・本番フォルダ両方から**同日付の旧ファイルを自動削除する
- **削除対象は【下書き】【完成】プレフィックスのファイルのみ**。それ以外は他の担当者のファイルの可能性があるため絶対に触らない

## ルール2：URLが変わったら必ずNotion同期する

Google Docs URLが変わる操作（新規保存・本番アップ・修正再保存）の後、**必ず以下を順番に実行する**：

```bash
# ① 作業フォルダの article.json に新URLを書き込む
# ② article_index.json を自動更新 + HTMLを再生成
python3 preview_generator.py --json /tmp/bunkyo_YYYYMMDD/article.json --save-article YYYYMMDD
# ③ インデックスHTML再生成 → 自動でNotion同期が走る
python3 index_generator.py
```

**この3ステップを省略した場合、Notionと記事インデックスが古いURLのまま残る。**

## ルール3：保存先フォルダを必ず明記する

保存後、チャットに以下を必ず表示する：
```
📁 保存先：【下書き】フォルダ OR 【2026年（本番）】フォルダ
🔗 [https://docs.google.com/document/d/...](https://docs.google.com/document/d/...)
```
- URLは必ず「URLテキストそのものをリンクにする」形式で表示する
  - ✅ `[https://docs.google.com/...](https://docs.google.com/...)`
  - ❌ `[Google Docsを開く](https://docs.google.com/...)` や `URL：https://...`（リンクなし）
- 下書き（GDOCS_FOLDER_ID）と本番（COMPLETED_FOLDER_ID）を絶対に混同しない

---

## Google Docs ファイル命名規則

| 種類 | ファイル名 |
|------|-----------|
| 完成記事 | 【完成】YYYYMMDD_タイトル |
| コメント待ち・写真待ち記事 | 【下書き】YYYYMMDD_タイトル |

> 依頼メール（mail.json）はGoogle Docsに保存しない。HTMLプレビューの下部に表示するのみ。

---

## 出力ファイルフォーマット（Google Docs本文）

```
ファイル名：YYYYMMDD_文京経済新聞_簡易タイトル

設定：フォント＝MSPゴシック、サイズ＝10.5

■タイトル（35字以内目安）
[タイトル]

■写真キャプション
[キャプション（体言止め1〜2文）]
[トップ写真のURL]

■本文（段落文頭１字下げ：文頭～初出「。」までリード）
[本文]

■フォトフラッシュタイトル

（リンク画像）[クリック誘導テキスト（25字以内目安）]
[リンク画像のURL]

（1）[サブ写真1のキャプション]
[サブ写真1のURL]

（2）～（5）同上

■記事下リンク（最大5件：関連画像含む）
[○○公式サイト]
[URL]

■住所（管理画面入力用）
[文京区〇〇N-NN-NN]
```
