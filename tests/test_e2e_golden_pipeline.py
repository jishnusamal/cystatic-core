
import pytest

from core.runtime import PREVENT_LEGACY_ARCHITECTURE
from engine.pipeline.pipeline import Pipeline
from engine.repository.facts import (
    Call,
    CallType,
    Endpoint,
    EndpointId,
    EndpointMethod,
    File,
    FileId,
    Symbol,
    SymbolId,
    SymbolKind,
    TestRelationship,
    TestRelationshipType,
)
from engine.repository.store import PersistentFactSink, SQLiteRepositoryStore
from models import (
    AnalysisRequest,
    AnalysisTrigger,
    DiffSnapshot,
    PullRequestReference,
    RepositoryReference,
)
from models.core import DiffFile, DiffHunk


@pytest.mark.asyncio
async def test_e2e_golden_pipeline_with_facts(tmp_path):
    """
    E2E Golden Test:
    - Base facts represent:
        - app.py containing checkout handler (Symbol 1)
        - payment.py containing process_payment (Symbol 2)
        - test_payment.py containing test_process_payment (Symbol 3)
        - Call edge: checkout (1) -> process_payment (2)
        - Endpoint fact: REST POST /checkout handled by checkout (1)
        - Test relationship: test_process_payment (3) covers process_payment (2)
    - PR diff:
        - Modifies process_payment in payment.py
    - Pipeline run executes:
        - Change compiler detects modified process_payment
        - Behavior compiler traverses to checkout handler and marks POST /checkout affected
        - Validation compiler resolves test_process_payment as unit test evidence
        - ReviewContext/LLMContext compilers produce fully populated, compressed context
    """
    db_file = str(tmp_path / "golden_store.db")
    store = SQLiteRepositoryStore(db_file)
    
    base_sha = "sha-base-golden"
    head_sha = "sha-head-golden"
    
    # 1. Create Repository & Version
    repo_id = store.create_repository("github", "golden-org", "golden-repo")
    version_id = store.create_version(repo_id, base_sha)
    store.set_version_context(repo_id, version_id)
    
    # 2. Add files and symbols
    sink = PersistentFactSink(store, repo_id, version_id)
    
    file_app = File(id=FileId(1), path="app.py", language="python")
    file_payment = File(id=FileId(2), path="payment.py", language="python")
    file_test = File(id=FileId(3), path="test_payment.py", language="python")
    
    sink.add_file(file_app)
    sink.add_file(file_payment)
    sink.add_file(file_test)
    
    # Symbols
    sym_checkout = Symbol(
        id=SymbolId(1),
        name="checkout",
        file_id=file_app.id,
        kind=SymbolKind.FUNCTION,
        language="python",
        start_line=1,
        end_line=10,
    )
    sym_payment = Symbol(
        id=SymbolId(2),
        name="process_payment",
        file_id=file_payment.id,
        kind=SymbolKind.FUNCTION,
        language="python",
        start_line=1,
        end_line=15,
    )
    sym_test = Symbol(
        id=SymbolId(3),
        name="test_process_payment",
        file_id=file_test.id,
        kind=SymbolKind.FUNCTION,
        language="python",
        start_line=1,
        end_line=8,
    )
    
    sink.add_symbol(sym_checkout)
    sink.add_symbol(sym_payment)
    sink.add_symbol(sym_test)
    
    # Call relationship: checkout -> process_payment
    call = Call(caller_id=sym_checkout.id, callee_id=sym_payment.id, call_type=CallType.DYNAMIC)
    sink.add_call(call)
    
    # REST endpoint fact for checkout handler
    endpoint = Endpoint(
        id=EndpointId(101),
        symbol_id=sym_checkout.id,
        method=EndpointMethod.POST,
        path="/checkout",
        framework="flask",
    )
    sink.add_endpoint(endpoint)
    
    # Test relationship: test_process_payment -> process_payment
    test_rel = TestRelationship(
        test_symbol_id=sym_test.id,
        target_symbol_id=sym_payment.id,
        relationship_type=TestRelationshipType.UNIT,
    )
    sink.add_test_relationship(test_rel)
    
    sink.flush()
    
    # 3. Setup mock provider to fetch modified file at head
    class MockProvider:
        async def fetch_file(self, repository, file_path, sha):
            if file_path == "payment.py":
                return "def process_payment():\n    # Modified body\n    return True\n"
            return None

    pipeline = Pipeline(
        repository_store=store,
        repository_provider=MockProvider(),
    )
    
    # 4. Construct Request and Diff for payment.py modification
    repo_ref = RepositoryReference(
        provider="github",
        owner="golden-org",
        repository="golden-repo",
        default_branch=base_sha,
    )
    pr_ref = PullRequestReference(
        number=7,
        base_sha=base_sha,
        head_sha=head_sha,
        title="Modify Payment Service",
    )
    hunk = DiffHunk(
        file_path="payment.py",
        source_start=1,
        source_length=3,
        target_start=1,
        target_length=3,
        added_lines=("+    # Modified body", "+    return True"),
        removed_lines=("-    return False",),
        lines=(" def process_payment():", "+    # Modified body"),
    )
    diff_file = DiffFile(
        file_path="payment.py",
        added_lines=("+    # Modified body", "+    return True"),
        removed_lines=("-    return False",),
        hunks=(hunk,),
    )
    diff_snapshot = DiffSnapshot(files=(diff_file,))
    
    request = AnalysisRequest(
        repository=repo_ref,
        pull_request=pr_ref,
        diff=diff_snapshot,
        trigger=AnalysisTrigger.MANUAL,
    )
    
    # Activate legacy guard and run pipeline
    token = PREVENT_LEGACY_ARCHITECTURE.set(True)
    try:
        context = await pipeline.run(request)
    finally:
        PREVENT_LEGACY_ARCHITECTURE.reset(token)
        
    # 5. E2E Assertions
    assert context.error is None
    
    # Verify change fact compiler output
    assert context.change_facts is not None
    assert len(context.change_facts.changed_symbols) == 1
    assert str(context.change_facts.changed_symbols[0].symbol_id) == str(sym_payment.id)
    
    # Verify impact/behavior compiler output
    assert context.impact_surface is not None
    assert str(sym_payment.id) in context.impact_surface.affected_symbols
    assert str(sym_checkout.id) in context.impact_surface.affected_symbols
    # verify API endpoint resolved as affected
    assert len(context.impact_surface.affected_endpoints) == 1
    
    # Verify operational compiler output (validation & API)
    assert context.ocm is not None
    assert context.ocm.api is not None
    assert len(context.ocm.api.rest) == 1
    method, path, _handler = context.ocm.api.rest[0]
    assert method == "POST"
    assert path == "/checkout"
    
    assert context.ocm.validation is not None
    assert len(context.ocm.validation.unit_tests) == 1
    assert str(context.ocm.validation.unit_tests[0].id) == str(sym_test.id)
    
    # Verify ReviewContext
    assert context.review_context is not None
    assert len(context.review_context.execution.entry_points) == 1
    ep_exec = context.review_context.execution.entry_points[0]
    assert ep_exec.endpoint == "/checkout"
    assert ep_exec.method == "POST"
    
    # Verify LLMContext
    assert context.llm_context is not None
    assert len(context.llm_context.sym) > 0
    assert len(context.llm_context.ep) > 0
    assert len(context.llm_context.cf) > 0
    
    print("\n✓ E2E Golden Test passed successfully with full compilation!")
