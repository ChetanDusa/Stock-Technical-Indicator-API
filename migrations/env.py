"""Use a direct migration URL when supplied; credentials stay out of alembic.ini."""

from alembic import context

from app.core.config import settings
from database import Base, build_engine
from models import User  # noqa: F401 -- registers metadata for autogeneration

target_metadata = Base.metadata


def run_migrations_online():
    migration_engine = build_engine(settings.DATABASE_MIGRATION_URL or settings.DATABASE_URL)
    try:
        with migration_engine.connect() as connection:
            context.configure(
                connection=connection, target_metadata=target_metadata, compare_type=True
            )
            with context.begin_transaction():
                context.run_migrations()
    finally:
        migration_engine.dispose()


def run_migrations_offline():
    from sqlalchemy.engine import make_url

    url = make_url(settings.DATABASE_MIGRATION_URL or settings.DATABASE_URL)
    if url.get_backend_name() in {"postgres", "postgresql"}:
        url = url.set(drivername="postgresql+psycopg2")
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
