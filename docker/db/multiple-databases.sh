#!/bin/bash
# Check if this script is being executed by ash (sh on Alpine)
if [ -z "$BASH_VERSION" ]; then
    # If not bash, re-execute with bash
    exec /bin/bash "$0" "$@"
fi

set -e
set -u

# Banco padrão para conectar e criar outros
DEFAULT_DB="postgres"

create_database() {
    database=$1
    echo "Creating database '$database'"
    psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$DEFAULT_DB" <<-EOSQL
        SELECT 'CREATE DATABASE $database' WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = '$database');
        \gexec
EOSQL
}

create_user_and_database() {
    user=$1
    password=$2
    db=$3
    echo "Creating user '$user' and database '$db'"
    psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$DEFAULT_DB" <<-EOSQL
        DO \$$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '$user') THEN
                CREATE USER $user WITH PASSWORD '$password';
            END IF;
        END
        \$$;

        SELECT 'CREATE DATABASE $db' WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = '$db');
        \gexec

        GRANT ALL PRIVILEGES ON DATABASE $db TO $user;

        -- Conecta ao novo banco e concede permissões ao usuário
        \c $db
        GRANT ALL ON SCHEMA public TO $user;
        ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO $user;
        ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO $user;
        ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON FUNCTIONS TO $user;
EOSQL
}

# Verificação de variáveis
if [ -z "${POSTGRES_USER:-}" ] || [ -z "${POSTGRES_MULTIPLE_DATABASES:-}" ]; then
    echo "POSTGRES_USER ou POSTGRES_MULTIPLE_DATABASES não definidos"
    exit 1
fi

if [ -n "$POSTGRES_MULTIPLE_DATABASES" ]; then
    echo "Multiple database creation requested: $POSTGRES_MULTIPLE_DATABASES"
    for db in $(echo "$POSTGRES_MULTIPLE_DATABASES" | tr ',' ' '); do
        if [ "$db" = "kong" ]; then
            if [ -z "${KONG_PG_USER:-}" ] || [ -z "${KONG_PG_PASSWORD:-}" ]; then
                echo "KONG_PG_USER ou KONG_PG_PASSWORD não definidos para criar o banco kong"
                exit 1
            fi
            create_user_and_database "$KONG_PG_USER" "$KONG_PG_PASSWORD" "$db"
        else
            create_database "$db"
        fi
    done
    echo "Multiple databases created"
fi