# Cystatic Analysis

## Summary

**Repository:** {{ repository }}
**Pull Request:** #{{ pr_number }}
**Language:** {{ language }}
{% if base_sha and head_sha %}
**Base:** {{ base_sha[:7] }}
**Head:** {{ head_sha[:7] }}
{% endif %}

{% if change.added_symbols_count > 0 or change.removed_symbols_count > 0 or change.modified_symbols_count > 0 %}
## Change Overview

{% if change.added_symbols_count > 0 %}
### Added Symbols ({{ change.added_symbols_count }})
{% for symbol in change.added_symbols %}
- `{{ symbol.name }}` ({{ symbol.type }}) in `{{ symbol.file_path }}`
{% endfor %}
{% endif %}

{% if change.removed_symbols_count > 0 %}
### Removed Symbols ({{ change.removed_symbols_count }})
{% for symbol in change.removed_symbols %}
- `{{ symbol.name }}` ({{ symbol.type }}) in `{{ symbol.file_path }}`
{% endfor %}
{% endif %}

{% if change.modified_symbols_count > 0 %}
### Modified Symbols ({{ change.modified_symbols_count }})
{% for modified in change.modified_symbols %}
- `{{ modified.symbol.name }}` ({{ modified.symbol.type }}) in `{{ modified.symbol.file_path }}`
  - Changes: {{ modified.changes | map(attribute='type') | join(', ') }}
{% endfor %}
{% endif %}

{% if change.changed_imports_count > 0 %}
### Changed Imports ({{ change.changed_imports_count }})
{% for imp in change.changed_imports %}
- `{{ imp.file }}`: {{ imp.change_type }}
{% endfor %}
{% endif %}

{% if change.changed_endpoints_count > 0 %}
### Changed Endpoints ({{ change.changed_endpoints_count }})
{% for ep in change.changed_endpoints %}
- `{{ ep.symbol_id }}`: {{ ep.change_type }} ({{ ep.old_method }} → {{ ep.new_method }})
{% endfor %}
{% endif %}
{% else %}
## Change Overview

No code changes detected.
{% endif %}

{% if behavior.behaviors_count > 0 %}
## Execution Surface

**Affected Behaviors:** {{ behavior.behaviors_count }}

{% for b in behavior.behaviors %}
### {{ b.name }}
- **Type:** {{ b.type }}
- **Symbols:** {{ b.symbols | length }}
{% endfor %}

{% if behavior.execution_graphs_count > 0 %}
### Execution Graphs
{% for graph in behavior.execution_graphs %}
- **{{ graph.name }}**: {{ graph.nodes_count }} nodes, {{ graph.edges_count }} edges
{% endfor %}
{% endif %}
{% endif %}

{% if dependency is defined %}
## Dependency Surface

Dependency changes detected. See JSON output for details.
{% endif %}

{% if data is defined %}
## Data Surface

Data model changes detected. See JSON output for details.
{% endif %}

{% if event is defined %}
## Events

Event changes detected. See JSON output for details.
{% endif %}

{% if api is defined %}
## APIs

API changes detected. See JSON output for details.
{% endif %}

{% if validation is defined %}
## Validation

Validation changes detected. See JSON output for details.
{% endif %}

{% if metrics is defined %}
## Metrics

Discovery metrics available. See JSON output for details.
{% endif %}

---

*Analysis completed in {{ total_time }}s*