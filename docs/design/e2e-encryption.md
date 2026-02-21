# End-to-End Encryption Design for Claude Code Telegram

## Status: Draft / RFC

## Problem Statement

The bot currently stores all user prompts, Claude responses, tool invocations, and webhook payloads in **plaintext SQLite**. Messages traverse Telegram's cloud servers in cleartext (standard Bot API behavior). This creates multiple exposure points:

| Threat | Current Protection | Risk |
|---|---|---|
| Telegram server compromise | HTTPS in transit only | Telegram sees all plaintext messages |
| Bot server / DB file theft | None (plaintext SQLite) | Full history exposed |
| Memory dump on bot server | None | Active session data exposed |
| Anthropic-side access | Necessary for function | Prompts visible to Claude API |
| Insider access to DB | Audit log only | All fields readable |

## Constraints

Before exploring solutions, it's important to acknowledge hard constraints:

1. **Claude must see plaintext prompts.** The AI model cannot operate on ciphertext. Any E2E scheme where Claude is not an endpoint is fundamentally incompatible with the bot's purpose.
2. **Telegram Bot API has no Secret Chat support.** Bots cannot initiate or participate in Telegram's E2E-encrypted Secret Chats. All bot messages traverse Telegram's cloud servers.
3. **The bot must read messages to route them.** The orchestrator, middleware, and security layers all inspect message content before forwarding to Claude.

These constraints mean "true" E2E encryption (where only the user's device and some remote endpoint share a secret, with all intermediaries blind) is **not possible without a custom client-side component**. The design below presents a layered approach from most practical to most ambitious.

---

## Threat Model

### Actors

- **User**: Telegram client on their device
- **Telegram**: Cloud servers routing Bot API messages
- **Bot Server**: This application (orchestrator, storage, middleware)
- **Anthropic**: Claude API servers processing prompts
- **Attacker**: Varies by layer (see below)

### What We're Protecting

| Data | Where it exists | Sensitivity |
|---|---|---|
| User prompts | Telegram, bot memory, SQLite, Anthropic | High (may contain code, secrets, business logic) |
| Claude responses | Anthropic, bot memory, SQLite, Telegram | High (may contain file contents, credentials) |
| Tool invocations | Bot memory, SQLite | High (bash commands, file paths, API URLs) |
| Session IDs | Bot memory, SQLite | Medium (enables session hijacking) |
| Webhook payloads | SQLite | Medium-High (commit data, user emails) |
| Cost/usage data | SQLite | Low |

---

## Layered Design

### Layer 1: Encryption at Rest (Database)

**Goal**: Protect stored data if the SQLite file is exfiltrated.

**Approach A: SQLCipher (Recommended)**

Replace `aiosqlite` with `sqlcipher3` (or `apsw` with SQLCipher extension). The entire database file is AES-256-CBC encrypted transparently.

```
┌────────────────────────────┐
│  Application (unchanged)   │
│  storage.Database          │
│  aiosqlite API             │
├────────────────────────────┤
│  SQLCipher Driver          │  ← swap layer
│  AES-256-CBC, PBKDF2       │
├────────────────────────────┤
│  Encrypted .db file        │  ← opaque on disk
└────────────────────────────┘
```

**Key management**:
- Derive from a `DATABASE_ENCRYPTION_KEY` env var (SecretStr in settings)
- Or integrate with a secrets manager (AWS KMS, HashiCorp Vault)
- Key rotation: `PRAGMA rekey` for online re-encryption

**Pros**: Transparent to application code, battle-tested, protects all tables.
**Cons**: Performance overhead (~5-15%), key must be in memory at runtime, doesn't protect against memory dumps or a compromised bot process.

**Approach B: Field-Level Encryption**

Encrypt sensitive columns (`messages.prompt`, `messages.response`, `tool_usage.tool_input`, `webhook_events.payload`) at the application layer before INSERT, decrypt after SELECT.

```python
# src/storage/crypto.py
from cryptography.fernet import Fernet, MultiFernet
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

class FieldEncryptor:
    """Encrypts/decrypts individual database fields."""

    def __init__(self, master_key: bytes):
        self._fernet = Fernet(master_key)

    def encrypt(self, plaintext: str) -> str:
        """Returns base64-encoded ciphertext."""
        return self._fernet.encrypt(plaintext.encode()).decode()

    def decrypt(self, ciphertext: str) -> str:
        """Returns plaintext string."""
        return self._fernet.decrypt(ciphertext.encode()).decode()

    @staticmethod
    def derive_user_key(master_key: bytes, user_id: int) -> bytes:
        """Derive a per-user key for compartmentalized encryption."""
        hkdf = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=None,
            info=f"user:{user_id}".encode(),
        )
        return base64.urlsafe_b64encode(hkdf.derive(master_key))
```

**Per-user key derivation** limits blast radius: compromising one user's key doesn't expose others' data. The master key derives per-user keys via HKDF.

**Pros**: Granular control, per-user isolation, works with any SQLite driver.
**Cons**: Can't query encrypted fields (no `WHERE prompt LIKE ...`), more code to maintain, must handle key versioning for rotation.

**Recommendation**: Use **both**. SQLCipher as the baseline (protects schema, indexes, metadata), field-level encryption for high-sensitivity columns (defense in depth).

---

### Layer 2: Ephemeral Message Handling

**Goal**: Minimize the window of exposure by not retaining sensitive data longer than necessary.

```
┌─────────────────────────────────────────────┐
│              Retention Policies              │
├─────────────────────────────────────────────┤
│  messages.prompt     │  Purge after 7 days   │
│  messages.response   │  Purge after 7 days   │
│  tool_usage.tool_input│ Purge after 7 days   │
│  webhook_events.payload│ Purge after 24 hours│
│  audit_log.event_data │ Retain 90 days       │
│  Cost/usage data      │ Retain indefinitely  │
└─────────────────────────────────────────────┘
```

**Implementation**: A scheduled task (using the existing APScheduler integration) runs periodic cleanup:

```python
# Purge sensitive fields but keep metadata for billing/audit
UPDATE messages SET prompt = '[purged]', response = '[purged]'
WHERE timestamp < datetime('now', '-7 days');

UPDATE tool_usage SET tool_input = '{}'
WHERE timestamp < datetime('now', '-7 days');

DELETE FROM webhook_events
WHERE received_at < datetime('now', '-1 day');
```

**Configuration**:
```
MESSAGE_RETENTION_DAYS=7        # 0 = don't store prompts/responses at all
WEBHOOK_RETENTION_HOURS=24
AUDIT_RETENTION_DAYS=90
```

Setting `MESSAGE_RETENTION_DAYS=0` would skip storing prompt/response entirely, keeping only metadata (cost, duration, tool names).

---

### Layer 3: Application-Layer Message Encryption (Telegram Channel)

**Goal**: Prevent Telegram's servers from reading message content.

This layer encrypts the payload between the user's device and the bot server, making the Telegram transport an opaque pipe. **Requires a client-side component.**

#### Architecture

```
┌──────────────┐     Encrypted blob      ┌──────────────┐
│  User Device │ ───────────────────────► │  Bot Server  │
│              │                          │              │
│  Companion   │  TG message contains:   │  Decrypts    │
│  Web App /   │  {"v":1,                │  before      │
│  Userbot     │   "ct":"<base64>",      │  processing  │
│              │   "nonce":"<base64>"}    │              │
│  Encrypts    │ ◄─────────────────────── │  Encrypts    │
│  before send │     Encrypted response   │  response    │
└──────────────┘                          └──────────────┘
         │                                       │
         │            ┌──────────┐               │
         └───────────►│ Telegram │◄──────────────┘
                      │ Servers  │
                      │ (sees    │
                      │ opaque   │
                      │ blobs)   │
                      └──────────┘
```

#### Key Exchange Protocol

**Option A: Pre-Shared Key (Simple)**
1. User generates a symmetric key locally
2. Shares it with the bot via a secure side-channel (e.g., `/setkey <key>` sent once)
3. Both sides use the key for AES-256-GCM encryption
4. Key stored in `user_tokens` table (encrypted by Layer 1)

**Option B: X25519 Key Agreement (Better)**
1. Bot generates an X25519 keypair at startup, publishes public key via `/pubkey` command
2. User's companion app generates ephemeral X25519 keypair per session
3. Shared secret derived via X25519 Diffie-Hellman
4. Session key derived via HKDF from shared secret
5. Forward secrecy: new ephemeral key each session

```
User                              Bot
─────                             ─────
Generate ephemeral X25519 keypair
Send public key with first message
                                  Derive shared secret (X25519)
                                  Derive session key (HKDF)
                                  Encrypt response with session key
Derive same shared secret
Derive same session key
Decrypt response
```

#### Message Format

```json
{
  "v": 1,
  "alg": "x25519-xsalsa20-poly1305",
  "epk": "<base64 ephemeral public key>",
  "nonce": "<base64 24-byte nonce>",
  "ct": "<base64 ciphertext>"
}
```

The bot detects encrypted messages by checking for this JSON structure. Unencrypted messages continue to work normally (backward compatible).

#### Client-Side Options

| Option | Effort | UX |
|---|---|---|
| **Telegram Web App** (Mini App) | Medium | Button in chat opens encryption UI |
| **Userbot script** | Low | User runs a Python script that wraps their Telegram client |
| **Browser extension** | Medium | Intercepts Telegram Web messages |
| **Custom Telegram client fork** | High | Native integration, best UX |

**Recommended**: Start with a **Telegram Mini App** (Web App). The bot sends an inline button that opens a Mini App for composing encrypted messages. The Mini App handles key generation, encryption, and submission.

---

### Layer 4: In-Memory Protection

**Goal**: Minimize plaintext exposure in bot process memory.

1. **Secure string wiping**: Overwrite sensitive strings in memory after use (Python makes this difficult due to string interning, but `ctypes` or `mmap`-backed buffers can help for critical secrets).

2. **Scoped decryption**: Only decrypt data in the narrowest scope needed:
   ```python
   async def run_command(self, prompt: str, ...) -> AsyncIterator[StreamEvent]:
       # prompt is in memory only during this call
       async for event in self._sdk.stream(prompt, ...):
           yield event
       # prompt goes out of scope here
       # (Python GC will collect, but not guaranteed to zero memory)
   ```

3. **No logging of sensitive data**: Ensure structlog formatters never serialize prompt/response content (already partially done via `_redact_secrets`).

4. **Process isolation**: Run the bot in a container with no swap, `--memory` limits, and `--security-opt=no-new-privileges`.

---

### Layer 5: Secure Session Management

**Goal**: Prevent session hijacking, cross-user session access, and replay attacks.

#### Existing Vulnerability: No Session Ownership Validation

The current session management has a significant gap. When a session is loaded -- either from the in-memory cache or from SQLite -- **no check verifies that the requesting user owns that session**. The vulnerable code path:

```
SessionManager.get_or_create_session(user_id=B, session_id="<A's session>")
    │
    ├─ Check active_sessions[session_id]     ← returns A's session, no user_id check
    │
    └─ storage.load_session(session_id)      ← SQL: WHERE session_id = ?
                                                (no AND user_id = ? clause)
```

The `load_session()` method in `src/storage/session_storage.py:124` queries only by `session_id`, and `get_or_create_session()` in `src/claude/session.py:182-194` never compares the returned `session.user_id` against the requesting `user_id`. If an attacker knows or guesses a valid session ID, they could resume another user's Claude conversation.

**Practical exploitability is limited** -- session IDs are generated by Claude's API (likely UUIDs) and `context.user_data` is per-user in Telegram's framework -- but the defense-in-depth principle demands fixing this.

#### 5.1: Session Ownership Enforcement (Fix Today)

The minimum fix -- add `user_id` validation at two points:

**A. Storage layer** -- `load_session()` should accept and filter by `user_id`:

```python
# src/storage/session_storage.py
async def load_session(
    self, session_id: str, user_id: int
) -> Optional[ClaudeSession]:
    async with self.db_manager.get_connection() as conn:
        cursor = await conn.execute(
            "SELECT * FROM sessions WHERE session_id = ? AND user_id = ?",
            (session_id, user_id),
        )
        row = await cursor.fetchone()
        if not row:
            return None
        # ...
```

**B. Session manager** -- assert ownership after load:

```python
# src/claude/session.py
async def get_or_create_session(self, user_id, project_path, session_id=None):
    if session_id and session_id in self.active_sessions:
        session = self.active_sessions[session_id]
        if session.user_id != user_id:
            logger.warning(
                "Session ownership mismatch",
                session_id=session_id,
                owner=session.user_id,
                requester=user_id,
            )
            session_id = None  # Fall through to create new session
        elif not session.is_expired(self.config.session_timeout_hours):
            return session

    if session_id:
        session = await self.storage.load_session(session_id, user_id)
        # load_session now returns None for wrong user_id
        if session and not session.is_expired(self.config.session_timeout_hours):
            self.active_sessions[session_id] = session
            return session

    # ... create new session
```

#### 5.2: Session Binding

Bind sessions to a context tuple so they can't be replayed from a different environment:

```python
@dataclass
class SessionBinding:
    user_id: int
    chat_id: int           # Telegram chat where session was created
    project_path: str      # Working directory
    created_from: str       # "direct" | "thread" | "webhook"
```

Store as a new column `binding_hash TEXT` on the `sessions` table (SHA-256 of the binding fields). On resume, recompute the hash and reject if it doesn't match. This prevents:
- Session reuse across different Telegram chats
- Session reuse across different project directories
- Webhook-initiated sessions being resumed interactively (and vice versa)

#### 5.3: Session Token Indirection

Instead of storing Claude's raw `session_id` in `context.user_data`, store an opaque **session token** that maps to the real ID:

```
┌─────────────┐         ┌──────────────────────┐
│ user_data   │         │ session_tokens table  │
│             │         │                       │
│ token: "t1" │────────►│ token: "t1"           │
│             │         │ session_id: "claude-x" │
│             │         │ user_id: 123          │
│             │         │ expires_at: ...       │
└─────────────┘         └──────────────────────┘
```

- Tokens are random 256-bit values, rotated after each interaction
- Even if a token leaks, it expires in minutes and can't be used by another user
- The real Claude session ID never appears in Telegram's context or logs

#### 5.4: Session Lifecycle Hardening

| Policy | Current | Proposed |
|---|---|---|
| Idle timeout | 24 hours | 24 hours (keep) |
| Hard max lifetime | None | 7 days regardless of activity |
| `/new` behavior | Sets `session_id = None` in user_data | Also: delete session token mapping, purge session key material (Layer 3), audit log the invalidation |
| Concurrent sessions per user | `max_sessions_per_user` (evicts oldest) | Same, but also invalidate evicted session's tokens |
| Session resume after bot restart | Resumes from SQLite (session ID persists) | Require re-authentication before resume; clear all in-memory `active_sessions` |

#### 5.5: Audit Trail for Session Events

Log these events to `audit_log` with `event_type = "session_*"`:

- `session_created` -- new session, with binding context
- `session_resumed` -- successful resume, with binding match result
- `session_ownership_denied` -- user_id mismatch (security alert)
- `session_expired` -- natural expiry
- `session_invalidated` -- explicit `/new` or eviction
- `session_binding_mismatch` -- resume attempted from different context

This creates a forensic trail for investigating any session-related incidents.

---

## Implementation Phases

### Phase 0: Session Ownership Fix (Critical, Immediate)

```
Files to modify:
  src/storage/session_storage.py  - Add user_id parameter to load_session()
  src/claude/session.py           - Add ownership check in get_or_create_session()
  src/claude/facade.py            - Pass user_id through consistently
  tests/unit/test_session.py      - Cross-user session access test
```

Addresses: Session hijacking via ID reuse. **This is a bug fix, not a feature -- should ship regardless of whether the rest of this design is adopted.**

### Phase 1: Database Encryption (Highest Impact, Lowest Effort)

```
Files to modify:
  src/config/settings.py          - Add DATABASE_ENCRYPTION_KEY setting
  src/storage/database.py         - SQLCipher integration or field encryption
  src/storage/crypto.py           - New: encryption utilities
  pyproject.toml                  - Add sqlcipher3 or cryptography dependency
  tests/unit/test_crypto.py       - New: encryption tests
```

Addresses: DB file theft, insider DB access.

### Phase 2: Data Retention Policies

```
Files to modify:
  src/config/settings.py          - Retention period settings
  src/storage/database.py         - Cleanup methods
  src/scheduler/                  - Scheduled purge job
```

Addresses: Accumulated data exposure, GDPR compliance.

### Phase 3: Application-Layer Encryption (Telegram)

```
Files to create:
  src/crypto/                     - Key exchange, encrypt/decrypt
  src/bot/middleware/crypto.py    - Decrypt incoming, encrypt outgoing
  webapp/                         - Telegram Mini App for client-side encryption

Files to modify:
  src/bot/orchestrator.py         - Detect and unwrap encrypted messages
  src/bot/handlers/               - /pubkey, /setkey commands
```

Addresses: Telegram server visibility.

### Phase 4: Full Session Hardening

```
Files to modify:
  src/claude/session.py           - Session binding, token indirection, lifecycle policies
  src/storage/session_storage.py  - Binding hash column, token table
  src/storage/database.py         - Schema migration for new columns/tables
  src/bot/orchestrator.py         - Token-based session references, re-auth on restart
  src/security/audit.py           - Session event audit logging
```

Addresses: Session hijacking, replay attacks, session lifecycle gaps.

### Phase 5: Memory Hardening

```
  docker-compose.yml              - Security constraints (no swap, etc.)
  src/bot/orchestrator.py         - Scoped decryption, memory wiping
```

Addresses: Memory exposure, process dump attacks.

---

## What This Does NOT Protect Against

It's important to be explicit about remaining risks even with all layers:

1. **Anthropic can read prompts.** This is fundamental -- Claude must process plaintext. If this is unacceptable, the bot cannot be used.

2. **Compromised bot process sees everything.** If an attacker gets code execution on the bot server, they can intercept prompts in memory before encryption and after decryption. Layers 1-3 protect data at rest and in transit, not in use.

3. **Compromised user device.** If the user's Telegram client or companion app is compromised, encryption is moot.

4. **Side-channel attacks.** Encrypted message length, timing, and frequency can leak information about content.

5. **Key compromise.** If `DATABASE_ENCRYPTION_KEY` or the bot's X25519 private key is stolen, all protections using those keys are void.

---

## Decision Matrix

| Phase | Protects Against | Effort | Dependencies | Breaking Change |
|---|---|---|---|---|
| 0: Session ownership fix | Cross-user session hijacking | **Very Low** | None | None (bug fix) |
| 1a: SQLCipher | DB theft | Low | sqlcipher3 lib | Migration needed |
| 1b: Field encryption | DB theft + compartmentalization | Medium | cryptography lib | Schema migration |
| 2: Retention policies | Data accumulation | Low | None new | None |
| 3: TG message encryption | Telegram visibility | High | Client-side app | New user flow |
| 4: Full session hardening | Session replay, lifecycle gaps | Medium | Schema migration | Token rotation changes resume UX |
| 5: Memory hardening | Process memory dumps | Medium | Container config | None |

---

## Open Questions

1. **Key management**: Self-hosted KMS vs. cloud KMS vs. environment variable? Depends on deployment model.
2. **Migration path**: How to encrypt existing plaintext databases? One-time migration script or re-create?
3. **Client adoption**: Would users actually use a Mini App for encryption, or is the friction too high?
4. **Regulatory requirements**: Does the deployment context require specific encryption standards (FIPS 140-2, etc.)?
5. **Performance budget**: What latency increase is acceptable for field-level encrypt/decrypt on every message?
