-- 0004: incremental sync and the nightly snapshot (SYNC-01, SYNC-03, SYNC-04, SYNC-05, APL-12). A store's answer is
-- hostile until checked: every text a store sends has a length limit here as well as in the reader.

-- The incremental read (SYNC-01). `watermark_gmt` is the store's own `date_modified_gmt` text (never the PC's clock):
-- after a full read or an incremental that fully worked, the larger of itself and the largest date the read saw less
-- the read's own duration (`catalog/watermark.py`). The `inc_*` columns are the last incremental: when, its outcome (NULL: it worked),
-- the status of its last failed request, the rows it returned and the catalog rows it changed.
ALTER TABLE sync_state ADD COLUMN watermark_gmt TEXT CHECK (
    watermark_gmt IS NULL OR (length(watermark_gmt) = 19
        AND watermark_gmt GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9]')
);
ALTER TABLE sync_state ADD COLUMN inc_started_at TEXT;
ALTER TABLE sync_state ADD COLUMN inc_finished_at TEXT;
ALTER TABLE sync_state ADD COLUMN inc_reason TEXT CHECK (inc_reason IS NULL OR length(inc_reason) BETWEEN 1 AND 40);
ALTER TABLE sync_state ADD COLUMN inc_http_status INTEGER;
ALTER TABLE sync_state ADD COLUMN inc_rows INTEGER CHECK (inc_rows IS NULL OR inc_rows >= 0);
ALTER TABLE sync_state ADD COLUMN inc_changed INTEGER CHECK (inc_changed IS NULL OR inc_changed >= 0);
ALTER TABLE sync_state ADD COLUMN inc_last_ok_at TEXT;

-- A store whose full read worked before this migration starts its incrementals from the largest date it saved: only
-- a date of the store's ASCII shape, and none more than a day ahead of this PC's clock (F7).
UPDATE sync_state SET watermark_gmt = (
    SELECT max(p.modified_gmt) FROM store_product p
    WHERE p.store_id = sync_state.store_id
      AND p.modified_gmt GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9]'
      AND p.modified_gmt <= strftime('%Y-%m-%dT%H:%M:%S', 'now', '+1 day')
) WHERE last_ok_at IS NOT NULL;

-- WooCommerce's `downloadable` flag (F8): a product is in the catalog when it is true and the product isn't in the
-- trash. A full read asks `downloadable=true`, so every row saved before this migration had it.
ALTER TABLE store_product ADD COLUMN downloadable INTEGER NOT NULL DEFAULT 1 CHECK (downloadable IN (0, 1));
-- When a snapshot confirmed the product deleted (WooCommerce's 404 for its id, review 1): a later snapshot doesn't ask
-- for it again. NULL: not confirmed deleted.
ALTER TABLE store_product ADD COLUMN deleted_at TEXT;

-- The nightly snapshot (SYNC-03, SYNC-04): one row per store per night. `night` is the local date of the night's
-- `snapshot_time`. `state`: `ok` (it worked), `retry` (an attempt failed; another is due at `next_try_at`, the same
-- night), `failed` (no attempt left, or a reason waiting can't change), `skipped` (paused, auto-paused, no catalog
-- yet: `reason` says why), `running`. `listing` says how the trash was listed: `include_status` (one listing with
-- `include_status=any,trash`) or `two_listings` (`status=any`, then `status=trash`).
CREATE TABLE snapshot_night (
    store_id     INTEGER NOT NULL REFERENCES store (id),
    night        TEXT NOT NULL CHECK (length(night) = 10 AND night GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'),
    state        TEXT NOT NULL CHECK (state IN ('running', 'ok', 'retry', 'failed', 'skipped')),
    attempts     INTEGER NOT NULL DEFAULT 0 CHECK (attempts BETWEEN 0 AND 3),
    started_at   TEXT,
    finished_at  TEXT,
    next_try_at  TEXT,
    reason       TEXT CHECK (reason IS NULL OR length(reason) BETWEEN 1 AND 40),
    http_status  INTEGER,
    listing      TEXT CHECK (listing IS NULL OR listing IN ('include_status', 'two_listings')),
    products     INTEGER CHECK (products IS NULL OR products >= 0),   -- rows read, trash included
    trashed      INTEGER CHECK (trashed IS NULL OR trashed >= 0),     -- of them, in the trash
    not_seen     INTEGER CHECK (not_seen IS NULL OR not_seen >= 0),   -- present catalog products a 404 confirmed gone
    variable     INTEGER CHECK (variable IS NULL OR variable >= 0),   -- variable products (their variations read)
    unconfirmed  INTEGER CHECK (unconfirmed IS NULL OR unconfirmed >= 0),  -- missing, not confirmed either way yet
    PRIMARY KEY (store_id, night)
);

-- The snapshots, stored as changes, not as copies: one row per product per unbroken run of nights in one state. A
-- product seen again in the same state on the store's next snapshot only moves `last_night`; a changed product, or one
-- seen again after a night it was missing, gets a new row. The nights a product can be restored to (APL-14) are the
-- `ok` nights of its store between `first_night` and `last_night` of its rows. Only what a restore needs is kept:
-- the status, slug, type and `downloadable` flag, the downloads (id, name, file), the `latest_version*` meta, and for a
-- variable product its variations' ids, statuses, downloads and meta. `state_sha256` is the SHA-256 (hex) of that
-- state.
CREATE TABLE snapshot_state (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    store_id        INTEGER NOT NULL REFERENCES store (id),
    wc_id           INTEGER NOT NULL CHECK (wc_id >= 1),
    status          TEXT NOT NULL CHECK (length(status) BETWEEN 1 AND 40),
    slug            TEXT NOT NULL CHECK (length(slug) <= 200),
    type            TEXT NOT NULL CHECK (length(type) BETWEEN 1 AND 40),
    downloadable    INTEGER NOT NULL CHECK (downloadable IN (0, 1)),
    downloads_json  TEXT NOT NULL CHECK (length(downloads_json) <= 262144 AND json_valid(downloads_json)),
    meta_json       TEXT NOT NULL CHECK (length(meta_json) <= 65536 AND json_valid(meta_json)),
    variations_json TEXT NOT NULL CHECK (length(variations_json) <= 4194304 AND json_valid(variations_json)),
    state_sha256    TEXT NOT NULL CHECK (length(state_sha256) = 64 AND state_sha256 NOT GLOB '*[^0-9a-f]*'),
    first_night     TEXT NOT NULL CHECK (length(first_night) = 10),
    last_night      TEXT NOT NULL CHECK (length(last_night) = 10 AND last_night >= first_night)
);

CREATE INDEX snapshot_state_product ON snapshot_state (store_id, wc_id, last_night);
CREATE INDEX snapshot_state_last_night ON snapshot_state (store_id, last_night);
