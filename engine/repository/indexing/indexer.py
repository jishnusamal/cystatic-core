import gc
from typing import Any
from zlib import adler32

from engine.repository.facts import (
    Call,
    DatabaseRelationship,
    Endpoint,
    EventPublication,
    EventSubscription,
    File,
    FileId,
    Import,
    ImportType,
    Reference,
    Symbol,
    SymbolId,
    TestRelationship,
    TypeRelationship,
)
from engine.repository.indexing.sink import RepositoryFactSink


def build_symbol_fqn(
    language: str, file_path: str, name: str, kind: str = "", parent: str = ""
) -> str:
    """Build a canonical symbol ID string (FQN) for a symbol entry."""
    if parent:
        return f"{language}://{file_path}#{parent}.{name}"
    if kind == "class":
        return f"{language}://{file_path}#{name}"
    if kind == "module":
        return f"{language}://{file_path}"
    return f"{language}://{file_path}::{name}"


class FactCapturer:
    def __init__(self, delegate):
        self.delegate = delegate
        self.captured = []

    def __getattr__(self, name):
        attr = getattr(self.delegate, name)
        if callable(attr) and name.startswith("add_"):
            def wrapper(*args, **kwargs):
                self.captured.append((name, args, kwargs))
                return attr(*args, **kwargs)
            return wrapper
        return attr


class RepositoryIndexer:
    """
    Orchestrates streaming fact extraction from a repository snapshot.

    Processes one file at a time, parses it using language adapters,
    extracts flat facts, writes them to the RepositoryFactSink, and releases
    the AST and file-scoped context before moving to the next file.
    """

    def __init__(self, sink: RepositoryFactSink) -> None:
        self.sink = sink
        self._file_id_map: dict[str, FileId] = {}
        self._next_file_id = 1

        self._symbol_id_map: dict[str, SymbolId] = {}
        self._symbol_fqn_map: dict[SymbolId, str] = {}
        self._next_symbol_id = 1

    def get_or_create_file_id(self, path: str) -> FileId:
        """Get or allocate a stable FileId for a file path."""
        normalized_path = path.replace("\\", "/")
        if normalized_path not in self._file_id_map:
            file_id = FileId(self._next_file_id)
            self._next_file_id += 1
            self._file_id_map[normalized_path] = file_id
        return self._file_id_map[normalized_path]

    def get_or_create_symbol_id(self, fqn: str) -> SymbolId:
        """Get or allocate a stable SymbolId for a symbol FQN."""
        if fqn not in self._symbol_id_map:
            sym_id = SymbolId(self._next_symbol_id)
            self._next_symbol_id += 1
            self._symbol_id_map[fqn] = sym_id
            self._symbol_fqn_map[sym_id] = fqn
        return self._symbol_id_map[fqn]

    def get_symbol_fqn(self, symbol_id: SymbolId) -> str | None:
        """Retrieve the canonical FQN string for a SymbolId."""
        return self._symbol_fqn_map.get(symbol_id)

    def _sync_mappings_from_sink(self) -> None:
        """Populate file and symbol ID maps from the sink/store to prevent collisions."""
        # 1. Check if the sink is PersistentFactSink (backed by SQLiteRepositoryStore)
        if (
            hasattr(self.sink, "store")
            and hasattr(self.sink, "repository_id")
            and hasattr(self.sink, "version_id")
            and hasattr(self.sink.store, "conn")
        ):
            try:
                conn = self.sink.store.conn
                repo_id = self.sink.repository_id
                version_id = self.sink.version_id
                cur = conn.cursor()

                # Load files
                cur.execute(
                    "SELECT id, path FROM files WHERE repository_id = ? AND version_id = ?",
                    (repo_id, version_id),
                )
                for row in cur.fetchall():
                    f_id = row["id"]
                    f_path = row["path"]
                    normalized_path = f_path.replace("\\", "/")
                    self._file_id_map[normalized_path] = FileId(f_id)
                    if f_id >= self._next_file_id:
                        self._next_file_id = f_id + 1

                # Load symbols and reconstruct FQNs
                cur.execute(
                    "SELECT s.id, s.name, s.kind, s.language, s.parent_symbol_id, f.path as file_path "
                    "FROM symbols s JOIN files f ON s.repository_id = f.repository_id AND s.version_id = f.version_id AND s.file_id = f.id "
                    "WHERE s.repository_id = ? AND s.version_id = ?",
                    (repo_id, version_id),
                )
                rows = cur.fetchall()
                parent_map = {row["id"]: row["name"] for row in rows}

                for row in rows:
                    sym_id = row["id"]
                    sym_name = row["name"]
                    sym_kind = row["kind"]
                    sym_lang = row["language"]
                    file_path = row["file_path"]
                    parent_id = row["parent_symbol_id"]

                    parent_name = parent_map.get(parent_id, "") if parent_id else ""
                    kind_str = str(sym_kind.value) if hasattr(sym_kind, "value") else str(sym_kind)
                    fqn = build_symbol_fqn(sym_lang, file_path, sym_name, kind_str, parent_name)

                    self._symbol_id_map[fqn] = SymbolId(sym_id)
                    self._symbol_fqn_map[SymbolId(sym_id)] = fqn
                    if sym_id >= self._next_symbol_id:
                        self._next_symbol_id = sym_id + 1
            except Exception:
                pass

        # 2. Check if the sink is InMemoryFactSink (backed by in-memory lists)
        elif hasattr(self.sink, "files") and hasattr(self.sink, "symbols"):
            try:
                # Load files
                for f in self.sink.files:
                    normalized_path = f.path.replace("\\", "/")
                    self._file_id_map[normalized_path] = f.id
                    if int(f.id) >= self._next_file_id:
                        self._next_file_id = int(f.id) + 1

                # Load symbols
                file_id_to_path = {f.id: f.path for f in self.sink.files}
                parent_map = {int(s.id): s.name for s in self.sink.symbols}

                for s in self.sink.symbols:
                    file_path = file_id_to_path.get(s.file_id)
                    if not file_path:
                        continue
                    parent_name = parent_map.get(int(s.parent_symbol_id), "") if s.parent_symbol_id else ""
                    kind_str = str(s.kind.value) if hasattr(s.kind, "value") else str(s.kind)
                    fqn = build_symbol_fqn(s.language, file_path, s.name, kind_str, parent_name)

                    self._symbol_id_map[fqn] = s.id
                    self._symbol_fqn_map[s.id] = fqn
                    if int(s.id) >= self._next_symbol_id:
                        self._next_symbol_id = int(s.id) + 1
            except Exception:
                pass

    def _get_cached_facts(self, conn, blob_sha: str) -> list[dict] | None:
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT fact_type, fact_payload FROM blob_fact_cache WHERE blob_sha = ?",
                (blob_sha,),
            )
            rows = cur.fetchall()
            if not rows:
                # Check if we have at least one entry indicating an empty file was indexed
                cur.execute(
                    "SELECT 1 FROM repository_materialization WHERE blob_sha = ? LIMIT 1",
                    (blob_sha,),
                )
                if cur.fetchone():
                    return []  # Cache hit, but empty list of facts
                return None
            return [{"fact_type": r["fact_type"], "payload": r["fact_payload"]} for r in rows]
        except Exception:
            return None

    def _save_cached_facts(self, conn, blob_sha: str, serialized_facts: list[dict]) -> None:
        try:
            with conn:
                # Check if already cached
                cur = conn.cursor()
                cur.execute("SELECT 1 FROM blob_fact_cache WHERE blob_sha = ? LIMIT 1", (blob_sha,))
                if cur.fetchone():
                    return
                
                # Insert facts
                for i, sf in enumerate(serialized_facts):
                    cur.execute(
                        "INSERT OR IGNORE INTO blob_fact_cache (blob_sha, fact_type, fact_identity, fact_payload) "
                        "VALUES (?, ?, ?, ?)",
                        (blob_sha, sf["fact_type"], str(i), sf["payload"]),
                    )
        except Exception:
            pass

    def _serialize_captured_fact(self, name: str, args: tuple) -> dict:
        fact = args[0]
        fact_type = name.replace("add_", "")
        
        file_id_to_path = {fid: path for path, fid in self._file_id_map.items()}
        
        d = {}
        if fact_type == 'symbol':
            d = {
                'id': self.get_symbol_fqn(fact.id),
                'name': fact.name,
                'file_id': file_id_to_path.get(fact.file_id),
                'kind': str(fact.kind.value) if hasattr(fact.kind, "value") else str(fact.kind),
                'language': fact.language,
                'start_line': fact.start_line,
                'end_line': fact.end_line,
                'visibility': str(fact.visibility.value) if hasattr(fact.visibility, "value") else str(fact.visibility),
                'parent_symbol_id': self.get_symbol_fqn(fact.parent_symbol_id) if fact.parent_symbol_id else None
            }
        elif fact_type == 'call':
            d = {
                'caller_id': self.get_symbol_fqn(fact.caller_id),
                'callee_id': self.get_symbol_fqn(fact.callee_id),
                'call_type': str(fact.call_type.value) if hasattr(fact.call_type, "value") else str(fact.call_type)
            }
        elif fact_type == 'reference':
            d = {
                'source_id': self.get_symbol_fqn(fact.source_id),
                'target_id': self.get_symbol_fqn(fact.target_id),
                'relation_type': str(fact.relation_type.value) if hasattr(fact.relation_type, "value") else str(fact.relation_type)
            }
        elif fact_type == 'import':
            d = {
                'source_file_id': file_id_to_path.get(fact.source_file_id),
                'target_file_id': file_id_to_path.get(fact.target_file_id) if fact.target_file_id else None,
                'module': fact.module,
                'imported_name': fact.imported_name,
                'import_type': str(fact.import_type.value) if hasattr(fact.import_type, "value") else str(fact.import_type)
            }
        elif fact_type == 'type_relationship':
            d = {
                'source_id': self.get_symbol_fqn(fact.source_id),
                'target_id': self.get_symbol_fqn(fact.target_id),
                'relationship_type': str(fact.relationship_type.value) if hasattr(fact.relationship_type, "value") else str(fact.relationship_type)
            }
        elif fact_type == 'endpoint':
            d = {
                'id': int(fact.id),
                'symbol_id': self.get_symbol_fqn(fact.symbol_id),
                'method': str(fact.method.value) if hasattr(fact.method, "value") else str(fact.method),
                'path': fact.path,
                'framework': fact.framework
            }
        elif fact_type == 'database_relationship':
            d = {
                'symbol_id': self.get_symbol_fqn(fact.symbol_id),
                'resource_id': int(fact.resource_id),
                'relationship_type': str(fact.relationship_type.value) if hasattr(fact.relationship_type, "value") else str(fact.relationship_type)
            }
        elif fact_type == 'event_publication':
            d = {
                'symbol_id': self.get_symbol_fqn(fact.symbol_id),
                'event_id': int(fact.event_id),
                'publication_type': str(fact.publication_type.value) if hasattr(fact.publication_type, "value") else str(fact.publication_type)
            }
        elif fact_type == 'event_subscription':
            d = {
                'symbol_id': self.get_symbol_fqn(fact.symbol_id),
                'event_id': int(fact.event_id),
                'subscription_type': str(fact.subscription_type.value) if hasattr(fact.subscription_type, "value") else str(fact.subscription_type)
            }
        elif fact_type == 'test_relationship':
            d = {
                'test_symbol_id': self.get_symbol_fqn(fact.test_symbol_id),
                'target_symbol_id': self.get_symbol_fqn(fact.target_symbol_id),
                'relationship_type': str(fact.relationship_type.value) if hasattr(fact.relationship_type, "value") else str(fact.relationship_type)
            }
        import json
        return {'fact_type': fact_type, 'payload': json.dumps(d)}

    def _deserialize_and_emit_fact(self, fact_type: str, payload_str: str) -> None:
        import json
        from engine.repository.facts import (
            Symbol, Call, Reference, Import, TypeRelationship, Endpoint,
            DatabaseRelationship, EventPublication, EventSubscription, TestRelationship,
            SymbolKind, SymbolVisibility, CallType, ReferenceType, ImportType,
            TypeRelationshipType, EndpointMethod, DatabaseRelationshipType,
            EventPublicationType, EventSubscriptionType, TestRelationshipType,
            SymbolId, FileId, EndpointId, ResourceId, EventId
        )

        d = json.loads(payload_str)
        if fact_type == 'symbol':
            fact = Symbol(
                id=self.get_or_create_symbol_id(d['id']),
                name=d['name'],
                file_id=self.get_or_create_file_id(d['file_id']),
                kind=SymbolKind(d['kind']),
                language=d['language'],
                start_line=d['start_line'],
                end_line=d['end_line'],
                visibility=SymbolVisibility(d['visibility']),
                parent_symbol_id=self.get_or_create_symbol_id(d['parent_symbol_id']) if d['parent_symbol_id'] else None
            )
            self.sink.add_symbol(fact)
        elif fact_type == 'call':
            fact = Call(
                caller_id=self.get_or_create_symbol_id(d['caller_id']),
                callee_id=self.get_or_create_symbol_id(d['callee_id']),
                call_type=CallType(d['call_type'])
            )
            self.sink.add_call(fact)
        elif fact_type == 'reference':
            fact = Reference(
                source_id=self.get_or_create_symbol_id(d['source_id']),
                target_id=self.get_or_create_symbol_id(d['target_id']),
                relation_type=ReferenceType(d['relation_type'])
            )
            self.sink.add_reference(fact)
        elif fact_type == 'import':
            fact = Import(
                source_file_id=self.get_or_create_file_id(d['source_file_id']),
                target_file_id=self.get_or_create_file_id(d['target_file_id']) if d['target_file_id'] else None,
                module=d['module'],
                imported_name=d['imported_name'],
                import_type=ImportType(d['import_type'])
            )
            self.sink.add_import(fact)
        elif fact_type == 'type_relationship':
            fact = TypeRelationship(
                source_id=self.get_or_create_symbol_id(d['source_id']),
                target_id=self.get_or_create_symbol_id(d['target_id']),
                relationship_type=TypeRelationshipType(d['relationship_type'])
            )
            self.sink.add_type_relationship(fact)
        elif fact_type == 'endpoint':
            fact = Endpoint(
                id=EndpointId(d['id']),
                symbol_id=self.get_or_create_symbol_id(d['symbol_id']),
                method=EndpointMethod(d['method']),
                path=d['path'],
                framework=d['framework']
            )
            self.sink.add_endpoint(fact)
        elif fact_type == 'database_relationship':
            fact = DatabaseRelationship(
                symbol_id=self.get_or_create_symbol_id(d['symbol_id']),
                resource_id=ResourceId(d['resource_id']),
                relationship_type=DatabaseRelationshipType(d['relationship_type'])
            )
            self.sink.add_database_relationship(fact)
        elif fact_type == 'event_publication':
            fact = EventPublication(
                symbol_id=self.get_or_create_symbol_id(d['symbol_id']),
                event_id=EventId(d['event_id']),
                publication_type=EventPublicationType(d['publication_type'])
            )
            self.sink.add_event_publication(fact)
        elif fact_type == 'event_subscription':
            fact = EventSubscription(
                symbol_id=self.get_or_create_symbol_id(d['symbol_id']),
                event_id=EventId(d['event_id']),
                subscription_type=EventSubscriptionType(d['subscription_type'])
            )
            self.sink.add_event_subscription(fact)
        elif fact_type == 'test_relationship':
            fact = TestRelationship(
                test_symbol_id=self.get_or_create_symbol_id(d['test_symbol_id']),
                target_symbol_id=self.get_or_create_symbol_id(d['target_symbol_id']),
                relationship_type=TestRelationshipType(d['relationship_type'])
            )
            self.sink.add_test_relationship(fact)

    def index_files(
        self,
        files: dict[str, str],
        language: str | None = None,
        adapter: Any | None = None,
        metrics: Any | None = None,
    ) -> None:
        """
        Arbitrary batch-oriented indexing of files independently.
        Supports incremental indexing by syncing mappings with the sink before processing.
        """
        import os
        import hashlib
        from engine.language.builtins import create_default_language_registry

        # Sync existing mappings from sink to prevent ID collisions
        self._sync_mappings_from_sink()

        registry = create_default_language_registry()

        for file_path, content in files.items():
            if content is None:
                continue

            if metrics is not None:
                metrics.record_file(
                    path=file_path,
                    size=len(content.encode("utf-8")),
                )

            # 1. Compute blob_sha
            blob_sha = hashlib.sha1(content.encode("utf-8")).hexdigest()

            # Check if sink has SQLite connection for caching
            has_db = (
                hasattr(self.sink, "store")
                and hasattr(self.sink, "repository_id")
                and hasattr(self.sink, "version_id")
                and hasattr(self.sink.store, "conn")
            )

            # Check if we can reuse blob facts
            cached_facts = None
            if has_db:
                cached_facts = self._get_cached_facts(self.sink.store.conn, blob_sha)

            self.sink.begin()
            try:
                file_id = self.get_or_create_file_id(file_path)

                # Determine the language dynamically (needed for both hit and miss)
                file_lang = None
                filename = os.path.basename(file_path)
                plugin = registry.find_by_filename(filename)
                if not plugin:
                    _, ext = os.path.splitext(file_path)
                    plugin = registry.find_by_extension(ext)

                if plugin:
                    file_lang = plugin.spec.id
                elif adapter:
                    file_lang = language or (adapter.get_language() if hasattr(adapter, "get_language") else "unknown")
                elif language:
                    plugin = registry.get(language)
                    if plugin:
                        file_lang = plugin.spec.id
                    else:
                        file_lang = language
                else:
                    file_lang = "unknown"

                if cached_facts is not None:
                    # Cache Hit!
                    if metrics is not None:
                        if hasattr(metrics, "blob_cache_hits"):
                            metrics.blob_cache_hits += 1
                        if hasattr(metrics, "indexed_files"):
                            metrics.indexed_files += 1

                    # Re-create File Fact
                    file_fact = File(id=file_id, path=file_path, language=file_lang)
                    self.sink.add_file(file_fact)

                    # Re-emit all cached facts
                    for cf in cached_facts:
                        self._deserialize_and_emit_fact(cf["fact_type"], cf["payload"])

                    if metrics is not None and hasattr(metrics, "facts_generated"):
                        metrics.facts_generated += len(cached_facts)

                    # Record materialization
                    if has_db:
                        self.sink.store.record_materialization(
                            self.sink.repository_id,
                            self.sink.version_id.split("@")[-1],
                            file_path,
                            blob_sha,
                            "indexed",
                        )

                else:
                    # Cache Miss!
                    if metrics is not None:
                        if hasattr(metrics, "blob_cache_misses"):
                            metrics.blob_cache_misses += 1
                        if hasattr(metrics, "indexed_files"):
                            metrics.indexed_files += 1

                    file_adapter = None
                    if plugin:
                        file_adapter = plugin.create_adapter()
                    elif adapter:
                        file_adapter = adapter
                    elif language:
                        plugin = registry.get(language)
                        if plugin:
                            file_adapter = plugin.create_adapter()

                    # Write File Fact
                    file_fact = File(id=file_id, path=file_path, language=file_lang)
                    self.sink.add_file(file_fact)

                    # Wrap sink to capture emitted facts
                    capturer = FactCapturer(self.sink)
                    orig_sink = self.sink
                    self.sink = capturer

                    if file_adapter:
                        file_index = file_adapter._index_single_file(file_path, content, file_lang)
                        self._extract_file_facts(file_index, file_id, file_lang)

                    # Restore original sink
                    self.sink = orig_sink

                    if metrics is not None and hasattr(metrics, "facts_generated"):
                        metrics.facts_generated += len(capturer.captured)

                    # Save captured facts to cache
                    if has_db:
                        serialized = [
                            self._serialize_captured_fact(name, args)
                            for name, args, kwargs in capturer.captured
                        ]
                        self._save_cached_facts(self.sink.store.conn, blob_sha, serialized)

                        # Record materialization
                        self.sink.store.record_materialization(
                            self.sink.repository_id,
                            self.sink.version_id.split("@")[-1],
                            file_path,
                            blob_sha,
                            "indexed",
                        )

                self.sink.flush()
            except Exception as e:
                if hasattr(self.sink, "rollback"):
                    self.sink.rollback()
                # Record materialization as failed if possible
                if has_db:
                    try:
                        self.sink.store.record_materialization(
                            self.sink.repository_id,
                            self.sink.version_id.split("@")[-1],
                            file_path,
                            blob_sha,
                            "failed",
                        )
                        # We must commit the failed status
                        if hasattr(self.sink, "store") and hasattr(self.sink.store, "conn"):
                            self.sink.store.conn.commit()
                    except Exception:
                        pass
                raise e
            finally:
                if "file_index" in locals():
                    del file_index
                gc.collect()

    def index_repository(
        self,
        repository_input: dict[str, Any],
        adapter: Any,
        metrics: Any | None = None,
    ) -> None:
        """
        Streamingly index a repository snapshot using the dynamically detected adapter per file.

        Args:
            repository_input: Snapshots dictionary with 'files' mapping path to content.
            adapter: Fallback language adapter (e.g. PythonLanguageAdapter, JavaLanguageAdapter).
            metrics: Optional metrics recorder.
        """
        files = repository_input.get("files", {})
        language = repository_input.get("language")
        if language is None and adapter is not None and hasattr(adapter, "get_language"):
            language = adapter.get_language()
        self.index_files(files, language=language, adapter=adapter, metrics=metrics)


    def _extract_file_facts(
        self, file_index: Any, file_id: FileId, language: str
    ) -> None:
        """Extract flat facts from a file index and write them to the sink."""
        # 1. Symbols
        for sym in file_index.symbols:
            fqn = build_symbol_fqn(
                language, file_index.path, sym.name, sym.kind, sym.parent
            )
            sym_id = self.get_or_create_symbol_id(fqn)

            parent_id = None
            if sym.parent:
                parent_fqn = build_symbol_fqn(
                    language, file_index.path, sym.parent, "class", ""
                )
                parent_id = self.get_or_create_symbol_id(parent_fqn)

            from engine.repository.facts import SymbolKind, SymbolVisibility

            try:
                kind = SymbolKind(sym.kind)
            except ValueError:
                kind = SymbolKind.FUNCTION
            try:
                visibility = SymbolVisibility(sym.visibility)
            except ValueError:
                visibility = SymbolVisibility.PUBLIC

            symbol_fact = Symbol(
                id=sym_id,
                name=sym.name,
                file_id=file_id,
                kind=kind,
                language=language,
                start_line=sym.start_line,
                end_line=sym.end_line,
                visibility=visibility,
                parent_symbol_id=parent_id,
            )
            self.sink.add_symbol(symbol_fact)

        # 2. Imports
        for imp in file_index.imports:
            # target_file_id will be resolved in Phase B/semantic compiler, initially None
            # or we can compute a stable FileId if the target path is known or guessable
            try:
                imp_type = ImportType(imp.import_type)
            except ValueError:
                imp_type = ImportType.STANDARD

            import_fact = Import(
                source_file_id=file_id,
                target_file_id=None,
                module=imp.module,
                imported_name=", ".join(imp.names) if imp.names else "",
                import_type=imp_type,
            )
            self.sink.add_import(import_fact)

        # 3. Calls
        for call in file_index.calls:
            # Caller
            caller_parent = getattr(call, "caller_parent", "")
            caller_fqn = build_symbol_fqn(
                language, file_index.path, call.caller, parent=caller_parent
            )
            caller_id = self.get_or_create_symbol_id(caller_fqn)

            # Callee FQN: since unresolved, we assign a placeholder FQN for the callee
            callee_fqn = f"unresolved://{call.callee}"
            callee_id = self.get_or_create_symbol_id(callee_fqn)

            from engine.repository.facts import CallType

            try:
                c_type = CallType(call.call_type)
            except ValueError:
                c_type = CallType.DIRECT

            call_fact = Call(
                caller_id=caller_id,
                callee_id=callee_id,
                call_type=c_type,
            )
            self.sink.add_call(call_fact)

        # 4. References
        for ref in file_index.references:
            parent_sym = getattr(ref, "parent_symbol", "")
            source_fqn = (
                build_symbol_fqn(language, file_index.path, parent_sym)
                if parent_sym
                else f"{language}://{file_index.path}"
            )
            source_id = self.get_or_create_symbol_id(source_fqn)

            target_fqn = f"unresolved://{ref.name}"
            target_id = self.get_or_create_symbol_id(target_fqn)

            from engine.repository.facts import ReferenceType

            ref_fact = Reference(
                source_id=source_id,
                target_id=target_id,
                relation_type=ReferenceType.REFERENCE,
            )
            self.sink.add_reference(ref_fact)

        # 5. Type Relationships
        for tr in file_index.type_relationships:
            source_fqn = build_symbol_fqn(language, file_index.path, tr.source)
            source_id = self.get_or_create_symbol_id(source_fqn)

            target_fqn = f"unresolved://{tr.target}"
            target_id = self.get_or_create_symbol_id(target_fqn)

            from engine.repository.facts import TypeRelationshipType

            try:
                tr_type = TypeRelationshipType(tr.relation_type)
            except ValueError:
                tr_type = TypeRelationshipType.EXTENDS

            tr_fact = TypeRelationship(
                source_id=source_id,
                target_id=target_id,
                relationship_type=tr_type,
            )
            self.sink.add_type_relationship(tr_fact)

        # 6. Endpoints (Entrypoints)
        for ep in file_index.entrypoints:
            handler_fqn = build_symbol_fqn(language, file_index.path, ep.handler)
            handler_id = self.get_or_create_symbol_id(handler_fqn)

            from engine.repository.facts import EndpointId, EndpointMethod

            # Create a stable integer ID for the endpoint
            ep_id_int = adler32(f"{ep.route}:{ep.handler}".encode()) & 0xFFFFFFFF
            ep_id = EndpointId(ep_id_int)

            method_str = ep.route.split(" ")[0] if " " in ep.route else "GET"
            try:
                method = EndpointMethod(method_str)
            except ValueError:
                method = EndpointMethod.ANY

            ep_fact = Endpoint(
                id=ep_id,
                symbol_id=handler_id,
                method=method,
                path=ep.route.split(" ")[1] if " " in ep.route else ep.route,
                framework=ep.framework,
            )
            self.sink.add_endpoint(ep_fact)

        # 7. Persistence Models
        for pm in file_index.persistence_models:
            model_fqn = build_symbol_fqn(
                language, file_index.path, pm.name, kind="class"
            )
            model_id = self.get_or_create_symbol_id(model_fqn)

            from engine.repository.facts import DatabaseRelationshipType, ResourceId

            res_id = (
                ResourceId(adler32(pm.table_name.encode()) & 0xFFFFFFFF)
                if pm.table_name
                else ResourceId(0)
            )

            db_fact = DatabaseRelationship(
                symbol_id=model_id,
                resource_id=res_id,
                relationship_type=DatabaseRelationshipType.READ,  # Default
            )
            self.sink.add_database_relationship(db_fact)

        # 8. Events
        for ev in file_index.events:
            symbol_fqn = build_symbol_fqn(language, file_index.path, ev.symbol_name)
            symbol_id = self.get_or_create_symbol_id(symbol_fqn)

            from engine.repository.facts import (
                EventId,
                EventPublicationType,
                EventSubscriptionType,
            )

            event_id = EventId(adler32(ev.event_name.encode()) & 0xFFFFFFFF)

            if ev.operation_kind in ("publish", "emit", "send", "produce"):
                try:
                    pub_type = EventPublicationType(ev.operation_kind)
                except ValueError:
                    pub_type = EventPublicationType.PUBLISH
                self.sink.add_event_publication(
                    EventPublication(
                        symbol_id=symbol_id,
                        event_id=event_id,
                        publication_type=pub_type,
                    )
                )
            else:
                try:
                    sub_type = EventSubscriptionType(ev.operation_kind)
                except ValueError:
                    sub_type = EventSubscriptionType.SUBSCRIBE
                self.sink.add_event_subscription(
                    EventSubscription(
                        symbol_id=symbol_id,
                        event_id=event_id,
                        subscription_type=sub_type,
                    )
                )

        # 9. Tests
        for test in file_index.tests:
            test_fqn = build_symbol_fqn(language, file_index.path, test.name)
            test_id = self.get_or_create_symbol_id(test_fqn)

            # Check if covers/references any symbols
            # TestEntry metadata can hold targets
            targets = test.metadata.get("covers", [])
            for target_name in targets:
                target_fqn = build_symbol_fqn(language, file_index.path, target_name)
                target_id = self.get_or_create_symbol_id(target_fqn)

                from engine.repository.facts import TestRelationshipType

                self.sink.add_test_relationship(
                    TestRelationship(
                        test_symbol_id=test_id,
                        target_symbol_id=target_id,
                        relationship_type=TestRelationshipType.COVERS,
                    )
                )
