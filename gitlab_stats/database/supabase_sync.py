"""CLI task to sync GitLab API event records into Supabase."""

from __future__ import annotations

import logging

from dotenv import load_dotenv

from gitlab_stats.database.supabase_client import upsert_events_to_supabase
from gitlab_stats.gitlab_stats_api_ingester import fetch_event_records_from_api

logger = logging.getLogger(__name__)


def run_sync() -> int:
    """Fetch API event records and upsert them into Supabase."""
    event_records = fetch_event_records_from_api()
    if event_records is None:
        logger.error("Failed to fetch event records from GitLab API")
        return 1

    if not event_records:
        logger.info("No event records found in the configured API window")
        return 0

    upserted_count = upsert_events_to_supabase(event_records)
    logger.info("Supabase sync complete. Upserted %s records", upserted_count)
    return 0


def main() -> None:
    """CLI entrypoint."""
    logging.basicConfig(level=logging.INFO)
    load_dotenv()
    raise SystemExit(run_sync())


if __name__ == "__main__":
    main()
