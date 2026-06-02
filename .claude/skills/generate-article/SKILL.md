---
name: generate-article
description: プレスリリースや取材文字起こしから文京経済新聞の記事を生成する。「記事を作成」「記事を書いて」「素材から記事を」「以下の素材から」等で自動起動。
allowed-tools: Read, Write, Edit, Bash, Glob, Grep
---

# 記事生成フロー

ユーザーが素材（プレスリリース or 文字起こし）を貼り付けたら、以下のフローで記事を生成する。

## 事前準備
1. `writing_rules.md` と `editor_feedback.md` を必ず読み込む
2. 作業フォルダを初期化（**古いmail.jsonを必ず削除**）：
   ```
   mkdir -p /tmp/bunkyo_YYYYMMDD
   rm -f /tmp/bunkyo_YYYYMMDD/mail.json
   ```
   > ⚠️ **`rm -f` は省略禁止。** `mkdir -p` は既存ファイルを消さないため、前のセッションで別記事のmail.jsonが残留していると質問が別の取材先に送られる重大インシデントになる。

## 生成フロー

```
① 素材を分析する
   → GoogleフォトアルバムURLがあれば写真を取得：
     python3 get_photos.py <アルバムURL> --max 7 --out /tmp/bunkyo_YYYYMMDD/photos.json
   → 写真URLを取得し、各写真をRead toolで確認してキャプション・テキストを生成
   → 写真スロットに割り当て（.claude/rules/photo.md 参照）

   **【住所の確認（必須）】**
   以下の手順で住所を確定する：
   1. 素材（プレスリリース・文字起こし）に番・号まで記載されている → そのまま使用
   2. 素材に丁目番号まで（例：後楽1）しか書いていない → WebSearchで施設の正式住所を検索して番・号まで確定する
      - 検索クエリ例：「日中友好会館 住所」「ホテル椿山荘東京 住所」
      - 公式サイト・Googleマップ等で確認する
   3. 検索しても住所が確定できない場合 → `address` フィールドに暫定値を入れ、ユーザーに確認を求める：
      > 「住所が「文京区〇〇N」までしか確認できませんでした。正式な番・号を教えていただけますか？」
   
   **【住所の使い分け（重要）】**
   - `address` フィールド（管理システム用）：番・号まで記載「文京区後楽1-5-3」
   - 記事本文リード文（括弧内）：丁目番号まで「（文京区後楽1）」← writing_rules.md準拠
   
   **【一度確定した住所はセッション内で再利用】**
   同じ施設・会場が同セッション内に再登場した場合は確認済みの住所をそのまま使う。

② writing_rules.md と editor_feedback.md に基づいて記事を生成する

③ コメント有無・写真有無を判定する

## has_comment の判定基準（厳守）

| 条件 | has_comment | 対応 |
|------|-------------|------|
| 取材先から直接コメントを取得済み（メール返信・対面取材等） | `true` | next_steps・mail.json 不要 |
| プレスリリースにコメントが含まれている | `false` | next_steps・mail.json を必ず作成 |
| コメントが全くない | `false` | next_steps・mail.json を必ず作成 |

> **プレスリリース内のコメントは「引用可能な参考情報」であり、独自取材のコメントではない。**
> プレスリリースにコメントが書いてあっても `has_comment: false` とし、追加コメント取得のための mail.json を作成する。
> `has_comment: true` にしてよいのは、ユーザーが「コメントが届いた」と素材を貼り付けたとき（update-comment スキル）のみ。

④ 品質評価ループ（9点以上になるまで自動修正）
   a. /tmp/bunkyo_YYYYMMDD/article.json に記事データを書き出す
   b. 素材テキストを保存（初回のみ）：
      cat > /tmp/bunkyo_YYYYMMDD/source.txt << 'EOF'
      （ユーザーが貼り付けた素材テキストをそのまま書き出す）
      EOF
   c. 素材フィンガープリント登録（初回のみ）：
      python3 article_check.py --json /tmp/bunkyo_YYYYMMDD/article.json --register-source
   d. ルールチェック実行（必須・毎回）：
      python3 article_check.py --json /tmp/bunkyo_YYYYMMDD/article.json
   e. **article-reviewerエージェントを呼び出す**：
      - article.json のパスと source.txt のパスを渡す
      - エージェントが返した採点結果をチャットに表示する
   f. スコア判定：
      - **9点以上** → ⑤（プレビュー生成）へ進む
      - **9点未満** → エージェントが示した改善点を全て修正し、④a に戻る（最大3回まで）
      - 3回修正してもなお9点未満の場合 → 現在のスコアと未解決の改善点をユーザーに報告し、どう対処するか確認する

⑤ プレビューを表示する
   a. プレビュー生成：
      python3 preview_generator.py --json /tmp/bunkyo_YYYYMMDD/article.json --open
   b. articles/ にHTML・JSONを保存してインデックスを更新：
      python3 preview_generator.py --json /tmp/bunkyo_YYYYMMDD/article.json --save-article YYYYMMDD
      python3 index_generator.py
   c. **INDEXリンク確認（必須）**：
      python3 check_index_link.py --json /tmp/bunkyo_YYYYMMDD/article.json
      → ✅ OK なら続行
      → ⚠️ 修復した場合は python3 index_generator.py を再実行してHTMLを再生成する

⑥ ユーザーが修正指示 → 修正して④dに戻る（re-review含む）
   ユーザーが「OK」→ ⑦へ

⑦ コメント/写真判定に応じて書き出し
   ├── コメントあり＆写真あり → 完成記事
   ├── コメントなし → /tmp/bunkyo_YYYYMMDD/mail.json を書き出し
   └── 写真なし → /tmp/bunkyo_YYYYMMDD/mail.json を書き出し

⑧ Google Docsに保存
   python3 save_to_gdocs.py --json /tmp/bunkyo_YYYYMMDD/article.json
   → save_to_gdocs.py が article.json の gdocs_url を自動更新する

⑨ インデックスを更新してURLをユーザーに返す
   → python3 preview_generator.py --json /tmp/bunkyo_YYYYMMDD/article.json --save-article YYYYMMDD
   → python3 check_index_link.py --json /tmp/bunkyo_YYYYMMDD/article.json
   → python3 index_generator.py
   → INDEXのURLをチャットに表示する：http://localhost:8765/article_index.html
```

> Google Docs 保存は、ユーザーが「OK」と承認してから行う。プレビュー段階ではGoogle Docsに保存しない。
