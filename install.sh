#!/usr/bin/env bash
#
# MultiCode AI Bot - Universal Installer
#
# Install with:
#   curl -fsSL https://raw.githubusercontent.com/milhy545/claude-code-telegram/main/install.sh | bash
#
# Or with custom directory:
#   curl -fsSL https://raw.githubusercontent.com/milhy545/claude-code-telegram/main/install.sh | bash -s -- --dir /custom/path
#

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
REPO_URL="https://github.com/milhy545/claude-code-telegram.git"
DEFAULT_INSTALL_DIR="$HOME/.multicode-bot"
INSTALL_DIR="${INSTALL_DIR:-$DEFAULT_INSTALL_DIR}"

# Functions
print_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

check_command() {
    if ! command -v "$1" &> /dev/null; then
        return 1
    fi
    return 0
}

# Banner
echo ""
echo -e "${BLUE}╔═══════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║${NC}     ${GREEN}MultiCode AI Bot Installer${NC}           ${BLUE}║${NC}"
echo -e "${BLUE}║${NC}     8 AI Providers in One Bot                ${BLUE}║${NC}"
echo -e "${BLUE}╚═══════════════════════════════════════════════╝${NC}"
echo ""

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --dir)
            INSTALL_DIR="$2"
            shift 2
            ;;
        --help)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --dir DIR     Install to custom directory (default: $DEFAULT_INSTALL_DIR)"
            echo "  --help        Show this help message"
            exit 0
            ;;
        *)
            print_error "Unknown option: $1"
            exit 1
            ;;
    esac
done

print_info "Installing to: $INSTALL_DIR"
echo ""

# Check prerequisites
print_info "Checking prerequisites..."

MISSING_DEPS=()

if ! check_command git; then
    MISSING_DEPS+=("git")
fi

if ! check_command python3; then
    MISSING_DEPS+=("python3")
fi

if ! check_command pip3; then
    MISSING_DEPS+=("python3-pip")
fi

if [ ${#MISSING_DEPS[@]} -gt 0 ]; then
    print_error "Missing required dependencies: ${MISSING_DEPS[*]}"
    echo ""
    echo "Install them with:"
    echo ""

    if [[ "$OSTYPE" == "linux-gnu"* ]]; then
        if check_command apt; then
            echo "  sudo apt update && sudo apt install -y ${MISSING_DEPS[*]}"
        elif check_command dnf; then
            echo "  sudo dnf install -y ${MISSING_DEPS[*]}"
        elif check_command pacman; then
            echo "  sudo pacman -S ${MISSING_DEPS[*]}"
        fi
    elif [[ "$OSTYPE" == "darwin"* ]]; then
        echo "  brew install ${MISSING_DEPS[*]}"
    fi

    exit 1
fi

print_success "All prerequisites satisfied"

# Check Python version
PYTHON_VERSION=$(python3 --version | cut -d' ' -f2)
PYTHON_MAJOR=$(echo $PYTHON_VERSION | cut -d'.' -f1)
PYTHON_MINOR=$(echo $PYTHON_VERSION | cut -d'.' -f2)

if [ "$PYTHON_MAJOR" -lt 3 ] || ([ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -lt 10 ]); then
    print_error "Python 3.10+ required, found $PYTHON_VERSION"
    exit 1
fi

print_success "Python version OK ($PYTHON_VERSION)"

# Clone repository
print_info "Cloning repository..."

if [ -d "$INSTALL_DIR" ]; then
    print_warning "Directory $INSTALL_DIR already exists"
    read -p "Remove and reinstall? (y/N) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        rm -rf "$INSTALL_DIR"
    else
        print_error "Installation cancelled"
        exit 1
    fi
fi

git clone --depth 1 "$REPO_URL" "$INSTALL_DIR"
cd "$INSTALL_DIR"

print_success "Repository cloned"

# Install Poetry (if not installed)
if ! check_command poetry; then
    print_info "Installing Poetry..."
    curl -sSL https://install.python-poetry.org | python3 -

    # Add Poetry to PATH for this session
    export PATH="$HOME/.local/bin:$PATH"

    print_success "Poetry installed"
else
    print_success "Poetry already installed"
fi

# Install dependencies
print_info "Installing dependencies (this may take a few minutes)..."
poetry install --no-dev

print_success "Dependencies installed"

# Create .env from example
if [ ! -f .env ]; then
    print_info "Creating .env file..."
    cp .env.example .env
    print_warning "Please edit .env and configure your settings:"
    print_warning "  $INSTALL_DIR/.env"
fi

# Create executable script
print_info "Creating executable..."

cat > "$INSTALL_DIR/multicode-bot" << 'EOF'
#!/usr/bin/env bash
cd "$(dirname "$0")"
poetry run python -m src.main "$@"
EOF

chmod +x "$INSTALL_DIR/multicode-bot"

# Add to PATH (optional)
SHELL_RC=""
if [ -n "$BASH_VERSION" ]; then
    SHELL_RC="$HOME/.bashrc"
elif [ -n "$ZSH_VERSION" ]; then
    SHELL_RC="$HOME/.zshrc"
fi

if [ -n "$SHELL_RC" ]; then
    if ! grep -q "multicode-bot" "$SHELL_RC"; then
        echo ""
        print_info "Add to PATH? (recommended)"
        read -p "This will modify $SHELL_RC (y/N) " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            echo "" >> "$SHELL_RC"
            echo "# MultiCode AI Bot" >> "$SHELL_RC"
            echo "export PATH=\"$INSTALL_DIR:\$PATH\"" >> "$SHELL_RC"
            print_success "Added to PATH in $SHELL_RC"
            print_warning "Run: source $SHELL_RC"
        fi
    fi
fi

# Create systemd service (Linux only)
if [[ "$OSTYPE" == "linux-gnu"* ]]; then
    echo ""
    print_info "Create systemd service? (optional)"
    read -p "This will create a user service to auto-start the bot (y/N) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        mkdir -p "$HOME/.config/systemd/user"

        cat > "$HOME/.config/systemd/user/multicode-bot.service" << EOF
[Unit]
Description=MultiCode AI Bot
After=network.target

[Service]
Type=simple
WorkingDirectory=$INSTALL_DIR
ExecStart=$INSTALL_DIR/multicode-bot
Restart=always
RestartSec=10

[Install]
WantedBy=default.target
EOF

        systemctl --user daemon-reload
        systemctl --user enable multicode-bot.service

        print_success "Systemd service created"
        print_info "Start with: systemctl --user start multicode-bot"
        print_info "Check logs: journalctl --user -u multicode-bot -f"
    fi
fi

# Final instructions
echo ""
echo -e "${GREEN}╔═══════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║${NC}     ${GREEN}Installation Complete!${NC}                  ${GREEN}║${NC}"
echo -e "${GREEN}╚═══════════════════════════════════════════════╝${NC}"
echo ""

print_info "Next steps:"
echo ""
echo "  1. Configure your bot:"
echo -e "     ${BLUE}nano $INSTALL_DIR/.env${NC}"
echo ""
echo "  2. Set required variables:"
echo "     - TELEGRAM_BOT_TOKEN"
echo "     - TELEGRAM_BOT_USERNAME"
echo "     - ALLOWED_USERS"
echo "     - DEFAULT_AI_PROVIDER (blackbox=instant, gemini=free)"
echo ""
echo "  3. Run the bot:"
echo -e "     ${BLUE}cd $INSTALL_DIR && ./multicode-bot${NC}"
echo ""

if [ -n "$SHELL_RC" ]; then
    echo "  Or after adding to PATH:"
    echo -e "     ${BLUE}source $SHELL_RC${NC}"
    echo -e "     ${BLUE}multicode-bot${NC}"
    echo ""
fi

print_info "Documentation:"
echo "  - Quick start: $INSTALL_DIR/README.md"
echo "  - AI providers: $INSTALL_DIR/MULTI_AI_STATUS.md"
echo "  - Docker: $INSTALL_DIR/DOCKER.md"
echo ""

print_success "Happy coding with 8 AI assistants! 🚀"
