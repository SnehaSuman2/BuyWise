"""Run background jobs without Celery: `python -m app.workers.run_jobs check_alerts refresh_prices`."""

import asyncio
import sys

from app.core.logging import configure_logging
from app.workers.jobs import JOBS, run_job_standalone


async def main(names: list[str]) -> None:
    for name in names or ["refresh_prices", "check_alerts"]:
        print(await run_job_standalone(name))


if __name__ == "__main__":
    configure_logging()
    args = sys.argv[1:]
    if args and args[0] in ("-h", "--help"):
        print("Usage: python -m app.workers.run_jobs [job ...]\nJobs:", ", ".join(JOBS))
        sys.exit(0)
    asyncio.run(main(args))
