---
name: thank-you-email
description: 記事公開後のお礼メールを生成する。「お礼メールを作って」「公開お知らせメール」「記事公開後のメール」等で自動起動。
allowed-tools: Read, WebFetch, WebSearch, Bash, Glob
---

# 公開お知らせ・お礼メール生成フロー

記事が公開されたあと、取材先へのお礼メールを生成する。

## 手順

### 1. 記事情報を確認する

`article_index.json` または `/tmp/bunkyo_YYYYMMDD/article.json` から以下を確認：
- 記事タイトル
- 記事日付（YYYYMMDD）

ユーザーから日付や記事名の指定がある場合はそれを優先する。

### 2. 文京経済新聞サイトで公開URLを探す

文京経済新聞のサイト内検索でタイトルキーワードを検索し、公開記事のURLを取得する。

```
検索ベースURL：https://bunkyo.keizai.biz/
サイト内検索：WebSearchで "site:bunkyo.keizai.biz [タイトルキーワード]" を試みる
または直接：https://bunkyo.keizai.biz/ をWebFetchしてトップや最新記事から探す
```

**注意：** メディア本部でタイトルや内容が変更されている場合があるため、元の記事タイトルで検索しつつ、内容が一致するものを選ぶ。見つかったページのタイトルを確認して合致するか判断する。

### 3. Yahoo!ニュースで公開URLを探す

記事タイトルから2〜3の固有キーワードを抽出し、以下のURLをWebFetchする：

```
https://news.yahoo.co.jp/search?p={キーワード1}+{キーワード2}+文京経済新聞&ei=utf-8
```

**キーワード抽出の例：**
- 「本郷のシードでクレヨン画の研修」→ `シード+クレヨン+文京経済新聞`
- 「茗荷谷の女性専用ジム「フィットリリーズ」が1周年」→ `フィットリリーズ+女性専用+文京経済新聞`
- 「東大・懐徳館で特別見学会」→ `懐徳館+見学会+文京経済新聞`

WebFetchのプロンプト：「文京経済新聞の[記事キーワード]に関する記事を探してください。`https://news.yahoo.co.jp/articles/` で始まるURLとタイトルを教えてください」

見つかった記事のタイトル・内容が一致するか確認してURLを取得する。
文京経済新聞の記事は通常 `https://news.yahoo.co.jp/articles/` のURLになる。

### 4. メール文を生成する

以下のフォーマットで出力する（署名・宛名は含めない）：

```
件名：文京経済新聞：記事公開のご連絡

お世話になっております。
文京経済新聞の横山です。

先日は情報提供ありがとうございます。
記事を公開しましたのでお知らせいたします。

※文京経済新聞
[文京経済新聞の記事URL]

※Yahoo!ニュース
[Yahoo!ニュースの記事URL]

今後も文京区に関わるイベントやニュースなどあれば
ご連絡いただけると幸いです。

よろしくお願いいたします。
```

**件名：** 常に「文京経済新聞：記事公開のご連絡」で固定
**宛名：** 出力しない（メールソフト側で追加）

### 5. インデックスを「公開済み」に更新する

メール文を出力したあと、**必ず** 以下を実行してインデックスに公開URLを登録する：

```python
import json

with open('article_index.json', encoding='utf-8') as f:
    data = json.load(f)

for entry in data:
    if entry.get('id') == <記事ID>:          # article_index.json で確認
        entry['status'] = 'published'
        entry['published_url'] = '<文京経済新聞の記事URL>'
        break

with open('article_index.json', 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, indent=2)
```

```bash
python3 index_generator.py
```

- `status` を `done` → `published` に変更する
- `published_url` に文京経済新聞の記事URL（手順2で取得）を登録する
- Yahoo!ニュースのURLは登録しない（管理不要）

### 6. URLが見つからない場合

- 文京経済新聞のURLが見つからない場合：「まだ公開されていない可能性があります。公開後に再度実行してください。」と伝える。インデックス更新も行わない。
- Yahoo!ニュースのURLが見つからない場合：URLを空欄にしてメール文を出力し、「Yahoo!ニュースの記事URLが見つかりませんでした。手動で追記してください。」と伝える。インデックス更新は文京経済新聞URLが取得できていれば実行する。
