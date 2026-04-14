"""Supabase REST helpers for reading and writing GitLab metrics over HTTPS."""

from __future__ import annotations

import json
import logging
from datetime import UTC
from datetime import date
from datetime import datetime
from datetime import timedelta
from typing import Any
from urllib.error import HTTPError
from urllib.error import URLError
from urllib.parse import quote
from urllib.parse import urlencode
from urllib.request import Request
from urllib.request import urlopen

from gitlab_stats.settings import read_supabase_setting

logger = logging.getLogger(__name__)


class SupabaseConfigError(RuntimeError):
    """Raised when required Supabase settings are missing."""

    @classmethod
    def missing_url(cls) -> SupabaseConfigError:
        """Build missing URL error."""
        return cls("Missing url (SUPABASE_URL) is required for Supabase API access")

    @classmethod
    def missing_read_key(cls) -> SupabaseConfigError:
        """Build missing read key error."""
        return cls(
            "Missing read key (SUPABASE_SERVICE_ROLE_KEY) is required for select operations",
        )

    @classmethod
    def missing_write_key(cls) -> SupabaseConfigError:
        """Build missing write key error."""
        return cls(
            "Missing write key (SUPABASE_SERVICE_ROLE_KEY) is required for upsert operations",
        )


class SupabaseRequestError(RuntimeError):
    """Raised when Supabase API returns an unexpected response."""

    @classmethod
    def expected_list_payload(cls) -> SupabaseRequestError:
        """Build list payload expectation error."""
        return cls("Expected list payload when reading Supabase events")

    @classmethod
    def http_failure(
        cls,
        method: str,
        url: str,
        status_code: int,
        detail: str,
    ) -> SupabaseRequestError:
        """Build HTTP failure error message."""
        return cls(f"Supabase {method} {url} failed ({status_code}): {detail}")

    @classmethod
    def network_failure(
        cls,
        method: str,
        url: str,
        detail: str,
    ) -> SupabaseRequestError:
        """Build network failure error message."""
        return cls(f"Supabase {method} {url} network failure: {detail}")


def _supabase_rest_base_url() -> str:
    """Return Supabase REST API base URL."""
    supabase_url = read_supabase_setting("SUPABASE_URL")
    if not supabase_url:
        raise SupabaseConfigError.missing_url()

    return f"{supabase_url.rstrip('/')}/rest/v1"


def _read_api_keys_for_select() -> list[str]:
    """Return service-role read key for server-side dashboard queries."""
    key = read_supabase_setting("SUPABASE_SERVICE_ROLE_KEY")
    if not key:
        raise SupabaseConfigError.missing_read_key()
    return [key]


def _write_api_key() -> str:
    """Return service-role key for Supabase upserts."""
    key = read_supabase_setting("SUPABASE_SERVICE_ROLE_KEY")
    if not key:
        raise SupabaseConfigError.missing_write_key()

    return key


def _request_json(
    method: str,
    path: str,
    api_key: str,
    payload: list[dict[str, Any]] | None = None,
    extra_headers: dict[str, str] | None = None,
) -> list[dict[str, Any]] | dict[str, Any] | None:
    """Execute a Supabase REST request and decode JSON responses."""
    base = _supabase_rest_base_url()
    url = f"{base}/{path}"

    headers = {
        "apikey": api_key,
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    if extra_headers:
        headers.update(extra_headers)

    data: bytes | None = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")

    request = Request(url=url, data=data, method=method, headers=headers)  # noqa: S310
    try:
        with urlopen(request, timeout=30) as response:  # noqa: S310
            body = response.read().decode("utf-8").strip()
            if not body:
                return None
            return json.loads(body)
    except HTTPError as exc:
        response_body = ""
        try:
            response_body = exc.read().decode("utf-8").strip()
        except (TypeError, ValueError, UnicodeDecodeError):
            response_body = "(unable to decode response body)"

        raise SupabaseRequestError.http_failure(
            method,
            url,
            exc.code,
            response_body or exc.reason,
        ) from exc
    except URLError as exc:
        raise SupabaseRequestError.network_failure(
            method,
            url,
            str(exc.reason),
        ) from exc


def _chunked(
    items: list[dict[str, Any]],
    chunk_size: int,
) -> list[list[dict[str, Any]]]:
    """Split a list into fixed-size chunks."""
    return [items[i : i + chunk_size] for i in range(0, len(items), chunk_size)]


def _parse_iso_date(raw_value: Any) -> date | None:
    """Parse a date-like value into a date object."""
    if not raw_value:
        return None
    try:
        return date.fromisoformat(str(raw_value))
    except ValueError:
        return None


def fetch_event_date_bounds_from_supabase() -> tuple[date, date] | None:
    """Fetch earliest and latest event dates using lightweight limit queries."""
    read_keys = _read_api_keys_for_select()

    oldest_path = "events?" + urlencode(
        {
            "select": "event_date",
            "order": "event_date.asc",
            "limit": 1,
        },
    )
    newest_path = "events?" + urlencode(
        {
            "select": "event_date",
            "order": "event_date.desc",
            "limit": 1,
        },
    )

    last_error: SupabaseRequestError | None = None
    for read_key in read_keys:
        try:
            oldest_payload = _request_json("GET", oldest_path, read_key)
            newest_payload = _request_json("GET", newest_path, read_key)
        except SupabaseRequestError as exc:
            last_error = exc
            continue

        if not isinstance(oldest_payload, list) or not isinstance(newest_payload, list):
            raise SupabaseRequestError.expected_list_payload()
        if not oldest_payload or not newest_payload:
            return None

        start_date = _parse_iso_date(oldest_payload[0].get("event_date"))
        end_date = _parse_iso_date(newest_payload[0].get("event_date"))
        if start_date is None or end_date is None:
            return None
        if start_date > end_date:
            start_date, end_date = end_date, start_date
        return start_date, end_date

    if last_error is not None:
        raise last_error
    return None


def fetch_events_from_supabase(
    lookback_days: int,
    period_start: date | None = None,
    period_end: date | None = None,
) -> list[dict[str, Any]]:
    """Fetch event rows from Supabase for the dashboard timeline window."""
    lookback_days = max(lookback_days, 1)

    read_keys = _read_api_keys_for_select()
    if period_start is not None and period_end is not None:
        if period_start > period_end:
            period_start, period_end = period_end, period_start
        after_date = period_start
        before_date = period_end
    else:
        before_date = datetime.now(tz=UTC).date()
        after_date = before_date - timedelta(days=lookback_days - 1)

    query = urlencode(
        {
            "select": "event_date,project,event_type,count",
            "order": "event_date.asc",
            "and": (
                f"(event_date.gte.{after_date.isoformat()},"
                f"event_date.lte.{before_date.isoformat()})"
            ),
        },
    )
    path = f"events?{query}"
    last_error: SupabaseRequestError | None = None
    response: list[dict[str, Any]] | dict[str, Any] | None = None
    for read_key in read_keys:
        try:
            response = _request_json("GET", path, read_key)
            break
        except SupabaseRequestError as exc:
            last_error = exc
            continue

    if response is None and last_error is not None:
        raise last_error

    if response is None:
        return []
    if not isinstance(response, list):
        raise SupabaseRequestError.expected_list_payload()

    return response


def _upsert_event_records_to_table(  # pylint: disable=too-many-locals
    event_records: list[dict[str, Any]],
    table_name: str,
) -> int:
    """Upsert normalized event records into a specific Supabase table."""
    if not event_records:
        return 0

    write_key = _write_api_key()

    aggregated_counts: dict[tuple[str, str, str], int] = {}
    for record in event_records:
        event_date_raw = record.get("event_date")
        project_name = str(record.get("project", "")).strip()
        event_type = str(record.get("event_type", "")).strip()
        count = int(record.get("count", 0))
        if not event_date_raw or not project_name or not event_type or count <= 0:
            continue

        event_date = str(event_date_raw)
        key = (project_name, event_type, event_date)
        aggregated_counts[key] = aggregated_counts.get(key, 0) + count

    payload: list[dict[str, Any]] = [
        {
            "project": project_name,
            "event_type": event_type,
            "event_date": event_date,
            "count": total_count,
        }
        for (
            project_name,
            event_type,
            event_date,
        ), total_count in aggregated_counts.items()
    ]

    if not payload:
        return 0

    conflict = quote("project,event_type,event_date", safe=",")
    path = f"{table_name}?on_conflict={conflict}"
    batch_size = 500
    for batch in _chunked(payload, batch_size):
        _request_json(
            "POST",
            path,
            write_key,
            payload=batch,
            extra_headers={"Prefer": "resolution=merge-duplicates,return=minimal"},
        )

    logger.info(
        "Upserted %s event records to Supabase table %s",
        len(payload),
        table_name,
    )
    return len(payload)


def upsert_events_to_supabase(event_records: list[dict[str, Any]]) -> int:
    """Upsert GitLab event records into Supabase events table."""
    return _upsert_event_records_to_table(event_records, "events")


def upsert_jira_events_to_supabase(event_records: list[dict[str, Any]]) -> int:
    """Upsert Jira event records into Supabase jira_events table."""
    return _upsert_event_records_to_table(event_records, "jira_events")
