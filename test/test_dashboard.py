"""Unit tests for dashboard helpers and orchestration."""

from __future__ import annotations

from datetime import date
from datetime import timedelta
from typing import Any

import pandas as pd
import pytest

from gitlab_stats import dashboard

# pylint: disable=protected-access


def test_normalize_metrics_for_cache_returns_plain_dicts():
    """Cache normalization should coerce mapping keys to plain string-keyed dicts."""
    # Arrange
    metrics = {"project-a": {"commits": 3}, "project-b": {"mr_opened": 2}}
    totals = {"total_contributions": 5}

    # Act
    normalized_metrics, normalized_totals = dashboard._normalize_metrics_for_cache(
        metrics,
        totals,
    )

    # Assert
    assert normalized_metrics == {
        "project-a": {"commits": 3},
        "project-b": {"mr_opened": 2},
    }
    assert normalized_totals == {"total_contributions": 5}


def test_parse_iso_date_handles_valid_and_invalid_values():
    """ISO parser should decode valid dates and return None for invalid input."""
    # Arrange / Act / Assert
    assert dashboard._parse_iso_date("2026-03-15") == date(2026, 3, 15)
    assert dashboard._parse_iso_date("") is None
    assert dashboard._parse_iso_date(None) is None
    assert dashboard._parse_iso_date("invalid") is None


def test_safe_int_uses_default_for_invalid_values():
    """Safe integer conversion should preserve defaults for invalid values."""
    # Arrange / Act / Assert
    assert dashboard._safe_int("7", default=1) == 7
    assert dashboard._safe_int(2.8, default=1) == 2
    assert dashboard._safe_int(None, default=9) == 9
    assert dashboard._safe_int("abc", default=4) == 4


def test_fallback_date_bounds_uses_minimum_window_and_today(monkeypatch):
    """Fallback bounds should cover at least one year ending on current UTC day."""
    # Arrange
    monkeypatch.setattr(dashboard, "_today_utc", lambda: date(2026, 4, 1))

    # Act
    start_date, end_date = dashboard._fallback_date_bounds()

    # Assert
    assert end_date == date(2026, 4, 1)
    assert start_date == end_date - timedelta(days=364)


def test_resolve_effective_bounds_handles_missing_invalid_and_swapped_payloads(
    monkeypatch,
):
    """Bounds resolution should fallback or normalize start/end ordering."""
    # Arrange
    monkeypatch.setattr(
        dashboard,
        "_fallback_date_bounds",
        lambda: (date(2025, 1, 1), date(2025, 12, 31)),
    )

    # Act
    fallback = dashboard._resolve_effective_bounds(None)
    invalid = dashboard._resolve_effective_bounds(
        {"start": "bad", "end": "2025-02-01", "source": "supabase"},
    )
    swapped = dashboard._resolve_effective_bounds(
        {"start": "2025-03-10", "end": "2025-03-01", "source": "supabase"},
    )

    # Assert
    assert fallback == (date(2025, 1, 1), date(2025, 12, 31), "fallback")
    assert invalid == (date(2025, 1, 1), date(2025, 12, 31), "fallback")
    assert swapped == (date(2025, 3, 1), date(2025, 3, 10), "supabase")


def test_window_from_preset_supports_all_time_ytd_custom_and_fixed(monkeypatch):
    """Preset window selection should map each preset to expected date ranges."""
    # Arrange
    absolute_start = date(2025, 1, 1)
    absolute_end = date(2025, 12, 31)
    monkeypatch.setattr(
        dashboard,
        "_render_custom_window_inputs",
        lambda *_: (date(2025, 5, 1), date(2025, 5, 20)),
    )

    # Act
    all_time = dashboard._window_from_preset("All time", absolute_start, absolute_end)
    ytd = dashboard._window_from_preset("YTD", absolute_start, absolute_end)
    custom = dashboard._window_from_preset("Custom", absolute_start, absolute_end)
    fixed = dashboard._window_from_preset("Last 30 days", absolute_start, absolute_end)

    # Assert
    assert all_time == (absolute_start, absolute_end)
    assert ytd == (absolute_start, absolute_end)
    assert custom == (date(2025, 5, 1), date(2025, 5, 20))
    assert fixed == (date(2025, 12, 2), absolute_end)


def test_enforce_min_window_adjusts_and_warns_when_window_too_small(monkeypatch):
    """Minimum-window enforcement should shift start date and emit warning."""
    # Arrange
    warnings: list[str] = []

    def _record_warning(message: str):
        """Capture warning text emitted by minimum-window enforcement."""
        warnings.append(message)

    monkeypatch.setattr(
        dashboard.st,
        "warning",
        _record_warning,
    )

    # Act
    start, end, days = dashboard._enforce_min_window(
        date(2026, 3, 28),
        date(2026, 4, 1),
        date(2026, 1, 1),
    )

    # Assert
    assert start == date(2026, 3, 26)
    assert end == date(2026, 4, 1)
    assert days == 7
    assert warnings == [
        "Minimum timeframe is 7 days. Window has been adjusted automatically.",
    ]


def test_totals_from_metric_df_handles_nonzero_and_zero_totals():
    """Aggregated totals should compute percentages only when total is positive."""
    # Arrange
    non_zero_df = pd.DataFrame(
        {
            "code_contributions": [8, 2],
            "collab_contributions": [2, 3],
            "total_contributions": [10, 5],
        },
    )
    zero_df = pd.DataFrame(
        {
            "code_contributions": [0],
            "collab_contributions": [0],
            "total_contributions": [0],
        },
    )

    # Act
    non_zero_totals = dashboard._totals_from_metric_df(non_zero_df)
    zero_totals = dashboard._totals_from_metric_df(zero_df)

    # Assert
    assert non_zero_totals["total_contributions"] == 15.0
    assert non_zero_totals["code_pct"] == 66.7
    assert non_zero_totals["collab_pct"] == 33.3
    assert zero_totals["code_pct"] == 0.0
    assert zero_totals["collab_pct"] == 0.0


def test_normalize_uploaded_metric_df_derives_missing_columns_and_filters_zero_rows():
    """Uploaded metric normalization should derive totals and drop zero-contribution rows."""
    # Arrange
    uploaded = pd.DataFrame(
        {
            "project": ["project-a", "project-b"],
            "commits": [2, 0],
            "branch_created": [1, 0],
            "branch_deleted": [0, 0],
            "mr_opened": [1, 0],
            "mr_merged": [0, 0],
            "mr_approved": [0, 0],
            "mr_commented": [0, 0],
            "issue_opened": [0, 0],
        },
    )

    # Act
    normalized = dashboard._normalize_uploaded_metric_df(uploaded)

    # Assert
    assert list(normalized.index) == ["project-a"]
    assert normalized.loc["project-a", "code_contributions"] == 3
    assert normalized.loc["project-a", "collab_contributions"] == 1
    assert normalized.loc["project-a", "total_contributions"] == 4
    assert normalized.loc["project-a", "code_pct"] == 75.0
    assert normalized.loc["project-a", "collab_pct"] == 25.0


def test_timeline_from_uploaded_df_handles_missing_and_valid_timeline_rows():
    """Timeline extraction should return metadata for absent and valid timeline rows."""
    # Arrange
    no_row_type = pd.DataFrame({"project": ["a"], "commits": [1]})
    invalid_timeline = pd.DataFrame(
        {
            "row_type": ["timeline_day"],
            "event_date": ["not-a-date"],
            "project": [""],
            "total_contributions": [1],
        },
    )
    valid_timeline = pd.DataFrame(
        {
            "row_type": ["timeline_day", "timeline_day"],
            "event_date": ["2026-03-01", "2026-03-03"],
            "project": ["", ""],
            "total_contributions": [1, 2],
            "code_contributions": [1, 1],
            "collab_contributions": [0, 1],
            "commits": [1, 1],
        },
    )

    # Act
    no_df, no_meta = dashboard._timeline_from_uploaded_df(no_row_type)
    invalid_df, invalid_meta = dashboard._timeline_from_uploaded_df(invalid_timeline)
    valid_df, valid_meta = dashboard._timeline_from_uploaded_df(valid_timeline)

    # Assert
    assert no_df is None
    assert no_meta["has_real_dates"] is False
    assert invalid_df is None
    assert invalid_meta["has_real_dates"] is False
    assert valid_df is not None
    assert valid_meta["period_start"] == "2026-03-01"
    assert valid_meta["period_end"] == "2026-03-03"
    assert valid_meta["expected_days"] == 3


def test_load_uploaded_metrics_csv_returns_none_for_empty_upload(monkeypatch):
    """CSV loader should return None when uploaded CSV contains no usable rows."""
    # Arrange
    monkeypatch.setattr(dashboard.pd, "read_csv", lambda *_: pd.DataFrame())

    # Act
    result = dashboard._load_uploaded_metrics_csv(b"project,commits\n")

    # Assert
    assert result is None


def test_load_uploaded_metrics_csv_parses_project_and_timeline_rows():
    """CSV loader should parse mixed project and timeline rows into payload tuple."""
    # Arrange
    csv_text = (
        "row_type,project,commits,branch_created,branch_deleted,mr_opened,mr_merged,"
        "mr_approved,mr_commented,issue_opened,event_date,code_contributions,"
        "collab_contributions,total_contributions\n"
        "project_metric,project-a,2,1,0,1,0,0,0,0,,3,1,4\n"
        "timeline_day,,1,0,0,0,0,0,0,0,2026-03-01,1,0,1\n"
    )

    # Act
    result = dashboard._load_uploaded_metrics_csv(csv_text.encode("utf-8"))

    # Assert
    assert result is not None
    metrics, totals, timeline_df, timeline_meta = result
    assert metrics["project-a"]["total_contributions"] == 4
    assert totals["total_contributions"] == 4.0
    assert timeline_df is not None
    assert timeline_meta["has_real_dates"] is True


def test_request_period_and_credential_helpers_work_as_expected():
    """Request parsing helpers should decode period dates and credential presence."""
    # Arrange
    request = {
        "period_start": "2026-03-01",
        "period_end": "2026-03-10",
        "api_base_url": " https://example.com ",
        "api_token": " token ",
    }

    # Act
    period = dashboard._request_period(request)  # type: ignore
    has_credentials = dashboard._has_source_credentials(
        request,  # type: ignore
        "api_base_url",
        "api_token",
    )

    # Assert
    assert period == (date(2026, 3, 1), date(2026, 3, 10))
    assert has_credentials is True


def test_normalize_source_result_attaches_source_and_normalizes_payload():
    """Source normalization should attach source and produce cache-safe mappings."""
    # Arrange
    result = (
        {"project-a": {"commits": 1}},
        {"total_contributions": 1},
        "timeline",
        {},
    )

    # Act
    normalized = dashboard._normalize_source_result(result, source_name="api")

    # Assert
    assert normalized is not None
    metrics, totals, timeline_df, timeline_meta = normalized
    assert metrics == {"project-a": {"commits": 1}}
    assert totals == {"total_contributions": 1}
    assert timeline_df == "timeline"
    assert timeline_meta["source"] == "api"


def test_load_metrics_cached_prefers_supabase_then_api(monkeypatch):
    """Cached loader should prefer Supabase and fallback to API when needed."""
    # Arrange
    api_result = (
        {"project-b": {"total_contributions": 2}},
        {"total_contributions": 2},
        "timeline2",
        {},
    )

    monkeypatch.setattr(
        dashboard,
        "fetch_metrics_from_supabase_with_time",
        lambda **_: None,
    )
    monkeypatch.setattr(
        dashboard,
        "fetch_metrics_from_api_with_time",
        lambda **_: api_result,
    )

    request = {
        "use_supabase": True,
        "use_api": True,
        "supabase_url": "https://supabase.example",
        "supabase_key": "key",
        "api_base_url": "https://gitlab.example",
        "api_token": "token",
        "period_start": "2026-03-01",
        "period_end": "2026-03-07",
    }

    # Act
    normalized = dashboard._load_metrics_cached(request)

    # Assert
    assert normalized is not None
    metrics, totals, _, timeline_meta = normalized
    assert metrics == {"project-b": {"total_contributions": 2}}
    assert totals == {"total_contributions": 2}
    assert timeline_meta["source"] == "api"


def test_configure_page_calls_page_setup_and_header(monkeypatch):
    """Page configuration should set Streamlit config and shared dashboard chrome."""
    # Arrange
    calls: dict[str, Any] = {}

    def _fake_set_page_config(**kwargs):
        """Capture page-config arguments."""
        calls["config"] = kwargs

    def _fake_inject_dashboard_styles():
        """Record stylesheet injection call."""
        calls["styles"] = True

    def _fake_render_main_header():
        """Record main-header rendering call."""
        calls["header"] = True

    monkeypatch.setattr(dashboard.st, "set_page_config", _fake_set_page_config)
    monkeypatch.setattr(
        dashboard,
        "inject_dashboard_styles",
        _fake_inject_dashboard_styles,
    )
    monkeypatch.setattr(dashboard, "render_main_header", _fake_render_main_header)

    # Act
    dashboard.configure_page()

    # Assert
    assert calls["config"]["layout"] == "wide"
    assert calls["config"]["page_title"] == "GitLab Contributions Dashboard"
    assert calls["styles"] is True
    assert calls["header"] is True


class _FakeSpinner:
    """Simple context manager for st.spinner patching in orchestration tests."""

    def __enter__(self):
        """Enter spinner context."""
        return self

    def __exit__(self, exc_type, exc_value, exc_traceback):
        """Exit spinner context without suppressing errors."""
        return False


def test_get_metrics_returns_supabase_result_with_attached_window(monkeypatch):
    """get_metrics should return Supabase data and attach selected window metadata."""
    # Arrange
    monkeypatch.setattr(dashboard.config, "USE_SUPABASE", True)
    monkeypatch.setattr(dashboard.config, "USE_API", False)
    monkeypatch.setattr(dashboard.config, "SHOW_DATA_SOURCE_INFO", False)
    monkeypatch.setattr(
        dashboard,
        "_load_date_bounds_cached",
        lambda *_: {
            "source": "supabase",
            "start": "2026-03-01",
            "end": "2026-03-10",
        },
    )
    monkeypatch.setattr(
        dashboard,
        "_select_time_window",
        lambda *_: (date(2026, 3, 4), date(2026, 3, 10), "selected-window"),
    )
    monkeypatch.setattr(
        dashboard,
        "_load_metrics_cached",
        lambda *_: (
            {"project-a": {"total_contributions": 4}},
            {"total_contributions": 4},
            "timeline",
            {"source": "supabase"},
        ),
    )
    monkeypatch.setattr(dashboard.st, "spinner", lambda *_: _FakeSpinner())
    monkeypatch.setattr(dashboard.st, "button", lambda *_, **__: False)

    # Act
    result = dashboard.get_metrics()

    # Assert
    assert result is not None
    _, _, _, timeline_meta = result
    assert timeline_meta["requested_period_start"] == "2026-03-04"
    assert timeline_meta["requested_period_end"] == "2026-03-10"
    assert timeline_meta["window_label"] == "selected-window"
    assert timeline_meta["bounds_source"] == "supabase"


def test_get_metrics_uses_csv_fallback_when_sources_fail(monkeypatch):
    """get_metrics should fallback to uploaded CSV when live source loads fail."""
    # Arrange
    monkeypatch.setattr(dashboard.config, "USE_SUPABASE", True)
    monkeypatch.setattr(dashboard.config, "USE_API", False)
    monkeypatch.setattr(dashboard.config, "SHOW_DATA_SOURCE_INFO", False)
    monkeypatch.setattr(dashboard, "_load_date_bounds_cached", lambda *_: None)
    monkeypatch.setattr(
        dashboard,
        "_select_time_window",
        lambda *_: (date(2026, 3, 1), date(2026, 3, 7), "window"),
    )
    monkeypatch.setattr(dashboard, "_load_metrics_cached", lambda *_: None)
    monkeypatch.setattr(dashboard.st, "spinner", lambda *_: _FakeSpinner())
    monkeypatch.setattr(dashboard.st, "warning", lambda *_: None)

    uploaded_payload = (
        {"project-a": {"total_contributions": 1}},
        {"total_contributions": 1},
        "timeline",
        {"source": "uploaded_csv"},
    )

    class _FakeUpload:  # pylint: disable=too-few-public-methods
        """Simple uploaded-file stand-in with getvalue support."""

        def __init__(self, payload: bytes):
            self._payload = payload

        def getvalue(self):
            """Return raw uploaded bytes."""
            return self._payload

    monkeypatch.setattr(
        dashboard.st,
        "file_uploader",
        lambda *_, **__: _FakeUpload(b"csv"),
    )
    monkeypatch.setattr(
        dashboard,
        "_load_uploaded_metrics_csv",
        lambda *_: uploaded_payload,
    )
    monkeypatch.setattr(dashboard.st, "info", lambda *_: None)

    # Act
    result = dashboard.get_metrics()

    # Assert
    assert result == uploaded_payload


def test_main_stops_with_error_when_metrics_unavailable(monkeypatch):
    """Main should show an error and stop when metrics cannot be loaded."""
    # Arrange
    calls: list[str] = []

    def _fake_configure_page():
        """No-op page configuration for failure-path testing."""
        return

    def _fake_get_metrics():
        """Return no metrics to trigger the main error branch."""
        return

    def _record_error(message: str):
        """Capture Streamlit error message for assertion."""
        calls.append(message)

    monkeypatch.setattr(dashboard, "configure_page", _fake_configure_page)
    monkeypatch.setattr(dashboard, "get_metrics", _fake_get_metrics)
    monkeypatch.setattr(dashboard.st, "error", _record_error)

    def _fake_stop():
        """Interrupt execution similarly to Streamlit stop."""
        raise RuntimeError("stop")

    monkeypatch.setattr(dashboard.st, "stop", _fake_stop)

    # Act / Assert
    with pytest.raises(RuntimeError, match="stop"):
        dashboard.main()
    assert calls == ["Unable to load metrics. Please check your data source."]


def test_main_renders_all_sections_when_metrics_available(monkeypatch):
    """Main should call each renderer in sequence when metrics load successfully."""
    # Arrange
    render_calls: list[str] = []
    metric_df = pd.DataFrame({"commits": [1]}, index=["project-a"])
    ordered_columns = ["commits"]
    metrics_result = (
        {"project-a": {"commits": 1}},
        {"total_contributions": 1},
        "timeline",
        {},
    )

    monkeypatch.setattr(
        dashboard,
        "configure_page",
        lambda: render_calls.append("configure"),
    )
    monkeypatch.setattr(dashboard, "get_metrics", lambda: metrics_result)
    monkeypatch.setattr(
        dashboard,
        "prepare_metric_df",
        lambda *_: (metric_df, ordered_columns),
    )
    monkeypatch.setattr(
        dashboard,
        "render_executive_summary",
        lambda *_: render_calls.append("executive"),
    )
    monkeypatch.setattr(
        dashboard,
        "render_profile",
        lambda *_: render_calls.append("profile"),
    )
    monkeypatch.setattr(
        dashboard,
        "render_behavior_analysis",
        lambda *_: render_calls.append("behavior"),
    )
    monkeypatch.setattr(
        dashboard,
        "render_key_insights",
        lambda *_: render_calls.append("insights"),
    )
    monkeypatch.setattr(
        dashboard,
        "render_contribution_distribution",
        lambda *_: render_calls.append("distribution"),
    )
    monkeypatch.setattr(
        dashboard,
        "render_breakdown_tabs",
        lambda *_: render_calls.append("breakdown"),
    )
    monkeypatch.setattr(
        dashboard,
        "render_performance_tabs",
        lambda *_: render_calls.append("performance"),
    )
    monkeypatch.setattr(
        dashboard,
        "render_top_projects",
        lambda *_: render_calls.append("top"),
    )
    monkeypatch.setattr(
        dashboard,
        "render_project_deep_dive",
        lambda *_: render_calls.append("deep_dive"),
    )
    monkeypatch.setattr(
        dashboard,
        "render_export_with_timeline",
        lambda *_: render_calls.append("export"),
    )

    # Act
    dashboard.main()

    # Assert
    assert render_calls == [
        "configure",
        "executive",
        "profile",
        "behavior",
        "insights",
        "distribution",
        "breakdown",
        "performance",
        "top",
        "deep_dive",
        "export",
    ]
