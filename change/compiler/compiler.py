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


class ChangeCompiler:
    """
    Compiles a git diff into a Change Model.
    
    This is the main entry point for Phase 2 compilation.
    It orchestrates the execution of all compiler passes in order.
    
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
        diff_data: dict[str, Any],
        old_repository_model: Any,
        new_repository_model: Any
    ) -> ChangeModel:
        """
        Compile a git diff into a Change Model.
        
        Args:
            diff_data: Git diff data (file changes, hunks, etc.)
            old_repository_model: RepositoryModel before the change
            new_repository_model: RepositoryModel after the change
            
        Returns:
            ChangeModel containing the complete change representation
        """
        # Initialize pass context with diff data and models
        context = ChangePassContext(
            diff_data=diff_data,
            metadata={
                'diff_data': diff_data,
                'old_repository_model': old_repository_model,
                'new_repository_model': new_repository_model,
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