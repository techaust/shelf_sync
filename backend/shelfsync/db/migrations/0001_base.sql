-- 0001: the two tables everything else rests on (04 section 4). Every other table arrives with its milestone.
CREATE TABLE schema_migration (
    version    INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);

CREATE TABLE setting (
    key        TEXT PRIMARY KEY,
    value_json TEXT NOT NULL
);
