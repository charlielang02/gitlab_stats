# Changelog

## Unreleased (2026-04-01)

### New features

#### Testing and coverage

* Add unit tests for dashboard functionality and improve coverage thresholds
* Add unit tests for dashboard chart builders
* Add unit tests for dashboard helper utilities
* Add initial Codecov configuration for coverage reporting
* Add unit tests for Supabase client and improve error messages
* Add unit tests for settings helpers, Supabase sync, and timeline utilities

#### Documentation and onboarding

* Add section for forking and running personal dashboards in README
* Add timeframe controls section to README with dynamic selector details

#### Dashboard and metrics functionality

* Add conditional visibility for weekly and monthly contribution charts based on selected days
* Implement time window selection and date bounds fetching for metrics
* Integrate Supabase for metrics handling and add sync functionality
* Implement CSV upload functionality and enhance export options in dashboard
* Enhance metrics handling and configuration reading in dashboard and API ingester
* Implement caching for metrics loading and update configuration for data source visibility

#### Integrations and analytics

* Enhance GitLab API integration with timeline analytics and behavior analysis features
* Enhance GitLab metrics fetching and processing with performance tracking
* Add GitLab API implementation and config

#### UI and charts

* Improve code quality and add charts
* Include Plotly charts and clean up dashboard, add CSV download

#### Miscellaneous additions

* Add placeholder txt file and logic, also fix import issue

### Fixes

#### CI and tooling

* Unterminated string for CI test coverage
* Update cache method from 'poetry' to 'pip' in CI workflow

#### Code quality and typing

* Pylance warnings for typing, imports, and None tuple unpacking

#### UI and data presentation

* Improve dashboard appearance
* Column ordering to group categories

#### Refactorings

#### Code organization

* Remove unused parser and update data source configuration for CSV fallback
* Move files to utils folder

#### Structure and maintainability

* Modularize code and turn into methods

### Docs

#### README updates

* Remove planned next branch section and update coverage thresholds in README
* Update README for new features
* Update README with enhanced features and API integration details
* README updates
* Add initial README

#### Changelog maintenance

* Update changelog for new features and fixes
* Update changelog for new features and fixes
* Changelog adding
* Add changelog

### Others

#### Testing and coverage workflows

* Add tests for sections and coverage reports
* Add code coverage reporting and workflow
* Update test files for improved coverage

#### Maintenance

* Update changelog for new features and fixes, and correct section headers
* Update version to 0.2.0 in pyproject.toml
