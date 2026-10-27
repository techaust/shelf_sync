-- 0002: the stores (SET-01, ERR-01; amends 04 section 4). The consumer key and secret are not here: they live in
-- Credential Manager as store-<id>-key and store-<id>-secret.
CREATE TABLE store (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,  -- ids are never reused (the secret names use them)
    name               TEXT NOT NULL CHECK (length(name) BETWEEN 1 AND 60),
    url                TEXT NOT NULL,                      -- normalised https://host[:port][/path], no trailing /
    code               TEXT NOT NULL CHECK (code GLOB '[A-Z][A-Z]'),
    shape              TEXT NOT NULL CHECK (shape IN ('circle', 'square', 'triangle', 'diamond')),
    color              TEXT NOT NULL CHECK (color IN ('indigo', 'teal')),  -- a palette key, not a hex value;
                                                           -- a new key needs a new migration (05 section 2.3)
    spacing_ms         INTEGER NOT NULL DEFAULT 150 CHECK (spacing_ms BETWEEN 50 AND 5000),
    main_button        TEXT NOT NULL DEFAULT 'Download' CHECK (length(main_button) BETWEEN 1 AND 40),
    state              TEXT NOT NULL DEFAULT 'active' CHECK (state IN ('active', 'paused')),
    wc_version         TEXT,
    wp_version         TEXT,
    health             TEXT NOT NULL DEFAULT 'unknown'
                       CHECK (health IN ('unknown', 'connected', 'unreachable', 'refused')),
    health_reason      TEXT,
    http_status        INTEGER,
    latency_ms         INTEGER,
    downloadable_count INTEGER,
    tested_at          TEXT,
    created_at         TEXT NOT NULL,
    removed_at         TEXT                                -- soft delete: history (M3) points at store ids
);

CREATE UNIQUE INDEX store_url_live ON store (url) WHERE removed_at IS NULL;
CREATE UNIQUE INDEX store_code_live ON store (code) WHERE removed_at IS NULL;
