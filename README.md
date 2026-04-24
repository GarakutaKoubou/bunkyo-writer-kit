# 文京経済新聞 記事生成ツール

プレスリリース・取材文字起こしから記事を自動生成し、Google Docsに保存するツールです。

## セットアップ

### 1. ライブラリのインストール

```bash
pip install -r requirements.txt
```

### 2. 環境変数の設定

`.env.example` をコピーして `.env` を作成し、各値を設定する。

```bash
cp .env.example .env
```

```
GEMINI_API_KEY=       # Google AI StudioのAPIキー
GOOGLE_APPLICATION_CREDENTIALS=./credentials.json  # サービスアカウントJSONのパス
GDOCS_FOLDER_ID=      # 保存先Google DriveフォルダのID
```

### 3. Gemini APIキーの取得

1. https://aistudio.google.com/ にアクセス
2. 「Get API key」→「Create API key」
3. 取得したキーを `.env` の `GEMINI_API_KEY` に設定

### 4. Google Docs API の設定

1. https://console.cloud.google.com/ でプロジェクトを作成
2. 「APIとサービス」→「ライブラリ」で以下を有効化：
   - Google Docs API
   - Google Drive API
3. 「APIとサービス」→「認証情報」→「サービスアカウント」を作成
4. サービスアカウントのJSONキーをダウンロードし `credentials.json` として保存
5. Google Driveのフォルダをサービスアカウントのメールアドレスと共有する

### 5. Google DriveフォルダIDの取得

保存先フォルダをブラウザで開き、URLの末尾の文字列がフォルダID。
```
https://drive.google.com/drive/folders/xxxxxxxxxxxxxxxxxxxxxxxxx
                                        ↑ これがFOLDER_ID
```

---

## 使い方

### 通常の実行（Claude Codeから素材を貼り付ける）

```bash
python main.py
```

起動後、素材テキストを貼り付けて空行2回でEnter。

### ファイルから読み込む

```bash
python main.py --file material.txt
```

### Google Docsに保存せず確認だけする

```bash
python main.py --dry-run
```

### コメント依頼先の名前を指定する

```bash
python main.py --target 田中
```

---

## 出力ファイルの命名規則

| 種類 | ファイル名 |
|------|-----------|
| 完成記事（コメントあり） | 【完成】YYYYMMDD_タイトル |
| 下書き記事（コメント待ち） | 【下書き】YYYYMMDD_タイトル |
| コメント依頼メール | 【メール依頼】YYYYMMDD_タイトル |
