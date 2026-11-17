-- 0003: the catalog (CAT-01, CAT-02, CAT-04 slug, CAT-05, APL-12, UI-WIZ; amends 04 section 4). A store's answer is
-- hostile until checked: every text a store sends has a length limit here as well as in the reader
-- (`apply/catalog_read.py`), which refuses a longer one before anything is saved.

-- The store's mirror: only the fields the reader asks for (`_fields`), never a description, a price or any other field.
-- `downloads_json` holds each download's id, name and file only; `meta_json` only the meta entries whose key starts
-- with `latest_version`. A row a full read no longer returns gets `gone_at`; rows are never deleted (m3.2, m3.3).
CREATE TABLE store_product (
    store_id       INTEGER NOT NULL REFERENCES store (id),
    wc_id          INTEGER NOT NULL CHECK (wc_id >= 1),
    slug           TEXT NOT NULL CHECK (length(slug) <= 200),          -- may be empty (a draft)
    title          TEXT NOT NULL CHECK (length(title) <= 1000),        -- `html.unescape` applied
    type           TEXT NOT NULL CHECK (length(type) BETWEEN 1 AND 40),
    status         TEXT NOT NULL CHECK (length(status) BETWEEN 1 AND 40),
    modified_gmt   TEXT CHECK (modified_gmt IS NULL OR length(modified_gmt) = 19),
    downloads_json TEXT NOT NULL CHECK (length(downloads_json) <= 262144 AND json_valid(downloads_json)),
    meta_json      TEXT NOT NULL CHECK (length(meta_json) <= 65536 AND json_valid(meta_json)),
    seen_at        TEXT NOT NULL,
    gone_at        TEXT,
    PRIMARY KEY (store_id, wc_id)
);

CREATE INDEX store_product_slug ON store_product (store_id, slug);

-- One real product. `canonical_slug` is NULL for an item that has no slug (a draft with an empty slug, a trashed slug,
-- or a slug another item already holds as its canonical slug): it is never linked by slug.
CREATE TABLE catalog_item (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    canonical_slug TEXT UNIQUE CHECK (canonical_slug IS NULL OR length(canonical_slug) BETWEEN 1 AND 200),
    title          TEXT NOT NULL CHECK (length(title) <= 1000),
    type           TEXT NOT NULL CHECK (length(type) BETWEEN 1 AND 40),
    created_at     TEXT NOT NULL
);

-- Which store product is which item. A link never moves once made (CAT-02): ids, the owner's slug edits and later
-- decisions survive every re-read.
CREATE TABLE item_link (
    catalog_item_id INTEGER NOT NULL REFERENCES catalog_item (id),
    store_id        INTEGER NOT NULL,
    wc_id           INTEGER NOT NULL,
    UNIQUE (store_id, wc_id),
    FOREIGN KEY (store_id, wc_id) REFERENCES store_product (store_id, wc_id)
);

CREATE INDEX item_link_item ON item_link (catalog_item_id);

-- Download slots (CAT-05): one main slot per item and extra slots paired across stores by their exact name. `slug` is
-- for M5's S3 naming and stays NULL until then. Slots are never deleted (later fingerprints point at them).
CREATE TABLE slot (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    catalog_item_id INTEGER NOT NULL REFERENCES catalog_item (id),
    name            TEXT NOT NULL CHECK (length(name) <= 200),
    is_main         INTEGER NOT NULL CHECK (is_main IN (0, 1)),
    slug            TEXT CHECK (slug IS NULL OR length(slug) BETWEEN 1 AND 200)
);

CREATE UNIQUE INDEX slot_main ON slot (catalog_item_id) WHERE is_main = 1;
CREATE UNIQUE INDEX slot_extra_name ON slot (catalog_item_id, name) WHERE is_main = 0;

-- Each slot's download on each store, rebuilt from the store's last full read.
CREATE TABLE slot_download (
    slot_id        INTEGER NOT NULL REFERENCES slot (id),
    store_id       INTEGER NOT NULL REFERENCES store (id),
    wc_download_id TEXT NOT NULL CHECK (length(wc_download_id) BETWEEN 1 AND 64),
    file_url       TEXT NOT NULL CHECK (length(file_url) <= 2048),
    UNIQUE (slot_id, store_id)
);

CREATE INDEX slot_download_store ON slot_download (store_id);

-- One row per store: its last full read and the failures-in-a-row count (APL-12), kept across runs. An auto-paused
-- store's reads are skipped until the owner resumes it; it doesn't change `store.state` (the owner's pause).
CREATE TABLE sync_state (
    store_id          INTEGER PRIMARY KEY REFERENCES store (id),
    read_started_at   TEXT,
    read_finished_at  TEXT,
    read_reason       TEXT CHECK (read_reason IS NULL OR length(read_reason) BETWEEN 1 AND 40),  -- NULL: it worked
    read_http_status  INTEGER,                                      -- the status of the last failed request
    read_pages        INTEGER CHECK (read_pages IS NULL OR read_pages >= 0),
    read_rows         INTEGER CHECK (read_rows IS NULL OR read_rows >= 0),
    read_total        INTEGER CHECK (read_total IS NULL OR read_total >= 0),  -- X-WP-Total
    last_ok_at        TEXT,                                         -- when the last full read that worked finished
    failures_in_row   INTEGER NOT NULL DEFAULT 0 CHECK (failures_in_row >= 0),
    auto_paused_at    TEXT,
    auto_pause_reason TEXT CHECK (auto_pause_reason IS NULL OR length(auto_pause_reason) BETWEEN 1 AND 40)
);

-- The first-run wizard (UI-WIZ): the owner's mark for a step whose state can't be read from the data.
CREATE TABLE wizard (
    step       TEXT PRIMARY KEY CHECK (length(step) BETWEEN 1 AND 20),
    state_json TEXT NOT NULL CHECK (length(state_json) <= 4096 AND json_valid(state_json))
);
