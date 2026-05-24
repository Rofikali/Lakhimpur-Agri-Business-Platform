#!/usr/bin/env bash
# =============================================================================
# PostgreSQL Container Recovery Script
# Production-grade Codespaces/Postgres bootstrap
# =============================================================================

set -Eeuo pipefail

readonly PG_USER="postgres"
readonly PG_DATA="/var/lib/postgres/data"
readonly PG_RUNTIME="/run/postgresql"
readonly PG_SOCKET_DIR="/tmp"
readonly PG_LOG="/tmp/postgres.log"

log() {
    echo ""
    echo "[$(date '+%H:%M:%S')] $1"
}

require_root() {
    if [[ "$EUID" -ne 0 ]]; then
        echo "ERROR: run as root"
        exit 1
    fi
}

configure_runtime() {
    log "Configuring runtime directories"

    mkdir -p "$PG_RUNTIME"
    chown "$PG_USER:$PG_USER" "$PG_RUNTIME"
    chmod 775 "$PG_RUNTIME"

    mkdir -p "$PG_DATA"
    chown -R "$PG_USER:$PG_USER" /var/lib/postgres
}

initialize_database() {
    if [[ ! -f "$PG_DATA/PG_VERSION" ]]; then
        log "Initializing PostgreSQL cluster"

        su "$PG_USER" -c \
            "initdb -D '$PG_DATA' \
             --encoding=UTF8 \
             --locale=C.UTF-8"
    else
        log "Existing PostgreSQL cluster detected"
    fi
}

configure_postgres() {
    log "Applying container-safe PostgreSQL config"

    local conf="$PG_DATA/postgresql.conf"

    sed -i "/^#*unix_socket_directories/d" "$conf"

    cat >> "$conf" <<EOF

# =============================================================================
# Container Runtime Overrides
# =============================================================================
unix_socket_directories = '$PG_SOCKET_DIR'
listen_addresses = '127.0.0.1'
max_connections = 200
shared_buffers = 256MB
EOF
}

start_postgres() {
    log "Starting PostgreSQL"

    su "$PG_USER" -c \
        "pg_ctl -D '$PG_DATA' \
         -l '$PG_LOG' \
         start"
}

verify_postgres() {
    log "Verifying PostgreSQL"

    sleep 2

    su "$PG_USER" -c \
        "psql -h '$PG_SOCKET_DIR' postgres -c '\l'"
}

main() {
    require_root
    configure_runtime
    initialize_database
    configure_postgres
    start_postgres
    verify_postgres

    log "PostgreSQL successfully started"

    echo ""
    echo "Socket Directory : $PG_SOCKET_DIR"
    echo "Data Directory   : $PG_DATA"
    echo "Log File         : $PG_LOG"
    echo ""
    echo "Connect using:"
    echo "psql -h $PG_SOCKET_DIR postgres"
}

main "$@"

# #!/usr/bin/env bash
# # .devcontainer/fix_postgres_codespaces.sh
# set -e

# echo "======================================"
# echo " PostgreSQL Codespaces Auto Fix"
# echo "======================================"

# PG_DATA="/var/lib/postgres/data"
# PG_LOG="/tmp/postgres.log"

# echo ""
# echo "[1] Creating postgres runtime dirs..."

# mkdir -p /run/postgresql
# chown postgres:postgres /run/postgresql
# chmod 775 /run/postgresql

# echo ""
# echo "[2] Ensuring postgres data dir exists..."

# mkdir -p $PG_DATA
# chown -R postgres:postgres /var/lib/postgres

# echo ""
# echo "[3] Initializing database if needed..."

# if [ ! -f "$PG_DATA/PG_VERSION" ]; then
#     su postgres -c "initdb -D $PG_DATA"
# fi

# echo ""
# echo "[4] Configuring socket directory for containers..."

# CONF_FILE="$PG_DATA/postgresql.conf"

# if ! grep -q "unix_socket_directories = '/tmp'" "$CONF_FILE"; then
#     echo "unix_socket_directories = '/tmp'" >> "$CONF_FILE"
# fi

# echo ""
# echo "[5] Starting PostgreSQL..."

# su postgres -c "pg_ctl -D $PG_DATA -l $PG_LOG start"

# echo ""
# echo "[6] Testing PostgreSQL..."

# sleep 2

# su postgres -c "psql -h /tmp postgres -c '\l'"

# echo ""
# echo "======================================"
# echo " PostgreSQL RUNNING SUCCESSFULLY"
# echo "======================================"
# echo ""
# echo "Socket location: /tmp"
# echo "Log file: $PG_LOG"
# echo ""

# echo "To connect manually:"
# echo "psql -h /tmp postgres"

# # chmod +x fix_postgres_codespaces.sh
# # ./fix_postgres_codespaces.sh