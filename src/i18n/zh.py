"""Chinese translations for Claude Code Telegram Bot."""

TRANSLATIONS: dict[str, str] = {
    # --- Agentic /start ---
    "start.private_topics_mode": (
        "\U0001f6ab <b>\u79c1\u4eba\u8a71\u984c\u6a21\u5f0f</b>\n\n"
        "\u8acb\u5728\u79c1\u4eba\u804a\u5929\u4e2d\u4f7f\u7528\u6b64\u6a5f\u5668\u4eba\uff0c\u4e26\u57f7\u884c <code>/start</code>\u3002"
    ),
    "start.topics_synced": (
        "\n\n\U0001f9f5 \u8a71\u984c\u5df2\u540c\u6b65\uff08\u5efa\u7acb {created} \u500b\uff0c\u8907\u7528 {reused} \u500b\uff09\u3002"
    ),
    "start.topic_sync_failed": (
        "\n\n\U0001f9f5 \u8a71\u984c\u540c\u6b65\u5931\u6557\u3002\u8acb\u57f7\u884c /sync_threads \u91cd\u8a66\u3002"
    ),
    "start.welcome": (
        "\u4f60\u597d {name}\uff01\u6211\u662f\u4f60\u7684 AI \u7a0b\u5f0f\u52a9\u624b\u3002\n"
        "\u544a\u8a34\u6211\u4f60\u9700\u8981\u4ec0\u9ebc \u2014 \u6211\u53ef\u4ee5\u8b80\u53d6\u3001\u7de8\u5beb\u548c\u57f7\u884c\u7a0b\u5f0f\u3002\n\n"
        "\u5de5\u4f5c\u76ee\u9304\uff1a{dir_display}\n"
        "\u6307\u4ee4\uff1a/new\uff08\u91cd\u7f6e\uff09\u00b7 /status"
    ),

    # --- Agentic /new ---
    "new.reset": "\u5de5\u4f5c\u968e\u6bb5\u5df2\u91cd\u7f6e\u3002\u63a5\u4e0b\u4f86\u8981\u505a\u4ec0\u9ebc\uff1f",

    # --- Agentic /status ---
    "status.line": "\U0001f4c2 {dir_display} \u00b7 \u5de5\u4f5c\u968e\u6bb5\uff1a{session_status}{cost_str}",

    # --- Agentic /verbose ---
    "verbose.current": (
        "\u8a73\u7d30\u7a0b\u5ea6\uff1a<b>{level}</b>\uff08{label}\uff09\n\n"
        "\u7528\u6cd5\uff1a<code>/verbose 0|1|2</code>\n"
        "  0 = \u7c21\u6f54\uff08\u50c5\u986f\u793a\u6700\u7d42\u56de\u61c9\uff09\n"
        "  1 = \u6b63\u5e38\uff08\u5de5\u5177 + \u63a8\u7406\u904e\u7a0b\uff09\n"
        "  2 = \u8a73\u7d30\uff08\u5de5\u5177\u8f38\u5165 + \u63a8\u7406\u904e\u7a0b\uff09"
    ),
    "verbose.invalid": "\u8acb\u4f7f\u7528\uff1a/verbose 0\u3001/verbose 1 \u6216 /verbose 2",
    "verbose.set": "\u8a73\u7d30\u7a0b\u5ea6\u5df2\u8a2d\u5b9a\u70ba <b>{level}</b>\uff08{label}\uff09",
    "verbose.quiet": "\u7c21\u6f54",
    "verbose.normal": "\u6b63\u5e38",
    "verbose.detailed": "\u8a73\u7d30",

    # --- Progress ---
    "progress.working": "\u8655\u7406\u4e2d...",
    "progress.transcribing": "\u8f49\u5beb\u4e2d...",
    "progress.earlier_entries": "...\uff08\u524d {count} \u689d\u8a18\u9304\uff09",

    # --- Errors ---
    "error.claude_unavailable": "Claude \u6574\u5408\u4e0d\u53ef\u7528\uff0c\u8acb\u6aa2\u67e5\u914d\u7f6e\u3002",
    "error.delivery_failed": (
        "\u7121\u6cd5\u50b3\u905e\u56de\u61c9\uff08Telegram \u932f\u8aa4\uff1a{error}\uff09\u3002\u8acb\u91cd\u8a66\u3002"
    ),
    "error.file_rejected": "\u6a94\u6848\u88ab\u62d2\u7d55\uff1a{error}",
    "error.file_too_large": "\u6a94\u6848\u904e\u5927\uff08{size}MB\uff09\u3002\u4e0a\u9650\uff1a10MB\u3002",
    "error.unsupported_format": "\u4e0d\u652f\u63f4\u7684\u6a94\u6848\u683c\u5f0f\uff0c\u5fc5\u9808\u662f\u6587\u5b57\u6a94\uff08UTF-8\uff09\u3002",
    "error.photo_unavailable": "\u7167\u7247\u8655\u7406\u529f\u80fd\u4e0d\u53ef\u7528\u3002",
    "error.rate_limited": "\u23f1\ufe0f {message}",
    "error.workspace_read": "\u8b80\u53d6\u5de5\u4f5c\u5340\u932f\u8aa4\uff1a{error}",
    "error.dir_not_found": "\u627e\u4e0d\u5230\u76ee\u9304\uff1a<code>{name}</code>",
    "error.a2a_not_enabled": "A2A \u672a\u555f\u7528\u3002",

    # --- /repo ---
    "repo.switched": "\u5df2\u5207\u63db\u5230 <code>{name}/</code>{git_badge}{session_badge}",
    "repo.git_badge": "\uff08git\uff09",
    "repo.session_resumed": " \u00b7 \u5df2\u6062\u5fa9\u5de5\u4f5c\u968e\u6bb5",
    "repo.no_repos": (
        "<code>{path}</code> \u4e2d\u6c92\u6709\u5009\u5eab\u3002\n"
        '\u544a\u8a34\u6211\u4f86\u514b\u9686\uff0c\u4f8b\u5982 <i>"clone org/repo"</i>\u3002'
    ),
    "repo.title": "<b>\u5009\u5eab\u5217\u8868</b>",

    # --- /lang ---
    "lang.current": (
        "\u76ee\u524d\u8a9e\u8a00\uff1a<b>{lang_name}</b>\n\n"
        "\u7528\u6cd5\uff1a<code>/lang en</code> \u6216 <code>/lang zh</code>"
    ),
    "lang.set": "\u8a9e\u8a00\u5df2\u8a2d\u5b9a\u70ba <b>{lang_name}</b>",
    "lang.invalid": (
        "\u4e0d\u652f\u63f4\u7684\u8a9e\u8a00\uff1a<code>{lang}</code>\n"
        "\u652f\u63f4\uff1a{supported}"
    ),
    "lang.en": "English",
    "lang.zh": "\u4e2d\u6587",

    # --- Voice ---
    "voice.unavailable": (
        "\u8a9e\u97f3\u8655\u7406\u529f\u80fd\u4e0d\u53ef\u7528\u3002"
        "\u8acb\u8a2d\u5b9a {api_key_env}\uff08{provider_name}\uff09\u4e26\u5b89\u88dd"
        '\u8a9e\u97f3\u64f4\u5c55\uff1apip install "claude-code-telegram[voice]"'
    ),

    # --- A2A ---
    "a2a.agent_usage": (
        "<b>\u7528\u6cd5\uff1a</b> <code>/agent &lt;\u5225\u540d&gt; &lt;\u8a0a\u606f&gt;</code>\n\n"
        "\u4f7f\u7528 <code>/agents</code> \u67e5\u770b\u5df2\u8a3b\u518a\u7684\u4ee3\u7406\u3002"
    ),
    "a2a.agent_not_found": (
        "\u627e\u4e0d\u5230\u5225\u540d\u70ba <code>{alias}</code> \u7684\u4ee3\u7406\u3002\n"
        "\u8acb\u5148\u57f7\u884c <code>/agents add {alias} &lt;url&gt;</code>\u3002"
    ),
    "a2a.no_agents": (
        "\U0001f916 <b>\u672a\u8a3b\u518a\u4efb\u4f55 A2A \u4ee3\u7406\u3002</b>\n\n"
        "\u8a3b\u518a\u4e00\u500b\uff1a\n"
        "<code>/agents add mybot https://example.com</code>"
    ),
    "a2a.agents_title": "\U0001f916 <b>\u5df2\u8a3b\u518a\u7684 A2A \u4ee3\u7406</b>\n",
    "a2a.agent_registered": (
        "\u2705 \u4ee3\u7406\u5df2\u8a3b\u518a\uff1a\n"
        "  \u5225\u540d\uff1a<code>{alias}</code>\n"
        "  \u540d\u7a31\uff1a{name}\n"
        "  \u7db2\u5740\uff1a{url}\n\n"
        "\u4f7f\u7528\uff1a<code>/agent {alias} &lt;\u8a0a\u606f&gt;</code>"
    ),
    "a2a.agent_removed": "\U0001f5d1 \u4ee3\u7406 <code>{alias}</code> \u5df2\u79fb\u9664\u3002",
    "a2a.agent_not_exists": "\u627e\u4e0d\u5230\u5225\u540d\u70ba <code>{alias}</code> \u7684\u4ee3\u7406\u3002",
    "a2a.agents_usage": (
        "<b>\u7528\u6cd5\uff1a</b>\n"
        "<code>/agents</code> \u2014 \u5217\u51fa\u4ee3\u7406\n"
        "<code>/agents add &lt;\u5225\u540d&gt; &lt;\u7db2\u5740&gt;</code> \u2014 \u8a3b\u518a\n"
        "<code>/agents remove &lt;\u5225\u540d&gt;</code> \u2014 \u53d6\u6d88\u8a3b\u518a"
    ),
    "a2a.call_failed": (
        "\u274c \u547c\u53eb <code>{alias}</code> \u5931\u6557\uff1a\n"
        "<code>{error}</code>"
    ),
    "a2a.resolve_failed": (
        "\u274c \u7121\u6cd5\u89e3\u6790\u4ee3\u7406\uff1a\n"
        "<code>{error}</code>"
    ),

    # --- Thread mode ---
    "thread.misconfigured": (
        "\u274c <b>\u5c08\u6848\u57f7\u884c\u7dd2\u6a21\u5f0f\u914d\u7f6e\u932f\u8aa4</b>\n\n"
        "\u57f7\u884c\u7dd2\u7ba1\u7406\u5668\u672a\u521d\u59cb\u5316\u3002"
    ),

    # --- Bot commands (menu descriptions) ---
    "cmd.start": "\u555f\u52d5\u6a5f\u5668\u4eba",
    "cmd.new": "\u958b\u59cb\u65b0\u7684\u5de5\u4f5c\u968e\u6bb5",
    "cmd.status": "\u986f\u793a\u5de5\u4f5c\u968e\u6bb5\u72c0\u614b",
    "cmd.verbose": "\u8a2d\u5b9a\u8f38\u51fa\u8a73\u7d30\u7a0b\u5ea6 (0/1/2)",
    "cmd.repo": "\u5217\u51fa\u5009\u5eab / \u5207\u63db\u5de5\u4f5c\u5340",
    "cmd.restart": "\u91cd\u65b0\u555f\u52d5\u6a5f\u5668\u4eba",
    "cmd.sync_threads": "\u540c\u6b65\u5c08\u6848\u8a71\u984c",
    "cmd.lang": "\u8a2d\u5b9a\u8a9e\u8a00 (en/zh)",
    "cmd.help": "\u986f\u793a\u53ef\u7528\u6307\u4ee4",
    "cmd.continue": "\u7e7c\u7e8c\u4e0a\u6b21\u7684\u5de5\u4f5c\u968e\u6bb5",
    "cmd.end": "\u7d50\u675f\u7576\u524d\u5de5\u4f5c\u968e\u6bb5\u4e26\u6e05\u9664\u4e0a\u4e0b\u6587",
    "cmd.ls": "\u5217\u51fa\u7576\u524d\u76ee\u9304\u7684\u6a94\u6848",
    "cmd.cd": "\u5207\u63db\u76ee\u9304\uff08\u6062\u5fa9\u5c08\u6848\u5de5\u4f5c\u968e\u6bb5\uff09",
    "cmd.pwd": "\u986f\u793a\u7576\u524d\u76ee\u9304",
    "cmd.projects": "\u986f\u793a\u6240\u6709\u5c08\u6848",
    "cmd.export": "\u532f\u51fa\u7576\u524d\u5de5\u4f5c\u968e\u6bb5",
    "cmd.actions": "\u986f\u793a\u5feb\u901f\u64cd\u4f5c",
    "cmd.git": "Git \u5009\u5eab\u6307\u4ee4",

    # --- Classic /start ---
    "classic.welcome": (
        "\U0001f44b \u6b61\u8fce\u4f7f\u7528 Claude Code Telegram Bot\uff0c{name}\uff01\n\n"
        "\U0001f916 \u6211\u53ef\u4ee5\u5e6b\u4f60\u900f\u904e Telegram \u9060\u7aef\u5b58\u53d6 Claude Code\u3002\n\n"
        "<b>\u53ef\u7528\u6307\u4ee4\uff1a</b>\n"
        "\u2022 <code>/help</code> - \u986f\u793a\u8a73\u7d30\u8aaa\u660e\n"
        "\u2022 <code>/new</code> - \u958b\u59cb\u65b0\u7684 Claude \u5de5\u4f5c\u968e\u6bb5\n"
        "\u2022 <code>/ls</code> - \u5217\u51fa\u7576\u524d\u76ee\u9304\u7684\u6a94\u6848\n"
        "\u2022 <code>/cd &lt;\u76ee\u9304&gt;</code> - \u5207\u63db\u76ee\u9304\n"
        "\u2022 <code>/projects</code> - \u986f\u793a\u53ef\u7528\u5c08\u6848\n"
        "\u2022 <code>/status</code> - \u986f\u793a\u5de5\u4f5c\u968e\u6bb5\u72c0\u614b\n"
        "\u2022 <code>/actions</code> - \u986f\u793a\u5feb\u901f\u64cd\u4f5c\n"
        "\u2022 <code>/git</code> - Git \u5009\u5eab\u6307\u4ee4\n\n"
        "<b>\u5feb\u901f\u958b\u59cb\uff1a</b>\n"
        "1. \u4f7f\u7528 <code>/projects</code> \u67e5\u770b\u53ef\u7528\u5c08\u6848\n"
        "2. \u4f7f\u7528 <code>/cd &lt;\u5c08\u6848&gt;</code> \u5207\u63db\u5230\u5c08\u6848\n"
        "3. \u767c\u9001\u4efb\u4f55\u8a0a\u606f\u958b\u59cb\u8207 Claude \u7de8\u7a0b\uff01\n\n"
        "\U0001f512 \u4f60\u7684\u5b58\u53d6\u5df2\u53d7\u4fdd\u8b77\uff0c\u6240\u6709\u64cd\u4f5c\u5747\u5df2\u8a18\u9304\u3002\n"
        "\U0001f4ca \u4f7f\u7528 <code>/status</code> \u67e5\u770b\u4f60\u7684\u4f7f\u7528\u984d\u5ea6\u3002"
    ),

    # --- Classic /help ---
    "classic.help": (
        "\U0001f916 <b>Claude Code Telegram Bot \u8aaa\u660e</b>\n\n"
        "<b>\u5c0e\u822a\u6307\u4ee4\uff1a</b>\n"
        "\u2022 <code>/ls</code> - \u5217\u51fa\u6a94\u6848\u548c\u76ee\u9304\n"
        "\u2022 <code>/cd &lt;\u76ee\u9304&gt;</code> - \u5207\u63db\u76ee\u9304\n"
        "\u2022 <code>/pwd</code> - \u986f\u793a\u7576\u524d\u76ee\u9304\n"
        "\u2022 <code>/projects</code> - \u986f\u793a\u53ef\u7528\u5c08\u6848\n\n"
        "<b>\u5de5\u4f5c\u968e\u6bb5\u6307\u4ee4\uff1a</b>\n"
        "\u2022 <code>/new</code> - \u6e05\u9664\u4e0a\u4e0b\u6587\u4e26\u958b\u59cb\u65b0\u7684\u5de5\u4f5c\u968e\u6bb5\n"
        "\u2022 <code>/continue [\u8a0a\u606f]</code> - \u7e7c\u7e8c\u4e0a\u6b21\u7684\u5de5\u4f5c\u968e\u6bb5\n"
        "\u2022 <code>/end</code> - \u7d50\u675f\u7576\u524d\u5de5\u4f5c\u968e\u6bb5\u4e26\u6e05\u9664\u4e0a\u4e0b\u6587\n"
        "\u2022 <code>/status</code> - \u986f\u793a\u5de5\u4f5c\u968e\u6bb5\u548c\u4f7f\u7528\u72c0\u614b\n"
        "\u2022 <code>/export</code> - \u532f\u51fa\u5de5\u4f5c\u968e\u6bb5\u6b77\u53f2\n"
        "\u2022 <code>/actions</code> - \u986f\u793a\u5feb\u901f\u64cd\u4f5c\n"
        "\u2022 <code>/git</code> - Git \u5009\u5eab\u8cc7\u8a0a\n\n"
        "<b>\u5de5\u4f5c\u968e\u6bb5\u884c\u70ba\uff1a</b>\n"
        "\u2022 \u5de5\u4f5c\u968e\u6bb5\u6703\u6309\u5c08\u6848\u76ee\u9304\u81ea\u52d5\u7dad\u8b77\n"
        "\u2022 \u4f7f\u7528 <code>/cd</code> \u5207\u63db\u76ee\u9304\u6642\u6703\u6062\u5fa9\u8a72\u5c08\u6848\u7684\u5de5\u4f5c\u968e\u6bb5\n"
        "\u2022 \u4f7f\u7528 <code>/new</code> \u6216 <code>/end</code> \u660e\u78ba\u6e05\u9664\u5de5\u4f5c\u968e\u6bb5\u4e0a\u4e0b\u6587\n"
        "\u2022 \u5de5\u4f5c\u968e\u6bb5\u5728\u6a5f\u5668\u4eba\u91cd\u555f\u5f8c\u4ecd\u7136\u4fdd\u7559\n\n"
        "<b>\u4f7f\u7528\u7bc4\u4f8b\uff1a</b>\n"
        "\u2022 <code>cd myproject</code> - \u9032\u5165\u5c08\u6848\u76ee\u9304\n"
        "\u2022 <code>ls</code> - \u67e5\u770b\u7576\u524d\u76ee\u9304\u5167\u5bb9\n"
        "\u2022 <code>\u5efa\u7acb\u4e00\u500b\u7c21\u55ae\u7684 Python \u8173\u672c</code> - \u8b93 Claude \u5e6b\u4f60\u5beb\u7a0b\u5f0f\n"
        "\u2022 \u50b3\u9001\u6a94\u6848\u8b93 Claude \u5e6b\u4f60\u5be9\u67e5\n\n"
        "<b>\u6a94\u6848\u64cd\u4f5c\uff1a</b>\n"
        "\u2022 \u50b3\u9001\u6587\u5b57\u6a94\u6848\uff08.py\u3001.js\u3001.md \u7b49\uff09\u9032\u884c\u5be9\u67e5\n"
        "\u2022 Claude \u53ef\u4ee5\u8b80\u53d6\u3001\u4fee\u6539\u548c\u5efa\u7acb\u6a94\u6848\n"
        "\u2022 \u6240\u6709\u6a94\u6848\u64cd\u4f5c\u90fd\u5728\u4f60\u7684\u6388\u6b0a\u76ee\u9304\u5167\n\n"
        "<b>\u5b89\u5168\u529f\u80fd\uff1a</b>\n"
        "\u2022 \U0001f512 \u8def\u5f91\u904d\u6b77\u4fdd\u8b77\n"
        "\u2022 \u23f1\ufe0f \u901f\u7387\u9650\u5236\u4ee5\u9632\u6b62\u6fe5\u7528\n"
        "\u2022 \U0001f4ca \u4f7f\u7528\u91cf\u8ffd\u8e64\u548c\u9650\u5236\n"
        "\u2022 \U0001f6e1\ufe0f \u8f38\u5165\u9a57\u8b49\u548c\u6d88\u6bd2\n\n"
        "<b>\u5c0f\u6280\u5de7\uff1a</b>\n"
        "\u2022 \u4f7f\u7528\u5177\u9ad4\u3001\u6e05\u6670\u7684\u8acb\u6c42\u4ee5\u7372\u5f97\u6700\u4f73\u7d50\u679c\n"
        "\u2022 \u4f7f\u7528 <code>/status</code> \u76e3\u63a7\u4f60\u7684\u4f7f\u7528\u91cf\n"
        "\u2022 \u53ef\u7528\u6642\u4f7f\u7528\u5feb\u901f\u64cd\u4f5c\u6309\u9215\n"
        "\u2022 \u4e0a\u50b3\u7684\u6a94\u6848\u6703\u81ea\u52d5\u7531 Claude \u8655\u7406\n\n"
        "\u9700\u8981\u66f4\u591a\u5e6b\u52a9\uff1f\u8acb\u806f\u7e6b\u4f60\u7684\u7ba1\u7406\u54e1\u3002"
    ),

    # --- Classic /new ---
    "classic.new.cleared": (
        "\n\U0001f5d1\ufe0f \u5148\u524d\u7684\u5de5\u4f5c\u968e\u6bb5 <code>{session_id}...</code> \u5df2\u6e05\u9664\u3002"
    ),
    "classic.new.message": (
        "\U0001f195 <b>\u65b0\u7684 Claude Code \u5de5\u4f5c\u968e\u6bb5</b>\n\n"
        "\U0001f4c2 \u5de5\u4f5c\u76ee\u9304\uff1a<code>{path}/</code>{cleared_info}\n\n"
        "\u4e0a\u4e0b\u6587\u5df2\u6e05\u9664\u3002\u767c\u9001\u8a0a\u606f\u958b\u59cb\u65b0\u7684\u5de5\u4f5c\uff0c"
        "\u6216\u4f7f\u7528\u4e0b\u65b9\u6309\u9215\uff1a"
    ),

    # --- Classic /continue ---
    "classic.continue.continuing": (
        "\U0001f504 <b>\u7e7c\u7e8c\u5de5\u4f5c\u968e\u6bb5</b>\n\n"
        "\u5de5\u4f5c\u968e\u6bb5 ID\uff1a<code>{session_id}...</code>\n"
        "\u76ee\u9304\uff1a<code>{path}/</code>\n\n"
        "{status}"
    ),
    "classic.continue.processing": "\u6b63\u5728\u8655\u7406\u4f60\u7684\u8a0a\u606f...",
    "classic.continue.resuming": "\u5f9e\u4e0a\u6b21\u4e2d\u65b7\u8655\u7e7c\u7e8c...",
    "classic.continue.searching": (
        "\U0001f50d <b>\u5c0b\u627e\u6700\u8fd1\u7684\u5de5\u4f5c\u968e\u6bb5</b>\n\n"
        "\u6b63\u5728\u6b64\u76ee\u9304\u4e2d\u641c\u5c0b\u4f60\u6700\u8fd1\u7684\u5de5\u4f5c\u968e\u6bb5..."
    ),
    "classic.continue.no_session": (
        "\u274c <b>\u627e\u4e0d\u5230\u5de5\u4f5c\u968e\u6bb5</b>\n\n"
        "\u5728\u6b64\u76ee\u9304\u4e2d\u627e\u4e0d\u5230\u6700\u8fd1\u7684 Claude \u5de5\u4f5c\u968e\u6bb5\u3002\n"
        "\u76ee\u9304\uff1a<code>{path}/</code>\n\n"
        "<b>\u4f60\u53ef\u4ee5\uff1a</b>\n"
        "\u2022 \u4f7f\u7528 <code>/new</code> \u958b\u59cb\u65b0\u7684\u5de5\u4f5c\u968e\u6bb5\n"
        "\u2022 \u4f7f\u7528 <code>/status</code> \u67e5\u770b\u4f60\u7684\u5de5\u4f5c\u968e\u6bb5\n"
        "\u2022 \u4f7f\u7528 <code>/cd</code> \u5207\u63db\u5230\u5176\u4ed6\u76ee\u9304"
    ),
    "classic.continue.error": (
        "\u274c <b>\u7e7c\u7e8c\u5de5\u4f5c\u968e\u6bb5\u6642\u767c\u751f\u932f\u8aa4</b>\n\n"
        "\u5617\u8a66\u7e7c\u7e8c\u4f60\u7684\u5de5\u4f5c\u968e\u6bb5\u6642\u767c\u751f\u932f\u8aa4\uff1a\n\n"
        "<code>{error}</code>\n\n"
        "<b>\u5efa\u8b70\uff1a</b>\n"
        "\u2022 \u5617\u8a66\u4f7f\u7528 <code>/new</code> \u958b\u59cb\u65b0\u7684\u5de5\u4f5c\u968e\u6bb5\n"
        "\u2022 \u4f7f\u7528 <code>/status</code> \u67e5\u770b\u4f60\u7684\u5de5\u4f5c\u968e\u6bb5\u72c0\u614b\n"
        "\u2022 \u5982\u554f\u984c\u6301\u7e8c\u8acb\u806f\u7e6b\u7ba1\u7406\u54e1"
    ),
    "classic.continue.not_available": (
        "\u274c <b>Claude \u6574\u5408\u4e0d\u53ef\u7528</b>\n\n"
        "Claude \u6574\u5408\u672a\u6b63\u78ba\u914d\u7f6e\u3002"
    ),

    # --- Classic /ls ---
    "classic.ls.empty": "\U0001f4c2 <code>{path}/</code>\n\n<i>\uff08\u7a7a\u76ee\u9304\uff09</i>",
    "classic.ls.more_items": "...\u53e6\u6709 {count} \u500b\u9805\u76ee",
    "classic.ls.error": "\u274c \u5217\u51fa\u76ee\u9304\u932f\u8aa4\uff1a{error}",

    # --- Classic /cd ---
    "classic.cd.usage": (
        "<b>\u7528\u6cd5\uff1a</b> <code>/cd &lt;\u76ee\u9304&gt;</code>\n\n"
        "<b>\u7bc4\u4f8b\uff1a</b>\n"
        "\u2022 <code>/cd myproject</code> - \u9032\u5165\u5b50\u76ee\u9304\n"
        "\u2022 <code>/cd ..</code> - \u8fd4\u56de\u4e0a\u4e00\u5c64\n"
        "\u2022 <code>/cd /</code> - \u56de\u5230\u6388\u6b0a\u76ee\u9304\u7684\u6839\u76ee\u9304\n\n"
        "<b>\u5c0f\u6280\u5de7\uff1a</b>\n"
        "\u2022 \u4f7f\u7528 <code>/ls</code> \u67e5\u770b\u53ef\u7528\u76ee\u9304\n"
        "\u2022 \u4f7f\u7528 <code>/projects</code> \u67e5\u770b\u6240\u6709\u5c08\u6848"
    ),
    "classic.cd.access_denied": "\u274c <b>\u5b58\u53d6\u88ab\u62d2\u7d55</b>\n\n{error}",
    "classic.cd.thread_restricted": (
        "\u274c <b>\u5b58\u53d6\u88ab\u62d2\u7d55</b>\n\n"
        "\u5728\u57f7\u884c\u7dd2\u6a21\u5f0f\u4e0b\uff0c\u5c0e\u822a\u50c5\u9650\u65bc\u7576\u524d\u5c08\u6848\u6839\u76ee\u9304\u3002"
    ),
    "classic.cd.not_found": (
        "\u274c <b>\u627e\u4e0d\u5230\u76ee\u9304</b>\n\n"
        "<code>{path}</code> \u4e0d\u5b58\u5728\u3002"
    ),
    "classic.cd.not_dir": (
        "\u274c <b>\u4e0d\u662f\u76ee\u9304</b>\n\n"
        "<code>{path}</code> \u4e0d\u662f\u76ee\u9304\u3002"
    ),
    "classic.cd.changed": (
        "\u2705 <b>\u76ee\u9304\u5df2\u5207\u63db</b>\n\n"
        "\U0001f4c2 \u7576\u524d\u76ee\u9304\uff1a<code>{path}</code>{session_info}"
    ),
    "classic.cd.session_resumed": (
        "\n\U0001f504 \u5df2\u6062\u5fa9\u5de5\u4f5c\u968e\u6bb5 <code>{session_id}...</code>"
        "\uff08{message_count} \u689d\u8a0a\u606f\uff09"
    ),
    "classic.cd.no_session": (
        "\n\U0001f195 \u7121\u73fe\u6709\u5de5\u4f5c\u968e\u6bb5\u3002\u767c\u9001\u8a0a\u606f\u958b\u59cb\u65b0\u7684\u5de5\u4f5c\u968e\u6bb5\u3002"
    ),
    "classic.cd.error": "\u274c <b>\u5207\u63db\u76ee\u9304\u932f\u8aa4</b>\n\n{error}",

    # --- Classic /pwd ---
    "classic.pwd": (
        "\U0001f4cd <b>\u7576\u524d\u76ee\u9304</b>\n\n"
        "\u76f8\u5c0d\u8def\u5f91\uff1a<code>{relative}/</code>\n"
        "\u7d55\u5c0d\u8def\u5f91\uff1a<code>{absolute}</code>"
    ),

    # --- Classic /projects ---
    "classic.projects.registry_error": (
        "\u274c <b>\u5c08\u6848\u8a3b\u518a\u8868\u672a\u521d\u59cb\u5316\u3002</b>"
    ),
    "classic.projects.no_projects": (
        "\U0001f4c1 <b>\u627e\u4e0d\u5230\u5c08\u6848</b>\n\n"
        "\u5c08\u6848\u914d\u7f6e\u4e2d\u627e\u4e0d\u5230\u5df2\u555f\u7528\u7684\u5c08\u6848\u3002"
    ),
    "classic.projects.configured": "\U0001f4c1 <b>\u5df2\u914d\u7f6e\u7684\u5c08\u6848</b>\n\n{list}",
    "classic.projects.no_dirs": (
        "\U0001f4c1 <b>\u627e\u4e0d\u5230\u5c08\u6848</b>\n\n"
        "\u4f60\u7684\u6388\u6b0a\u76ee\u9304\u4e2d\u6c92\u6709\u5b50\u76ee\u9304\u3002\n"
        "\u5efa\u7acb\u4e00\u4e9b\u76ee\u9304\u4f86\u7d44\u7e54\u4f60\u7684\u5c08\u6848\uff01"
    ),
    "classic.projects.available": (
        "\U0001f4c1 <b>\u53ef\u7528\u5c08\u6848</b>\n\n"
        "{list}\n\n"
        "\u9ede\u64ca\u4e0b\u65b9\u5c08\u6848\u5207\u63db\uff1a"
    ),
    "classic.projects.error": "\u274c \u8f09\u5165\u5c08\u6848\u932f\u8aa4\uff1a{error}",

    # --- Classic /status ---
    "classic.status.title": "\U0001f4ca <b>\u5de5\u4f5c\u968e\u6bb5\u72c0\u614b</b>",
    "classic.status.directory": "\U0001f4c2 \u76ee\u9304\uff1a<code>{path}/</code>",
    "classic.status.session_active": "\U0001f916 Claude \u5de5\u4f5c\u968e\u6bb5\uff1a\u2705 \u9032\u884c\u4e2d",
    "classic.status.session_none": "\U0001f916 Claude \u5de5\u4f5c\u968e\u6bb5\uff1a\u274c \u7121",
    "classic.status.usage": "\U0001f4b0 \u4f7f\u7528\u91cf\uff1a${current:.2f} / ${limit:.2f}\uff08{pct:.0f}%\uff09",
    "classic.status.usage_error": "\U0001f4b0 \u4f7f\u7528\u91cf\uff1a<i>\u7121\u6cd5\u53d6\u5f97</i>",
    "classic.status.last_update": "\U0001f550 \u6700\u5f8c\u66f4\u65b0\uff1a{time}",
    "classic.status.session_id": "\U0001f194 \u5de5\u4f5c\u968e\u6bb5 ID\uff1a<code>{id}...</code>",
    "classic.status.resumable": (
        "\U0001f504 \u53ef\u6062\u5fa9\uff1a<code>{id}...</code>\uff08{count} \u689d\u8a0a\u606f\uff09"
    ),
    "classic.status.auto_resume": "\U0001f4a1 \u5de5\u4f5c\u968e\u6bb5\u5c07\u5728\u4f60\u7684\u4e0b\u4e00\u689d\u8a0a\u606f\u6642\u81ea\u52d5\u6062\u5fa9",

    # --- Classic /export ---
    "classic.export.unavailable": (
        "\U0001f4e4 <b>\u532f\u51fa\u5de5\u4f5c\u968e\u6bb5</b>\n\n"
        "\u5de5\u4f5c\u968e\u6bb5\u532f\u51fa\u529f\u80fd\u4e0d\u53ef\u7528\u3002\n\n"
        "<b>\u898f\u5283\u4e2d\u7684\u529f\u80fd\uff1a</b>\n"
        "\u2022 \u532f\u51fa\u5c0d\u8a71\u6b77\u53f2\n"
        "\u2022 \u5132\u5b58\u5de5\u4f5c\u968e\u6bb5\u72c0\u614b\n"
        "\u2022 \u5206\u4eab\u5c0d\u8a71\n"
        "\u2022 \u5efa\u7acb\u5de5\u4f5c\u968e\u6bb5\u5099\u4efd"
    ),
    "classic.export.no_session": (
        "\u274c <b>\u7121\u9032\u884c\u4e2d\u7684\u5de5\u4f5c\u968e\u6bb5</b>\n\n"
        "\u6c92\u6709\u53ef\u532f\u51fa\u7684 Claude \u5de5\u4f5c\u968e\u6bb5\u3002\n\n"
        "<b>\u4f60\u53ef\u4ee5\uff1a</b>\n"
        "\u2022 \u4f7f\u7528 <code>/new</code> \u958b\u59cb\u65b0\u7684\u5de5\u4f5c\u968e\u6bb5\n"
        "\u2022 \u4f7f\u7528 <code>/continue</code> \u7e7c\u7e8c\u73fe\u6709\u7684\u5de5\u4f5c\u968e\u6bb5\n"
        "\u2022 \u4f7f\u7528 <code>/status</code> \u67e5\u770b\u4f60\u7684\u72c0\u614b"
    ),
    "classic.export.ready": (
        "\U0001f4e4 <b>\u532f\u51fa\u5de5\u4f5c\u968e\u6bb5</b>\n\n"
        "\u6e96\u5099\u532f\u51fa\u5de5\u4f5c\u968e\u6bb5\uff1a<code>{session_id}...</code>\n\n"
        "<b>\u9078\u64c7\u532f\u51fa\u683c\u5f0f\uff1a</b>"
    ),

    # --- Classic /end ---
    "classic.end.no_session": (
        "\u2139\ufe0f <b>\u7121\u9032\u884c\u4e2d\u7684\u5de5\u4f5c\u968e\u6bb5</b>\n\n"
        "\u6c92\u6709\u53ef\u7d50\u675f\u7684 Claude \u5de5\u4f5c\u968e\u6bb5\u3002\n\n"
        "<b>\u4f60\u53ef\u4ee5\uff1a</b>\n"
        "\u2022 \u4f7f\u7528 <code>/new</code> \u958b\u59cb\u65b0\u7684\u5de5\u4f5c\u968e\u6bb5\n"
        "\u2022 \u4f7f\u7528 <code>/status</code> \u67e5\u770b\u4f60\u7684\u5de5\u4f5c\u968e\u6bb5\u72c0\u614b\n"
        "\u2022 \u767c\u9001\u4efb\u4f55\u8a0a\u606f\u958b\u59cb\u5c0d\u8a71"
    ),
    "classic.end.ended": (
        "\u2705 <b>\u5de5\u4f5c\u968e\u6bb5\u5df2\u7d50\u675f</b>\n\n"
        "\u4f60\u7684 Claude \u5de5\u4f5c\u968e\u6bb5\u5df2\u7d42\u6b62\u3002\n\n"
        "<b>\u7576\u524d\u72c0\u614b\uff1a</b>\n"
        "\u2022 \u76ee\u9304\uff1a<code>{path}/</code>\n"
        "\u2022 \u5de5\u4f5c\u968e\u6bb5\uff1a\u7121\n"
        "\u2022 \u5df2\u6e96\u5099\u597d\u63a5\u53d7\u65b0\u6307\u4ee4\n\n"
        "<b>\u4e0b\u4e00\u6b65\uff1a</b>\n"
        "\u2022 \u4f7f\u7528 <code>/new</code> \u958b\u59cb\u65b0\u7684\u5de5\u4f5c\u968e\u6bb5\n"
        "\u2022 \u4f7f\u7528 <code>/status</code> \u67e5\u770b\u72c0\u614b\n"
        "\u2022 \u767c\u9001\u4efb\u4f55\u8a0a\u606f\u958b\u59cb\u65b0\u7684\u5c0d\u8a71"
    ),

    # --- Classic /actions ---
    "classic.actions.disabled": (
        "\u274c <b>\u5feb\u901f\u64cd\u4f5c\u5df2\u505c\u7528</b>\n\n"
        "\u5feb\u901f\u64cd\u4f5c\u529f\u80fd\u672a\u555f\u7528\u3002\n"
        "\u8acb\u806f\u7e6b\u7ba1\u7406\u54e1\u555f\u7528\u6b64\u529f\u80fd\u3002"
    ),
    "classic.actions.unavailable": (
        "\u274c <b>\u5feb\u901f\u64cd\u4f5c\u4e0d\u53ef\u7528</b>\n\n"
        "\u5feb\u901f\u64cd\u4f5c\u670d\u52d9\u4e0d\u53ef\u7528\u3002"
    ),
    "classic.actions.none": (
        "\U0001f916 <b>\u7121\u53ef\u7528\u64cd\u4f5c</b>\n\n"
        "\u7576\u524d\u4e0a\u4e0b\u6587\u6c92\u6709\u53ef\u7528\u7684\u5feb\u901f\u64cd\u4f5c\u3002\n\n"
        "<b>\u8a66\u8a66\uff1a</b>\n"
        "\u2022 \u4f7f\u7528 <code>/cd</code> \u5207\u63db\u5230\u5c08\u6848\u76ee\u9304\n"
        "\u2022 \u5efa\u7acb\u4e00\u4e9b\u7a0b\u5f0f\u78bc\u6a94\u6848\n"
        "\u2022 \u4f7f\u7528 <code>/new</code> \u958b\u59cb Claude \u5de5\u4f5c\u968e\u6bb5"
    ),
    "classic.actions.title": (
        "\u26a1 <b>\u5feb\u901f\u64cd\u4f5c</b>\n\n"
        "\U0001f4c2 \u4e0a\u4e0b\u6587\uff1a<code>{path}/</code>\n\n"
        "\u9078\u64c7\u8981\u57f7\u884c\u7684\u64cd\u4f5c\uff1a"
    ),
    "classic.actions.error": "\u274c <b>\u8f09\u5165\u64cd\u4f5c\u932f\u8aa4</b>\n\n{error}",

    # --- Classic /git ---
    "classic.git.disabled": (
        "\u274c <b>Git \u6574\u5408\u5df2\u505c\u7528</b>\n\n"
        "Git \u6574\u5408\u529f\u80fd\u672a\u555f\u7528\u3002\n"
        "\u8acb\u806f\u7e6b\u7ba1\u7406\u54e1\u555f\u7528\u6b64\u529f\u80fd\u3002"
    ),
    "classic.git.unavailable": (
        "\u274c <b>Git \u6574\u5408\u4e0d\u53ef\u7528</b>\n\n"
        "Git \u6574\u5408\u670d\u52d9\u4e0d\u53ef\u7528\u3002"
    ),
    "classic.git.not_repo": (
        "\U0001f4c2 <b>\u4e0d\u662f Git \u5009\u5eab</b>\n\n"
        "\u7576\u524d\u76ee\u9304 <code>{path}/</code> \u4e0d\u662f git \u5009\u5eab\u3002\n\n"
        "<b>\u9078\u9805\uff1a</b>\n"
        "\u2022 \u4f7f\u7528 <code>/cd</code> \u5207\u63db\u5230 git \u5009\u5eab\n"
        "\u2022 \u521d\u59cb\u5316\u65b0\u7684\u5009\u5eab\uff08\u8b93 Claude \u5e6b\u5fd9\uff09\n"
        "\u2022 \u514b\u9686\u73fe\u6709\u7684\u5009\u5eab\uff08\u8b93 Claude \u5e6b\u5fd9\uff09"
    ),
    "classic.git.error": "\u274c <b>Git \u932f\u8aa4</b>\n\n{error}",

    # --- Classic /restart ---
    "classic.restart": "\U0001f504 <b>\u6b63\u5728\u91cd\u65b0\u555f\u52d5\u6a5f\u5668\u4eba\u2026</b>\n\n\u99ac\u4e0a\u56de\u4f86\u3002",

    # --- Classic /sync_threads ---
    "classic.sync.disabled": "\u2139\ufe0f <b>\u5c08\u6848\u57f7\u884c\u7dd2\u6a21\u5f0f\u5df2\u505c\u7528\u3002</b>",
    "classic.sync.not_init": "\u274c <b>\u5c08\u6848\u57f7\u884c\u7dd2\u7ba1\u7406\u5668\u672a\u521d\u59cb\u5316\u3002</b>",
    "classic.sync.syncing": "\U0001f504 <b>\u6b63\u5728\u540c\u6b65\u5c08\u6848\u8a71\u984c...</b>",
    "classic.sync.private_error": (
        "\u274c <b>\u79c1\u4eba\u57f7\u884c\u7dd2\u6a21\u5f0f</b>\n\n"
        "\u8acb\u5728\u8207\u6a5f\u5668\u4eba\u7684\u79c1\u4eba\u804a\u5929\u4e2d\u57f7\u884c <code>/sync_threads</code>\u3002"
    ),
    "classic.sync.group_no_chat_id": (
        "\u274c <b>\u7fa4\u7d44\u57f7\u884c\u7dd2\u6a21\u5f0f\u914d\u7f6e\u932f\u8aa4</b>\n\n"
        "\u8acb\u5148\u8a2d\u5b9a <code>PROJECT_THREADS_CHAT_ID</code>\u3002"
    ),
    "classic.sync.group_wrong_chat": (
        "\u274c <b>\u7fa4\u7d44\u57f7\u884c\u7dd2\u6a21\u5f0f</b>\n\n"
        "\u8acb\u5728\u5df2\u914d\u7f6e\u7684\u5c08\u6848\u57f7\u884c\u7dd2\u7fa4\u7d44\u4e2d\u57f7\u884c <code>/sync_threads</code>\u3002"
    ),
    "classic.sync.no_config": (
        "\u274c <b>\u5c08\u6848\u57f7\u884c\u7dd2\u6a21\u5f0f\u914d\u7f6e\u932f\u8aa4</b>\n\n"
        "\u8acb\u5c07 <code>PROJECTS_CONFIG_PATH</code> \u8a2d\u5b9a\u70ba\u6709\u6548\u7684 YAML \u6a94\u6848\u3002"
    ),
    "classic.sync.complete": (
        "\u2705 <b>\u5c08\u6848\u8a71\u984c\u540c\u6b65\u5b8c\u6210</b>\n\n"
        "\u2022 \u5efa\u7acb\uff1a<b>{created}</b>\n"
        "\u2022 \u8907\u7528\uff1a<b>{reused}</b>\n"
        "\u2022 \u91cd\u65b0\u547d\u540d\uff1a<b>{renamed}</b>\n"
        "\u2022 \u91cd\u65b0\u958b\u555f\uff1a<b>{reopened}</b>\n"
        "\u2022 \u95dc\u9589\uff1a<b>{closed}</b>\n"
        "\u2022 \u505c\u7528\uff1a<b>{deactivated}</b>\n"
        "\u2022 \u5931\u6557\uff1a<b>{failed}</b>"
    ),
    "classic.sync.failed": (
        "\u274c <b>\u5c08\u6848\u8a71\u984c\u540c\u6b65\u5931\u6557</b>\n\n{error}"
    ),

    # --- Classic start sync section ---
    "classic.start.sync_section": (
        "\n\n\U0001f9f5 <b>\u5c08\u6848\u8a71\u984c\u5df2\u540c\u6b65</b>\n"
        "\u2022 \u5efa\u7acb\uff1a<b>{created}</b>\n"
        "\u2022 \u8907\u7528\uff1a<b>{reused}</b>\n"
        "\u2022 \u91cd\u65b0\u547d\u540d\uff1a<b>{renamed}</b>\n"
        "\u2022 \u5931\u6557\uff1a<b>{failed}</b>\n\n"
        "\u4f7f\u7528\u5c08\u6848\u8a71\u984c\u57f7\u884c\u7dd2\u958b\u59cb\u7de8\u7a0b\u3002"
    ),
    "classic.start.sync_warning": (
        "\n\n\u26a0\ufe0f <b>\u8a71\u984c\u540c\u6b65\u8b66\u544a</b>\n"
        "{error}\n\n"
        "\u57f7\u884c <code>/sync_threads</code> \u91cd\u8a66\u3002"
    ),
    "classic.start.misconfigured": (
        "\u274c <b>\u5c08\u6848\u57f7\u884c\u7dd2\u6a21\u5f0f\u914d\u7f6e\u932f\u8aa4</b>\n\n"
        "\u57f7\u884c\u7dd2\u7ba1\u7406\u5668\u672a\u521d\u59cb\u5316\u3002"
    ),

    # --- Button labels ---
    "btn.show_projects": "\U0001f4c1 \u986f\u793a\u5c08\u6848",
    "btn.get_help": "\u2753 \u53d6\u5f97\u5e6b\u52a9",
    "btn.new_session": "\U0001f195 \u65b0\u5de5\u4f5c\u968e\u6bb5",
    "btn.check_status": "\U0001f4ca \u67e5\u770b\u72c0\u614b",
    "btn.start_coding": "\U0001f4dd \u958b\u59cb\u7de8\u7a0b",
    "btn.change_project": "\U0001f4c1 \u5207\u63db\u5c08\u6848",
    "btn.quick_actions": "\U0001f4cb \u5feb\u901f\u64cd\u4f5c",
    "btn.help": "\u2753 \u5e6b\u52a9",
    "btn.go_up": "\u2b06\ufe0f \u8fd4\u56de\u4e0a\u5c64",
    "btn.go_root": "\U0001f3e0 \u56de\u5230\u6839\u76ee\u9304",
    "btn.refresh": "\U0001f504 \u91cd\u65b0\u6574\u7406",
    "btn.projects": "\U0001f4c1 \u5c08\u6848",
    "btn.list_files": "\U0001f4c1 \u6a94\u6848\u5217\u8868",
    "btn.continue": "\U0001f504 \u7e7c\u7e8c",
    "btn.start_session": "\U0001f195 \u958b\u59cb\u5de5\u4f5c\u968e\u6bb5",
    "btn.export": "\U0001f4e4 \u532f\u51fa",
    "btn.status": "\U0001f4ca \u72c0\u614b",
    "btn.show_diff": "\U0001f4ca \u986f\u793a\u5dee\u7570",
    "btn.show_log": "\U0001f4dc \u986f\u793a\u65e5\u8a8c",
    "btn.files": "\U0001f4c1 \u6a94\u6848",
    "btn.markdown": "\U0001f4dd Markdown",
    "btn.html": "\U0001f310 HTML",
    "btn.json": "\U0001f4cb JSON",
    "btn.cancel": "\u274c \u53d6\u6d88",

    # --- Error handler (core.py) ---
    "error.auth_required": "\U0001f512 \u9700\u8981\u9a57\u8b49\u3002\u8acb\u806f\u7e6b\u7ba1\u7406\u54e1\u3002",
    "error.security_violation": "\U0001f6e1\ufe0f \u5075\u6e2c\u5230\u5b89\u5168\u9055\u898f\u3002\u6b64\u4e8b\u4ef6\u5df2\u8a18\u9304\u3002",
    "error.rate_limit": "\u23f1\ufe0f \u5df2\u8d85\u904e\u901f\u7387\u9650\u5236\u3002\u8acb\u7a0d\u5f8c\u518d\u767c\u9001\u8a0a\u606f\u3002",
    "error.config": "\u2699\ufe0f \u914d\u7f6e\u932f\u8aa4\u3002\u8acb\u806f\u7e6b\u7ba1\u7406\u54e1\u3002",
    "error.timeout": "\u23f0 \u64cd\u4f5c\u903e\u6642\u3002\u8acb\u4f7f\u7528\u66f4\u7c21\u55ae\u7684\u8acb\u6c42\u91cd\u8a66\u3002",
    "error.unexpected": "\u274c \u767c\u751f\u4e86\u610f\u5916\u932f\u8aa4\u3002\u8acb\u91cd\u8a66\u3002",
}
