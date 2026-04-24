"""
get_photos.py
Google フォト共有アルバムから写真URLを取得する

使い方:
  python3 get_photos.py <アルバムURL>
  python3 get_photos.py <アルバムURL> --max 5
  python3 get_photos.py <アルバムURL> --out /tmp/photos.json

出力（JSON）:
  {
    "album_title": "20260203_結の村かつらお展",
    "album_url": "https://photos.app.goo.gl/...",
    "photos": [
      {"url": "https://lh3.googleusercontent.com/pw/...", "caption": ""},
      ...
    ]
  }
"""

import sys
import re
import json
import argparse
import urllib.request


def get_photos(album_url: str, max_photos: int = 10) -> dict:
    """
    Google フォト共有アルバムから写真URLのリストを返す

    Args:
        album_url:   photos.app.goo.gl または photos.google.com/share の URL
        max_photos:  最大取得枚数

    Returns:
        {"album_title": str, "album_url": str, "photos": [{"url": str, "caption": str}]}
    """
    # シンプルなUA文字列でGoogle Photosのサーバーサイドレンダリングを引き出す
    # （フルChrome UAだとJSレンダリングページが返り画像URLが取れない）
    req = urllib.request.Request(
        album_url,
        headers={"User-Agent": "Mozilla/5.0"},
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        html = resp.read().decode("utf-8")

    # ページタイトルを取得
    title_match = re.search(r"<title>(.*?)</title>", html)
    title = (
        title_match.group(1)
        .replace(" - Google Photos", "")
        .replace(" - Google フォト", "")
        .strip()
        if title_match
        else ""
    )

    # /pw/ プレフィックスの写真URLを抽出
    # プロフィール画像 (/a/) やサムネイル等は除外し、/pw/ のみ取得
    raw = re.findall(
        r"https://lh3\.googleusercontent\.com/pw/[A-Za-z0-9_\-]+", html
    )
    # 順序を保ちながら重複除去
    unique = list(dict.fromkeys(raw))

    return {
        "album_title": title,
        "album_url": album_url,
        "photos": [{"url": u, "caption": ""} for u in unique[:max_photos]],
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Google フォト共有アルバムから写真URLを取得"
    )
    parser.add_argument("url", help="Google フォトアルバムのURL")
    parser.add_argument(
        "--max", type=int, default=10, help="最大取得枚数（デフォルト:10）"
    )
    parser.add_argument(
        "--out", help="出力JSONファイルのパス（省略時は標準出力）"
    )
    args = parser.parse_args()

    result = get_photos(args.url, args.max)

    output = json.dumps(result, ensure_ascii=False, indent=2)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(output)
        print(f"✅ 写真URL {len(result['photos'])} 件 → {args.out}")
    else:
        print(output)
