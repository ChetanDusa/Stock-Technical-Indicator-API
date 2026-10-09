"""SQLAlchemy engine and session factory for PostgreSQL (SQLite in isolated tests)."""

from sqlalchemy import create_engine, event
from sqlalchemy.engine import make_url
from sqlalchemy.orm import declarative_base, sessionmaker

from app.core.config import settings


def build_engine(connection_url: str):
    url = make_url(connection_url)
    options = {"pool_pre_ping": True}
    if url.get_backend_name() in {"postgres", "postgresql"}:
        url = url.set(drivername="postgresql+psycopg2")

    if url.get_backend_name() == "postgresql":
        if url.host and url.host.endswith(".neon.tech") and "sslmode" not in url.query:
            url = url.update_query_dict({"sslmode": "require"})
        options.update(
            pool_size=settings.DB_POOL_SIZE,
            max_overflow=0,
            pool_timeout=settings.DEPENDENCY_TIMEOUT_SECONDS,
            pool_recycle=300,
            connect_args={
                "connect_timeout": settings.DEPENDENCY_TIMEOUT_SECONDS,
            },
        )
    elif url.get_backend_name() == "sqlite" and settings.APP_ENV == "test":
        options["connect_args"] = {"check_same_thread": False}
    else:
        raise ValueError("Use a PostgreSQL DATABASE_URL; SQLite is supported only in tests")
    created_engine = create_engine(url, **options)
    if url.get_backend_name() == "postgresql":

        @event.listens_for(created_engine, "begin")
        def set_transaction_timeout(connection):
            # SET LOCAL also works through Neon's transaction-mode pooler.
            connection.exec_driver_sql(
                f"SET LOCAL statement_timeout = {settings.DEPENDENCY_TIMEOUT_SECONDS * 1000}"
            )

    return created_engine


engine = build_engine(settings.DATABASE_URL)
SessionLocal = sessionmaker(autoflush=False, expire_on_commit=False, bind=engine)
Base = declarative_base()
