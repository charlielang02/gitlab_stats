# GitLab Stats

GitLab Stats is a Streamlit dashboard package for visualizing GitLab contribution activity.

The current package is built around a Supabase-first data flow:

- Sync normalized GitLab API events into Supabase (HTTPS only)
- Rebuild project metrics and behavior timelines from Supabase event rows
- Fall back to direct GitLab API reads when enabled
- Fall back to uploaded CSV only when live sources are unavailable

You can run this project in two supported modes:

- **Quick local mode (~5 minutes):** Run the dashboard directly from the GitLab API (no Supabase required)
- **Deployed mode (~15 minutes):** Sync data to Supabase, then run/deploy the Supabase-backed dashboard

## Table of Contents

- [What Is Included](#what-is-included)
- [Architecture](#architecture)
- [Requirements](#requirements)
- [Installation](#installation)
- [Configuration](#configuration)
- [Choose Your Setup Path](#choose-your-setup-path)
- [Quick Local Dashboard (API Only, ~5 Minutes)](#quick-local-dashboard-api-only-5-minutes)
- [Deployed Dashboard With Supabase (~15 Minutes)](#deployed-dashboard-with-supabase-15-minutes)
- [Usage](#usage)
- [Timeframe Controls](#timeframe-controls)
- [Windows Task Scheduler (Recommended)](#windows-task-scheduler-recommended)
- [Project Structure](#project-structure)
- [Development](#development)
- [Coverage In Pull Requests](#coverage-in-pull-requests)
- [License](#license)

## What Is Included

- Supabase-first dashboard loading (`USE_SUPABASE = True` by default)
- GitLab API ingestion and normalization pipeline
- Supabase sync CLI for scheduled backfills
- Streamlit + Plotly interactive analytics dashboard
- Behavior analysis from real timeline data
- Dynamic timeframe selector (7-day minimum up to all available history)
- CSV upload fallback for offline viewing/export replay
- Pre-commit, linting, and test tooling via Poetry

## Architecture

```mermaid
graph TB
    A[GitLab API /users/:id/events]
    B[gitlab_stats.database.supabase_sync]
    C[Supabase events table]
    D[gitlab_stats.dashboard]
    E[gitlab_stats.gitlab_stats_api_ingester]
    F[CSV upload fallback]
    G[Streamlit + Plotly Dashboard]

    A --> B
    B --> C
    C --> E
    A --> E
    E --> D
    F --> D
    D --> G
```

## Requirements

- Python 3.11+
- Poetry
- Git
- A GitLab Personal Access Token
- Supabase project URL + service role key (only for Supabase/deployed mode)

## Installation

1. Clone the repository.

```bash
git clone <repository-url>
cd gitlab_stats
```

1. Install Poetry (Windows helper script is included).

```powershell
.\tools\install_poetry.bat
```

1. Set up the environment and hooks.

```powershell
.\tools\after_checkout.bat
```

## Configuration

Create a `.env` file in the repository root:

```bash
# Supabase (required for Supabase-first mode)
SUPABASE_URL=https://<your-project>.supabase.co
SUPABASE_SERVICE_ROLE_KEY=<your-service-role-key>

# GitLab API (required for sync and API fallback)
GITLAB_API_BASE_URL=https://<your-gitlab-host>/api/v4
GITLAB_API_TOKEN=<your-gitlab-personal-access-token>
```

Primary runtime flags are in `gitlab_stats/config.py`:

- `USE_SUPABASE`: Load dashboard metrics from Supabase first
- `USE_API`: Allow API fallback when Supabase is unavailable
- `SHOW_DATA_SOURCE_INFO`: Show source/timing banners in the UI
- `SUPABASE_LOOKBACK_DAYS`: Supabase read window for timeline/metrics
- `API_LOOKBACK_DAYS`: API event lookback window
- `API_EVENTS_PER_PAGE`: GitLab events page size (max 100)
- `API_MAX_EVENT_PAGES`: Upper bound on paginated API fetches
- `DATA_CACHE_TTL_SECONDS`: Streamlit cache TTL for expensive loads
- `STREAK_HOLIDAY_COUNTRY`: Optional ISO country code for holiday-aware streaks

## Choose Your Setup Path

**Do users need to fork this repository?**

- **No, not required.** A local user can clone this repository directly and run it.
- **Forking is recommended** only if someone wants their own hosted/deployed copy
(for example, Streamlit Community Cloud linked to their own GitHub account).

Use one of the two setup paths below.

## Quick Local Dashboard (API Only, ~5 Minutes)

Use this when the user just needs a local dashboard quickly.

1. Clone the repository (fork optional):

```bash
git clone <repository-url>
cd gitlab_stats
```

1. Install Poetry and project dependencies:

```powershell
.\tools\install_poetry.bat
.\tools\after_checkout.bat
```

1. Add a `.env` file with GitLab API settings only:

```bash
GITLAB_API_BASE_URL=https://<your-gitlab-host>/api/v4
GITLAB_API_TOKEN=<your-gitlab-personal-access-token>
```

1. Enable API mode in `gitlab_stats/config.py`:

- Set `USE_API = True`
- Set `USE_SUPABASE = False`

1. Start the dashboard:

```bash
poetry run streamlit run gitlab_stats/dashboard.py
```

Open the local URL shown by Streamlit (usually `http://localhost:8501`).

## Deployed Dashboard With Supabase (~15 Minutes)

Use this when you want persistent synced data and a shareable hosted dashboard.

1. Clone or fork the repository.

- Clone is fine for local-only use.
- Fork if you plan to deploy from your own GitHub repository.

1. Create a Supabase project and capture:

- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY`

1. Configure `.env` with both Supabase and API credentials:

```bash
SUPABASE_URL=https://<your-project>.supabase.co
SUPABASE_SERVICE_ROLE_KEY=<your-service-role-key>
GITLAB_API_BASE_URL=https://<your-gitlab-host>/api/v4
GITLAB_API_TOKEN=<your-gitlab-personal-access-token>
```

1. Configure `gitlab_stats/config.py` for Supabase-first mode:

- Set `USE_SUPABASE = True`
- Set `USE_API = True` (recommended fallback)

1. Run an initial sync to populate Supabase:

```bash
poetry run python -m gitlab_stats.database.supabase_sync
```

1. Run locally to validate:

```bash
poetry run streamlit run gitlab_stats/dashboard.py
```

1. Deploy (optional but typical for this path):

- Streamlit Community Cloud: connect your fork/repo and set the same secrets in the app settings.
- Any other host: provide the same environment variables in deployment config.

Notes:

- This project is user-configurable by environment variables; no personal account IDs are hardcoded.
- If your GitLab API is internal-only, run sync from a machine that has network access to that GitLab instance.
- You do not need a shared multi-user login flow to use this project for individual dashboards.

## Usage

Deployed dashboard:

- <https://git-lab-stats-cl.streamlit.app/>

Run the dashboard:

```bash
poetry run streamlit run gitlab_stats/dashboard.py
```

Run a one-time sync from GitLab API into Supabase:

```bash
poetry run python -m gitlab_stats.database.supabase_sync
```

Open the dashboard at the local Streamlit URL (usually `http://localhost:8501`).

### Data Source Behavior

Load order is:

1. Supabase (if enabled and credentials exist)
2. GitLab API (if enabled and credentials exist)
3. Uploaded CSV fallback (only after live-source failure)

The dashboard also provides a `Refresh Data Cache` button to clear Streamlit cache and re-fetch data.

## Timeframe Controls

The dashboard includes a dynamic timeframe selector shown above the Executive Summary.

- Presets: Last 7 days, Last 30 days, Last 90 days, Last 6 months, Last 1 year, YTD, All time, Custom
- Minimum window: 7 days
- Maximum window: all available contribution history (earliest to latest date available)

Behavior-analysis chart visibility is window-aware:

- Weekly Contribution Mix is hidden for windows shorter than 4 weeks
- Monthly Contribution Volume is hidden for windows shorter than 2 months

## Windows Task Scheduler (Recommended)

For automation, schedule the Supabase sync command at login or daily:

```powershell
poetry run python -m gitlab_stats.database.supabase_sync
```

Suggested scheduler settings:

- Trigger: At log on (or daily)
- Run whether user is logged on or not (if permissions allow)
- Start in: repository root directory
- Redirect output to a log file for troubleshooting

## Project Structure

```bash
gitlab_stats/
├── README.md
├── LICENSE
├── pyproject.toml
├── poetry.toml
├── doc/
│   ├── changelog_prompts.txt
│   ├── markdownlint_report.txt
│   └── pylint_report.txt
├── gitlab_stats/
│   ├── __init__.py
│   ├── config.py
│   ├── dashboard.py
│   ├── gitlab_stats_api_ingester.py
│   ├── settings.py
│   ├── dashboard_utils/
│   │   ├── activity_rules.py
│   │   ├── charts.py
│   │   ├── helpers.py
│   │   ├── metrics_schema.py
│   │   ├── sections.py
│   │   └── timeline_utils.py
│   └── database/
│       ├── __init__.py
│       ├── supabase_client.py
│       └── supabase_sync.py
├── test/
│   ├── __init__.py
│   ├── test_charts.py
│   ├── test_dashboard.py
│   ├── test_gitlab_stats_api_ingester.py
│   ├── test_helpers.py
│   ├── test_sections.py
│   ├── test_settings.py
│   ├── test_supabase_client.py
│   ├── test_supabase_sync.py
│   └── test_timeline_utils.py
└── tools/
    ├── __init__.py
    ├── after_checkout.bat
    ├── install_poetry.bat
    └── pylint_reporter.py
```

## Development

Run all quality checks:

```bash
poetry run pre-commit run --all-files
```

Run focused linting:

```bash
poetry run pylint gitlab_stats/dashboard.py gitlab_stats/gitlab_stats_api_ingester.py
```

Run tests:

```bash
poetry run pytest
```

Run tests with coverage and a minimum threshold:

```bash
poetry run pytest --cov=gitlab_stats --cov-branch --cov-report=term-missing --cov-report=xml --cov-fail-under=80
```

## Coverage In Pull Requests

This repository includes a GitHub Actions workflow at `.github/workflows/ci.yml` that:

- runs on pushes and pull requests
- executes pytest with branch coverage
- fails if total coverage drops below 80%
- uploads `coverage.xml` as a build artifact
- optionally uploads coverage to Codecov for PR annotations

Increase the `--cov-fail-under` value in `.github/workflows/ci.yml`
as coverage improves so quality gates continue getting stricter.

To make this visible and enforceable in GitHub:

1. Go to repository Settings -> Branches -> Branch protection rules.
2. Require status checks before merging.
3. Select the `Tests and coverage` check from the CI workflow.

Optional (recommended) for richer PR coverage UI:

1. Connect the repository to Codecov.
2. Add `CODECOV_TOKEN` as a repository secret (required for private repositories).
3. Keep the existing Codecov step enabled to get coverage comments and patch coverage in PRs.

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE).
