# APT Repository on GitHub Pages

This project can be installed with `apt install` by publishing a signed APT repository to GitHub Pages.

## What this setup provides

- Debian package builder: `scripts/build-deb.sh`
- APT repository builder/signing script: `scripts/build-apt-repo.sh`
- CI workflow to publish repository to GitHub Pages: `.github/workflows/publish-apt-repo.yml`

Once published, users can install with:

```bash
sudo apt update
sudo apt install claude-code-telegram
```

## Maintainer setup (one-time)

### 1) Enable GitHub Pages

In your repository settings:

- **Settings → Pages**
- Source: **GitHub Actions**

### 2) Generate a repository signing key

Create a dedicated keypair for the APT metadata signatures:

```bash
gpg --full-generate-key
# Choose RSA and RSA, 4096 bits, set a reasonable expiration
```

Get the key id:

```bash
gpg --list-secret-keys --keyid-format LONG
```

### 3) Add GitHub Actions secrets

Add these repository secrets:

- `APT_GPG_KEY_ID` — long key id (example: `0123ABCD4567EF89`)
- `APT_GPG_PRIVATE_KEY_B64` — base64 of ASCII-armored private key
- `APT_GPG_PASSPHRASE` — passphrase for the key (empty if no passphrase)

Export and encode the private key:

```bash
gpg --armor --export-secret-keys <KEY_ID> | base64 -w0
```

Use the output as `APT_GPG_PRIVATE_KEY_B64`.

## Publishing

Publishing occurs automatically when a GitHub release is published, or manually via **Actions → Publish APT Repository → Run workflow**.

The workflow will:

1. Build a `.deb` package
2. Build and sign repository metadata (`Release`, `Release.gpg`, `InRelease`)
3. Deploy `apt-repo/` to GitHub Pages

## Client installation

Replace placeholders:
- `<owner>`: GitHub org/user
- `<repo>`: repository name

```bash
curl -fsSL https://<owner>.github.io/<repo>/claude-code-telegram-archive-keyring.gpg \
  | sudo tee /usr/share/keyrings/claude-code-telegram-archive-keyring.gpg >/dev/null

echo "deb [signed-by=/usr/share/keyrings/claude-code-telegram-archive-keyring.gpg] https://<owner>.github.io/<repo>/ stable main" \
  | sudo tee /etc/apt/sources.list.d/claude-code-telegram.list >/dev/null

sudo apt update
sudo apt install claude-code-telegram
```

## Package runtime layout

The package installs:

- Binary wrapper: `/usr/bin/claude-code-telegram`
- Python virtualenv: `/opt/claude-code-telegram/venv`
- Config file: `/etc/claude-code-telegram/claude-code-telegram.env`
- State dir: `/var/lib/claude-code-telegram`
- Logs dir: `/var/log/claude-code-telegram`
- Systemd unit: `claude-code-telegram.service`

After install:

```bash
sudoedit /etc/claude-code-telegram/claude-code-telegram.env
sudo systemctl enable --now claude-code-telegram
sudo systemctl status claude-code-telegram
```

## Local testing

Build package locally:

```bash
./scripts/build-deb.sh
```

Build local signed repository from generated package:

```bash
export GPG_PASSPHRASE='...'
./scripts/build-apt-repo.sh apt-repo dist/deb/claude-code-telegram_<version>-1_all.deb <KEY_ID>
```
