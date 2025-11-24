# Changelog

All notable changes to this project are documented in this file.

## [1.0.1] - 2025-11-15
### Changed
- Added a friendly CSRF error handler to `app.py` to flash a user-facing message and redirect instead of exposing debug stack traces.
- Added lightweight server-side logging for failed admin login attempts and CSRF failures.
- Fixed admin dashboard template runtime error by computing the "Recent (Today)" ticket count server-side and passing `recent_count` into the template.

### Notes
- Development server still runs with `debug=True` by default for local development; do not run the debug server in production.

## [1.0.0] - 2024-01-01
- Initial release.
