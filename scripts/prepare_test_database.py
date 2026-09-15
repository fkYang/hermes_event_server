import argparse
import os
import re
from pathlib import Path

import pymysql
from dotenv import dotenv_values

SAFE_DATABASE = re.compile(r"^[A-Za-z0-9_]+_test$")


def load_config(env_file: Path, port_override: int | None) -> dict[str, object]:
    values = dotenv_values(env_file)
    database = values.get("MYSQL_DATABASE", "")
    if not isinstance(database, str) or not SAFE_DATABASE.fullmatch(database):
        raise SystemExit("MYSQL_DATABASE must be a simple name ending in _test")
    password = values.get("MYSQL_PASSWORD")
    if not isinstance(password, str) or not password:
        raise SystemExit("MYSQL_PASSWORD is missing")
    return {
        "host": values.get("MYSQL_HOST", "127.0.0.1"),
        "port": port_override or int(values.get("MYSQL_PORT", "3306")),
        "user": values.get("MYSQL_USER", "root"),
        "password": password,
        "database": database,
        "charset": values.get("MYSQL_CHARSET", "utf8mb4"),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Safely prepare an isolated AutoQQ test database")
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--port", type=int)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--probe", action="store_true", help="inspect without changing the server")
    mode.add_argument("--create", action="store_true")
    mode.add_argument("--recreate", action="store_true")
    args = parser.parse_args()
    config = load_config(args.env_file, args.port)
    database = str(config.pop("database"))
    connection = pymysql.connect(
        **config,
        connect_timeout=5,
        read_timeout=10,
        write_timeout=10,
        autocommit=True,
    )
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT VERSION(), CURRENT_USER(), @@character_set_server, "
                "@@collation_server, @@time_zone"
            )
            version, current_user, charset, collation, time_zone = cursor.fetchone()
            cursor.execute("SHOW STATUS LIKE 'Ssl_cipher'")
            ssl_row = cursor.fetchone()
            cursor.execute(
                "SELECT COUNT(*) FROM information_schema.SCHEMATA WHERE SCHEMA_NAME=%s",
                (database,),
            )
            exists = bool(cursor.fetchone()[0])
            print(f"server_version={version}")
            print(f"current_user={current_user}")
            print(f"server_charset={charset}")
            print(f"server_collation={collation}")
            print(f"server_time_zone={time_zone}")
            print(f"tls={'enabled' if ssl_row and ssl_row[1] else 'disabled'}")
            print(f"test_database={database}; exists={str(exists).lower()}")
            if args.recreate:
                cursor.execute(f"DROP DATABASE IF EXISTS `{database}`")
                cursor.execute(
                    f"CREATE DATABASE `{database}` CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci"
                )
                print(f"recreated_test_database={database}")
            elif args.create and not exists:
                cursor.execute(
                    f"CREATE DATABASE `{database}` CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci"
                )
                print(f"created_test_database={database}")
    finally:
        connection.close()


if __name__ == "__main__":
    os.umask(0o077)
    main()
