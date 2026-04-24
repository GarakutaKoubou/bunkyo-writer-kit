# JSON出力フォーマット

## 記事（/tmp/bunkyo_YYYYMMDD/article.json）

```json
{
  "article": {
    "title": "タイトル（35字以内）",
    "caption": "写真キャプション（トップ写真の説明・1〜2文体言止め）",
    "top_photo_url": "https://lh3.googleusercontent.com/pw/...",
    "body": "本文",
    "link_image_text": "（リンク画像）用テキスト（クリックしたくなる文章・25字以内目安）",
    "link_image_url": "https://lh3.googleusercontent.com/pw/...",
    "generated_at": "YYYYMMDD",
    "photos": [
      {"url": "...", "caption": "（1）のキャプション"},
      {"url": "...", "caption": "（2）のキャプション"},
      {"url": "...", "caption": "（3）のキャプション"},
      {"url": "...", "caption": "（4）のキャプション"},
      {"url": "...", "caption": "（5）のキャプション"}
    ],
    "address": "文京区〇〇N-NN-NN",
    "related_links": [
      {"url": "https://example.com/", "text": "○○公式サイト"}
    ]
  },
  "has_comment": false,
  "next_steps": {
    "type": "comment_only",
    "comment_request": {
      "target": "○○さん（役職・団体名）",
      "questions": [
        "質問1（取材先に確認したいこと）",
        "質問2"
      ]
    },
    "photo_request": {
      "suggestions": [
        "欲しい写真の説明1",
        "欲しい写真の説明2"
      ]
    },
    "missing_info": []
  },
  "gdocs_url": ""
}
```

**`next_steps` フィールドのルール（必須）：**
- `has_comment: false` の場合は **必ず** `next_steps` を設定する
- `type`：`"comment_only"` / `"photo_only"` / `"comment_and_photo"` のいずれか
- `comment_request`：コメント不要なら省略可。`target`（依頼先）と `questions`（質問案3件程度）を記入
  - **質問は以下の観点から3つ程度に絞って生成する（重要）：**
    1. **記事を書いていてぼやけた・掘り下げられなかったポイント**（素材だけでは伝えきれない核心）
    2. **素材に書かれていない、記事に深みを与える情報**（背景・苦労・こだわり・驚きなど）
    3. **読者へのメッセージ**（記事のターゲット層・ステークホルダーに向けた言葉）
    4. **今後の展望・広がり**（継続性・次のステップ・社会的な波及効果）
  - 上記4観点のうち記事に最も必要な3つを選ぶ。汎用的な質問（「感想を聞かせてください」等）は禁止
  - 質問は具体的に：「○○と△△の違いをどう感じますか」より「改革前後でPTAへの保護者の反応はどう変わりましたか」のように核心を突く形で
- `photo_request`：写真不要なら省略可。`suggestions`（欲しい写真の説明）を記入
- `missing_info`：住所・日時など取材で確認が必要な情報をリストで記入（なければ `[]`）
- `has_comment: true`（完成記事）の場合は `next_steps` を省略してよい

**フィールド注意事項：**
- `top_photo_url` / `link_image_url` / `photos` はGoogleフォトアルバムがある場合のみ設定
- アルバムがない場合はこれらのフィールドを空文字 `""` または `[]` にする
- `related_links[].text`：**必ず記入する**（15字以内目安）

---

## 住所の抽出ルール
- プレスリリースの「会場」「住所」欄から抽出する
- 形式：「文京区〇〇N-NN-NN」（丁目・番・号は算用数字とハイフンで表記）
  - 例：「東京都文京区千駄木三丁目35番12号」→ `"文京区千駄木3-35-12"`
  - 例：「文京区本郷7丁目3番1号」→ `"文京区本郷7-3-1"`
- 「東京都」→ `"文京区〇〇"` に省略
- 丁目のみの場合：「文京区春日1丁目」→ `"文京区春日1"`
- 住所が文京区外の場合でもそのまま記載。不明な場合は `"文京区"` のまま

---

## 記事下リンクの抽出ルール
- プレスリリース内の「URL」「公式サイト」「イベントページ」欄から抽出する
- **主催者の公式サイト or 当該イベント専用ページ**を優先する（最大1件が基本）
- SNS（インスタグラム・X・フェイスブック）は含めない
- URLが見当たらない場合は `[]` のまま
- `text` フィールドの記入例：
  - 「東京ドーム公式サイト」「89th with BASEBALLページ」「CCBTイベントページ」

---

## 依頼メール（/tmp/bunkyo_YYYYMMDD/mail.json）

> **必須ルール：mail.json の質問内容は `next_steps.comment_request.questions` と完全に一致させる。**
> 質問を変更したら必ず両方を同時に更新する。片方だけ更新するのは禁止。

```json
{
  "mail_type": "comment_only | photo_only | comment_and_photo",
  "mail_text": "件名：...\n\n本文..."
}
```
- `comment_only`：パターンA（コメントのみ依頼）
- `photo_only`：パターンB（写真のみ依頼）
- `comment_and_photo`：パターンC（コメント＆写真依頼）
- テンプレートは `mail_templates.md` を参照（コメントなし記事の mail.json 作成時のみ読み込む）
