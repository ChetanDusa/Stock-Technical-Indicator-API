"""Container entrypoint: load configuration, apply migrations and replace this process with Uvicorn."""

import os
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv


def main():
    root = Path(__file__).resolve().parents[1]
    os.chdir(root)
    load_dotenv(root / ".env")
    os.environ.setdefault("POLARS_MAX_THREADS", "2")
    port = int(os.environ.get("PORT", "8000"))
    if not 1 <= port <= 65535:
        raise SystemExit("PORT must be between 1 and 65535")
    if os.environ.get("RUN_MIGRATIONS", "1") == "1":
        subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], check=True)
    os.execv(
        sys.executable,
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "0.0.0.0",
            "--port",
            str(port),
            "--workers",
            "1",
            "--no-access-log",
            "--limit-concurrency",
            "40",
            "--timeout-graceful-shutdown",
            "30",
        ],
    )


if __name__ == "__main__":
    main()
