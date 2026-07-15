"""Change compiler - orchestrates compilation passes."""

from typing import Any

from .passes import (
    ChangePassContext,
    ChangedSymbolsPass,
    ChangeClassificationPass,
)
from change.model import (
    ChangeModel,
    ModifiedSymbol,
    ImportChange,
    EndpointChange,
    FunctionBodyChange,
    SignatureChange,
    VisibilityChange,
    DecoratorChange,
    SuperclassChange,
    InterfaceChange,
    EndpointAnnotationChange,
)
from change.model.repository_comparison import RepositoryComparison
from language_adapters.model import RepositoryModel


class ChangeCompiler:
    """
    Compiles a git diff into a Change Model.
    
    This is the main entry point for change compilation.
    It orchestrates the execution of all compilation passes in order.
    
    Input: Git diff data with old and new repository models
    Output: ChangeModel containing the complete change representation
    """
    
    def __init__(self):
        """Initialize the compiler with all passes."""
        self.passes = [
            ChangedSymbolsPass(),
            ChangeClassificationPass(),
        ]
    
    def compile(
        self,
        comparison: RepositoryComparison
    ) -> ChangeModel:
        """
        Compile a git diff into a Change Model.
        
        Args:
            comparison: RepositoryComparison containing base model, head model, and diff
            
        Returns:
            ChangeModel containing the complete change representation
            
        Raises:
            ValueError: If comparison is invalid
        """
        # Validate the comparison (frozen dataclass ensures immutability)
        if comparison.is_same_commit():
            # This is allowed but worth noting
            pass
        
        # Initialize pass context with comparison data
        context = ChangePassContext(
            diff_data=comparison.diff,
            metadata={
                'diff_data': comparison.diff,
                'old_repository_model': comparison.base_model,
                'new_repository_model': comparison.head_model,
                'base_sha': comparison.base_sha,
                'head_sha': comparison.head_sha,
            }
        )
        
        # Execute each pass in sequence
        for compiler_pass in self.passes:
            context = compiler_pass.run(context)
        
        # Create and return the change model
        return self._build_change_model(context)
    
    def _build_change_model(self, context: ChangePassContext) -> ChangeModel:
        """
        Build the final ChangeModel from the pass context.
        
        Args:
            context: Final pass context with all change data
            
        Returns:
            Complete ChangeModel
        """
        # Convert modified symbols to ModifiedSymbol objects
        modified_symbols = []
        for modified_data in context.modified_symbols:
            symbol = modified_data['symbol']
            symbol_id = symbol.id
            
            # Get classified changes for this symbol
            changes = context.symbol_changes.get(symbol_id, [])
            
            modified_symbols.append(ModifiedSymbol(
                symbol=symbol,
                changes=tuple(changes)
            ))
        
        # Convert import changes to ImportChange objects
        changed_imports = [
            ImportChange(
                file=imp['file'],
                old_import=imp['old_import'],
                new_import=imp['new_import'],
                change_type=imp['change_type']
            )
            for imp in context.changed_imports
        ]
        
        # Convert endpoint changes to EndpointChange objects
        changed_endpoints = [
            EndpointChange(
                symbol_id=ep['symbol_id'],
                old_endpoint=ep['old_endpoint'],
                new_endpoint=ep['new_endpoint'],
                old_method=ep['old_method'],
                new_method=ep['new_method'],
                change_type=ep['change_type']
            )
            for ep in context.changed_endpoints
        ]
        
        return ChangeModel(
            added_symbols=tuple(context.added_symbols),
            removed_symbols=tuple(context.removed_symbols),
            modified_symbols=tuple(modified_symbols),
            changed_imports=tuple(changed_imports),
            changed_endpoints=tuple(changed_endpoints)
        )
    
    def get_pass_names(self) -> list[str]:
        """Get the names of all passes in execution order."""
        return [pass_.name for pass_ in self.passes]