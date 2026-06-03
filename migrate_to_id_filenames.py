#!/usr/bin/env python3
"""
migrate_to_id_filenames.py
既存の日付名ファイル（articles/YYYYMMDD.html/.json）を
ID名（articles/{id}.html/.json）にリネームし、Sheetsの参照も更新する。

【目的】
  日付はかぶる（同じ日に複数記事を作る）。日付をファイル名キーにしていると
  同日付の別記事を上書きしてしまう。記事固有のユニークID（Sheets通し番号）を
  唯一のキーにすることで、衝突を構造的に根絶する。

使い方:
  python3 migrate_to_id_filenames.py --dry-run   # 確認のみ（変更しない）
  python3 migrate_to_id_filenames.py             # 実行
"""
import sys
import os
import json
import argparse

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
ARTICLES_DIR = os.path.join(PROJECT_DIR, "articles")
sys.path.insert(0, PROJECT_DIR)

from dotenv import load_dotenv
load_dotenv(override=False)


def main():
    parser = argparse.ArgumentParser(description="日付名ファイルをID名に移行する")
    parser.add_argument("--dry-run", action="store_true", help="変更せず計画だけ表示")
    args = parser.parse_args()

    from sheets_index import load_from_sheets, update_article

    articles = load_from_sheets()

    plans = []   # (article_id, old_html, new_html, old_json, new_json)
    skipped = []

    for a in articles:
        aid = a.get("id")
        if not str(aid).strip().isdigit():
            skipped.append((aid, "id が数値でない"))
            continue
        aid = int(aid)

        html_file = a.get("html_file", "")
        json_file = a.get("json_file", "")

        # html_file が日付名（articles/YYYYMMDD...）かどうか
        if not html_file:
            continue
        stem = html_file.replace("articles/", "").replace(".html", "")
        if not (len(stem) >= 8 and stem[:8].isdigit()):
            # すでにID名など → スキップ
            continue

        new_html = f"articles/{aid}.html"
        new_json = f"articles/{aid}.json"

        plans.append((aid, html_file, new_html, json_file or html_file.replace(".html", ".json"), new_json))

    if not plans:
        print("✅ 移行対象なし（すべてID名に移行済み）")
        return

    print(f"=== 移行計画（{len(plans)}件）===")
    for aid, oh, nh, oj, nj in plans:
        print(f"  id={aid:>3}: {oh} → {nh}")

    if args.dry_run:
        print("\n（--dry-run のため変更なし）")
        return

    print("\n=== 実行中 ===")
    done = 0
    for aid, old_html, new_html, old_json, new_json in plans:
        old_html_path = os.path.join(PROJECT_DIR, old_html)
        new_html_path = os.path.join(PROJECT_DIR, new_html)
        old_json_path = os.path.join(PROJECT_DIR, old_json)
        new_json_path = os.path.join(PROJECT_DIR, new_json)

        # HTML をリネーム
        if os.path.exists(old_html_path) and old_html_path != new_html_path:
            if os.path.exists(new_html_path):
                print(f"  ⚠️ id={aid}: {new_html} が既に存在。スキップ")
            else:
                os.rename(old_html_path, new_html_path)

        # JSON をリネーム
        if os.path.exists(old_json_path) and old_json_path != new_json_path:
            if os.path.exists(new_json_path):
                print(f"  ⚠️ id={aid}: {new_json} が既に存在。スキップ")
            else:
                os.rename(old_json_path, new_json_path)

        # ID名ファイルが実在する場合のみ Sheets を更新
        update_fields = {}
        if os.path.exists(new_html_path):
            update_fields["html_file"] = new_html
        if os.path.exists(new_json_path):
            update_fields["json_file"] = new_json

        if update_fields:
            update_article(aid, update_fields)
            print(f"  ✅ id={aid}: {update_fields}")
            done += 1
        else:
            print(f"  ⏭️  id={aid}: 実ファイルが見つからずSheets未更新")

    print(f"\n✅ 移行完了（{done}/{len(plans)}件）")


if __name__ == "__main__":
    main()
