"""CLI task to sync GitLab API event records into Supabase."""

from __future__ import annotations

import logging

from dotenv import load_dotenv

from gitlab_stats.database.supabase_client import upsert_events_to_supabase
from gitlab_stats.database.supabase_client import upsert_jira_events_to_supabase
from gitlab_stats.gitlab_stats_api_ingester import fetch_event_records_from_api
from gitlab_stats.jira_api_ingester import fetch_event_records_from_jira
from gitlab_stats.settings import read_setting

logger = logging.getLogger(__name__)


def _sync_sources() -> set[str]:
    """Return enabled sync sources from SYNC_SOURCES or source-specific flags."""
    raw_sources = read_setting("SYNC_SOURCES").strip().lower()
    if raw_sources:
        parsed_sources = {
            source.strip() for source in raw_sources.split(",") if source.strip()
        }
        valid_sources = {"gitlab", "jira"}
        enabled_sources = parsed_sources & valid_sources
        if enabled_sources:
            return enabled_sources

    enabled_sources = {"gitlab"}
    if read_setting("SYNC_JIRA").strip().lower() not in {"0", "false", "no"}:
        enabled_sources.add("jira")

    return enabled_sources


def run_sync() -> int:
    """Fetch GitLab and Jira event records and upsert them into Supabase."""
    enabled_sources = _sync_sources()

    gitlab_records = []
    if "gitlab" in enabled_sources:
        gitlab_records = fetch_event_records_from_api()
        if gitlab_records is None:
            logger.error("Failed to fetch event records from GitLab API")
            return 1

    jira_records = []
    if "jira" in enabled_sources:
        jira_records = fetch_event_records_from_jira()
        if jira_records is None:
            logger.error("Failed to fetch event records from Jira API")
            return 1

    if not gitlab_records and not jira_records:
        logger.info(
            "No GitLab or Jira event records found in the configured API window",
        )
        return 0

    upserted_gitlab_count = 0
    if "gitlab" in enabled_sources:
        upserted_gitlab_count = upsert_events_to_supabase(gitlab_records)

    upserted_jira_count = 0
    if "jira" in enabled_sources:
        upserted_jira_count = upsert_jira_events_to_supabase(jira_records)

    logger.info(
        (
            "Supabase sync complete. Upserted %s records (%s GitLab rows to events, "
            "%s Jira rows to jira_events)"
        ),
        upserted_gitlab_count + upserted_jira_count,
        upserted_gitlab_count,
        upserted_jira_count,
    )
    return 0


def main() -> None:
    """CLI entrypoint."""
    logging.basicConfig(level=logging.INFO)
    load_dotenv()
    raise SystemExit(run_sync())


if __name__ == "__main__":
    main()
