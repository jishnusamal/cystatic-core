"""Java persistence extractor - detects JPA/Hibernate entities and Spring Data repositories."""

import re
from typing import Any

from engine.language.base import BaseExtractor


class JavaPersistenceExtractor(BaseExtractor):
    """
    Extracts ORM/ODM persistence constructs from Java source files.

    Recognizes:
    - JPA entities (@Entity)
    - Hibernate entities
    - Spring Data JPA repositories
    - Table/column mappings (@Table, @Column)
    - Relationships (@OneToMany, @ManyToOne, etc.)

    Produces a list of dicts with keys: type, symbol_id, name, table_name,
    framework, fields, relationships.
    """

    def extract(self, tree: list[str], file_path: str) -> list[dict[str, Any]]:
        """
        Extract persistence constructs from a Java source file.

        Args:
            tree: List of lines from the source file
            file_path: Path to the source file

        Returns:
            List of persistence construct dicts
        """
        constructs = []
        content = "\n".join(tree)

        # Detect if this is a JPA entity
        if "@Entity" in content:
            model = self._extract_entity(tree, content, file_path)
            if model:
                constructs.append(model)

        # Detect if this is a Spring Data repository interface
        if re.search(r"(?:extends\s+\w*Repository|@Repository)", content):
            constructs.extend(self._extract_repositories(content, file_path))

        return constructs

    def _extract_entity(
        self, lines: list[str], content: str, file_path: str
    ) -> dict[str, Any] | None:
        """Extract a JPA entity class."""
        class_match = re.search(r"(?:public\s+)?class\s+(\w+)", content)
        if not class_match:
            return None

        class_name = class_match.group(1)
        symbol_id = f"java://{file_path}#{class_name}"

        # Extract @Table name
        table_name = ""
        table_match = re.search(r'@Table\s*\(\s*name\s*=\s*"([^"]+)"', content)
        if table_match:
            table_name = table_match.group(1)

        # Extract fields and relationships
        fields = []
        relationships = []

        # Find class body
        brace_depth = 0
        in_class = False

        for i, line in enumerate(lines):
            line_stripped = line.strip()

            # Skip annotations and field declarations outside class body
            if not in_class:
                if "{" in line:
                    brace_depth += line.count("{")
                    in_class = True
                continue

            brace_depth += line.count("{") - line.count("}")
            if brace_depth <= 0:
                break

            # Check for @Column or @JoinColumn annotations
            is_join = any(
                ann in line_stripped
                for ann in [
                    "@OneToOne",
                    "@OneToMany",
                    "@ManyToOne",
                    "@ManyToMany",
                    "@JoinColumn",
                ]
            )

            # Extract field declaration
            field_match = re.search(
                r"(?:private|public|protected)?\s*(\w+(?:<[^>]+>)?)\s+(\w+)\s*;",
                line_stripped,
            )
            if field_match:
                field_type = field_match.group(1)
                field_name = field_match.group(2)

                if field_type.lower() in (
                    "int",
                    "long",
                    "double",
                    "float",
                    "boolean",
                    "string",
                    "byte",
                    "short",
                    "char",
                    "void",
                ):
                    continue

                column_name = field_name
                column_match = re.search(r'@Column\s*\(\s*name\s*=\s*"([^"]+)"', line)
                if column_match:
                    column_name = column_match.group(1)

                if is_join:
                    relationships.append(
                        {
                            "name": field_name,
                            "field_type": field_type,
                            "is_relationship": True,
                            "related_model": field_type,
                            "nullable": False,
                            "unique": False,
                            "index": False,
                        }
                    )
                else:
                    fields.append(
                        {
                            "name": field_name,
                            "field_type": field_type,
                            "is_relationship": False,
                            "column_name": column_name,
                            "nullable": "nullable" in line_stripped.lower(),
                            "unique": "unique" in line_stripped.lower(),
                        }
                    )

        return {
            "type": "persistence_model",
            "symbol_id": symbol_id,
            "name": class_name,
            "table_name": table_name,
            "framework": "jpa",
            "fields": fields,
            "relationships": relationships,
        }

    def _extract_repositories(
        self, content: str, file_path: str
    ) -> list[dict[str, Any]]:
        """Extract Spring Data JPA repository interfaces."""
        repositories = []

        repo_pattern = (
            r"(?:public\s+)?interface\s+(\w+)\s+extends\s+(\w*(?:Repository|CrudRepository|JpaRepository|MongoRepository|PagingAndSortingRepository))"
            r"(?:<(\w+)"
        )  # Entity type

        for match in re.finditer(repo_pattern, content):
            interface_name = match.group(1)
            repo_type = match.group(2)
            entity_type = match.group(3) if match.lastindex is not None and match.lastindex >= 3 else ""

            symbol_id = f"java://{file_path}#{interface_name}"

            repositories.append(
                {
                    "type": "repository_interface",
                    "symbol_id": symbol_id,
                    "name": interface_name,
                    "framework": "spring_data",
                    "repository_type": repo_type,
                    "entity_type": entity_type,
                }
            )

        return repositories
