"""Endpoint discovery pass - identifies externally reachable entry points."""

from typing import Any

from ..base import CompilerPass, PassContext
from repository.model import EntryPoint, EntryPointKind, Symbol


class EndpointDiscoveryPass(CompilerPass):
    """
    Pass 4: Endpoint Discovery
    
    Identifies externally reachable entry points from the semantic graph.
    
    Input: Symbols from Pass 1, semantic graph with endpoint information
    Output: Entry points (REST, GraphQL, CLI, etc.)
    """
    
    @property
    def name(self) -> str:
        return "endpoint_discovery"
    
    def run(self, context: PassContext) -> PassContext:
        """
        Execute endpoint discovery pass.
        
        Args:
            context: Pass context with symbols and semantic graph
            
        Returns:
            Updated context with entry points
        """
        if not context.symbols:
            # No symbols to discover endpoints for
            context.entry_points = []
            return context
        
        # Get semantic graph from metadata
        semantic_graph = context.metadata.get('semantic_graph', {})
        
        # Discover entry points
        entry_points = []
        
        # Process each file in the semantic graph
        for file_path, file_data in semantic_graph.items():
            # Discover REST endpoints
            for endpoint in file_data.get('rest_endpoints', []):
                entry_points.extend(self._discover_rest_endpoint(file_path, endpoint, context.symbol_index))
            
            # Discover GraphQL resolvers
            for resolver in file_data.get('graphql_resolvers', []):
                entry_points.extend(self._discover_graphql_resolver(file_path, resolver, context.symbol_index))
            
            # Discover RPC handlers
            for handler in file_data.get('rpc_handlers', []):
                entry_points.extend(self._discover_rpc_handler(file_path, handler, context.symbol_index))
            
            # Discover CLI commands
            for command in file_data.get('cli_commands', []):
                entry_points.extend(self._discover_cli_command(file_path, command, context.symbol_index))
            
            # Discover scheduled jobs
            for job in file_data.get('scheduled_jobs', []):
                entry_points.extend(self._discover_scheduled_job(file_path, job, context.symbol_index))
            
            # Discover worker entry points
            for worker in file_data.get('worker_entries', []):
                entry_points.extend(self._discover_worker_entry(file_path, worker, context.symbol_index))
        
        # Update context
        context.entry_points = entry_points
        
        return context
    
    def _discover_rest_endpoint(self, file_path: str, endpoint_data: dict[str, Any],
                               symbol_index: dict[str, Symbol]) -> list[EntryPoint]:
        """
        Discover a REST endpoint.
        
        Returns:
            List of EntryPoint objects
        """
        entry_points = []
        
        # Get endpoint information
        method = endpoint_data.get('method', 'GET').upper()
        route = endpoint_data.get('route', '')
        handler_name = endpoint_data.get('handler', '')
        
        if not route or not handler_name:
            return entry_points
        
        # Find the handler symbol
        handler_id = self._find_handler_symbol(file_path, handler_name, symbol_index)
        
        if handler_id:
            # Create route string (e.g., "POST /checkout")
            route_string = f"{method} {route}"
            
            entry_point = EntryPoint(
                kind=EntryPointKind.REST_ENDPOINT,
                route=route_string,
                handler_id=handler_id,
                metadata={
                    'method': method,
                    'route': route,
                    'file': file_path
                }
            )
            entry_points.append(entry_point)
        
        return entry_points
    
    def _discover_graphql_resolver(self, file_path: str, resolver_data: dict[str, Any],
                                  symbol_index: dict[str, Symbol]) -> list[EntryPoint]:
        """
        Discover a GraphQL resolver.
        
        Returns:
            List of EntryPoint objects
        """
        entry_points = []
        
        # Get resolver information
        query_name = resolver_data.get('query', '')
        mutation_name = resolver_data.get('mutation', '')
        resolver_name = resolver_data.get('resolver', '')
        
        if not resolver_name:
            return entry_points
        
        # Determine the route
        if query_name:
            route = f"Query.{query_name}"
        elif mutation_name:
            route = f"Mutation.{mutation_name}"
        else:
            route = resolver_name
        
        # Find the resolver symbol
        resolver_id = self._find_handler_symbol(file_path, resolver_name, symbol_index)
        
        if resolver_id:
            entry_point = EntryPoint(
                kind=EntryPointKind.GRAPHQL_RESOLVER,
                route=route,
                handler_id=resolver_id,
                metadata={
                    'query': query_name,
                    'mutation': mutation_name,
                    'file': file_path
                }
            )
            entry_points.append(entry_point)
        
        return entry_points
    
    def _discover_rpc_handler(self, file_path: str, handler_data: dict[str, Any],
                             symbol_index: dict[str, Symbol]) -> list[EntryPoint]:
        """
        Discover an RPC handler.
        
        Returns:
            List of EntryPoint objects
        """
        entry_points = []
        
        # Get handler information
        service_name = handler_data.get('service', '')
        method_name = handler_data.get('method', '')
        handler_name = handler_data.get('handler', '')
        
        if not handler_name:
            return entry_points
        
        # Determine the route
        route = f"{service_name}.{method_name}" if service_name and method_name else handler_name
        
        # Find the handler symbol
        handler_id = self._find_handler_symbol(file_path, handler_name, symbol_index)
        
        if handler_id:
            entry_point = EntryPoint(
                kind=EntryPointKind.RPC_HANDLER,
                route=route,
                handler_id=handler_id,
                metadata={
                    'service': service_name,
                    'method': method_name,
                    'file': file_path
                }
            )
            entry_points.append(entry_point)
        
        return entry_points
    
    def _discover_cli_command(self, file_path: str, command_data: dict[str, Any],
                             symbol_index: dict[str, Symbol]) -> list[EntryPoint]:
        """
        Discover a CLI command.
        
        Returns:
            List of EntryPoint objects
        """
        entry_points = []
        
        # Get command information
        command_name = command_data.get('name', '')
        handler_name = command_data.get('handler', '')
        
        if not command_name or not handler_name:
            return entry_points
        
        # Find the handler symbol
        handler_id = self._find_handler_symbol(file_path, handler_name, symbol_index)
        
        if handler_id:
            entry_point = EntryPoint(
                kind=EntryPointKind.CLI_COMMAND,
                route=command_name,
                handler_id=handler_id,
                metadata={
                    'command': command_name,
                    'file': file_path
                }
            )
            entry_points.append(entry_point)
        
        return entry_points
    
    def _discover_scheduled_job(self, file_path: str, job_data: dict[str, Any],
                               symbol_index: dict[str, Symbol]) -> list[EntryPoint]:
        """
        Discover a scheduled job.
        
        Returns:
            List of EntryPoint objects
        """
        entry_points = []
        
        # Get job information
        job_name = job_data.get('name', '')
        cron_schedule = job_data.get('schedule', '')
        handler_name = job_data.get('handler', '')
        
        if not handler_name:
            return entry_points
        
        # Find the handler symbol
        handler_id = self._find_handler_symbol(file_path, handler_name, symbol_index)
        
        if handler_id:
            route = f"{job_name} ({cron_schedule})" if cron_schedule else job_name
            
            entry_point = EntryPoint(
                kind=EntryPointKind.SCHEDULED_JOB,
                route=route,
                handler_id=handler_id,
                metadata={
                    'job_name': job_name,
                    'schedule': cron_schedule,
                    'file': file_path
                }
            )
            entry_points.append(entry_point)
        
        return entry_points
    
    def _discover_worker_entry(self, file_path: str, worker_data: dict[str, Any],
                              symbol_index: dict[str, Symbol]) -> list[EntryPoint]:
        """
        Discover a worker entry point.
        
        Returns:
            List of EntryPoint objects
        """
        entry_points = []
        
        # Get worker information
        worker_name = worker_data.get('name', '')
        queue_name = worker_data.get('queue', '')
        handler_name = worker_data.get('handler', '')
        
        if not handler_name:
            return entry_points
        
        # Find the handler symbol
        handler_id = self._find_handler_symbol(file_path, handler_name, symbol_index)
        
        if handler_id:
            route = f"{worker_name} (queue: {queue_name})" if queue_name else worker_name
            
            entry_point = EntryPoint(
                kind=EntryPointKind.WORKER_ENTRY,
                route=route,
                handler_id=handler_id,
                metadata={
                    'worker_name': worker_name,
                    'queue': queue_name,
                    'file': file_path
                }
            )
            entry_points.append(entry_point)
        
        return entry_points
    
    def _find_handler_symbol(self, file_path: str, handler_name: str,
                            symbol_index: dict[str, Symbol]) -> str | None:
        """
        Find a handler symbol by name.
        
        This is a simplified implementation - in practice, this would need
        to handle various handler patterns and naming conventions.
        """
        # Try exact match on symbol name
        for symbol in symbol_index.values():
            if symbol.name == handler_name and symbol.kind.value in ["function", "method"]:
                return symbol.id
        
        # Try qualified name match (e.g., ClassName.method_name)
        for symbol in symbol_index.values():
            if symbol.name == handler_name:
                return symbol.id
        
        return None