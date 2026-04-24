#!/usr/bin/env python3
"""
claim_article.py
記事の執筆開始を共有インデックス（Google Sheets）に登録する

他のライターが「この記事はもう誰かが書いている」と確認できるようにする。
トークンをほぼ消費しない軽量スクリプト。

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

from sheets_index import load_from_sheets, append_article as sheets_append


def main():
    parser = argparse.ArgumentParser(description="記事の執筆開始を共有インデックスに登録する")
    parser.add_argument("title", help="記事タイトル（仮）")
    parser.add_argument("--work-dir", help="作業ディレクトリ（省略時は /tmp/bunkyo_YYYYMMDD）")
    args = parser.parse_args()

    writer   = os.environ.get("WRITER_NAME", "横山")
    date_str = datetime.now().strftime("%Y%m%d")
    today    = datetime.now().strftime("%Y-%m-%d")

    # 既存記事の最大IDを取得して次のIDを採番
    articles     = load_from_sheets()
    existing_ids = [a.get("id", 0) for a in articles if isinstance(a.get("id"), int)]
    new_id       = max(existing_ids, default=0) + 1

    article = {
        "id":        new_id,
        "date":      date_str,
        "title":     args.title,
        "gdocs_url": "",
        "status":    "writing",
        "saved_at":  today,
        "html_file": "",
        "json_file": "",
        "writer":    writer,
    }

    sheets_append(article)

    # 作業フォルダに claim_id.txt を保存（後で --save-article が参照する）
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
    print(f"   → 記事生成時、この ID が article.json の \"id\" フィールドに自動設定されます")

    return new_id


if __name__ == "__main__":
    main()
