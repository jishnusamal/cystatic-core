"""Symbol collection pass - extracts all symbols from semantic graph."""

from typing import Any

from ..base import CompilerPass, PassContext
from repository.model import Symbol, SymbolKind, SymbolVisibility


class SymbolCollectionPass(CompilerPass):
    """
    Pass 1: Symbol Collection
    
    Extracts all symbols from the semantic graph and assigns stable identifiers.
    
    Input: Semantic graph (from language adapter)
    Output: Complete symbol inventory with stable IDs
    """
    
    @property
    def name(self) -> str:
        return "symbol_collection"
    
    def run(self, context: PassContext) -> PassContext:
        """
        Execute symbol collection pass.
        
        Args:
            context: Pass context with semantic graph data
            
        Returns:
            Updated context with symbols collected
        """
        # Extract symbols from semantic graph
        # The semantic graph is expected to be in context.metadata['semantic_graph']
        semantic_graph = context.metadata.get('semantic_graph', {})
        
        symbols = []
        
        # Extract symbols from semantic graph
        # This is a generic implementation - language adapters provide the semantic graph
        for file_path, file_data in semantic_graph.items():
            file_symbols = self._extract_symbols_from_file(file_path, file_data)
            symbols.extend(file_symbols)
        
        # Update context
        context.symbols = symbols
        
        # Build indices for fast lookup
        context.symbol_index = {s.id: s for s in symbols}
        context.file_index = {}
        for symbol in symbols:
            if symbol.file not in context.file_index:
                context.file_index[symbol.file] = []
            context.file_index[symbol.file].append(symbol)
        
        return context
    
    def _extract_symbols_from_file(self, file_path: str, file_data: dict[str, Any]) -> list[Symbol]:
        """
        Extract symbols from a single file's semantic graph data.
        
        Args:
            file_path: Path to the file
            file_data: Semantic graph data for the file
            
        Returns:
            List of symbols found in the file
        """
        symbols = []
        language = file_data.get('language', 'unknown')
        
        # Extract functions
        for func in file_data.get('functions', []):
            symbol = self._create_function_symbol(file_path, func, language)
            symbols.append(symbol)
        
        # Extract classes
        for cls in file_data.get('classes', []):
            symbols.extend(self._create_class_symbols(file_path, cls, language))
        
        # Extract methods (if not already included in classes)
        for method in file_data.get('methods', []):
            symbol = self._create_method_symbol(file_path, method, language)
            symbols.append(symbol)
        
        # Extract modules
        for module in file_data.get('modules', []):
            symbol = self._create_module_symbol(file_path, module, language)
            symbols.append(symbol)
        
        # Extract constants
        for constant in file_data.get('constants', []):
            symbol = self._create_constant_symbol(file_path, constant, language)
            symbols.append(symbol)
        
        # Extract enums
        for enum in file_data.get('enums', []):
            symbols.extend(self._create_enum_symbols(file_path, enum, language))
        
        # Extract interfaces
        for interface in file_data.get('interfaces', []):
            symbol = self._create_interface_symbol(file_path, interface, language)
            symbols.append(symbol)
        
        return symbols
    
    def _create_function_symbol(self, file_path: str, func_data: dict[str, Any], language: str) -> Symbol:
        """Create a function symbol from function data."""
        name = func_data.get('name', 'unknown')
        start_line = func_data.get('start_line', 0)
        end_line = func_data.get('end_line', start_line)
        
        # Generate stable ID: language://file_path::function_name
        symbol_id = f"{language}://{file_path}::{name}"
        
        return Symbol(
            id=symbol_id,
            name=name,
            kind=SymbolKind.FUNCTION,
            language=language,
            file=file_path,
            range=(start_line, end_line),
            visibility=self._parse_visibility(func_data.get('visibility', 'public')),
            properties=func_data.get('properties', {})
        )
    
    def _create_method_symbol(self, file_path: str, method_data: dict[str, Any], language: str) -> Symbol:
        """Create a method symbol from method data."""
        name = method_data.get('name', 'unknown')
        class_name = method_data.get('class_name', '')
        start_line = method_data.get('start_line', 0)
        end_line = method_data.get('end_line', start_line)
        
        # Generate stable ID: language://file_path#class_name.method_name
        if class_name:
            symbol_id = f"{language}://{file_path}#{class_name}.{name}"
        else:
            symbol_id = f"{language}://{file_path}::{name}"
        
        return Symbol(
            id=symbol_id,
            name=name,
            kind=SymbolKind.METHOD,
            language=language,
            file=file_path,
            range=(start_line, end_line),
            visibility=self._parse_visibility(method_data.get('visibility', 'public')),
            properties=method_data.get('properties', {})
        )
    
    def _create_class_symbols(self, file_path: str, class_data: dict[str, Any], language: str) -> list[Symbol]:
        """Create class symbol and its methods from class data."""
        symbols = []
        name = class_data.get('name', 'unknown')
        start_line = class_data.get('start_line', 0)
        end_line = class_data.get('end_line', start_line)
        
        # Generate stable ID: language://file_path#class_name
        symbol_id = f"{language}://{file_path}#{name}"
        
        # Create class symbol
        class_symbol = Symbol(
            id=symbol_id,
            name=name,
            kind=SymbolKind.CLASS,
            language=language,
            file=file_path,
            range=(start_line, end_line),
            visibility=self._parse_visibility(class_data.get('visibility', 'public')),
            properties=class_data.get('properties', {})
        )
        symbols.append(class_symbol)
        
        # Create method symbols
        for method in class_data.get('methods', []):
            method_symbol = self._create_method_symbol(file_path, method, language)
            symbols.append(method_symbol)
        
        return symbols
    
    def _create_module_symbol(self, file_path: str, module_data: dict[str, Any], language: str) -> Symbol:
        """Create a module symbol from module data."""
        name = module_data.get('name', file_path)
        start_line = module_data.get('start_line', 0)
        end_line = module_data.get('end_line', start_line)
        
        # Generate stable ID: language://file_path
        symbol_id = f"{language}://{file_path}"
        
        return Symbol(
            id=symbol_id,
            name=name,
            kind=SymbolKind.MODULE,
            language=language,
            file=file_path,
            range=(start_line, end_line),
            visibility=SymbolVisibility.PUBLIC,
            properties=module_data.get('properties', {})
        )
    
    def _create_constant_symbol(self, file_path: str, constant_data: dict[str, Any], language: str) -> Symbol:
        """Create a constant symbol from constant data."""
        name = constant_data.get('name', 'unknown')
        start_line = constant_data.get('start_line', 0)
        end_line = constant_data.get('end_line', start_line)
        
        # Generate stable ID: language://file_path::constant_name
        symbol_id = f"{language}://{file_path}::{name}"
        
        return Symbol(
            id=symbol_id,
            name=name,
            kind=SymbolKind.CONSTANT,
            language=language,
            file=file_path,
            range=(start_line, end_line),
            visibility=self._parse_visibility(constant_data.get('visibility', 'public')),
            properties=constant_data.get('properties', {})
        )
    
    def _create_enum_symbols(self, file_path: str, enum_data: dict[str, Any], language: str) -> list[Symbol]:
        """Create enum symbol from enum data."""
        symbols = []
        name = enum_data.get('name', 'unknown')
        start_line = enum_data.get('start_line', 0)
        end_line = enum_data.get('end_line', start_line)
        
        # Generate stable ID: language://file_path#enum_name
        symbol_id = f"{language}://{file_path}#{name}"
        
        enum_symbol = Symbol(
            id=symbol_id,
            name=name,
            kind=SymbolKind.ENUM,
            language=language,
            file=file_path,
            range=(start_line, end_line),
            visibility=self._parse_visibility(enum_data.get('visibility', 'public')),
            properties=enum_data.get('properties', {})
        )
        symbols.append(enum_symbol)
        
        return symbols
    
    def _create_interface_symbol(self, file_path: str, interface_data: dict[str, Any], language: str) -> Symbol:
        """Create an interface symbol from interface data."""
        name = interface_data.get('name', 'unknown')
        start_line = interface_data.get('start_line', 0)
        end_line = interface_data.get('end_line', start_line)
        
        # Generate stable ID: language://file_path#interface_name
        symbol_id = f"{language}://{file_path}#{name}"
        
        return Symbol(
            id=symbol_id,
            name=name,
            kind=SymbolKind.INTERFACE,
            language=language,
            file=file_path,
            range=(start_line, end_line),
            visibility=self._parse_visibility(interface_data.get('visibility', 'public')),
            properties=interface_data.get('properties', {})
        )
    
    def _parse_visibility(self, visibility: str) -> SymbolVisibility:
        """Parse visibility string to SymbolVisibility enum."""
        visibility_map = {
            'public': SymbolVisibility.PUBLIC,
            'private': SymbolVisibility.PRIVATE,
            'protected': SymbolVisibility.PROTECTED,
            'internal': SymbolVisibility.INTERNAL,
            'package': SymbolVisibility.PACKAGE,
        }
        return visibility_map.get(visibility.lower(), SymbolVisibility.PUBLIC)