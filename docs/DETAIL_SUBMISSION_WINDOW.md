# Detail: version dates alongside other deadlines (#401)

`GrantCallVersion.submission_open_at` / `submission_close_at` are source-version values, not an independently evidenced `GrantDeadline`. If the version has either date and no normalized application deadline, detail API adds an `APPLICATION_WINDOW` with `evidenceId: null`, even when another deadline (for example `PROJECT_FINISH`) is normalized. A normalized `APPLICATION_WINDOW`, `APPLICATION_OPEN`, or `APPLICATION_CLOSE` suppresses this fallback to avoid implying an additional application period. This does not fill a missing half of a partially normalized application window; that remains a separate data-completeness question.

The detail marks the fallback as a summary without its own attached evidence, and tells users to verify the exact submission deadline with the provider. Real D1/API regression and full-stack desktop/mobile browser test cover the mixed case; no absence of a deadline is interpreted as unlimited submissions.
