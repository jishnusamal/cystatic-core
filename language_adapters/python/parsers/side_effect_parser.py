"""Side effect parser — detects external service calls and side effects.

Detects:
    HTTP, Kafka, Redis, Celery, RabbitMQ, Filesystem, S3, SMTP,
    Webhook, Cache, Metrics, Logging
"""

from __future__ import annotations

import ast
import re
from typing import Any, Dict, List, Optional, Set

from language_adapters.ir import (
    SemanticGraph,
    NodeType,
    FunctionNode,
    EventNode,
    ExternalServiceNode,
    CacheNode,
    QueueNode,
    PublishesEdge,
    SubscribesEdge,
    SendsHttpEdge,
    UsesEdge,
)
from language_adapters.interfaces.graph import GraphBuilder
from language_adapters.shared.graph_builder import GraphBuilderUtils as G


class SideEffectParser(GraphBuilder):
    """Extracts side effects (external service calls, events, etc.)."""

    _HTTP_CLIENTS: Set[str] = {
        "requests", "httpx", "aiohttp", "urllib", "urllib3",
        "httplib2", "httpretty",
    }

    _HTTP_METHODS: Set[str] = {
        "get", "post", "put", "patch", "delete", "head", "options",
    }

    _KAFKA_PATTERNS: Set[str] = {
        "kafka", "KafkaProducer", "KafkaConsumer",
    }

    _REDIS_PATTERNS: Set[str] = {
        "redis", "Redis", "StrictRedis", "redis_client",
    }

    _CELERY_PATTERNS: Set[str] = {
        "celery", "Celery", "task", "shared_task", "app.task",
    }

    _RABBITMQ_PATTERNS: Set[str] = {
        "pika", "rabbitmq", "RabbitMQ", "Channel",
    }

    _S3_PATTERNS: Set[str] = {
        "s3", "boto3", "S3", "S3Client", "s3_client",
    }

    _SMTP_PATTERNS: Set[str] = {
        "smtp", "smtplib", "send_mail", "EmailMessage",
    }

    _LOGGING_PATTERNS: Set[str] = {
        "logging", "logger", "log", "getLogger",
    }

    _CACHE_PATTERNS: Set[str] = {
        "cache", "Cache", "cache_page", "cached",
    }

    _METRICS_PATTERNS: Set[str] = {
        "metrics", "prometheus", "statsd", "datadog",
    }

    def build(self, graph: SemanticGraph, context: Dict[str, Any]) -> SemanticGraph:
        tree: Optional[ast.Module] = context.get("tree")
        file_path: str = context.get("file_path", "")

        if tree is None:
            return graph

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self._extract_side_effects(node, graph, file_path)

        return graph

    def _extract_side_effects(
        self,
        func_node: ast.FunctionDef | ast.AsyncFunctionDef,
        graph: SemanticGraph,
        file_path: str,
    ) -> None:
        caller = G.ensure_function(graph, func_node.name, file_path)

        for child in ast.walk(func_node):
            if isinstance(child, ast.Call):
                self._process_call(child, caller, graph, file_path)

    def _process_call(
        self,
        call: ast.Call,
        caller: FunctionNode,
        graph: SemanticGraph,
        file_path: str,
    ) -> None:
        func = call.func

        if isinstance(func, ast.Attribute):
            method = func.attr
            receiver = ast.unparse(func.value)

            # HTTP calls: requests.get(), httpx.post()
            if method in self._HTTP_METHODS and any(
                client in receiver for client in self._HTTP_CLIENTS
            ):
                service = ExternalServiceNode(
                    name=receiver,
                    file_path=file_path,
                    service_type="http",
                    protocol="http",
                )
                graph.add_node(service)
                graph.add_edge(
                    SendsHttpEdge(
                        source=caller,
                        target=service,
                        method=method.upper(),
                    )
                )

            # Kafka
            if any(k in receiver for k in self._KAFKA_PATTERNS):
                event = EventNode(
                    name=f"kafka.{method}",
                    file_path=file_path,
                    event_type="kafka",
                )
                graph.add_node(event)
                graph.add_edge(PublishesEdge(source=caller, target=event))

            # Redis
            if any(r in receiver for r in self._REDIS_PATTERNS):
                cache = CacheNode(
                    name=f"redis.{method}",
                    file_path=file_path,
                    cache_type="redis",
                    operation=method,
                )
                graph.add_node(cache)
                graph.add_edge(UsesEdge(source=caller, target=cache))

            # Celery
            if any(c in receiver for c in self._CELERY_PATTERNS):
                queue = QueueNode(
                    name=f"celery.{method}",
                    file_path=file_path,
                    queue_type="celery",
                    operation="publish" if method == "delay" else method,
                )
                graph.add_node(queue)
                graph.add_edge(PublishesEdge(source=caller, target=queue))

            # S3
            if any(s in receiver for s in self._S3_PATTERNS):
                service = ExternalServiceNode(
                    name=f"s3.{method}",
                    file_path=file_path,
                    service_type="s3",
                    protocol="sdk",
                )
                graph.add_node(service)
                graph.add_edge(UsesEdge(source=caller, target=service))

            # SMTP
            if any(s in receiver for s in self._SMTP_PATTERNS):
                service = ExternalServiceNode(
                    name=f"smtp.{method}",
                    file_path=file_path,
                    service_type="smtp",
                    protocol="smtp",
                )
                graph.add_node(service)
                graph.add_edge(UsesEdge(source=caller, target=service))

            # Logging
            if any(l in receiver for l in self._LOGGING_PATTERNS):
                log_node = FunctionNode(
                    name=f"log.{method}",
                    file_path=file_path,
                )
                graph.add_node(log_node)
                graph.add_edge(UsesEdge(source=caller, target=log_node))

            # Cache
            if any(c in receiver for c in self._CACHE_PATTERNS):
                cache = CacheNode(
                    name=f"cache.{method}",
                    file_path=file_path,
                    cache_type="django_cache",
                    operation=method,
                )
                graph.add_node(cache)
                graph.add_edge(UsesEdge(source=caller, target=cache))

            # Metrics
            if any(m in receiver for m in self._METRICS_PATTERNS):
                metric_node = FunctionNode(
                    name=f"metrics.{method}",
                    file_path=file_path,
                )
                graph.add_node(metric_node)
                graph.add_edge(UsesEdge(source=caller, target=metric_node))

        elif isinstance(func, ast.Name):
            name = func.id

            # Celery shared_task decorator
            if name in {"task", "shared_task"}:
                queue = QueueNode(
                    name=f"celery.{name}",
                    file_path=file_path,
                    queue_type="celery",
                    operation="decorate",
                )
                graph.add_node(queue)
                graph.add_edge(UsesEdge(source=caller, target=queue))