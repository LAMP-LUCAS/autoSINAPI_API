#!/bin/bash
set -e
set -u

function create_database() {
	local database=$1
	echo "  Creating database '$database'"
	psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" <<-EOSQL
	    CREATE DATABASE $database;
EOSQL
}

function create_user_and_database() {
	local user=$1
	local password=$2
	local db=$3
	echo " Creating user '$user' and database '$db'"
	psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" <<-EOSQL
		CREATE USER $user WITH PASSWORD '$password';
		CREATE DATABASE $db;
		GRANT ALL PRIVILEGES ON DATABASE $db TO $user;
EOSQL
}

if [ -n "$POSTGRES_MULTIPLE_DATABASES" ]; then
	echo "Multiple database creation requested: $POSTGRES_MULTIPLE_DATABASES"
	for db in $(echo $POSTGRES_MULTIPLE_DATABASES | tr ',' ' '); do
		if [ "$db" == "kong" ]; then
			create_user_and_database $KONG_PG_USER $KONG_PG_PASSWORD $db
		else
			create_database $db
		fi
	done
	echo "Multiple databases created"
fi
