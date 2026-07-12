"""Call graph pass - builds repository-wide call graph."""

from typing import Any

from ..base import CompilerPass, PassContext
from repository.model import CallEdge, CallGraph, Symbol


class CallGraphPass(CompilerPass):
    """
    Pass 3: Call Graph
    
    Builds a repository-wide directed call graph from the semantic graph.
    
    Input: Symbols from Pass 1, semantic graph with call information
    Output: Directed call graph
    """
    
    @property
    def name(self) -> str:
        return "call_graph"
    
    def run(self, context: PassContext) -> PassContext:
        """
        Execute call graph pass.
        
        Args:
            context: Pass context with symbols and semantic graph
            
        Returns:
            Updated context with call graph
        """
        if not context.symbols:
            # No symbols to build call graph for
            context.call_graph = CallGraph(edges=tuple())
            return context
        
        # Get semantic graph from metadata
        semantic_graph = context.metadata.get('semantic_graph', {})
        
        # Build call edges
        call_edges = []
        
        # Process each file in the semantic graph
        for file_path, file_data in semantic_graph.items():
            # Extract function calls
            for func_call in file_data.get('function_calls', []):
                call_edges.extend(self._process_function_call(file_path, func_call, context.symbol_index))
            
            # Extract method calls
            for method_call in file_data.get('method_calls', []):
                call_edges.extend(self._process_method_call(file_path, method_call, context.symbol_index))
            
            # Extract constructor calls
            for constructor_call in file_data.get('constructor_calls', []):
                call_edges.extend(self._process_constructor_call(file_path, constructor_call, context.symbol_index))
        
        # Create call graph
        context.call_graph = CallGraph(edges=tuple(call_edges))
        
        return context
    
    def _process_function_call(self, file_path: str, call_data: dict[str, Any],
                              symbol_index: dict[str, Symbol]) -> list[CallEdge]:
        """
        Process a function call.
        
        Returns:
            List of CallEdge objects
        """
        edges = []
        
        # Get caller information
        caller_id = call_data.get('caller_id')
        if not caller_id:
            return edges
        
        # Get callee information
        callee_name = call_data.get('callee_name', '')
        if not callee_name:
            return edges
        
        # Try to find the callee symbol
        callee_id = self._find_callee_symbol(file_path, callee_name, symbol_index)
        
        if callee_id:
            call_type = call_data.get('call_type', 'direct')
            edges.append(CallEdge(
                caller_id=caller_id,
                callee_id=callee_id,
                call_type=call_type
            ))
        
        return edges
    
    def _process_method_call(self, file_path: str, call_data: dict[str, Any],
                            symbol_index: dict[str, Symbol]) -> list[CallEdge]:
        """
        Process a method call.
        
        Returns:
            List of CallEdge objects
        """
        edges = []
        
        # Get caller information
        caller_id = call_data.get('caller_id')
        if not caller_id:
            return edges
        
        # Get callee information
        method_name = call_data.get('method_name', '')
        class_name = call_data.get('class_name', '')
        if not method_name:
            return edges
        
        # Try to find the callee symbol
        callee_id = self._find_method_symbol(file_path, method_name, class_name, symbol_index)
        
        if callee_id:
            call_type = call_data.get('call_type', 'direct')
            edges.append(CallEdge(
                caller_id=caller_id,
                callee_id=callee_id,
                call_type=call_type
            ))
        
        return edges
    
    def _process_constructor_call(self, file_path: str, call_data: dict[str, Any],
                                 symbol_index: dict[str, Symbol]) -> list[CallEdge]:
        """
        Process a constructor call.
        
        Returns:
            List of CallEdge objects
        """
        edges = []
        
        # Get caller information
        caller_id = call_data.get('caller_id')
        if not caller_id:
            return edges
        
        # Get callee information (class being instantiated)
        class_name = call_data.get('class_name', '')
        if not class_name:
            return edges
        
        # Try to find the class symbol (constructor)
        callee_id = self._find_class_symbol(file_path, class_name, symbol_index)
        
        if callee_id:
            call_type = call_data.get('call_type', 'direct')
            edges.append(CallEdge(
                caller_id=caller_id,
                callee_id=callee_id,
                call_type=call_type
            ))
        
        return edges
    
    def _find_callee_symbol(self, file_path: str, callee_name: str,
                           symbol_index: dict[str, Symbol]) -> str | None:
        """
        Find a callee symbol by name.
        
        This is a simplified implementation - in practice, this would need
        to handle scoping, imports, and qualified names.
        """
        # Try exact match on symbol name
        for symbol in symbol_index.values():
            if symbol.name == callee_name and symbol.kind.value in ["function", "method"]:
                return symbol.id
        
        # Try qualified name match
        qualified_name = callee_name
        for symbol in symbol_index.values():
            if symbol.name == qualified_name:
                return symbol.id
        
        return None
    
    def _find_method_symbol(self, file_path: str, method_name: str, class_name: str,
                           symbol_index: dict[str, Symbol]) -> str | None:
        """Find a method symbol by name and class."""
        # Try exact match with class name
        if class_name:
            method_id = f"python://{file_path}#{class_name}.{method_name}"
            if method_id in symbol_index:
                return method_id
        
        # Try to find by method name across all symbols
        for symbol in symbol_index.values():
            if symbol.name == method_name and symbol.kind.value == "method":
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
            if symbol.name == class_name and symbol.kind.value == "class":
                return symbol.id
        
        return None