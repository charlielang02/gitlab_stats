"""Configuration for GitLab Stats dashboard.

Feature flags and settings. Sensitive credentials are loaded from .env file.
"""

# --- Data Source Configuration ---
# Set to True to use GitLab API as primary data source (with parser fallback)
# Set to False to use only file-based parser
USE_API = True

# When USE_API is True and API returns data, still show this data source in UI
SHOW_DATA_SOURCE_INFO = False

# --- API Behavior Configuration (non-secret) ---
# Default lookback for API event ingestion window.
API_LOOKBACK_DAYS = 365

# Pagination controls for /users/:id/events.
API_EVENTS_PER_PAGE = 100
API_MAX_EVENT_PAGES = 200

# Dashboard cache window for expensive API/parser loads.
DATA_CACHE_TTL_SECONDS = 1800  # 30 minutes

# Optional holiday filtering for streak calculations (ISO country code, e.g. "US").
# Leave empty to use weekday-only streak calculations.
STREAK_HOLIDAY_COUNTRY = "CA"
