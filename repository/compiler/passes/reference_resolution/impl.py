"""Reference resolution pass - resolves symbol-to-symbol references."""

from typing import Any

from ..base import CompilerPass, PassContext
from repository.model import ReferenceGraph, Symbol


class ReferenceResolutionPass(CompilerPass):
    """
    Pass 2: Reference Resolution
    
    Resolves symbol-to-symbol references from the semantic graph.
    
    Input: Symbols from Pass 1, semantic graph with references
    Output: Reference graph with all symbol relationships
    """
    
    @property
    def name(self) -> str:
        return "reference_resolution"
    
    def run(self, context: PassContext) -> PassContext:
        """
        Execute reference resolution pass.
        
        Args:
            context: Pass context with symbols and semantic graph
            
        Returns:
            Updated context with reference graph
        """
        if not context.symbols:
            # No symbols to resolve references for
            context.reference_graph = ReferenceGraph(edges=tuple())
            return context
        
        # Get semantic graph from metadata
        semantic_graph = context.metadata.get('semantic_graph', {})
        
        # Build reference edges
        reference_edges = []
        
        # Process each file in the semantic graph
        for file_path, file_data in semantic_graph.items():
            file_symbol_id = f"{file_data.get('language', 'unknown')}://{file_path}"
            
            # Resolve imports
            for import_ref in file_data.get('imports', []):
                reference_edges.extend(self._resolve_import(file_path, import_ref, context.symbol_index))
            
            # Resolve class inheritance
            for class_data in file_data.get('classes', []):
                reference_edges.extend(self._resolve_inheritance(file_path, class_data, context.symbol_index))
            
            # Resolve interface implementations
            for class_data in file_data.get('classes', []):
                reference_edges.extend(self._resolve_implements(file_path, class_data, context.symbol_index))
            
            # Resolve type references
            for type_ref in file_data.get('type_references', []):
                reference_edges.extend(self._resolve_type_reference(file_path, type_ref, context.symbol_index))
            
            # Resolve decorator references
            for decorator_ref in file_data.get('decorators', []):
                reference_edges.extend(self._resolve_decorator(file_path, decorator_ref, context.symbol_index))
        
        # Create reference graph
        context.reference_graph = ReferenceGraph(edges=tuple(reference_edges))
        
        return context
    
    def _resolve_import(self, file_path: str, import_data: dict[str, Any], 
                       symbol_index: dict[str, Symbol]) -> list[tuple[str, str, str]]:
        """
        Resolve an import reference.
        
        Returns:
            List of (source_id, target_id, relationship_type) tuples
        """
        edges = []
        
        import_type = import_data.get('type', 'unknown')  # 'import', 'from_import', etc.
        module_name = import_data.get('module', '')
        imported_names = import_data.get('names', [])
        
        # Get the source symbol (the file doing the import)
        source_id = self._get_file_symbol_id(file_path, symbol_index)
        if not source_id:
            return edges
        
        # Create reference edges for each imported name
        for imported_name in imported_names:
            # Try to find the target symbol in the symbol index
            target_id = self._find_imported_symbol(module_name, imported_name, symbol_index)
            
            if target_id:
                edges.append((source_id, target_id, "imports"))
        
        return edges
    
    def _resolve_inheritance(self, file_path: str, class_data: dict[str, Any],
                            symbol_index: dict[str, Symbol]) -> list[tuple[str, str, str]]:
        """
        Resolve class inheritance references.
        
        Returns:
            List of (source_id, target_id, relationship_type) tuples
        """
        edges = []
        
        class_name = class_data.get('name', '')
        if not class_name:
            return edges
        
        # Get the class symbol ID
        class_id = f"python://{file_path}#{class_name}"
        if class_id not in symbol_index:
            return edges
        
        # Process base classes
        for base_class in class_data.get('bases', []):
            base_name = base_class.get('name', '')
            if not base_name:
                continue
            
            # Try to find the base class symbol
            base_id = self._find_class_symbol(file_path, base_name, symbol_index)
            
            if base_id:
                edges.append((class_id, base_id, "inherits"))
        
        return edges
    
    def _resolve_implements(self, file_path: str, class_data: dict[str, Any],
                           symbol_index: dict[str, Symbol]) -> list[tuple[str, str, str]]:
        """
        Resolve interface implementation references.
        
        Returns:
            List of (source_id, target_id, relationship_type) tuples
        """
        edges = []
        
        class_name = class_data.get('name', '')
        if not class_name:
            return edges
        
        # Get the class symbol ID
        class_id = f"python://{file_path}#{class_name}"
        if class_id not in symbol_index:
            return edges
        
        # Process implemented interfaces
        for interface in class_data.get('implements', []):
            interface_name = interface.get('name', '')
            if not interface_name:
                continue
            
            # Try to find the interface symbol
            interface_id = self._find_interface_symbol(file_path, interface_name, symbol_index)
            
            if interface_id:
                edges.append((class_id, interface_id, "implements"))
        
        return edges
    
    def _resolve_type_reference(self, file_path: str, type_ref_data: dict[str, Any],
                               symbol_index: dict[str, Symbol]) -> list[tuple[str, str, str]]:
        """
        Resolve type references.
        
        Returns:
            List of (source_id, target_id, relationship_type) tuples
        """
        edges = []
        
        # Get the source symbol (function/method that uses this type)
        source_symbol_id = type_ref_data.get('symbol_id')
        if not source_symbol_id:
            return edges
        
        # Get the target type name
        type_name = type_ref_data.get('type_name', '')
        if not type_name:
            return edges
        
        # Try to find the type symbol
        target_id = self._find_type_symbol(file_path, type_name, symbol_index)
        
        if target_id:
            edges.append((source_symbol_id, target_id, "references"))
        
        return edges
    
    def _resolve_decorator(self, file_path: str, decorator_data: dict[str, Any],
                          symbol_index: dict[str, Symbol]) -> list[tuple[str, str, str]]:
        """
        Resolve decorator references.
        
        Returns:
            List of (source_id, target_id, relationship_type) tuples
        """
        edges = []
        
        # Get the source symbol (function/method/class being decorated)
        source_symbol_id = decorator_data.get('symbol_id')
        if not source_symbol_id:
            return edges
        
        # Get the decorator name
        decorator_name = decorator_data.get('name', '')
        if not decorator_name:
            return edges
        
        # Try to find the decorator symbol
        target_id = self._find_decorator_symbol(file_path, decorator_name, symbol_index)
        
        if target_id:
            edges.append((source_symbol_id, target_id, "references"))
        
        return edges
    
    def _get_file_symbol_id(self, file_path: str, symbol_index: dict[str, Symbol]) -> str | None:
        """Get the module symbol ID for a file."""
        # Try to find a module symbol for this file
        for symbol in symbol_index.values():
            if symbol.file == file_path and symbol.kind.value == "module":
                return symbol.id
        return None
    
    def _find_imported_symbol(self, module_name: str, imported_name: str,
                             symbol_index: dict[str, Symbol]) -> str | None:
        """
        Find a symbol that was imported.
        
        This is a simplified implementation - in practice, this would need
        to resolve module paths and imported names to actual symbols.
        """
        # Try exact match on symbol name
        for symbol in symbol_index.values():
            if symbol.name == imported_name:
                return symbol.id
        
        # Try qualified name match (e.g., module.name)
        qualified_name = f"{module_name}.{imported_name}" if module_name else imported_name
        for symbol in symbol_index.values():
            if symbol.name == qualified_name:
                return symbol.id
        
        return None
    
    def _find_class_symbol(self, file_path: str, class_name: str,
                          symbol_index: dict[str, Symbol]) -> str | None:
        """Find a class symbol by name."""
        # Try exact match in the same file
        class_id = f"python://{file_path}#{class_name}"
        if class_id in symbol_index:
            return class_id
        
        # Try to find by name across all files
        for symbol in symbol_index.values():
            if symbol.name == class_name and symbol.kind.value in ["class", "interface"]:
                return symbol.id
        
        return None
    
    def _find_interface_symbol(self, file_path: str, interface_name: str,
                              symbol_index: dict[str, Symbol]) -> str | None:
        """Find an interface symbol by name."""
        # Try exact match in the same file
        interface_id = f"python://{file_path}#{interface_name}"
        if interface_id in symbol_index:
            return interface_id
        
        # Try to find by name across all files
        for symbol in symbol_index.values():
            if symbol.name == interface_name and symbol.kind.value == "interface":
                return symbol.id
        
        return None
    
    def _find_type_symbol(self, file_path: str, type_name: str,
                         symbol_index: dict[str, Symbol]) -> str | None:
        """Find a type symbol by name."""
        # Try to find by name across all symbols
        for symbol in symbol_index.values():
            if symbol.name == type_name:
                return symbol.id
        
        return None
    
    def _find_decorator_symbol(self, file_path: str, decorator_name: str,
                              symbol_index: dict[str, Symbol]) -> str | None:
        """Find a decorator symbol by name."""
        # Try to find by name across all symbols
        for symbol in symbol_index.values():
            if symbol.name == decorator_name:
                return symbol.id
        
        return None