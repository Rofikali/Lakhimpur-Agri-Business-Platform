#!/usr/bin/env bash
# =============================================================================
# Codespaces Service Bootstrap
# Starts local PostgreSQL + Redis/Valkey without systemd or Docker.
# =============================================================================

set -Eeuo pipefail

readonly PG_USER="postgres"
readonly PG_DATA="/var/lib/postgres/data"
readonly PG_RUNTIME="/run/postgresql"
readonly PG_SOCKET_DIR="/tmp"
readonly PG_LOG="/tmp/postgres.log"
readonly PG_PASSWORD="devpassword"

export PATH="$HOME/.local/bin:$PATH"

log() {
    echo "[$(date '+%H:%M:%S')] $1"
}

ensure_postgres_cluster() {
    mkdir -p "$PG_RUNTIME" "$PG_DATA"
    chown "$PG_USER:$PG_USER" "$PG_RUNTIME"
    chmod 775 "$PG_RUNTIME"
    chown -R "$PG_USER:$PG_USER" /var/lib/postgres

    if [[ ! -f "$PG_DATA/PG_VERSION" ]]; then
        log "Initializing PostgreSQL cluster"
        su "$PG_USER" -c "initdb -D '$PG_DATA' --encoding=UTF8 --locale=C.UTF-8"
    fi
}

configure_postgres() {
    local conf="$PG_DATA/postgresql.conf"

    sed -i \
        -e "/^#*unix_socket_directories/d" \
        -e "/^#*listen_addresses/d" \
        -e "/^#*port/d" \
        "$conf"

    cat >> "$conf" <<EOF

# =============================================================================
# Codespaces local runtime overrides
# =============================================================================
unix_socket_directories = '$PG_SOCKET_DIR'
listen_addresses = '127.0.0.1'
port = 5432
EOF
}

start_postgres() {
    if su "$PG_USER" -c "pg_ctl status -D '$PG_DATA'" >/dev/null 2>&1; then
        log "PostgreSQL already running"
        return
    fi

    log "Starting PostgreSQL"
    su "$PG_USER" -c "pg_ctl -D '$PG_DATA' -l '$PG_LOG' -o '-k $PG_SOCKET_DIR -p 5432' -w start"
}

bootstrap_databases() {
    log "Ensuring PostgreSQL role and databases"

    su "$PG_USER" -c "psql -h '$PG_SOCKET_DIR' -d postgres -c \"ALTER USER postgres PASSWORD '$PG_PASSWORD';\"" >/dev/null
    su "$PG_USER" -c "createdb -h '$PG_SOCKET_DIR' lakhimpur_dev" 2>/dev/null || true
    su "$PG_USER" -c "createdb -h '$PG_SOCKET_DIR' lakhimpur_test" 2>/dev/null || true
}

start_redis() {
    if redis-cli ping >/dev/null 2>&1; then
        log "Redis already running"
        return
    fi

    log "Starting Redis/Valkey"
    redis-server \
        --daemonize yes \
        --bind 127.0.0.1 \
        --port 6379 \
        --logfile /tmp/redis.log
}

wait_for_redis() {
    for _ in {1..20}; do
        if redis-cli ping >/dev/null 2>&1; then
            return 0
        fi
        sleep 0.25
    done

    echo "ERROR: Redis/Valkey did not become ready"
    tail -40 /tmp/redis.log || true
    return 1
}

wait_for_postgres() {
    for _ in {1..20}; do
        if psql "postgresql://postgres:$PG_PASSWORD@127.0.0.1:5432/lakhimpur_dev" -c "SELECT 1;" >/dev/null 2>&1; then
            return 0
        fi
        sleep 0.25
    done

    echo "ERROR: PostgreSQL did not become ready"
    tail -40 "$PG_LOG" || true
    return 1
}

verify_services() {
    log "Verifying services"

    wait_for_redis
    wait_for_postgres
}

main() {
    ensure_postgres_cluster
    configure_postgres
    start_postgres
    bootstrap_databases
    start_redis
    verify_services

    echo ""
    echo "============================================================================="
    echo " SERVICES READY"
    echo "============================================================================="
    echo "PostgreSQL : postgresql://postgres:$PG_PASSWORD@127.0.0.1:5432/lakhimpur_dev"
    echo "Redis      : redis://127.0.0.1:6379/0"
    echo ""
}

main "$@"
