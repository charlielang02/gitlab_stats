# Changelog

## Unreleased (2026-03-31)

### New Features

#### Dashboard & Visualization

* add conditional visibility for weekly and monthly contribution charts based on selected days
* improve code quality and add charts
* include poltly charts and cleanup dashboard, add csv download

#### Metrics & Data Handling

* implement time window selection and date bounds fetching for metrics
* integrate Supabase for metrics handling and add sync functionality
* enhance metrics handling and configuration reading in dashboard and API ingester
* implement caching for metrics loading and update configuration for data source visibility
* enhance GitLab metrics fetching and processing with performance tracking

#### API & Integration

* enhance GitLab API integration with timeline analytics and behavior analysis features
* add gitlab API impleentation and config

#### Import/Export

* implement CSV upload functionality and enhance export options in dashboard

#### Miscellaneous

* add timeframe controls section to README with dynamic selector details
* add placeholder txt file and logic, also fix import issue

### Fixes

#### Code & Typing

* pylance warnings for typing, imports and none tuple unpacking

#### UI/UX

* improve dashboard appearance
* column ordering to group categories

### Refactorings

#### Code Organization

* move files to utils folder
* modularize code and turn into methods

#### Configuration & Cleanup

* remove unused parser and update data source configuration for CSV fallback

### Docs

#### Changelog

* update changelog for new features and fixes
* update changelog for new features and fixes
* changelog adding
* add changelog

#### README

* update README for new features
* update README with enhanced features and API integration details
* README updates
* add initial README

### Others

* update version to 0.2.0 in pyproject.toml
