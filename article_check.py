"""
article_check.py
記事データの整合性チェック・執筆ルールチェックを行う

使い方:
  # プレビュー前チェック（必須）
  python3 article_check.py --json /tmp/bunkyo_20260329/article.json

  # 素材フィンガープリントを登録（記事生成時に1回）
  python3 article_check.py --json /tmp/bunkyo_20260329/article.json --register-source <<< "素材テキスト"

終了コード:
  0: 全チェック通過
  1: 警告あり（プレビュー可）
  2: エラーあり（修正必要）
"""

import json
import os
import re
import sys
import hashlib
import argparse
from datetime import datetime

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))


# ── 素材フィンガープリント ─────────────────────────────────────────────────

def compute_hash(text: str) -> str:
    """テキストのSHA-256ハッシュ（先頭16文字）を返す"""
    return hashlib.sha256(text.strip().encode("utf-8")).hexdigest()[:16]


def register_source(json_path: str, source_text: str):
    """素材のフィンガープリントを記事JSONの _meta に保存する"""
    with open(json_path, encoding="utf-8") as f:
        data = json.load(f)

    if "_meta" not in data:
        data["_meta"] = {}

    data["_meta"]["source_hash"] = compute_hash(source_text)
    data["_meta"]["registered_at"] = datetime.now().isoformat()

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"✅ 素材フィンガープリントを登録しました: {data['_meta']['source_hash']}")


# ── データ整合性チェック ───────────────────────────────────────────────────

def check_data_integrity(data: dict, json_path: str) -> list:
    """データ整合性をチェックし、結果リストを返す"""
    results = []
    article = data.get("article", data)
    generated_at = article.get("generated_at", "")

    # 1. 必須フィールドの存在確認
    required = ["title", "body", "generated_at"]
    missing = [f for f in required if not article.get(f)]
    if missing:
        results.append(("ERROR", f"必須フィールドが不足: {', '.join(missing)}"))
    else:
        results.append(("OK", "必須フィールド完備"))

    # 2. 日付の整合性（フォルダ名 vs generated_at）
    dir_name = os.path.basename(os.path.dirname(json_path))
    if dir_name.startswith("bunkyo_") and len(dir_name) == 15:
        folder_date = dir_name[7:]  # "bunkyo_YYYYMMDD" → "YYYYMMDD"
        if generated_at and folder_date != generated_at:
            results.append(("ERROR", f"日付不一致: フォルダ={folder_date} / JSON={generated_at}（別記事のデータが混入している可能性）"))
        elif generated_at:
            results.append(("OK", f"日付一致: {generated_at}"))
    elif generated_at:
        results.append(("OK", f"記事日付: {generated_at}"))

    # 3. 正規データ（articles/YYYYMMDD.json）との比較
    if generated_at:
        canonical = os.path.join(PROJECT_DIR, "articles", f"{generated_at}.json")
        if os.path.exists(canonical):
            canonical_mtime = os.path.getmtime(canonical)
            current_mtime = os.path.getmtime(json_path)
            if current_mtime < canonical_mtime:
                results.append(("ERROR", f"先祖返りの疑い: 作業ファイルが articles/{generated_at}.json より古い（正規データを読み直してください）"))
            else:
                results.append(("OK", f"正規データ（articles/{generated_at}.json）より新しい"))

            # 本文の比較：正規データにコメントが入っているのに作業ファイルにない場合
            try:
                with open(canonical, encoding="utf-8") as f:
                    canon_data = json.load(f)
                canon_article = canon_data.get("article", canon_data)
                canon_body = canon_article.get("body", "")
                current_body = article.get("body", "")
                # 正規データにはコメントがあるのに、作業ファイルにはプレースホルダーがある場合
                if "コメント（取得待ち）" in current_body and "コメント（取得待ち）" not in canon_body and len(canon_body) > 100:
                    results.append(("ERROR", "先祖返りの疑い: 正規データにはコメントが組み込まれているが、作業ファイルはプレースホルダーのまま"))
            except Exception:
                pass
        else:
            results.append(("OK", f"新規記事（articles/{generated_at}.json はまだ存在しない）"))

    # 4. 素材フィンガープリントの確認
    meta = data.get("_meta", {})
    if meta.get("source_hash"):
        results.append(("OK", f"素材フィンガープリント: {meta['source_hash']}"))
    else:
        results.append(("WARN", "素材フィンガープリント未登録（--register-source で登録推奨）"))

    # 5. mail.json の存在確認（has_comment: false のとき必須）
    has_comment = data.get("has_comment", True)
    if not has_comment:
        next_steps = data.get("next_steps", {})
        comment_request = next_steps.get("comment_request", {})
        photo_request = next_steps.get("photo_request", {})
        needs_mail = bool(comment_request) or bool(photo_request)

        # next_steps 自体が未設定
        if not next_steps:
            results.append(("ERROR", "next_steps が未設定（has_comment: false の場合は必須）"))
        elif needs_mail:
            # mail.json の存在確認
            work_dir = os.path.dirname(json_path)
            mail_path = os.path.join(work_dir, "mail.json")
            if not os.path.exists(mail_path):
                results.append(("ERROR", "mail.json が未作成（next_steps.comment_request/photo_request が設定されているのにメール案がない）→ mail.json を作成してください"))
            else:
                # mail.json と next_steps の質問内容が一致しているか確認
                try:
                    with open(mail_path, encoding="utf-8") as f:
                        mail_data = json.load(f)
                    mail_text = mail_data.get("mail_text", "")
                    questions = comment_request.get("questions", [])
                    mismatched = []
                    for q in questions:
                        # 質問の冒頭20字がmail_textに含まれているか
                        if len(q) >= 10 and q[:20] not in mail_text:
                            mismatched.append(q[:20] + "…")
                    if mismatched:
                        results.append(("WARN", f"mail.json の質問内容が next_steps と不一致の可能性: {mismatched[0]}"))
                    else:
                        results.append(("OK", "mail.json 作成済み・質問内容一致"))
                except Exception:
                    results.append(("WARN", "mail.json の読み込みに失敗しました"))

    return results


# ── 執筆ルールチェック ─────────────────────────────────────────────────────

# 禁止表現リスト
PROHIBITED_WORDS = [
    "厳選", "実力派", "高品質", "個性豊かな", "上質な", "最大級",
    "本格的な", "逸品", "堪能", "大人リッチ", "少数精鋭",
    "往年の大スター", "レジェンド", "至芸", "熱量",
]

# ひらがなに開くべき漢字
HIRAGANA_RULES = {
    "子供": "子ども",
    "様々": "さまざま",
    "色々": "いろいろ",
    "賑わ": "にぎわ",
    "挨拶": "あいさつ",
    "可愛い": "かわいい",
    "界隈": "かいわい",
    "喋": "しゃべ",
    "研鑽": "研さん",
    "惹き": "引き",
    "惹か": "引か",
}

# 特定の漢字変換
KANJI_RULES = {
    "想い": "思い",
    "活かし": "生かし",
    "活かす": "生かす",
    "入口": "入り口",
    "附属": "付属",
    "出揃": "出そろ",
    "揃え": "そろえ",
    "切り拓": "切り開",
}

# 半角→全角のチェック対象
HALFWIDTH_SYMBOLS = {
    "!": "！",
    "?": "？",
    "&": "＆",
    "%": "％",
}


def find_line_number(text: str, pattern: str) -> str:
    """パターンが出現する行番号を返す（表示用）"""
    for i, line in enumerate(text.split("\n"), 1):
        if pattern in line:
            return f"L{i}"
    return ""


def check_writing_rules(data: dict) -> list:
    """writing_rules.md に基づくチェックを行い、結果リストを返す"""
    results = []
    article = data.get("article", data)
    title = article.get("title", "")
    body = article.get("body", "")
    caption = article.get("caption", "")

    # 全テキスト（title + body + caption）を結合してチェック
    all_text = f"{title}\n{caption}\n{body}"

    # ── タイトル ──

    title_len = len(title)
    if title_len > 35:
        results.append(("WARN", f"タイトル {title_len}字（上限35字）"))
    elif title_len > 0:
        results.append(("OK", f"タイトル {title_len}字"))

    if re.search(r"\d+月\d+日", title):
        results.append(("ERROR", f"タイトルに日付あり: 「{title}」"))
    else:
        results.append(("OK", "タイトルに日付なし"))

    if "開催" in title:
        results.append(("ERROR", f"タイトルに「開催」あり → 「開く」「始まる」等に"))
    else:
        results.append(("OK", "タイトルに「開催」なし"))

    # ── コメント語順 ──
    # 悪い例：「○○したい」と白井会長は話す → 「...」と + 人名 + は
    bad_order = re.findall(
        r"「[^」]+」\s*と\s*([^\s「」、。]{1,15}(?:さん|会長|社長|代表|店主|店長|担当|理事長|教授|先生|氏))\s*は",
        body
    )
    if bad_order:
        for name in bad_order:
            results.append(("ERROR", f"コメント語順NG: 「…」と{name}は → {name}は「…」と に修正"))
    else:
        # コメントが存在する場合のみOK表示
        if "「" in body and "と話" in body:
            results.append(("OK", "コメント語順OK"))

    # ── 語尾「だ」 ──
    da_matches = re.findall(r"[^「」\n]{2,8}だ。", body)
    if da_matches:
        for m in da_matches[:3]:  # 最大3件表示
            ln = find_line_number(body, m)
            results.append(("WARN", f"語尾「だ」: {ln}「{m}」→ 体言止め・動詞に"))
    else:
        results.append(("OK", "語尾「だ」なし"))

    # ── 「語る」使用 ──
    if re.search(r"と語[るっ]", body):
        results.append(("ERROR", "「語る」使用 → 「話す」「強調する」等に"))
    else:
        results.append(("OK", "「語る」なし"))

    # ── 記号の全角統一 ──
    # URL内の & ? は除外するため、行ごとにURLを除去してからチェック
    symbol_errors = []
    for line in all_text.split("\n"):
        # URL部分を除去
        line_no_url = re.sub(r"https?://\S+", "", line)
        for half, full in HALFWIDTH_SYMBOLS.items():
            if half in line_no_url:
                ln = find_line_number(all_text, line.strip()[:20])
                symbol_errors.append(f"{ln}「{half}」→「{full}」")
    if symbol_errors:
        for e in symbol_errors[:3]:
            results.append(("ERROR", f"半角記号: {e}"))
    else:
        results.append(("OK", "記号全角統一"))

    # ── 禁止表現 ──
    found_prohibited = []
    for word in PROHIBITED_WORDS:
        if word in all_text:
            ln = find_line_number(all_text, word)
            found_prohibited.append(f"{ln}「{word}」")
    if found_prohibited:
        for p in found_prohibited:
            results.append(("ERROR", f"禁止表現: {p}"))
    else:
        results.append(("OK", "禁止表現なし"))

    # ── 漢字変換（ひらがなに開く） ──
    kanji_errors = []
    for wrong, correct in {**HIRAGANA_RULES, **KANJI_RULES}.items():
        if wrong in all_text:
            ln = find_line_number(all_text, wrong)
            kanji_errors.append(f"{ln}「{wrong}」→「{correct}」")
    if kanji_errors:
        for k in kanji_errors:
            results.append(("ERROR", f"漢字変換: {k}"))
    else:
        results.append(("OK", "漢字変換OK"))

    # ── 「ヴ」使用 ──
    if "ヴ" in all_text:
        ln = find_line_number(all_text, "ヴ")
        results.append(("ERROR", f"「ヴ」使用: {ln} → 「ビ」「ベ」等に"))
    else:
        results.append(("OK", "「ヴ」なし"))

    # ── 二重かぎ括弧 ──
    if "『" in all_text:
        ln = find_line_number(all_text, "『")
        results.append(("ERROR", f"二重かぎ括弧『』使用: {ln} → 「」に統一"))
    else:
        results.append(("OK", "括弧ルールOK"))

    # ── 「注目は」（主観的表現） ──
    if "注目は" in all_text:
        ln = find_line_number(all_text, "注目は")
        results.append(("ERROR", f"主観的表現: {ln}「注目は」→ 削除"))

    # ── 段落冒頭の1字下げ ──
    body_lines = [l for l in body.split("\n") if l.strip()]
    if body_lines:
        non_indented = [l for l in body_lines if l and not l.startswith("　") and not l.startswith("【")]
        if non_indented:
            results.append(("WARN", f"段落冒頭1字下げ漏れ: {len(non_indented)}段落"))
        else:
            results.append(("OK", "段落冒頭1字下げOK"))

    # ── 曜日チェック ──
    if re.search(r"[月火水木金土日]曜日?\)", body) or re.search(r"（[月火水木金土日]）", body):
        results.append(("WARN", "曜日が含まれています → 削除推奨"))

    return results


# ── 出力フォーマット ───────────────────────────────────────────────────────

def format_results(integrity_results: list, writing_results: list) -> tuple:
    """結果を整形して出力文字列と終了コードを返す"""
    all_results = integrity_results + writing_results
    error_count = sum(1 for l, _ in all_results if l == "ERROR")
    warn_count  = sum(1 for l, _ in all_results if l == "WARN")

    if error_count:
        exit_code = 2
    elif warn_count:
        exit_code = 1
    else:
        exit_code = 0

    # 全通過時は1行サマリーのみ（トークン節約）
    if exit_code == 0:
        total = len(all_results)
        return f"✅ 全チェック通過（{total}項目）", 0

    # エラー・警告時は詳細表示
    lines = []
    lines.append("")
    lines.append("🔍 記事チェック結果")
    lines.append("━" * 40)

    lines.append("■ データ整合性")
    for level, msg in integrity_results:
        icon = {"OK": "  ✅", "WARN": "  ⚠️", "ERROR": "  ❌"}[level]
        lines.append(f"{icon} {msg}")

    lines.append("")
    lines.append("■ 執筆ルール")
    for level, msg in writing_results:
        icon = {"OK": "  ✅", "WARN": "  ⚠️", "ERROR": "  ❌"}[level]
        lines.append(f"{icon} {msg}")

    lines.append("")
    lines.append("━" * 40)

    if error_count:
        lines.append(f"結果: ❌ エラー {error_count}件（修正必要）" + (f" / ⚠️ 警告 {warn_count}件" if warn_count else ""))
    else:
        lines.append(f"結果: ⚠️ 警告 {warn_count}件（修正推奨）")

    return "\n".join(lines), exit_code


# ── メイン ─────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="記事データの整合性・執筆ルールチェック")
    parser.add_argument("--json", required=True, help="記事JSONファイルのパス")
    parser.add_argument("--register-source", action="store_true",
                        help="標準入力から素材テキストを読み、フィンガープリントを登録する")
    args = parser.parse_args()

    if not os.path.exists(args.json):
        print(f"❌ ファイルが見つかりません: {args.json}")
        sys.exit(2)

    # フィンガープリント登録モード
    if args.register_source:
        source_text = sys.stdin.read()
        if not source_text.strip():
            print("❌ 素材テキストが空です")
            sys.exit(2)
        register_source(args.json, source_text)
        sys.exit(0)

    # チェック実行
    with open(args.json, encoding="utf-8") as f:
        data = json.load(f)

    integrity_results = check_data_integrity(data, args.json)
    writing_results = check_writing_rules(data)

    output, exit_code = format_results(integrity_results, writing_results)
    print(output)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
