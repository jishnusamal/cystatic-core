"""Shared model compiler - compiles a language-agnostic semantic graph into a RepositoryModel."""

from typing import Any

from language_adapters.model import (
    RepositoryModel,
    Symbol,
    SymbolKind,
    SymbolVisibility,
    CallEdge,
    CallGraph,
    ReferenceEdge,
    ReferenceGraph,
    EntryPoint,
    EntryPointKind,
)


class ModelCompiler:
    """
    Language-agnostic compiler that transforms a semantic graph into a RepositoryModel.
    
    The semantic graph is a dict[file_path, file_data] where each file_data contains
    the extracted semantic elements (functions, classes, imports, function_calls, 
    rest_endpoints) produced by language-specific extractors.
    
    This replaces the duplicated _compile_to_model methods previously inlined in 
    each language adapter.
    """
    
    def compile(self, semantic_graph: dict[str, dict[str, Any]], language: str) -> RepositoryModel:
        """
        Compile a semantic graph into a RepositoryModel.
        
        Args:
            semantic_graph: Dict mapping file paths to extracted file data
            language: Programming language identifier
            
        Returns:
            RepositoryModel containing the complete repository representation
        """
        symbols: list[Symbol] = []
        symbol_index: dict[str, Symbol] = {}
        call_graph_edges: list[CallEdge] = []
        reference_graph_edges: list[ReferenceEdge] = []
        entry_points: list[EntryPoint] = []
        
        # Pass 1: Symbol Collection
        for file_path, file_data in semantic_graph.items():
            self._collect_symbols(file_path, language, file_data, symbols, symbol_index)
        
        # Pass 2: Reference Resolution (imports)
        for symbol in symbols:
            if symbol.kind == SymbolKind.IMPORT:
                self._resolve_import_references(symbol, symbol_index, reference_graph_edges)
        
        # Pass 3: Call Graph
        for file_path, file_data in semantic_graph.items():
            for call in file_data.get('function_calls', []):
                self._process_call(call, symbol_index, call_graph_edges)
        
        # Pass 4: Endpoint Discovery
        for file_path, file_data in semantic_graph.items():
            for endpoint in file_data.get('rest_endpoints', []):
                self._process_rest_endpoint(endpoint, file_path, language, symbol_index, entry_points)
        
        return RepositoryModel(
            symbols=frozenset(symbols),
            call_graph=CallGraph(edges=tuple(call_graph_edges)),
            reference_graph=ReferenceGraph(edges=tuple(reference_graph_edges)),
            entry_points=tuple(entry_points),
        )
    
    def _collect_symbols(
        self,
        file_path: str,
        language: str,
        file_data: dict[str, Any],
        symbols: list[Symbol],
        symbol_index: dict[str, Symbol],
    ) -> None:
        """Collect symbols from a file's extracted data."""
        # Collect functions
        for func in file_data.get('functions', []):
            symbol = self._create_function_symbol(file_path, language, func)
            symbols.append(symbol)
            symbol_index[symbol.id] = symbol
        
        # Collect classes with methods
        for cls in file_data.get('classes', []):
            class_symbol = self._create_class_symbol(file_path, language, cls)
            symbols.append(class_symbol)
            symbol_index[class_symbol.id] = class_symbol
            
            for method in cls.get('methods', []):
                method_symbol = self._create_method_symbol(
                    file_path, language, method, cls['name']
                )
                symbols.append(method_symbol)
                symbol_index[method_symbol.id] = method_symbol
        
        # Collect imports
        for imp in file_data.get('imports', []):
            import_symbol = self._create_import_symbol(file_path, language, imp)
            if import_symbol:
                symbols.append(import_symbol)
                symbol_index[import_symbol.id] = import_symbol
    
    def _create_function_symbol(self, file_path: str, language: str, func_data: dict) -> Symbol:
        """Create a Symbol for a function."""
        func_name = func_data['name']
        symbol_id = f"{language}://{file_path}::{func_name}"
        
        return Symbol(
            id=symbol_id,
            name=func_name,
            kind=SymbolKind.FUNCTION,
            language=language,
            file=file_path,
            range=(func_data['start_line'], func_data['end_line']),
            visibility=SymbolVisibility(func_data.get('visibility', 'public')),
            properties=func_data.get('properties', {})
        )
    
    def _create_class_symbol(self, file_path: str, language: str, class_data: dict) -> Symbol:
        """Create a Symbol for a class."""
        class_name = class_data['name']
        symbol_id = f"{language}://{file_path}#{class_name}"
        
        return Symbol(
            id=symbol_id,
            name=class_name,
            kind=SymbolKind.CLASS,
            language=language,
            file=file_path,
            range=(class_data['start_line'], class_data['end_line']),
            visibility=SymbolVisibility(class_data.get('visibility', 'public')),
            properties=class_data.get('properties', {})
        )
    
    def _create_method_symbol(
        self, file_path: str, language: str, method_data: dict, class_name: str
    ) -> Symbol:
        """Create a Symbol for a method."""
        method_name = method_data['name']
        symbol_id = f"{language}://{file_path}#{class_name}.{method_name}"
        
        return Symbol(
            id=symbol_id,
            name=method_name,
            kind=SymbolKind.METHOD,
            language=language,
            file=file_path,
            range=(method_data['start_line'], method_data['end_line']),
            visibility=SymbolVisibility(method_data.get('visibility', 'public')),
            properties=method_data.get('properties', {})
        )
    
    def _create_import_symbol(
        self, file_path: str, language: str, import_data: dict
    ) -> Symbol | None:
        """Create a Symbol for an import statement."""
        imp_type = import_data.get('type', 'import')
        module = import_data.get('module', '')
        names = import_data.get('names', [])
        
        if not names:
            return None
        
        first_name = names[0]
        symbol_id = f"{language}://{file_path}::import::{first_name}"
        
        return Symbol(
            id=symbol_id,
            name=first_name,
            kind=SymbolKind.IMPORT,
            language=language,
            file=file_path,
            range=(0, 0),
            visibility=SymbolVisibility.PUBLIC,
            properties={'type': imp_type, 'module': module, 'names': names}
        )
    
    def _resolve_import_references(
        self,
        import_symbol: Symbol,
        symbol_index: dict[str, Symbol],
        reference_graph_edges: list[ReferenceEdge],
    ) -> None:
        """Resolve references for an import symbol."""
        imported_module = import_symbol.properties.get('module', '')
        imported_names = import_symbol.properties.get('names', [])
        
        for imported_name in imported_names:
            for symbol_id, symbol in symbol_index.items():
                if symbol_id == import_symbol.id:
                    continue
                
                if self._matches_import(symbol, imported_module, imported_name):
                    edge = ReferenceEdge(
                        source_id=import_symbol.id,
                        target_id=symbol.id,
                        relation_type="import"
                    )
                    reference_graph_edges.append(edge)
    
    def _matches_import(self, symbol: Symbol, module: str, name: str) -> bool:
        """Check if a symbol matches an import statement."""
        if symbol.name != name:
            return False
        
        symbol_file = symbol.file
        if module and module in symbol_file:
            return True
        
        return False
    
    def _process_call(
        self,
        call: dict[str, Any],
        symbol_index: dict[str, Symbol],
        call_graph_edges: list[CallEdge],
    ) -> None:
        """Process a single function call and create a call edge."""
        caller_id = call.get('caller_id')
        callee_name = call.get('callee_name')
        call_type = call.get('call_type', 'direct')
        
        if not caller_id or not callee_name:
            return
        
        callee_id = self._resolve_callee_id(callee_name, caller_id, symbol_index)
        
        if callee_id:
            edge = CallEdge(
                caller_id=caller_id,
                callee_id=callee_id,
                call_type=call_type
            )
            call_graph_edges.append(edge)
    
    def _resolve_callee_id(
        self,
        callee_name: str,
        caller_id: str,
        symbol_index: dict[str, Symbol],
    ) -> str | None:
        """Resolve a callee name to a symbol id."""
        # Try exact name match first
        for symbol_id, symbol in symbol_index.items():
            if symbol.name == callee_name:
                return symbol_id
        
        # Try to construct id from caller's file path
        if '::' in caller_id:
            parts = caller_id.split('::')
            if len(parts) == 2:
                potential_id = f"{parts[0]}::{callee_name}"
                if potential_id in symbol_index:
                    return potential_id
        
        return None
    
    def _process_rest_endpoint(
        self,
        endpoint: dict[str, Any],
        file_path: str,
        language: str,
        symbol_index: dict[str, Symbol],
        entry_points: list[EntryPoint],
    ) -> None:
        """Process a REST endpoint and create an EntryPoint."""
        method = endpoint.get('method', 'GET')
        route = endpoint.get('route', '')
        handler_name = endpoint.get('handler', '')
        
        if not route or not handler_name:
            return
        
        handler_id = f"{language}://{file_path}::{handler_name}"
        
        if handler_id not in symbol_index:
            return
        
        entry_point = EntryPoint(
            kind=EntryPointKind.REST_ENDPOINT,
            route=f"{method} {route}",
            handler_id=handler_id,
            metadata={
                'method': method,
                'route': route,
                'handler': handler_name,
                'file': file_path,
            }
        )
        
        entry_points.append(entry_point)