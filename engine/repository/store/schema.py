# DDL Schema statements for SQLite Repository Store

CREATE_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS repositories (
    id TEXT PRIMARY KEY,
    provider TEXT NOT NULL,
    owner TEXT NOT NULL,
    name TEXT NOT NULL,
    UNIQUE(provider, owner, name)
);

CREATE TABLE IF NOT EXISTS repository_versions (
    id TEXT PRIMARY KEY,
    repository_id TEXT NOT NULL,
    commit_sha TEXT NOT NULL,
    created_at TEXT NOT NULL,
    status TEXT NOT NULL,
    FOREIGN KEY (repository_id) REFERENCES repositories(id),
    UNIQUE(repository_id, commit_sha)
);

CREATE TABLE IF NOT EXISTS files (
    repository_id TEXT NOT NULL,
    version_id TEXT NOT NULL,
    id INTEGER NOT NULL,
    path TEXT NOT NULL,
    language TEXT NOT NULL,
    PRIMARY KEY (repository_id, version_id, id),
    FOREIGN KEY (version_id) REFERENCES repository_versions(id)
);

CREATE TABLE IF NOT EXISTS symbols (
    repository_id TEXT NOT NULL,
    version_id TEXT NOT NULL,
    id INTEGER NOT NULL,
    name TEXT NOT NULL,
    file_id INTEGER NOT NULL,
    kind TEXT NOT NULL,
    language TEXT NOT NULL,
    start_line INTEGER NOT NULL,
    end_line INTEGER NOT NULL,
    visibility TEXT NOT NULL,
    parent_symbol_id INTEGER,
    PRIMARY KEY (repository_id, version_id, id),
    FOREIGN KEY (version_id) REFERENCES repository_versions(id)
);

CREATE TABLE IF NOT EXISTS calls (
    repository_id TEXT NOT NULL,
    version_id TEXT NOT NULL,
    caller_id INTEGER NOT NULL,
    callee_id INTEGER NOT NULL,
    call_type TEXT NOT NULL,
    FOREIGN KEY (version_id) REFERENCES repository_versions(id)
);

CREATE TABLE IF NOT EXISTS "references" (
    repository_id TEXT NOT NULL,
    version_id TEXT NOT NULL,
    source_id INTEGER NOT NULL,
    target_id INTEGER NOT NULL,
    relation_type TEXT NOT NULL,
    FOREIGN KEY (version_id) REFERENCES repository_versions(id)
);

CREATE TABLE IF NOT EXISTS imports (
    repository_id TEXT NOT NULL,
    version_id TEXT NOT NULL,
    source_file_id INTEGER NOT NULL,
    target_file_id INTEGER,
    module TEXT NOT NULL,
    imported_name TEXT NOT NULL,
    import_type TEXT NOT NULL,
    FOREIGN KEY (version_id) REFERENCES repository_versions(id)
);

CREATE TABLE IF NOT EXISTS type_relationships (
    repository_id TEXT NOT NULL,
    version_id TEXT NOT NULL,
    source_id INTEGER NOT NULL,
    target_id INTEGER NOT NULL,
    relationship_type TEXT NOT NULL,
    FOREIGN KEY (version_id) REFERENCES repository_versions(id)
);

CREATE TABLE IF NOT EXISTS endpoints (
    repository_id TEXT NOT NULL,
    version_id TEXT NOT NULL,
    id INTEGER NOT NULL,
    symbol_id INTEGER NOT NULL,
    method TEXT NOT NULL,
    path TEXT NOT NULL,
    framework TEXT NOT NULL,
    PRIMARY KEY (repository_id, version_id, id),
    FOREIGN KEY (version_id) REFERENCES repository_versions(id)
);

CREATE TABLE IF NOT EXISTS database_relationships (
    repository_id TEXT NOT NULL,
    version_id TEXT NOT NULL,
    symbol_id INTEGER NOT NULL,
    resource_id INTEGER NOT NULL,
    relationship_type TEXT NOT NULL,
    FOREIGN KEY (version_id) REFERENCES repository_versions(id)
);

CREATE TABLE IF NOT EXISTS event_publications (
    repository_id TEXT NOT NULL,
    version_id TEXT NOT NULL,
    symbol_id INTEGER NOT NULL,
    event_id INTEGER NOT NULL,
    publication_type TEXT NOT NULL,
    FOREIGN KEY (version_id) REFERENCES repository_versions(id)
);

CREATE TABLE IF NOT EXISTS event_subscriptions (
    repository_id TEXT NOT NULL,
    version_id TEXT NOT NULL,
    symbol_id INTEGER NOT NULL,
    event_id INTEGER NOT NULL,
    subscription_type TEXT NOT NULL,
    FOREIGN KEY (version_id) REFERENCES repository_versions(id)
);

CREATE TABLE IF NOT EXISTS test_relationships (
    repository_id TEXT NOT NULL,
    version_id TEXT NOT NULL,
    test_symbol_id INTEGER NOT NULL,
    target_symbol_id INTEGER NOT NULL,
    relationship_type TEXT NOT NULL,
    FOREIGN KEY (version_id) REFERENCES repository_versions(id)
);
"""

CREATE_INDEXES_SQL = """
CREATE INDEX IF NOT EXISTS idx_files_path ON files (repository_id, version_id, path);

CREATE INDEX IF NOT EXISTS idx_symbols_file ON symbols (repository_id, version_id, file_id);
CREATE INDEX IF NOT EXISTS idx_symbols_parent ON symbols (repository_id, version_id, parent_symbol_id);

CREATE INDEX IF NOT EXISTS idx_calls_caller ON calls (repository_id, version_id, caller_id);
CREATE INDEX IF NOT EXISTS idx_calls_callee ON calls (repository_id, version_id, callee_id);

CREATE INDEX IF NOT EXISTS idx_references_source ON "references" (repository_id, version_id, source_id);
CREATE INDEX IF NOT EXISTS idx_references_target ON "references" (repository_id, version_id, target_id);

CREATE INDEX IF NOT EXISTS idx_imports_source ON imports (repository_id, version_id, source_file_id);
CREATE INDEX IF NOT EXISTS idx_imports_target ON imports (repository_id, version_id, target_file_id);

CREATE INDEX IF NOT EXISTS idx_type_relationships_source ON type_relationships (repository_id, version_id, source_id);
CREATE INDEX IF NOT EXISTS idx_type_relationships_target ON type_relationships (repository_id, version_id, target_id);

CREATE INDEX IF NOT EXISTS idx_endpoints_symbol ON endpoints (repository_id, version_id, symbol_id);

CREATE INDEX IF NOT EXISTS idx_database_relationships_symbol ON database_relationships (repository_id, version_id, symbol_id);

CREATE INDEX IF NOT EXISTS idx_event_publications_symbol ON event_publications (repository_id, version_id, symbol_id);

CREATE INDEX IF NOT EXISTS idx_event_subscriptions_event ON event_subscriptions (repository_id, version_id, event_id);

CREATE INDEX IF NOT EXISTS idx_test_relationships_target ON test_relationships (repository_id, version_id, target_symbol_id);
"""
