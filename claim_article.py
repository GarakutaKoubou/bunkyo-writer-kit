#!/usr/bin/env python3
"""
claim_article.py
記事の執筆開始を共有インデックス（Google Sheets）に登録する

他のライターが「この記事はもう誰かが書いている」と確認できるようにする。
IDはSheets行番号から採番されるため、複数セッション同時実行でも衝突しない。

使い方:
  python3 claim_article.py "根津神社のつつじまつり"
  python3 claim_article.py "根津神社のつつじまつり" --work-dir /tmp/bunkyo_20260424
"""

import sys
import os
import argparse
from datetime import datetime

import warnings
warnings.filterwarnings("ignore")

from dotenv import load_dotenv
load_dotenv(override=True)

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_DIR)

from sheets_index import append_article as sheets_append


def main():
    parser = argparse.ArgumentParser(description="記事の執筆開始を共有インデックスに登録する")
    parser.add_argument("title", help="記事タイトル（仮）")
    parser.add_argument("--work-dir", help="作業ディレクトリ（省略時は /tmp/bunkyo_YYYYMMDD）")
    args = parser.parse_args()

    writer   = os.environ.get("WRITER_NAME", "横山")
    date_str = datetime.now().strftime("%Y%m%d")
    today    = datetime.now().strftime("%Y-%m-%d")

    article = {
        "date":      date_str,
        "title":     args.title,
        "gdocs_url": "",
        "status":    "writing",
        "saved_at":  today,
        "html_file": "",
        "json_file": "",
        "writer":    writer,
        # id は sheets_append() が行番号から採番して返す（ここでは指定しない）
    }

    # Sheetsにappend → 行番号ベースのIDを取得（複数セッション同時実行でも衝突しない）
    new_id = sheets_append(article)

    if not new_id:
        print("❌ Sheetsへの登録に失敗しました。SHEETS_INDEX_ID の設定を確認してください。")
        sys.exit(1)

    # 作業フォルダに claim_id.txt を保存（後で preview_generator.py が参照する）
    work_dir = args.work_dir or f"/tmp/bunkyo_{date_str}"
    os.makedirs(work_dir, exist_ok=True)
    claim_file = os.path.join(work_dir, "claim_id.txt")
    with open(claim_file, "w") as f:
        f.write(str(new_id))

    print(f"✅ 記事ID={new_id} で執筆中として登録しました")
    print(f"   ライター：{writer}")
    print(f"   タイトル：{article['title']}")
    print(f"   他のライターのインデックスに「✏️ 執筆中」として表示されます")
    print(f"")
    print(f"   作業フォルダ: {work_dir}")
    print(f"   → claim_id.txt に ID={new_id} を保存しました")
    print(f"   → 記事生成後、この ID が article.json の \"id\" フィールドに自動設定されます")

    return new_id


if __name__ == "__main__":
    main()
