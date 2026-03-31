"""Configuration for GitLab Stats dashboard.

Feature flags and settings.
"""

# --- Data Source Configuration ---
# Set to True to use GitLab API as primary data source (with parser fallback)
# Set to False to use only file-based parser
USE_API = True

# Set to True to load dashboard metrics from Supabase first (HTTPS only).
USE_SUPABASE = True

# When USE_API is True and API returns data, still show this data source in UI
SHOW_DATA_SOURCE_INFO = True

# --- API Behavior Configuration (non-secret) ---
# Default lookback for API event ingestion window.
API_LOOKBACK_DAYS = 365

# Pagination controls for /users/:id/events.
API_EVENTS_PER_PAGE = 100
API_MAX_EVENT_PAGES = 200

# Dashboard cache window for expensive API/parser loads.
DATA_CACHE_TTL_SECONDS = 1800  # 30 minutes

# Supabase timeline read window (days) for dashboard metrics.
SUPABASE_LOOKBACK_DAYS = 365

# Optional holiday filtering for streak calculations (ISO country code, e.g. "US").
# Leave empty to use weekday-only streak calculations.
STREAK_HOLIDAY_COUNTRY = "CA"
