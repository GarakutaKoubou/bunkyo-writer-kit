#!/usr/bin/env python3
"""
check_index_link.py
INDEXのリンク（html_file / json_file）がSheetsに登録されているか確認し、
未登録なら自動修復する。

使い方:
  python3 check_index_link.py --json /tmp/bunkyo_YYYYMMDD/article.json
"""
import sys
import os
import json
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv(override=False)


def main():
    parser = argparse.ArgumentParser(description="INDEXリンク登録を確認・修復する")
    parser.add_argument("--json", required=True, help="article.json のパス")
    args = parser.parse_args()

    with open(args.json, encoding="utf-8") as f:
        data = json.load(f)

    article    = data["article"]
    date_str   = article.get("generated_at", "")
    article_id = data.get("id") or data.get("article_id")

    if not date_str:
        print("❌ article.json に generated_at がありません")
        sys.exit(1)

    html_file = f"articles/{date_str}.html"
    json_file = f"articles/{date_str}.json"

    # ── Sheets の状態を確認 ──────────────────────────────────────
    from sheets_index import load_from_sheets, update_article

    articles = load_from_sheets()

    # ID か日付で対象エントリを探す
    target = None
    for a in articles:
        if article_id and str(a.get("id", "")) == str(article_id):
            target = a
            break
        if a.get("date") == str(date_str) and not target:
            target = a  # 日付一致はフォールバック

    if target is None:
        print(f"❌ Sheetsに記事が見つかりません（id={article_id}, date={date_str}）")
        sys.exit(1)

    # ── リンク登録状態を確認 ──────────────────────────────────────
    sheets_html = target.get("html_file", "")
    sheets_json = target.get("json_file", "")
    found_id    = target.get("id", article_id)

    missing = []
    if not sheets_html:
        missing.append("html_file")
    if not sheets_json:
        missing.append("json_file")

    if not missing:
        print(f"✅ INDEXリンク確認OK（id={found_id}）")
        print(f"   html_file: {sheets_html}")
        print(f"   json_file: {sheets_json}")
        return

    # ── 未登録なら自動修復 ──────────────────────────────────────
    print(f"⚠️  Sheetsに {', '.join(missing)} が未登録です（id={found_id}）。自動修復します...")

    update_fields = {}
    if not sheets_html:
        update_fields["html_file"] = html_file
    if not sheets_json:
        update_fields["json_file"] = json_file

    # タイトルも更新
    title = article.get("title", "")
    if title and not target.get("title"):
        update_fields["title"] = title

    try:
        update_article(int(found_id), update_fields)
        print(f"✅ Sheets を修復しました（id={found_id}）")
        print(f"   更新フィールド: {update_fields}")
    except Exception as e:
        print(f"❌ Sheets修復失敗: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
