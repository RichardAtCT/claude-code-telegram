"""Lightweight dictionary-based i18n for bot UI messages."""

from typing import Dict

# Type alias for nested translation dictionaries
_Translations = Dict[str, Dict[str, str]]

_MESSAGES: _Translations = {
    # /start welcome
    "welcome": {
        "ja": (
            "{name}、おかえり! わたしはまい、AI秘書だよ\n"
            "なんでも聞いてね — ファイルの読み書きもコード実行もできるよ\n\n"
            "作業ディレクトリ: {dir}\n"
            "コマンド: /new (リセット) · /status"
        ),
        "en": (
            "Hi {name}! I'm your AI coding assistant.\n"
            "Just tell me what you need — I can read, write, and run code.\n\n"
            "Working in: {dir}\n"
            "Commands: /new (reset) · /status"
        ),
    },
    # /new session reset
    "session_reset": {
        "ja": "セッションをリセットしたよ。次は何する?",
        "en": "Session reset. What's next?",
    },
    # /status
    "status": {
        "ja": "\U0001f4c2 {dir} · セッション: {session}{cost}",
        "en": "\U0001f4c2 {dir} · Session: {session}{cost}",
    },
    # /verbose - current level display
    "verbose_current": {
        "ja": (
            "出力レベル: <b>{level}</b> ({label})\n\n"
            "使い方: <code>/verbose 0|1|2</code>\n"
            "  0 = 静か (最終回答のみ)\n"
            "  1 = 通常 (ツール名+推論)\n"
            "  2 = 詳細 (ツール入力+推論)"
        ),
        "en": (
            "Verbosity: <b>{level}</b> ({label})\n\n"
            "Usage: <code>/verbose 0|1|2</code>\n"
            "  0 = quiet (final response only)\n"
            "  1 = normal (tools + reasoning)\n"
            "  2 = detailed (tools with inputs + reasoning)"
        ),
    },
    # /verbose - invalid input
    "verbose_invalid": {
        "ja": "/verbose 0, /verbose 1, /verbose 2 のどれかで指定してね",
        "en": "Please use: /verbose 0, /verbose 1, or /verbose 2",
    },
    # /verbose - level set confirmation
    "verbose_set": {
        "ja": "出力レベルを <b>{level}</b> ({label}) に変更したよ",
        "en": "Verbosity set to <b>{level}</b> ({label})",
    },
    # Working indicator
    "working": {
        "ja": "処理中...",
        "en": "Working...",
    },
    # Claude unavailable
    "claude_unavailable": {
        "ja": "Claude に接続できないよ。設定を確認してね",
        "en": "Claude integration not available. Check configuration.",
    },
    # Send failed
    "send_failed": {
        "ja": "応答の送信に失敗したよ (Telegramエラー: {error})。もう一度試してみてね",
        "en": (
            "Failed to deliver response "
            "(Telegram error: {error}). "
            "Please try again."
        ),
    },
    # File rejected
    "file_rejected": {
        "ja": "ファイルが拒否されたよ: {error}",
        "en": "File rejected: {error}",
    },
    # File too large
    "file_too_large": {
        "ja": "ファイルが大きすぎるよ ({size}MB)。最大: 10MB",
        "en": "File too large ({size}MB). Max: 10MB.",
    },
    # Unsupported file format
    "unsupported_format": {
        "ja": "対応していないファイル形式だよ。テキスト形式 (UTF-8) にしてね",
        "en": "Unsupported file format. Must be text-based (UTF-8).",
    },
    # Photo not available
    "photo_unavailable": {
        "ja": "写真処理は利用できないよ",
        "en": "Photo processing is not available.",
    },
    # /repo - directory not found
    "repo_not_found": {
        "ja": "ディレクトリが見つからないよ: <code>{name}</code>",
        "en": "Directory not found: <code>{name}</code>",
    },
    # /repo - switched
    "repo_switched": {
        "ja": "<code>{name}/</code> に切り替えたよ{badges}",
        "en": "Switched to <code>{name}/</code>{badges}",
    },
    # /repo - workspace error
    "repo_workspace_error": {
        "ja": "ワークスペースの読み込みに失敗したよ: {error}",
        "en": "Error reading workspace: {error}",
    },
    # /repo - no repos
    "repo_empty": {
        "ja": (
            "<code>{path}</code> にリポジトリがないよ\n"
            '「clone org/repo」みたいに言ってくれたらクローンするよ'
        ),
        "en": (
            "No repos in <code>{path}</code>.\n"
            'Clone one by telling me, e.g. <i>"clone org/repo"</i>.'
        ),
    },
    # /repo - list header
    "repo_list_header": {
        "ja": "<b>リポジトリ</b>",
        "en": "<b>Repos</b>",
    },
    # Auth: system unavailable
    "auth_unavailable": {
        "ja": "認証システムが利用できないよ。しばらく待ってからもう一度試してね",
        "en": "Authentication system unavailable. Please try again later.",
    },
    # Auth: welcome
    "auth_welcome": {
        "ja": "認証されたよ!\nセッション開始: {time}",
        "en": "Welcome! You are now authenticated.\nSession started at {time}",
    },
    # Auth: failed
    "auth_failed": {
        "ja": (
            "<b>認証が必要だよ</b>\n\n"
            "このBotを使う権限がないみたい\n"
            "管理者にアクセスを依頼してね\n\n"
            "あなたのTelegram ID: <code>{user_id}</code>\n"
            "このIDを管理者に共有してね"
        ),
        "en": (
            "<b>Authentication Required</b>\n\n"
            "You are not authorized to use this bot.\n"
            "Please contact the administrator for access.\n\n"
            "Your Telegram ID: <code>{user_id}</code>\n"
            "Share this ID with the administrator to request access."
        ),
    },
    # Auth: require_auth
    "auth_required": {
        "ja": "このコマンドを使うには認証が必要だよ",
        "en": "Authentication required to use this command.",
    },
    # Error handler messages
    "error_auth": {
        "ja": "認証が必要だよ。管理者に連絡してね",
        "en": "Authentication required. Please contact the administrator.",
    },
    "error_security": {
        "ja": "セキュリティ違反を検出したよ。このインシデントは記録されたよ",
        "en": "Security violation detected. This incident has been logged.",
    },
    "error_rate_limit": {
        "ja": "レート制限に達したよ。少し待ってからもう一度送ってね",
        "en": "Rate limit exceeded. Please wait before sending more messages.",
    },
    "error_config": {
        "ja": "設定エラーだよ。管理者に連絡してね",
        "en": "Configuration error. Please contact the administrator.",
    },
    "error_timeout": {
        "ja": "タイムアウトしたよ。もう少し簡単なリクエストで試してみてね",
        "en": "Operation timed out. Please try again with a simpler request.",
    },
    "error_unexpected": {
        "ja": "予期しないエラーが起きたよ。もう一度試してみてね",
        "en": "An unexpected error occurred. Please try again.",
    },
    # Bot command descriptions
    "cmd_start": {
        "ja": "Botを開始",
        "en": "Start the bot",
    },
    "cmd_new": {
        "ja": "新しいセッションを開始",
        "en": "Start a fresh session",
    },
    "cmd_status": {
        "ja": "セッション状態を表示",
        "en": "Show session status",
    },
    "cmd_verbose": {
        "ja": "出力の詳細度を設定 (0/1/2)",
        "en": "Set output verbosity (0/1/2)",
    },
    "cmd_repo": {
        "ja": "リポジトリ一覧 / ワークスペース切替",
        "en": "List repos / switch workspace",
    },
    "cmd_sync_threads": {
        "ja": "プロジェクトトピックを同期",
        "en": "Sync project topics",
    },
}

# Verbose level labels
_VERBOSE_LABELS: Dict[str, Dict[int, str]] = {
    "ja": {0: "静か", 1: "通常", 2: "詳細"},
    "en": {0: "quiet", 1: "normal", 2: "detailed"},
}


def t(key: str, lang: str = "en", **kwargs: object) -> str:
    """Look up a translated message.

    Args:
        key: Message key (e.g. "welcome", "session_reset").
        lang: Language code ("ja" or "en"). Falls back to "en".
        **kwargs: Format placeholders.

    Returns:
        Formatted translated string.
    """
    messages = _MESSAGES.get(key)
    if not messages:
        return key
    text = messages.get(lang) or messages.get("en", key)
    if kwargs:
        text = text.format(**kwargs)
    return text


def verbose_label(level: int, lang: str = "en") -> str:
    """Return the human-readable label for a verbose level."""
    labels = _VERBOSE_LABELS.get(lang, _VERBOSE_LABELS["en"])
    return labels.get(level, "?")
