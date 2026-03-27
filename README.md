# GitLab Stats

A comprehensive dashboard for visualizing and analyzing GitLab contribution statistics.
Parse GitLab activity logs and gain insights into your development patterns,
collaboration metrics, and project contributions.

## Table of Contents

- [Features](#features)
- [Description](#description)
- [Architecture](#architecture)
- [Installation](#installation)
  - [Prerequisites](#prerequisites)
  - [Setup Instructions](#setup-instructions)
  - [Pre-commit Hooks](#pre-commit-hooks)
- [Usage](#usage)
  - [Running the Dashboard](#running-the-dashboard)
  - [Data Format](#data-format)
  - [Placeholder Data](#placeholder-data)
- [Project Structure](#project-structure)
- [Contributing](#contributing)
  - [Branch Strategy](#branch-strategy)
  - [Development Workflow](#development-workflow)
  - [Commit Standards](#commit-standards)
- [License](#license)

## Features

- **API-First Ingestion**: Pulls contribution data directly from GitLab API (`/users/:id/events`)
- **Parser Fallback**: Falls back to local text parsing when API data is unavailable
- **Behavior Analytics (API-Only)**: Timeline, streak, momentum, weekly mix, and monthly volumes
- **Interactive Dashboard**: Streamlit + Plotly visualizations for totals, breakdowns, and project deep dives
- **Contribution Metrics**: Commits, branches, merge requests, approvals, comments, issues, and derived totals
- **Smart Caching**: Dashboard data load is cached to prevent expensive refetches on widget interactions
- **Cache Refresh Control**: Manual refresh button shown under source-load status to force fresh data
- **Pre-commit Integration**: Automated quality checks (formatting, linting, tests)

## Description

GitLab Stats is a Python package that transforms GitLab activity data into actionable insights. It provides:

1. **Data Ingestion**:
   - API-first ingestion from GitLab events endpoint
   - File-parser fallback for resilience and local workflows
2. **Metrics Calculation**: Computes comprehensive statistics including:
   - Total contributions per project
   - Code contributions (commits, branches)
   - Collaboration contributions (merge requests, issues, reviews)
   - Code vs collaboration percentages
3. **Interactive Visualization**: Presents data through a Streamlit dashboard with:
   - Overall summary metrics
   - Per-project breakdown tables
   - Contribution charts and comparisons
   - Deep-dive project analysis
4. **Behavior Analysis**:
   - API timeline charts and business-day streaks (optionally excluding holidays)
   - Explicit "unavailable" messaging when timeline data cannot be trusted

## Architecture

```mermaid
graph TB
   A[GitLab API /users/:id/events]
   B[gitlab_contributions.txt]
   C[doc/gitlab_contributions_placeholder.txt]
   D[dashboard.py]
   E[Streamlit cache_data]
   F[gitlab_stats_api_ingester.py]
   G[gitlab_stats_parser.py]
   H[helpers.py: prepare_metric_df]
   I[sections.py]
   J[charts.py]
   K[Streamlit Dashboard]

   A -->|Primary source| F
   B -->|Parser source| G
   C -.->|Fallback if local file missing| G
   D --> E
   E -->|API path| F
   E -->|Fallback path| G
   F -->|metrics + totals + timeline| H
   G -->|metrics + totals| H
   H -->|DataFrame + ordered columns| I
   I -->|Build visual objects| J
   I -->|Render| K
   J -->|Plotly figures| K

   subgraph "Input Layer"
      A
      B
      C
   end

   subgraph "Application Layer"
      D
      E
      F
      G
      H
      I
      J
   end

   subgraph "Presentation"
      K
   end
```

**Key Components:**

- **gitlab_stats/gitlab_stats_api_ingester.py**: API ingestion and event normalization
  - Authenticated user resolution and event pagination
  - Event-to-metric mapping with guardrails for merge/history push inflation
  - Timeline dataset construction for behavior analysis
- **gitlab_stats/gitlab_stats_parser.py**: File parser fallback metrics engine
  - Regex-based log parsing
  - Contribution classification
  - Aggregation and computation
- **gitlab_stats/dashboard.py**: Streamlit entrypoint and source orchestration
  - Streamlit page setup
  - API-first with parser fallback selection
  - Cached data-loading path for fast widget interactions
  - Section orchestration
- **gitlab_stats/dashboard_utils/helpers.py**: Constants, CSS injection, DataFrame preparation
- **gitlab_stats/dashboard_utils/sections.py**: Dashboard section rendering
- **gitlab_stats/dashboard_utils/charts.py**: Plotly figure builders
- **gitlab_stats/dashboard_utils/timeline_utils.py**: Timeline aggregation helpers
- **gitlab_stats/dashboard_utils/activity_rules.py**: Shared rules for commit-count normalization
- **gitlab_stats/dashboard_utils/metrics_schema.py**: Shared metric-key schema constants
- **doc/gitlab_contributions_placeholder.txt**: Demo dataset fallback for local parser mode

## Installation

### Prerequisites

- Python 3.11 or higher
- Git
- Poetry (optional but recommended)
- Windows PowerShell (for batch scripts)

### Setup Instructions

1. **Clone the repository:**

   ```bash
   git clone <repository-url>
   cd gitlab_stats
   ```

2. **Install Poetry version:**
   - On Windows, run the install script:

     ```powershell
     .\tools\install_poetry.bat
     ```

   - This ensures the correct Poetry version is installed on your system

3. **Run post-checkout setup:**
   - On Windows:

     ```powershell
     .\tools\after_checkout.bat
     ```

   - This will:
     - Set up your virtual environment
     - Install all dependencies
     - Download and configure pre-commit hooks

### Pre-commit Hooks

The project includes comprehensive pre-commit hooks that automatically:

- Check Python syntax and code quality (Ruff, Pylint)
- Format code (Black, isort, autopep8)
- Check YAML and TOML files
- Fix spelling issues (typos, codespell)
- Run unit tests
- Validate commit messages

Pre-commit hooks run automatically before each commit. To manually run all checks:

```bash
poetry run pre-commit run --all-files
```

All `.txt` files are excluded from pre-commit processing to prevent issues with data files.

## Usage

### Running the Dashboard

Activate your Poetry environment or run directly with Poetry:

```bash
poetry run streamlit run gitlab_stats/dashboard.py
```

The dashboard launches at `http://localhost:8501` by default (or the next available port).

### API Configuration (.env)

Set the following environment variables in your `.env` file:

```bash
GITLAB_API_BASE_URL=https://your.gitlab.instance/api/v4
GITLAB_API_TOKEN=your_personal_access_token
```

If API credentials are missing or API fetch fails, the dashboard can fall back to parser mode.

### Data Source and Behavior Notes

- API is the default primary source (`USE_API = True` in config).
- Parser is fallback-only for metrics.
- Behavior analysis is API-only and will not be synthesized from parser data.
- Behavior charts trim leading inactive days for readability, but KPI windows still use real timeline data.
- Business-day streaks exclude weekends and the current day; holidays can be excluded via config.
- Data loading is cached via Streamlit (`DATA_CACHE_TTL_SECONDS`) to avoid full refetch on simple widget interactions.
- Manual cache refresh is available under the source-load banner ("Metrics loaded from ...").

### Data Format

GitLab Stats expects a text file with GitLab activity logs in the following format:

```bash
[User] [action] at [project-name]
[User] pushed to branch [branch-name] at [project/name]
... and X more commits
```

Example:

```bash
Avery pushed to branch orbit at nova-studio/helium-garden
... and 4 more commits
Avery opened merge request !23 at nova-studio/helium-garden
Jordan pushed new branch comet-ui at terra-works/aurora-cafe
```

Supported actions:

- `pushed to branch` - Commit pushed
- `pushed new branch` - New branch created
- `deleted branch` - Branch deleted
- `opened merge request` - MR created
- `accepted merge request` - MR merged
- `approved merge request` - MR approved
- `commented on merge request` - MR comment
- `opened issue` - Issue created

### Placeholder Data

If parser mode is used and the actual contribution file is not found, the dashboard falls back to placeholder data.
A warning banner displays when sample data is shown.

The default file path is: `gitlab_contributions.txt`

The fallback placeholder path is: `doc/gitlab_contributions_placeholder.txt`

To use a custom file path, enter it in the text input field in the dashboard.

## Key Configuration

Primary runtime toggles in `gitlab_stats/config.py`:

- `USE_API`: Enables API-first ingestion (with parser fallback)
- `SHOW_DATA_SOURCE_INFO`: Shows/hides source timing/info banners
- `API_LOOKBACK_DAYS`: Time window for API event ingestion
- `API_EVENTS_PER_PAGE`: GitLab events page size (max 100)
- `API_MAX_EVENT_PAGES`: Max number of paginated API pages to fetch
- `DATA_CACHE_TTL_SECONDS`: Cache time-to-live for expensive data loads
- `STREAK_HOLIDAY_COUNTRY`: ISO country code for holiday-aware streak calculations

## Project Structure

```bash
gitlab_stats/
├── .gitignore              # Git ignore rules
├── .pre-commit-config.yaml # Pre-commit hook configuration
├── .pylintrc               # Pylint configuration
├── .yamlfmt                # YAML formatting config
├── pyproject.toml          # Poetry dependencies and project config
├── poetry.lock             # Locked dependency versions
├── README.md               # This file
├── LICENSE                 # Project license
├── gitlab_contributions.txt   # Real activity export file used as primary local input
├── gitlab_stats/           # Main package
│   ├── __init__.py
│   ├── config.py           # Runtime feature flags and ingestion settings
│   ├── dashboard.py        # Streamlit dashboard UI
│   ├── gitlab_stats_api_ingester.py  # API ingestion and mapping engine
│   ├── gitlab_stats_parser.py     # Parser fallback metrics engine
│   └── dashboard_utils/
│       ├── __init__.py
│       ├── activity_rules.py   # Commit/history push normalization rules
│       ├── charts.py       # Plotly figure builders
│       ├── helpers.py      # Shared constants/data helpers/style injection
│       ├── metrics_schema.py   # Shared metric keys
│       ├── sections.py     # Dashboard section renderers
│       └── timeline_utils.py   # Timeline aggregation helpers
├── test/                   # Test suite
│   ├── __init__.py
│   └── test_gitlab_stats.py
├── tools/                  # Development utilities
│   ├── after_checkout.bat  # Post-checkout setup script
│   ├── install_poetry.bat  # Poetry installer script
│   └── pylint_reporter.py  # Pylint reporting tool
└── doc/                    # Documentation
    ├── changelog_prompts.txt
    ├── gitlab_contributions_placeholder.txt
    ├── markdownlint_report.txt
    └── pylint_report.txt
```

## Contributing

We welcome contributions! Please follow these steps to ensure smooth collaboration and maintain code quality.

### Branch Strategy

- **Main branch**: Production-ready code
- **Develop branch**: Integration branch for features and fixes
- **Feature/fix branches**: Always branch off from `develop`

### Development Workflow

1. **Prepare your environment:**
   - Run the install_poetry.bat file located in the `tools/` folder to force the correct Poetry version onto your system
   - Run the `after_checkout.bat` file to:
     - Set up your virtual environment
     - Download and install all dependencies
     - Configure pre-commit hooks

2. **Create your feature branch:**

   ```bash
   git checkout develop
   git pull origin develop
   git checkout -b feature/your-feature-name
   ```

3. **Make your changes:**
   - Write clear, well-documented code (and tests)
   - Run pre-commit checks: `poetry run pre-commit run --all-files`

4. **Merge develop into your branch (before opening PR):**

   ```bash
   git fetch origin
   git merge origin/develop
   ```

5. **Push and open a Pull Request:**

   ```bash
   git push origin feature/your-feature-name
   ```

   - Open your pull request against the `develop` branch
   - Provide a clear description of your changes
   - Ensure all CI checks pass

### Commit Standards

Keep your commits clear and descriptive. Use [Conventional Commits](https://www.conventionalcommits.org/) standard when possible.

**Commit types:**

- `feat:` - A new feature
- `fix:` - A bug fix
- `docs:` - Documentation changes
- `style:` - Code style changes (formatting, missing semicolons, etc.)
- `refactor:` - Code refactoring without feature or bug fixes
- `perf:` - Performance improvements
- `test:` - Adding or updating tests
- `chore:` - Build, CI, or dependency changes
- `build:` - Changes to build system or dependencies
- `ci:` - CI/CD configuration changes
- `tools:` - Changes to development tools and scripts

**Examples:**

```bash
feat: add project contribution filtering
fix: handle missing branch data in parser
docs: update README with architecture diagram
style: format dashboard code with Black
refactor: extract metrics computation into separate function
```

**Before committing:**

- Ensure code follows project style (Black, isort, autopep8)
- All tests pass
- No linting errors
- Commit messages are descriptive and follow the convention

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

For questions or issues, please open a GitHub issue or contact the maintainers.
