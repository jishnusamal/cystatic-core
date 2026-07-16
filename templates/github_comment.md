# Engineering Discovery

## Summary

**Repository:** {{ repository }}
**Pull Request:** #{{ pr_number }}
**Language:** {{ language }}
{% if base_sha and head_sha %}
**Base:** {{ base_sha[:7] }}
**Head:** {{ head_sha[:7] }}
{% endif %}
**Analysis completed in {{ total_time }}s**

---

## Change Surface (What Changed?)

{% if change.added_symbols_count > 0 or change.removed_symbols_count > 0 or change.modified_symbols_count > 0 %}
| Metric | Count |
|--------|-------|
| Added Symbols | {{ change.added_symbols_count }} |
| Removed Symbols | {{ change.removed_symbols_count }} |
| Modified Symbols | {{ change.modified_symbols_count }} |
| Changed Imports | {{ change.changed_imports_count }} |
| Changed Endpoints | {{ change.changed_endpoints_count }} |

{% if change.added_symbols_count > 0 %}
### Added
{% for symbol in change.added_symbols %}
- `{{ symbol.name }}` ({{ symbol.type }}) in `{{ symbol.file_path }}`
{% endfor %}
{% endif %}

{% if change.removed_symbols_count > 0 %}
### Removed
{% for symbol in change.removed_symbols %}
- `{{ symbol.name }}` ({{ symbol.type }}) in `{{ symbol.file_path }}`
{% endfor %}
{% endif %}

{% if change.modified_symbols_count > 0 %}
### Modified
{% for modified in change.modified_symbols %}
- `{{ modified.symbol.name }}` ({{ modified.symbol.type }}) in `{{ modified.symbol.file_path }}`
  - Changes: {{ modified.changes | map(attribute='type') | join(', ') }}
{% endfor %}
{% endif %}
{% else %}
No code changes detected.
{% endif %}

---

{% if execution is defined and execution.behaviors_count > 0 %}
## Execution Surface (What Executes?)

**Affected Behaviors:** {{ execution.behaviors_count }}
**Execution Depth:** {{ execution.execution_depth }}
**Execution Units:** {{ execution.execution_units_count }}
**Execution Chains:** {{ execution.execution_chains_count }}

### Entry Points
{% if execution.entry_points_count > 0 %}
{% for ep in execution.entry_points %}
- **{{ ep.kind }}**: {{ ep.route }} ({{ ep.behavior_id }})
{% endfor %}
{% else %}
No entry points identified.
{% endif %}

### Terminal Points
{% if execution.terminal_points_count > 0 %}
{% for tp in execution.terminal_points %}
- **{{ tp.kind }}**: {{ tp.symbol_id.split('#')[-1] if '#' in tp.symbol_id else tp.symbol_id }}
{% endfor %}
{% else %}
No terminal points identified.
{% endif %}

### Shared Executions
{% if execution.shared_executions_count > 0 %}
{% for se in execution.shared_executions %}
- **{{ se.symbol_id.split('#')[-1] if '#' in se.symbol_id else se.symbol_id }}**: used by {{ se.used_by_count }} behaviors
{% endfor %}
{% else %}
No shared executions identified.
{% endif %}

### Affected Behaviors
{% for b in execution.behaviors %}
- **{{ b.name }}** ({{ b.type }})
  - Entry Point: {{ b.entry_point }}
  - Changed Symbols: {{ b.changed_symbols_count }}
{% endfor %}
{% else %}
## Execution Surface

No affected behaviors identified.

{% endif %}

---

{% if dependency is defined %}
## Dependency Surface (Who Depends on This?)

Dependency changes detected.

| Metric | Value |
|--------|-------|
| Dependency Depth | {{ dependency.dependency_depth if dependency.dependency_depth is defined else 'N/A' }} |
{% if dependency.fan_in is defined %}
| Max Fan-In | {{ dependency.fan_in.values() | max if dependency.fan_in else 0 }} |
{% endif %}
{% if dependency.fan_out is defined %}
| Max Fan-Out | {{ dependency.fan_out.values() | max if dependency.fan_out else 0 }} |
{% endif %}
{% endif %}

{% if data is defined %}
## Data Surface (What Data Changes?)

Data model changes detected.
{% endif %}

{% if event is defined %}
## Event Surface (What Async Behavior Changes?)

Event changes detected.
{% endif %}

{% if api is defined %}
## API Surface (What Interfaces Change?)

API changes detected.
{% endif %}

{% if validation is defined %}
## Validation Surface (What Validates the Change?)

Validation changes detected.
{% endif %}

---

*This is a deterministic analysis produced by the Engineering Discovery Compiler. All evidence is directly traceable to the repository source code.*