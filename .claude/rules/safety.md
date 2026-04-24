# 情報混入防止・先祖返り防止ルール

## 情報混入防止（最重要・絶対に違反しない）

> 別記事の情報を混入させると、取材先への誤った質問・誤報につながる。信頼を失い、二度と取材に応じてもらえなくなる可能性がある。

### 絶対ルール：今回の素材のみを使う

**mail.json・editorial_advice・next_stepsを生成するとき：**
- **今回ユーザーが貼り付けた素材のみ**を根拠にする
- 過去記事・他のプレスリリース・セッション中に扱った別記事の情報は**一切使わない**
- 「この情報は今回の素材のどこに書いてあるか？」を1件ずつ確認してから書く
- 確認できない情報は**書かない**（不明な場合は「プレスリリースに記載なし・確認要」と明記）

### チェックリスト（mail.json・editorial_advice生成前に必ず確認）
- [ ] 質問・情報の根拠が今回の素材に実在するか？
- [ ] 前の記事（同セッション内の別記事）の内容が混入していないか？
- [ ] 他の取材先・別イベントの情報が混入していないか？

---

## 記事データの一貫性ルール（3層防御）

> 過去に「記事が古いバージョンに戻る」「別記事のアドバイスが混入する」致命的なバグが発生した。

### 第1層：記事ごとの作業フォルダ分離

記事の作業ファイルは `/tmp/bunkyo_YYYYMMDD/` に**記事ごとに独立**して配置する。
**共用ファイル（`/tmp/article_preview.json`）は使用禁止。**

```
/tmp/bunkyo_YYYYMMDD/
  ├── article.json       ← この記事の作業データ
  ├── mail.json           ← この記事の依頼メール（あれば）
  └── photos.json         ← この記事の写真データ（あれば）
```

- 記事Aと記事Bは物理的に別フォルダなので、**データの混入が構造的に不可能**
- 新しい記事を始めるとき：`mkdir -p /tmp/bunkyo_YYYYMMDD`
- preview_generator.py には `--json /tmp/bunkyo_YYYYMMDD/article.json` を渡す

### 第2層：article_check.py による自動検証

**プレビュー生成の前に必ず実行する。** エラーがあればプレビューを生成しない。

```bash
python3 article_check.py --json /tmp/bunkyo_YYYYMMDD/article.json
```

検出するもの：
- **日付不一致**：フォルダ名と generated_at が異なる → 別記事のデータが混入している
- **先祖返り**：作業ファイルが `articles/YYYYMMDD.json` より古い
- **コメント先祖返り**：正規データにはコメントがあるのに作業ファイルはプレースホルダーのまま
- **執筆ルール違反**：タイトル文字数・語順・禁止表現・漢字変換など自動検出

### 第3層：正規データ（Single Source of Truth）

| 段階 | 正規データの所在 |
|------|----------------|
| 新規記事（初回生成） | ユーザーが貼り付けた素材のみ |
| 下書き以降 | `articles/YYYYMMDD.json`（プロジェクトフォルダ内） |
| 最終版 | Google Docs（`article_index.json` の `gdocs_url`） |

### 記事切り替え時の手順

1. **現在の記事の状態を確認**：未保存の変更があれば `articles/YYYYMMDD.json` に保存する
2. **新しい記事の作業フォルダを使う**：`/tmp/bunkyo_新YYYYMMDD/`（前の記事のフォルダは触らない）
3. **前の記事のデータをメモリ上で「忘れる」**：前の記事のtitle/body/advice/mail等を新しい記事に持ち込まない

### 記事修正時の手順

1. `articles/YYYYMMDD.json` を**ファイルから読み直す**（Read toolを使用）
2. 読み直したデータを `/tmp/bunkyo_YYYYMMDD/article.json` にコピーする
3. 読み直したデータをベースに修正を加える（**記憶やコンテキスト上のデータは使わない**）
4. `python3 article_check.py` で整合性を検証してからプレビュー

---

## 過去記事の修正ルール（絶対遵守）

> articles/YYYYMMDD.jsonが古い状態のことがある。そのまま上書きするとコメント組み込み済みの最新内容が消える。

### 必須手順（修正・GDocs保存のたびに毎回実施）

1. `article_index.json` で該当記事の `gdocs_url` を確認する
2. **`google_drive_fetch` ツールでGDocsの最新本文を取得する**（省略禁止）
3. `articles/YYYYMMDD.json` の内容とGDocsを照合し、差分を確認する
4. GDocsの内容が新しい場合は、**GDocsの本文をベースに** `/tmp/bunkyo_YYYYMMDD/article.json` を作成する
5. その上で修正を加える
6. **`python3 article_check.py`** を実行し、エラーがないことを確認する
7. エラーがなければ `save_to_gdocs.py` でGDocsを更新する

### 絶対にやってはいけないこと
- GDocsを確認せず `articles/YYYYMMDD.json` をそのまま上書きする
- `article_check.py` を通さずにGDocsに保存する
- GDocsのURLが変わったのに `article_index.json` を更新しない

---

## 修正依頼にWordファイルが添付された場合のルール

> **Google Driveにアップされている記事（gdocs_url）が唯一の正解**。Wordファイルは参考資料に過ぎない。

### 正しい手順
1. `article_index.json` で `gdocs_url` を確認する
2. **GDocsの最新本文を取得してベースにする**（Wordファイルではなく）
3. ユーザーの修正指示をGDocsベースに適用する
4. `article_check.py` → プレビュー → ユーザーOK → `save_to_gdocs.py`

### やってはいけないこと
- Wordファイルの内容をそのままarticle.jsonに上書きする
- テキスト指示だけを見てキャプション・URLを推測・自作する
- GDocsを確認せずにWordや記憶をベースに修正を加える
