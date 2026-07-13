"""Changed symbols pass - identifies which symbols changed in the diff."""

from typing import Any

from ..base import ChangeCompilerPass, ChangePassContext
from language_adapters.model import Symbol


class ChangedSymbolsPass(ChangeCompilerPass):
    """
    Pass 1: Changed Symbols
    
    Identifies which repository symbols changed by comparing old and new repository models.
    
    Input: Git diff data with old and new repository models
    Output: Lists of added, removed, modified, and renamed symbols
    """
    
    @property
    def name(self) -> str:
        return "changed_symbols"
    
    def run(self, context: ChangePassContext) -> ChangePassContext:
        """
        Execute changed symbols pass.
        
        Args:
            context: Pass context with diff data containing old and new repository models
            
        Returns:
            Updated context with changed symbols identified
        """
        # Extract old and new repository models from diff data
        old_model = context.metadata.get('old_repository_model')
        new_model = context.metadata.get('new_repository_model')
        
        if not old_model or not new_model:
            # If no models provided, return empty context
            return context
        
        # Build indices for fast lookup
        old_symbol_index = {s.id: s for s in old_model.symbols}
        new_symbol_index = {s.id: s for s in new_model.symbols}
        
        context.old_symbol_index = old_symbol_index
        context.new_symbol_index = new_symbol_index
        
        # Identify added, removed, and modified symbols
        old_ids = set(old_symbol_index.keys())
        new_ids = set(new_symbol_index.keys())
        
        # Added symbols: in new but not in old
        added_ids = new_ids - old_ids
        context.added_symbols = [new_symbol_index[sid] for sid in added_ids]
        
        # Removed symbols: in old but not in new
        removed_ids = old_ids - new_ids
        context.removed_symbols = [old_symbol_index[sid] for sid in removed_ids]
        
        # Modified symbols: in both but with differences
        common_ids = old_ids & new_ids
        modified = []
        for sid in common_ids:
            old_symbol = old_symbol_index[sid]
            new_symbol = new_symbol_index[sid]
            
            if self._symbol_changed(old_symbol, new_symbol):
                modified.append({
                    'symbol': new_symbol,
                    'old_symbol': old_symbol
                })
        
        context.modified_symbols = modified
        
        # Detect renamed symbols (deterministic structural match)
        context.renamed_symbols = self._detect_renames(
            context.added_symbols,
            context.removed_symbols
        )
        
        return context
    
    def _symbol_changed(self, old_symbol: Symbol, new_symbol: Symbol) -> bool:
        """
        Determine if a symbol has changed by comparing its properties.
        
        Args:
            old_symbol: Symbol from old repository model
            new_symbol: Symbol from new repository model
            
        Returns:
            True if the symbol has changed, False otherwise
        """
        # Check if range changed (lines added/removed)
        if old_symbol.range != new_symbol.range:
            return True
        
        # Check if visibility changed
        if old_symbol.visibility != new_symbol.visibility:
            return True
        
        # Check if properties changed
        if old_symbol.properties != new_symbol.properties:
            return True
        
        return False
    
    def _detect_renames(
        self,
        added: list[Symbol],
        removed: list[Symbol]
    ) -> list[dict]:
        """
        Detect deterministic symbol renames by exact structural match.

        A rename is detected when, for the same kind and file, exactly one
        symbol was removed and exactly one was added. This is a deterministic
        structural match, not a speculative inference.

        Args:
            added: List of added symbols
            removed: List of removed symbols

        Returns:
            List of deterministic rename mappings
        """
        renames = []

        # Group by kind and file for matching
        added_by_kind_file: dict[tuple[str, str], list[Symbol]] = {}
        for symbol in added:
            key = (symbol.kind, symbol.file)
            if key not in added_by_kind_file:
                added_by_kind_file[key] = []
            added_by_kind_file[key].append(symbol)

        removed_by_kind_file: dict[tuple[str, str], list[Symbol]] = {}
        for symbol in removed:
            key = (symbol.kind, symbol.file)
            if key not in removed_by_kind_file:
                removed_by_kind_file[key] = []
            removed_by_kind_file[key].append(symbol)

        # Match deterministic renames: one removed + one added of same kind/file
        for key, added_list in added_by_kind_file.items():
            if key not in removed_by_kind_file:
                continue

            removed_list = removed_by_kind_file[key]

            # Deterministic 1:1 match by structural position
            if len(added_list) == len(removed_list) == 1:
                renames.append({
                    'old_symbol': removed_list[0],
                    'new_symbol': added_list[0],
                })

        return renames
