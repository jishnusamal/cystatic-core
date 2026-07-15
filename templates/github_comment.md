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
{% else %}
## Change Overview

No code changes detected.
{% endif %}

{% if execution is defined and execution.behaviors_count > 0 %}
## Execution Surface

**Affected Behaviors:** {{ execution.behaviors_count }}
**Execution Depth:** {{ execution.execution_depth }}

{% for b in execution.behaviors %}
### {{ b.name }}
- **Type:** {{ b.type }}
- **Entry Point:** {{ b.entry_point }}
- **Changed Symbols:** {{ b.changed_symbols_count }}
{% endfor %}

{% if execution.entry_points_count > 0 %}
### Entry Points
{% for ep in execution.entry_points %}
- **{{ ep.kind }}**: {{ ep.route }}
{% endfor %}
{% endif %}

{% if execution.terminal_points_count > 0 %}
### Terminal Points
{% for tp in execution.terminal_points %}
- **{{ tp.kind }}**: {{ tp.symbol_id.split('#')[-1] if '#' in tp.symbol_id else tp.symbol_id }}
{% endfor %}
{% endif %}

{% if execution.shared_executions_count > 0 %}
### Shared Executions
{% for se in execution.shared_executions %}
- **{{ se.symbol_id.split('#')[-1] if '#' in se.symbol_id else se.symbol_id }}**: used by {{ se.used_by_count }} behaviors
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
