import asyncio
import socket
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.engine import make_url

from newsintel.core.config import Settings, get_settings
from newsintel.core.schema import (
    EXPECTED_SCHEMA_REVISION,
    REQUIRED_V25_COLUMNS,
    REQUIRED_V25_INDEXES,
    REQUIRED_V25_TABLES,
)
from newsintel.infrastructure.db.session import Database


@dataclass(frozen=True, slots=True)
class DatabaseTarget:
    host: str
    port: int
    redacted_url: str


def database_target(settings: Settings) -> DatabaseTarget:
    url = make_url(settings.database_url)
    return DatabaseTarget(
        host=url.host or "localhost",
        port=url.port or 5432,
        redacted_url=url.render_as_string(hide_password=True),
    )


def tcp_reachable(host: str, port: int, timeout_seconds: float = 2.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout_seconds):
            return True
    except OSError:
        return False


async def inspect_database(settings: Settings) -> tuple[bool, list[str]]:
    target = database_target(settings)
    messages = [f"Database target: {target.redacted_url}"]
    if not tcp_reachable(target.host, target.port):
        messages.extend(
            [
                f"[FAIL] PostgreSQL is not reachable at {target.host}:{target.port}.",
                "Start PostgreSQL before starting the API or poller.",
            ]
        )
        return False, messages

    database = Database(settings)
    try:
        async with database.session_factory() as session:
            await session.execute(text("SELECT 1"))
            version_table = await session.scalar(
                text("SELECT to_regclass('public.alembic_version')")
            )
            revision = (
                await session.scalar(
                    text(
                        "SELECT version_num FROM alembic_version "
                        "ORDER BY version_num DESC LIMIT 1"
                    )
                )
                if version_table
                else None
            )
            channels_table = await session.scalar(
                text("SELECT to_regclass('public.discovery_channels')")
            )
            article_versions_table = await session.scalar(
                text("SELECT to_regclass('public.article_versions')")
            )
            article_fetch_runs_table = await session.scalar(
                text("SELECT to_regclass('public.article_fetch_runs')")
            )
            article_claims_table = await session.scalar(
                text("SELECT to_regclass('public.article_claims')")
            )
            fetch_jobs_table = await session.scalar(
                text("SELECT to_regclass('public.fetch_jobs')")
            )
            server_version_num = await session.scalar(text("SHOW server_version_num"))
            postgis_extension = await session.scalar(
                text("SELECT extname FROM pg_extension WHERE extname = 'postgis'")
            )
            release_tables = {
                name: await session.scalar(
                    text("SELECT to_regclass(:qualified)"),
                    {"qualified": f"public.{name}"},
                )
                for name in REQUIRED_V25_TABLES
            }
            release_indexes = {
                name: await session.scalar(
                    text("SELECT to_regclass(:qualified)"),
                    {"qualified": f"public.{name}"},
                )
                for name in REQUIRED_V25_INDEXES
            }
            release_columns = {
                f"{table_name}.{column_name}": await session.scalar(
                    text(
                        "SELECT 1 FROM information_schema.columns "
                        "WHERE table_schema='public' AND table_name=:table_name "
                        "AND column_name=:column_name LIMIT 1"
                    ),
                    {"table_name": table_name, "column_name": column_name},
                )
                for table_name, column_name in REQUIRED_V25_COLUMNS
            }
    except Exception as exc:
        messages.append(f"[FAIL] PostgreSQL connection failed: {type(exc).__name__}")
        return False, messages
    finally:
        await database.dispose()

    if not revision or not channels_table:
        messages.extend(
            [
                "[FAIL] PostgreSQL is reachable, but application migrations are missing.",
                "Run: .\\.venv\\Scripts\\alembic.exe -c backend\\alembic.ini upgrade head",
            ]
        )
        return False, messages

    missing_tables = [name for name, value in release_tables.items() if not value]
    missing_indexes = [name for name, value in release_indexes.items() if not value]
    missing_columns = [name for name, value in release_columns.items() if not value]
    if revision != EXPECTED_SCHEMA_REVISION or missing_tables or missing_indexes or missing_columns:
        messages.append(
            f"[FAIL] Database schema is not ready for this release. Expected revision: {EXPECTED_SCHEMA_REVISION}; current: {revision}."
        )
        if missing_tables:
            messages.append(f"[FAIL] Missing release tables: {', '.join(missing_tables)}")
        if missing_indexes:
            messages.append(f"[FAIL] Missing release indexes: {', '.join(missing_indexes)}")
        if missing_columns:
            messages.append(f"[FAIL] Missing release columns: {', '.join(missing_columns)}")
        messages.append(r"Run: .\.venv\Scripts\alembic.exe -c backend\alembic.ini upgrade head")
        return False, messages

    messages.extend(
        [
            "[OK] PostgreSQL connection succeeded.",
            f"[OK] PostgreSQL server_version_num: {server_version_num}",
            f"[OK] Database migration revision: {revision}",
            "[OK] Release-required acquisition, intelligence, historical, extraction-profile, and semantic-index structures are available.",
            (
                "[OK] PostGIS extension is available."
                if postgis_extension
                else "[WARN] PostGIS extension is not installed; current v1.0 intelligence features do not require it directly."
            ),
            "[OK] Acquisition tables are available.",
            (
                "[OK] Article processing tables are available."
                if article_versions_table and article_fetch_runs_table
                else "[WARN] Article processing tables are not available yet."
            ),
            (
                "[OK] Claim/evidence lineage tables are available."
                if article_claims_table
                else "[WARN] Claim/evidence lineage tables are not available yet."
            ),
            (
                "[OK] Source dashboard/fetch job tables are available."
                if fetch_jobs_table
                else "[WARN] Source dashboard/fetch job tables are not available yet."
            ),
        ]
    )
    return True, messages


async def doctor(settings: Settings | None = None) -> bool:
    healthy, messages = await inspect_database(settings or get_settings())
    print("\n".join(messages))
    if not healthy:
        print(
            "\nFree local options:\n"
            "1. Install Docker Desktop, then run: docker compose up -d postgres\n"
            "2. Install PostgreSQL 17 locally and create the configured database/user."
        )
    return healthy


def run() -> None:
    raise SystemExit(0 if asyncio.run(doctor()) else 1)


if __name__ == "__main__":
    run()
