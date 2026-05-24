#!/usr/bin/env bash
# =============================================================================
# Lightweight Service Bootstrap
# Auto-start PostgreSQL + Redis for Codespaces
# =============================================================================

set -Eeuo pipefail

readonly PG_DATA="/var/lib/postgres/data"
readonly PG_LOG="/tmp/postgres.log"

export PATH="$HOME/.local/bin:$PATH"

log() {
    echo "[$(date '+%H:%M:%S')] $1"
}

start_postgres() {
    if su postgres -c \
        "pg_ctl status -D '$PG_DATA'" \
        >/dev/null 2>&1; then

        log "PostgreSQL already running"
        return
    fi

    log "Starting PostgreSQL"

    su postgres -c \
        "pg_ctl -D '$PG_DATA' \
         -l '$PG_LOG' \
         start"
}

start_redis() {
    if redis-cli ping >/dev/null 2>&1; then
        log "Redis already running"
        return
    fi

    log "Starting Redis"

    redis-server \
        --daemonize yes \
        --bind 127.0.0.1 \
        --logfile /tmp/redis.log
}

verify_services() {
    sleep 1

    redis-cli ping >/dev/null

    su postgres -c \
        "psql -h /tmp postgres -c 'SELECT version();'" \
        >/dev/null
}

main() {
    start_postgres
    start_redis
    verify_services

    echo ""
    echo "============================================================================="
    echo " SERVICES READY"
    echo "============================================================================="
    echo ""
    echo "PostgreSQL : RUNNING"
    echo "Redis      : RUNNING"
    echo ""
}

main "$@"

# #!/usr/bin/env bash
# # Add to ~/.bashrc so services auto-start when terminal opens
# # .devcontainer/start-services.sh
# export PATH="$HOME/.local/bin:$PATH"

# # PostgreSQL
# sudo -u postgres pg_ctl status -D /var/lib/postgres/data > /dev/null 2>&1 \
#   || sudo -u postgres pg_ctl start -D /var/lib/postgres/data \
#        -l /var/log/postgresql.log -o "-p 5432" -w

# # Redis
# redis-cli ping > /dev/null 2>&1 \
#   || redis-server --daemonize yes --bind 127.0.0.1 \
#        --logfile /var/log/redis.log

# echo "✓ Services ready (PG + Redis)"