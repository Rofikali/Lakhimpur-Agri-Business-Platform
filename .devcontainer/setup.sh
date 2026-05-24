#!/usr/bin/env bash
# =============================================================================
# Full Development Environment Bootstrap
# Arch Linux + Codespaces + FastAPI + Nuxt
# =============================================================================

set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

log() {
    echo ""
    echo "[$(date '+%H:%M:%S')] $1"
}

install_system_packages() {
    log "Installing system packages"

    pacman -Syu --noconfirm

    pacman -S --noconfirm \
        base-devel \
        git \
        git-lfs \
        less \
        curl \
        wget \
        unzip \
        python \
        python-pip \
        nodejs \
        npm \
        pnpm \
        postgresql \
        redis \
        openssl

    # Initialize Git LFS
    git lfs install
}

install_uv() {
    log "Installing uv"

    curl -LsSf https://astral.sh/uv/install.sh | sh

    export PATH="$HOME/.local/bin:$PATH"

    if ! grep -q ".local/bin" ~/.bashrc; then
        echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
    fi

    uv --version
}

bootstrap_postgres() {
    log "Bootstrapping PostgreSQL"

    chmod +x "$ROOT_DIR/.devcontainer/fix_postgres_codespaces.sh"

    "$ROOT_DIR/.devcontainer/fix_postgres_codespaces.sh"

    su postgres -c \
        "createdb lakhimpur_dev" \
        2>/dev/null || true

    su postgres -c \
        "createdb lakhimpur_test" \
        2>/dev/null || true
}

start_redis() {
    log "Starting Redis"

    redis-server \
        --daemonize yes \
        --bind 127.0.0.1 \
        --logfile /tmp/redis.log

    sleep 1

    redis-cli ping
}

install_backend() {
    log "Installing backend dependencies"

    cd "$ROOT_DIR/backend"

    export PATH="$HOME/.local/bin:$PATH"

    uv sync --all-groups
}

install_frontend() {
    log "Installing frontend dependencies"

    cd "$ROOT_DIR/frontend"

    pnpm install
}

summary() {
    echo ""
    echo "============================================================================="
    echo " ENVIRONMENT READY"
    echo "============================================================================="
    echo ""
    echo "Backend:"
    echo "  make dev-be"
    echo ""
    echo "Frontend:"
    echo "  make dev-fe"
    echo ""
    echo "Database:"
    echo "  make migrate"
    echo "  make seed"
    echo ""
    echo "PostgreSQL Socket:"
    echo "  /tmp"
    echo ""
}

main() {
    install_system_packages
    install_uv
    bootstrap_postgres
    start_redis
    install_backend
    install_frontend
    summary
}

main "$@"

# #!/usr/bin/env bash
# # .devcontainer/setup.sh
# set -euo pipefail

# echo "=== [1/6] Updating Arch Linux + installing packages ==="
# pacman -Syu --noconfirm
# pacman -S --noconfirm \
#   base-devel git curl wget \
#   python python-pip \
#   postgresql redis \
#   nodejs npm \
#   openssl

# echo "=== [2/6] Installing uv ==="
# curl -LsSf https://astral.sh/uv/install.sh | sh
# export PATH="$HOME/.local/bin:$PATH"
# echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
# uv --version

# echo "=== [3/6] Setting up PostgreSQL ==="
# # Codespaces has no systemd — use pg_ctl directly
# mkdir -p /var/lib/postgres/data /var/log
# chown postgres:postgres /var/lib/postgres/data || true
# sudo -u postgres initdb -D /var/lib/postgres/data \
#   --encoding=UTF8 --locale=C.UTF-8 2>/dev/null || true
# sudo -u postgres pg_ctl start \
#   -D /var/lib/postgres/data \
#   -l /var/log/postgresql.log \
#   -o "-p 5432" || true
# sleep 3
# # Create databases
# sudo -u postgres psql -c "ALTER USER postgres PASSWORD 'devpassword';" 2>/dev/null || true
# sudo -u postgres createdb lakhimpur_dev  2>/dev/null || true
# sudo -u postgres createdb lakhimpur_test 2>/dev/null || true
# echo "PostgreSQL: ✓ lakhimpur_dev + lakhimpur_test created"

# echo "=== [4/6] Starting Redis ==="
# redis-server --daemonize yes \
#   --logfile /var/log/redis.log \
#   --bind 127.0.0.1 2>/dev/null || true
# sleep 1
# redis-cli ping && echo "Redis: ✓"

# echo "=== [5/6] Installing Python deps via uv ==="
# cd backend
# uv sync --all-groups
# echo "uv: ✓ $(uv run python --version)"

# echo "=== [6/6] Installing frontend deps ==="
# cd ../frontend
# pnpm install
# echo "Node: ✓ $(node --version)"

# echo ""
# echo "✅ Setup complete!"
# echo ""
# echo "Next steps:"
# echo "  1. cp backend/.env.example backend/.env.local"
# echo "  2. Fill JWT keys: make gen-keys"
# echo "  3. make migrate && make seed"
# echo "  4. make dev-be   (terminal 1)"
# echo "  5. make dev-fe   (terminal 2)"