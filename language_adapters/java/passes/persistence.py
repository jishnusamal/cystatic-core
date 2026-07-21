"""Java persistence index pass - detects JPA/Hibernate entities and Spring Data repositories.

Emits only structural persistence facts. No resolution, no graph construction.
"""

import re
from typing import Any

from language_adapters.base.file_context import FileContext
from language_adapters.base.passes import BaseIndexPass
from language_adapters.model.repository_index import PersistenceEntry


class JavaPersistenceIndexPass(BaseIndexPass):
    """Index pass that extracts persistence facts from Java source.

    Extracts: JPA entities, table mappings, fields, relationships, Spring Data repositories.
    No semantic interpretation - just structural persistence discovery.
    """

    def process(self, context: FileContext, builder: dict[str, Any]) -> None:
        """Extract persistence constructs from a Java file context."""
        lines = context.ast
        file_path = context.path
        content = '\n'.join(lines)

        # Detect if this is a JPA entity
        if '@Entity' in content:
            model = self._extract_entity(lines, content, file_path)
            if model:
                builder["persistence_models"].append(model)

        # Detect if this is a Spring Data repository interface
        if re.search(r'(?:extends\s+\w*Repository|@Repository)', content):
            for repo in self._extract_repositories(content, file_path):
                repo_entry = PersistenceEntry(
                    name=repo['name'],
                    kind="repository_interface",
                    table_name="",
                    framework="spring_data",
                    file=file_path,
                    line=0,
                    metadata={
                        'repository_type': repo.get('repository_type', ''),
                        'entity_type': repo.get('entity_type', ''),
                    },
                )
                builder["persistence_models"].append(repo_entry)

    def _extract_entity(
        self,
        lines: list[str],
        content: str,
        file_path: str,
    ) -> PersistenceEntry | None:
        """Extract a JPA entity class."""
        class_match = re.search(r'(?:public\s+)?class\s+(\w+)', content)
        if not class_match:
            return None

        class_name = class_match.group(1)

        # Extract @Table name
        table_name = ''
        table_match = re.search(r'@Table\s*\(\s*name\s*=\s*"([^"]+)"', content)
        if table_match:
            table_name = table_match.group(1)

        # Extract fields and relationships
        fields: list[dict[str, Any]] = []
        relationships: list[dict[str, Any]] = []

        class_start = class_match.start()
        brace_depth = 0
        in_class = False

        for i, line in enumerate(lines):
            line_stripped = line.strip()

            if not in_class:
                if '{' in line:
                    brace_depth += line.count('{')
                    in_class = True
                continue

            brace_depth += line.count('{') - line.count('}')
            if brace_depth <= 0:
                break

            is_join = any(ann in line_stripped for ann in
                         ['@OneToOne', '@OneToMany', '@ManyToOne', '@ManyToMany', '@JoinColumn'])

            field_match = re.search(
                r'(?:private|public|protected)?\s*(\w+(?:<[^>]+>)?)\s+(\w+)\s*;',
                line_stripped,
            )
            if field_match:
                field_type = field_match.group(1)
                field_name = field_match.group(2)

                if field_type.lower() in (
                    'int', 'long', 'double', 'float', 'boolean',
                    'string', 'byte', 'short', 'char', 'void',
                ):
                    continue

                column_name = field_name
                column_match = re.search(r'@Column\s*\(\s*name\s*=\s*"([^"]+)"', line)
                if column_match:
                    column_name = column_match.group(1)

                if is_join:
                    relationships.append({
                        'name': field_name,
                        'field_type': field_type,
                        'related_model': field_type,
                    })
                else:
                    fields.append({
                        'name': field_name,
                        'field_type': field_type,
                        'column_name': column_name,
                    })

        # Determine line from class match
        line = content[:class_start].count('\n') + 1

        return PersistenceEntry(
            name=class_name,
            kind="table",
            table_name=table_name or class_name.lower(),
            framework="jpa",
            file=file_path,
            line=line,
            fields=tuple(fields),
            relationships=tuple(relationships),
        )

    def _extract_repositories(self, content: str, file_path: str) -> list[dict[str, Any]]:
        """Extract Spring Data JPA repository interfaces."""
        repositories = []

        repo_pattern = (
            r'(?:public\s+)?interface\s+(\w+)\s+extends\s+'
            r'(\w*(?:Repository|CrudRepository|JpaRepository|MongoRepository|PagingAndSortingRepository))'
            r'(?:<(\w+))?'
        )

        for match in re.finditer(repo_pattern, content):
            interface_name = match.group(1)
            repo_type = match.group(2)
            entity_type = match.group(3) if match.lastindex and match.lastindex >= 3 else ''

            repositories.append({
                'name': interface_name,
                'repository_type': repo_type,
                'entity_type': entity_type,
            })

        return repositories