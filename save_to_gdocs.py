"""
save_to_gdocs.py
Claude Codeが生成した記事をGoogle Docsに保存する

使い方:
  python3 save_to_gdocs.py --json /tmp/article.json
  python3 save_to_gdocs.py --json /tmp/article.json --move-completed

※ メール文（mail.json）はHTMLプレビューにのみ表示。Google Docsへの保存は不要のため、--mailオプションは廃止。
"""

import warnings
warnings.filterwarnings("ignore")

import json
import argparse
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))
from post_to_gdocs import save_article, save_mail, move_to_completed


def main():
    parser = argparse.ArgumentParser(description="Google Docs保存スクリプト")
    parser.add_argument("--json",             required=True, help="記事JSONファイルのパス")
    parser.add_argument("--move-completed",   action="store_true", help="保存後に完成フォルダへ移動する")
    args = parser.parse_args()

    # 記事JSONを読み込む
    with open(args.json, encoding="utf-8") as f:
        data = json.load(f)

    article     = data["article"]
    has_comment = data["has_comment"]
    gdocs_url   = data.get("gdocs_url", "")

    # 記事を保存（既存URLがあれば上書き更新）
    article_url = save_article(article, has_comment, gdocs_url=gdocs_url)
    print(f"ARTICLE_URL:{article_url}")

    # 完成フォルダに移動（--move-completed フラグがある場合）
    if args.move_completed:
        doc_id = article_url.split("/d/")[1].split("/")[0]
        date_str = data["article"].get("generated_at", "")
        move_to_completed(doc_id, date_str=date_str)

    # article.json の gdocs_url を自動更新（手動 Edit 不要にする）
    data["gdocs_url"] = article_url
    with open(args.json, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"✅ article.json の gdocs_url を更新しました")

    # ※ メール文はHTMLプレビューにのみ表示。Google Docsには保存しない。


if __name__ == "__main__":
    main()
