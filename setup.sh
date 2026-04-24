#!/bin/bash
# setup.sh
# 文京経済新聞 ライター環境セットアップスクリプト
#
# 使い方（初回のみ）:
#   bash setup.sh
#
# 実行内容:
#   1. Python依存パッケージのインストール確認
#   2. ライター名を .env に設定
#   3. Google OAuth認証（ブラウザが開きます）

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ENV_FILE="$SCRIPT_DIR/.env"
TOKEN_FILE="$SCRIPT_DIR/token.json"
CLIENT_SECRETS="$SCRIPT_DIR/client_secrets.json"

echo ""
echo "========================================"
echo " 文京経済新聞 ライター環境セットアップ"
echo "========================================"
echo ""

# ── 1. Python確認 ─────────────────────────────────────────────────────────────
echo "【1/3】Python環境を確認しています..."

if ! command -v python3 &>/dev/null; then
    echo "❌ Python3 が見つかりません。インストールしてから再実行してください。"
    exit 1
fi

python3 -c "import google.oauth2, googleapiclient, dotenv" 2>/dev/null || {
    echo "📦 必要なパッケージをインストールします..."
    pip3 install --quiet google-auth google-auth-oauthlib google-auth-httplib2 \
        google-api-python-client python-dotenv
    echo "✅ パッケージのインストール完了"
}
echo "✅ Python環境 OK"
echo ""

# ── 2. ライター名の設定 ────────────────────────────────────────────────────────
echo "【2/3】ライター名を設定します"
echo ""

# 既存の WRITER_NAME を確認
existing_name=""
if [ -f "$ENV_FILE" ]; then
    existing_name=$(grep "^WRITER_NAME=" "$ENV_FILE" 2>/dev/null | cut -d'=' -f2)
fi

if [ -n "$existing_name" ]; then
    echo "   現在の設定: WRITER_NAME=$existing_name"
    read -p "   変更しますか？ (y/N): " change_name
    if [[ "$change_name" =~ ^[Yy]$ ]]; then
        existing_name=""
    fi
fi

if [ -z "$existing_name" ]; then
    echo "   あなたの名前を入力してください（例：田中）"
    read -p "   名前: " writer_name

    if [ -z "$writer_name" ]; then
        echo "❌ 名前が入力されませんでした。セットアップを中止します。"
        exit 1
    fi

    # .env に WRITER_NAME を追記（既存行があれば置換）
    if [ -f "$ENV_FILE" ] && grep -q "^WRITER_NAME=" "$ENV_FILE"; then
        # 既存行を置換（macOS と Linux 両対応）
        if [[ "$OSTYPE" == "darwin"* ]]; then
            sed -i '' "s/^WRITER_NAME=.*/WRITER_NAME=$writer_name/" "$ENV_FILE"
        else
            sed -i "s/^WRITER_NAME=.*/WRITER_NAME=$writer_name/" "$ENV_FILE"
        fi
    else
        echo "WRITER_NAME=$writer_name" >> "$ENV_FILE"
    fi

    echo "✅ WRITER_NAME=$writer_name を .env に設定しました"
else
    echo "✅ ライター名はそのまま使用します: $existing_name"
fi
echo ""

# ── 3. Google OAuth認証 ───────────────────────────────────────────────────────
echo "【3/3】Google認証を設定します"
echo ""

if [ ! -f "$CLIENT_SECRETS" ]; then
    echo "❌ client_secrets.json が見つかりません。"
    echo "   横山さんから client_secrets.json を受け取り、"
    echo "   このフォルダ（$SCRIPT_DIR）に置いてから再実行してください。"
    exit 1
fi

if [ -f "$TOKEN_FILE" ]; then
    echo "   既存の認証情報（token.json）が見つかりました。"
    read -p "   再認証しますか？ (y/N): " redo_auth
    if [[ "$redo_auth" =~ ^[Yy]$ ]]; then
        rm "$TOKEN_FILE"
        echo "   token.json を削除しました。ブラウザで再認証します..."
    else
        echo "✅ 既存の認証情報を使用します"
        echo ""
        echo "========================================"
        echo " セットアップ完了！"
        echo "========================================"
        echo ""
        echo "記事を書くときは Claude Code を起動して、"
        echo "素材を貼り付けてください。"
        echo ""
        exit 0
    fi
fi

echo "   ブラウザでGoogleアカウントにログインしてください..."
echo "   （Google Docs・Drive・Sheetsへのアクセスを許可します）"
echo ""
python3 -c "
import warnings; warnings.filterwarnings('ignore')
import os, sys
sys.path.insert(0, '$SCRIPT_DIR')
os.chdir('$SCRIPT_DIR')
from dotenv import load_dotenv; load_dotenv(override=True)
from post_to_gdocs import get_service
get_service()
print('✅ Google認証が完了しました')
"

echo ""

# ── 4. Claude Code ログイン ───────────────────────────────────────────────────
echo "【補足】Claude Code のログイン確認"
echo ""

if command -v claude &>/dev/null; then
    echo "   Claude Code がインストールされています。"
    echo "   未ログインの場合は以下を実行してください："
    echo ""
    echo "   claude login"
    echo ""
    echo "   → ブラウザで claude.ai の Pro/Max アカウントにログインしてください"
else
    echo "   ⚠️  Claude Code がインストールされていません。"
    echo "   以下を実行してインストールしてください："
    echo ""
    echo "   npm install -g @anthropic-ai/claude-code"
    echo "   claude login"
    echo ""
fi

echo "========================================"
echo " セットアップ完了！"
echo "========================================"
echo ""
echo "記事を書くときは Claude Code を起動して、"
echo "素材を貼り付けてください。"
echo ""
