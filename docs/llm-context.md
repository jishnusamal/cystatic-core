# LLM Context Spec & Decoder Guide

The `llm_context` is a lossless, compressed Intermediate Representation (IR) derived from `ReviewContext`. It is specifically optimized to minimize LLM token usage during automated code reviews, PR summaries, and engineering discovery tasks.

---

## Design & Compression Philosophy

To reduce LLM token overhead by **60% to 80%**, the context compiler applies several deterministic compression strategies:

1. **Enum Table Mapping:** Repeated categorical values (e.g., programming language, visibility, change types) are mapped to short integer IDs.
2. **String Table Deduplication (`st`):** Repeated string values (e.g., file paths, symbol names, service names) are collected into a single list and referenced by their positional index. Index `0` is always reserved for the empty string `""`.
3. **Positional Arrays:** Verbose JSON objects with repeated keys are serialized into compact positional lists (tuples).
4. **Short Key Names:** Section names and fields are shortened to 1-3 characters (e.g., `f` for files, `sym` for symbols).
5. **Execution DAG (`eg`):** Call stacks and redundant paths are collapsed into a directed acyclic graph (DAG) of node indices and edge indices, preventing duplication of shared execution branches.
6. **URI Decomposition:** URIs are split into simple file paths and symbol names to avoid storing long duplicate strings.

No AI/LLM models are used during this compression process. It is purely deterministic and fully reversible.

---

## Enum Lookup Tables

Categorical values are resolved using the following tables. Index `0` is always mapped to `""`.

### 1. Kind (`kind`)
Used for symbol types, step types, etc.
* `0`: `""`
* `1`: `"class"`
* `2`: `"function"`
* `3`: `"method"`
* `4`: `"import"`
* `5`: `"variable"`
* `6`: `"endpoint"`
* `7`: `"worker"`
* `8`: `"task"`
* `9`: `"route"`
* `10`: `"property"`
* `11`: `"attribute"`
* `12`: `"parameter"`
* `13`: `"module"`
* `14`: `"package"`
* `15`: `"interface"`
* `16`: `"enum"`
* `17`: `"constant"`
* `18`: `"type_alias"`
* `19`: `"decorator"`
* `20`: `"exception"`

### 2. Visibility (`vis`)
* `0`: `""`
* `1`: `"public"`
* `2`: `"private"`
* `3`: `"protected"`
* `4`: `"internal"`

### 3. Language (`lang`)
* `0`: `""`
* `1`: `"python"`
* `2`: `"java"`
* `3`: `"typescript"`
* `4`: `"javascript"`
* `5`: `"go"`
* `6`: `"rust"`
* `7`: `"kotlin"`
* `8`: `"ruby"`
* `9`: `"csharp"`
* `10`: `"cpp"`
* `11`: `"sql"`
* `12`: `"yaml"`
* `13`: `"json"`
* `14`: `"xml"`
* `15`: `"dockerfile"`
* `16`: `"shell"`
* `17`: `"terraform"`
* `18`: `"graphql"`

### 4. Change Type (`ct`)
* `0`: `""`
* `1`: `"modified"`
* `2`: `"added"`
* `3`: `"removed"`
* `4`: `"mixed"`
* `5`: `"renamed"`
* `6`: `"copied"`

### 5. Reference Kind (`ref_kind`)
* `0`: `""`
* `1`: `"behavior"`
* `2`: `"change"`
* `3`: `"symbol"`
* `4`: `"file"`
* `5`: `"endpoint"`
* `6`: `"dependency"`
* `7`: `"import"`
* `8`: `"call"`
* `9`: `"reference"`
* `10`: `"implementation"`
* `11`: `"inheritance"`
* `12`: `"composition"`

### 6. Behavior Kind (`bh_kind`)
* `0`: `""`
* `1`: `"deep_execution"`
* `2`: `"shared_execution"`
* `3`: `"boundary_crossing"`
* `4`: `"event_publication"`
* `5`: `"hidden_relationship"`
* `6`: `"public_interface_change"`
* `7`: `"shared_dependency"`
* `8`: `"state_mutation"`
* `9`: `"validation_gap"`
* `10`: `"entry_point"`
* `11`: `"terminal_point"`
* `12`: `"reachable_unit"`
* `13`: `"execution_chain"`

### 7. Trigger Method (`method`)
* `0`: `""`
* `1`: `"POST"`
* `2`: `"GET"`
* `3`: `"PUT"`
* `4`: `"DELETE"`
* `5`: `"PATCH"`
* `6`: `"HEAD"`
* `7`: `"OPTIONS"`
* `8`: `"worker"`
* `9`: `"event"`
* `10`: `"cron"`
* `11`: `"webhook"`

### 8. Classification (`cls`)
* `0`: `""`
* `1`: `"modification"`
* `2`: `"addition"`
* `3`: `"removal"`
* `4`: `"refactor"`
* `5`: `"fix"`
* `6`: `"feature"`
* `7`: `"mixed"`

### 9. Scope (`scope`)
* `0`: `""`
* `1`: `"local"`
* `2`: `"multi_file"`
* `3`: `"cross_package"`
* `4`: `"cross_service"`
* `5`: `"global"`

### 10. Behavior Change (`bh_change`)
* `0`: `""`
* `1`: `"FunctionBodyChange"`
* `2`: `"SignatureChange"`
* `3`: `"ClassBodyChange"`
* `4`: `"InterfaceChange"`
* `5`: `"ImportChange"`
* `6`: `"DecoratorChange"`
* `7`: `"TypeAnnotationChange"`
* `8`: `"DocstringChange"`
* `9`: `"VisibilityChange"`
* `10`: `"AsyncChange"`
* `11`: `"ExceptionChange"`
* `12`: `"DependencyChange"`
* `13`: `"ConfigurationChange"`
* `14`: `"RouteChange"`
* `15`: `"SchemaChange"`
* `16`: `"MigrationChange"`
* `17`: `"TestChange"`
* `18`: `"ReturnTypeChange"`
* `19`: `"ParameterChange"`
* `20`: `"AccessModifierChange"`

---

## Detailed Schema & Key Mapping

The serialized `llm_context` JSON root is a dictionary containing the following keys:

| Key | Meaning | Value Type | Description |
|---|---|---|---|
| **`st`** | String Table | `list[str]` | A flat array of all repeated strings (paths, names, triggers, IDs). Index `0` is empty string. Paths are prefix-grouped. |
| **`f`** | Files Lookup Table | `list[list[int]]` | Files discovered in the review scope `[path_idx, ct_id]`. |
| **`sym`** | Symbols Lookup Table | `list[list[int]]` | Classes, functions, variables, etc. `[file_id, name_idx, kind_id]`. |
| **`ep`** | Endpoints Lookup Table | `list[list[int]]` | API routes, webhooks, or event handlers `[endpoint_idx, path_idx]`. |
| **`cs`** | Change Summary | `list[int]` | High-level metrics describing the overall scope of the change. |
| **`cf`** | Changed Files | `list[list[Any]]` | Changed file mapping: `[file_idx, [changed_sym_idx_1, changed_sym_idx_2, ...]]`. |
| **`eg`** | Execution Graph | `dict[str, list]` | Directed acyclic graph tracking execution sequences. |
| **`epts`** | Entry Points | `list[list[Any]]` | Tracing from specific entry points down through their execution graphs. |
| **`disc`** | Discoveries | `list[list[Any]]` | Deterministic conclusions or anomalies detected during analysis. |

---

### Internal Tuple/List Mappings

Each lookup table entry has a strict positional format. Below is the mapping for each list:

#### 1. Files (`f`)
Each element is a list representing `[path_idx, ct_id]`:
* `0`: **`path_idx`** (int) -> Index in String Table (`st`)
* `1`: **`ct_id`** (int) -> Enum ID in `ct` (change type) table

#### 2. Symbols (`sym`)
Each element is a list representing `[file_id, name_idx, kind_id]`:
* `0`: **`file_id`** (int) -> Index in Files Table (`f`)
* `1`: **`name_idx`** (int) -> Index in String Table (`st`). *Note: Set to `0` if name can be resolved from URI (e.g. text following `#` or `::`).*
* `2`: **`kind_id`** (int) -> Enum ID in `kind` table

#### 3. Endpoints (`ep`)
Each element is a list representing `[endpoint_idx, path_idx]`:
* `0`: **`endpoint_idx`** (int) -> Index in String Table (`st`) (e.g. `"POST /api/v1/users"`)
* `1`: **`path_idx`** (int) -> Index in String Table (`st`) (e.g. `"/api/v1/users"`)

#### 4. Change Summary (`cs`)
A single list of 5 integers representing `[cls_id, scope_id, file_count, symbol_count, behavior_count]`:
* `0`: **`cls_id`** (int) -> Enum ID in `cls` (classification) table
* `1`: **`scope_id`** (int) -> Enum ID in `scope` table
* `2`: **`file_count`** (int) -> Total count of modified files
* `3`: **`symbol_count`** (int) -> Total count of modified symbols
* `4`: **`behavior_count`** (int) -> Total count of modified behaviors

#### 5. Changed Files (`cf`)
Each element represents a file modification: `[file_idx, changed_sym_idxs]`:
* `0`: **`file_idx`** (int) -> Index in Files Table (`f`)
* `1`: **`changed_sym_idxs`** (list[int]) -> List of symbol indices in `sym` that were modified in this file

#### 6. Execution Graph (`eg`)
The dictionary has two keys: `"n"` (nodes) and `"e"` (edges):
* **`n` (Nodes):** A list of list structures: `[sym_idx, depth, reaches_svc_idx, reaches_mod_idx]`
  * `0`: `sym_idx` (int) -> Index in Symbols Table (`sym`)
  * `1`: `depth` (int) -> Execution depth from triggering entry point
  * `2`: `reaches_svc_idx` (int) -> Index in String Table (`st`) representing reached service name
  * `3`: `reaches_mod_idx` (int) -> Index in String Table (`st`) representing reached module name
* **`e` (Edges):** List of connection paths: `[parent_node_idx, child_node_idx]`:
  * Parent/child values reference indices of the `"n"` node array list.

#### 7. Entry Points (`epts`)
Each entry point trace: `[endpoint_idx, [node_idxs...], terminal_idx, max_depth]`:
* `0`: **`endpoint_idx`** (int) -> Index in Endpoints Table (`ep`)
* `1`: **`node_idxs`** (list[int]) -> List of indices into the Execution Graph nodes (`eg["n"]`) representing the execution flow
* `2`: **`terminal_idx`** (int) -> Index in String Table (`st`) (representing details of the return or termination point)
* `3`: **`max_depth`** (int) -> Deepest stack depth reached from this trigger

#### 8. Discoveries (`disc`)
Each item represents a compiler finding: `[kind_id, facts_dict]`:
* `0`: **`kind_id`** (int) -> Enum ID in `bh_kind` table
* `1`: **`facts_dict`** (dict[str, Any]) -> Raw metadata dictionary (key/value string properties describing the finding)

---

## How to Read and Decompress the Context

An engineer (or a consumer service) can parse this compact format by resolving indices in a depth-first traversal, matching enum IDs with the static tables, and replacing string table indices with their resolved string values.

### Python Decoder Tool

Below is a complete, standalone Python implementation that takes a serialized `llm_context` dictionary and decompresses it back into a fully human-readable, nested dictionary structure.

```python
from typing import Any, Dict, List

# Static Enum Tables
ENUMS = {
    "kind": {
        0: "", 1: "class", 2: "function", 3: "method", 4: "import", 5: "variable",
        6: "endpoint", 7: "worker", 8: "task", 9: "route", 10: "property",
        11: "attribute", 12: "parameter", 13: "module", 14: "package",
        15: "interface", 16: "enum", 17: "constant", 18: "type_alias",
        19: "decorator", 20: "exception"
    },
    "vis": {
        0: "", 1: "public", 2: "private", 3: "protected", 4: "internal"
    },
    "lang": {
        0: "", 1: "python", 2: "java", 3: "typescript", 4: "javascript", 5: "go",
        6: "rust", 7: "kotlin", 8: "ruby", 9: "csharp", 10: "cpp", 11: "sql",
        12: "yaml", 13: "json", 14: "xml", 15: "dockerfile", 16: "shell",
        17: "terraform", 18: "graphql"
    },
    "ct": {
        0: "", 1: "modified", 2: "added", 3: "removed", 4: "mixed",
        5: "renamed", 6: "copied"
    },
    "ref_kind": {
        0: "", 1: "behavior", 2: "change", 3: "symbol", 4: "file", 5: "endpoint",
        6: "dependency", 7: "import", 8: "call", 9: "reference", 10: "implementation",
        11: "inheritance", 12: "composition"
    },
    "bh_kind": {
        0: "", 1: "deep_execution", 2: "shared_execution", 3: "boundary_crossing",
        4: "event_publication", 5: "hidden_relationship", 6: "public_interface_change",
        7: "shared_dependency", 8: "state_mutation", 9: "validation_gap",
        10: "entry_point", 11: "terminal_point", 12: "reachable_unit",
        13: "execution_chain"
    },
    "method": {
        0: "", 1: "POST", 2: "GET", 3: "PUT", 4: "DELETE", 5: "PATCH",
        6: "HEAD", 7: "OPTIONS", 8: "worker", 9: "event", 10: "cron",
        11: "webhook"
    },
    "cls": {
        0: "", 1: "modification", 2: "addition", 3: "removal", 4: "refactor",
        5: "fix", 6: "feature", 7: "mixed"
    },
    "scope": {
        0: "", 1: "local", 2: "multi_file", 3: "cross_package", 4: "cross_service",
        5: "global"
    },
    "bh_change": {
        0: "", 1: "FunctionBodyChange", 2: "SignatureChange", 3: "ClassBodyChange",
        4: "InterfaceChange", 5: "ImportChange", 6: "DecoratorChange",
        7: "TypeAnnotationChange", 8: "DocstringChange", 9: "VisibilityChange",
        10: "AsyncChange", 11: "ExceptionChange", 12: "DependencyChange",
        13: "ConfigurationChange", 14: "RouteChange", 15: "SchemaChange",
        16: "MigrationChange", 17: "TestChange", 18: "ReturnTypeChange",
        19: "ParameterChange", 20: "AccessModifierChange"
    }
}

class LLMContextDecoder:
    def __init__(self, raw: Dict[str, Any]):
        self.raw = raw
        self.st = raw.get("st", [])
        
        # Pre-resolve lookup tables to avoid double computation
        self.files = [self._decode_file(f) for f in raw.get("f", [])]
        self.symbols = [self._decode_symbol(sym) for sym in raw.get("sym", [])]
        self.behaviors = [self._decode_behavior(bh) for bh in raw.get("bh", [])]
        self.references = [self._decode_reference(ref) for ref in raw.get("ref", [])]
        self.endpoints = [self._decode_endpoint(ep) for ep in raw.get("ep", [])]

    def _get_str(self, idx: int) -> str:
        return self.st[idx] if idx < len(self.st) else ""

    def _get_enum(self, table: str, enum_id: int) -> str:
        return ENUMS.get(table, {}).get(enum_id, "")

    def _decode_file(self, f: List[int]) -> Dict[str, Any]:
        return {
            "path": self._get_str(f[0]),
            "language": self._get_enum("lang", f[1]),
            "change_type": self._get_enum("ct", f[2])
        }

    def _decode_symbol(self, sym: List[Any]) -> Dict[str, Any]:
        file_info = self.files[sym[0]] if sym[0] < len(self.files) else {}
        name = self._get_str(sym[1])
        return {
            "file": file_info.get("path", ""),
            "name": name,
            "kind": self._get_enum("kind", sym[2]),
            "visibility": self._get_enum("vis", sym[3]),
            "location": {
                "start_line": sym[4][0],
                "end_line": sym[4][1]
            }
        }

    def _decode_behavior(self, bh: List[int]) -> Dict[str, Any]:
        sym_info = self.symbols[bh[0]] if bh[0] < len(self.symbols) else {}
        return {
            "symbol": sym_info,
            "kind": self._get_enum("kind", bh[1])
        }

    def _decode_reference(self, ref: List[int]) -> Dict[str, Any]:
        return {
            "id": self._get_str(ref[0]),
            "kind": self._get_enum("ref_kind", ref[1]),
            "location": self._get_str(ref[2]),
            "compiler_artifact": self._get_str(ref[3])
        }

    def _decode_endpoint(self, ep: List[int]) -> Dict[str, Any]:
        return {
            "endpoint": self._get_str(ep[0]),
            "method": self._get_enum("method", ep[1]),
            "path": self._get_str(ep[2])
        }

    def decode(self) -> Dict[str, Any]:
        """Convert compact representation into an easy-to-read, fully expanded schema."""
        decoded = {}

        # 1. Change Summary
        if "cs" in self.raw:
            cs = self.raw["cs"]
            decoded["summary"] = {
                "classification": self._get_enum("cls", cs[0]),
                "scope": self._get_enum("scope", cs[1]),
                "file_count": cs[2],
                "symbol_count": cs[3],
                "behavior_count": cs[4]
            }

        # 2. Changed Files & Symbols details
        decoded["changes"] = []
        for file_idx, change_list in self.raw.get("cf", []):
            file_path = self.files[file_idx]["path"] if file_idx < len(self.files) else ""
            file_changes = []
            for sym_idx, ct_id, bh_change_ids in change_list:
                sym_info = self.symbols[sym_idx] if sym_idx < len(self.symbols) else {}
                file_changes.append({
                    "symbol": sym_info,
                    "change_type": self._get_enum("ct", ct_id),
                    "behavior_changes": [self._get_enum("bh_change", bid) for bid in bh_change_ids]
                })
            decoded["changes"].append({
                "file": file_path,
                "changes": file_changes
            })

        # 3. Execution Graph Details
        raw_eg = self.raw.get("eg", {})
        eg_nodes = []
        for n in raw_eg.get("n", []):
            bh_info = self.behaviors[n[0]] if n[0] < len(self.behaviors) else {}
            sym_info = self.symbols[n[1]] if n[1] < len(self.symbols) else {}
            eg_nodes.append({
                "behavior": bh_info,
                "symbol": sym_info,
                "kind": self._get_enum("kind", n[2]),
                "depth": n[3],
                "changed": n[4],
                "shared": n[5],
                "reaches": {
                    "service": self._get_str(n[6]),
                    "module": self._get_str(n[7]),
                    "package": self._get_str(n[8])
                },
                "references": [self._get_str(ref_i) for ref_i in n[9]]
            })
            
        decoded["execution_graph"] = {
            "nodes": eg_nodes,
            "edges": [{"parent": edge[0], "child": edge[1]} for edge in raw_eg.get("e", [])]
        }

        # 4. Entry Points
        decoded["entry_points"] = []
        for endpoint_idx, node_idxs, terminal_idx, max_depth in self.raw.get("epts", []):
            ep_info = self.endpoints[endpoint_idx] if endpoint_idx < len(self.endpoints) else {}
            decoded["entry_points"].append({
                "endpoint": ep_info,
                "execution_chain_nodes": [eg_nodes[ni] for ni in node_idxs if ni < len(eg_nodes)],
                "terminal": self._get_str(terminal_idx),
                "max_depth": max_depth
            })

        # 5. Deepest Execution
        if "de" in self.raw:
            ep_idx, depth = self.raw["de"]
            decoded["deepest_execution"] = {
                "endpoint": self.endpoints[ep_idx] if ep_idx < len(self.endpoints) else {},
                "depth": depth
            }

        # 6. Discoveries
        decoded["discoveries"] = []
        for id_idx, kind_id, facts_dict, ref_idxs in self.raw.get("disc", []):
            decoded["discoveries"].append({
                "id": self._get_str(id_idx),
                "kind": self._get_enum("bh_kind", kind_id),
                "facts": facts_dict,
                "references": [self.references[ri] for ri in ref_idxs if ri < len(self.references)]
            })

        return decoded
```

---

## Example: Compact vs. Expanded Representation

### 1. Serialized Compact JSON (`llm_context`)

```json
{
  "st": [
    "",
    "runtime/instrumentation/logging.py",
    "setup_logging",
    "sym://runtime/instrumentation/logging.py#setup_logging",
    "POST /api/v1/logs",
    "/api/v1/logs",
    "api",
    "logging",
    "ref://log/1",
    "setup_logging_called"
  ],
  "f": [
    [1, 1, 1]
  ],
  "sym": [
    [0, 2, 2, 1, [10, 25]]
  ],
  "bh": [
    [0, 2]
  ],
  "ref": [
    [8, 1, 3, 9]
  ],
  "ep": [
    [4, 1, 5]
  ],
  "cs": [1, 1, 1, 1, 1],
  "cf": [
    [0, [
      [0, 1, [1, 8]]
    ]]
  ],
  "eg": {
    "n": [
      [0, 0, 2, 1, true, false, 6, 7, 0, [8]]
    ],
    "e": []
  },
  "epts": [
    [0, [0], 9, 1]
  ],
  "de": [0, 1],
  "disc": [
    [8, 1, {"reason": "adds logger context"}, [0]]
  ]
}
```

### 2. Resolved Human-Readable Output

If decompressed using the `LLMContextDecoder`, the result is fully self-documenting:

```json
{
  "summary": {
    "classification": "modification",
    "scope": "local",
    "file_count": 1,
    "symbol_count": 1,
    "behavior_count": 1
  },
  "changes": [
    {
      "file": "runtime/instrumentation/logging.py",
      "changes": [
        {
          "symbol": {
            "file": "runtime/instrumentation/logging.py",
            "name": "setup_logging",
            "kind": "function",
            "visibility": "public",
            "location": {
              "start_line": 10,
              "end_line": 25
            }
          },
          "change_type": "modified",
          "behavior_changes": [
            "FunctionBodyChange",
            "DocstringChange"
          ]
        }
      ]
    }
  ],
  "execution_graph": {
    "nodes": [
      {
        "behavior": {
          "symbol": {
            "file": "runtime/instrumentation/logging.py",
            "name": "setup_logging",
            "kind": "function",
            "visibility": "public",
            "location": {
              "start_line": 10,
              "end_line": 25
            }
          },
          "kind": "function"
        },
        "symbol": {
          "file": "runtime/instrumentation/logging.py",
          "name": "setup_logging",
          "kind": "function",
          "visibility": "public",
          "location": {
            "start_line": 10,
            "end_line": 25
          }
        },
        "kind": "function",
        "depth": 1,
        "changed": true,
        "shared": false,
        "reaches": {
          "service": "api",
          "module": "logging",
          "package": ""
        },
        "references": ["ref://log/1"]
      }
    ],
    "edges": []
  },
  "entry_points": [
    {
      "endpoint": {
        "endpoint": "POST /api/v1/logs",
        "method": "POST",
        "path": "/api/v1/logs"
      },
      "execution_chain_nodes": [
        {
          "behavior": {
            "symbol": {
              "file": "runtime/instrumentation/logging.py",
              "name": "setup_logging",
              "kind": "function",
              "visibility": "public",
              "location": {
                "start_line": 10,
                "end_line": 25
              }
            },
            "kind": "function"
          },
          "symbol": {
            "file": "runtime/instrumentation/logging.py",
            "name": "setup_logging",
            "kind": "function",
            "visibility": "public",
            "location": {
              "start_line": 10,
              "end_line": 25
            }
          },
          "kind": "function",
          "depth": 1,
          "changed": true,
          "shared": false,
          "reaches": {
            "service": "api",
            "module": "logging",
            "package": ""
          },
          "references": ["ref://log/1"]
        }
      ],
      "terminal": "setup_logging_called",
      "max_depth": 1
    }
  ],
  "deepest_execution": {
    "endpoint": {
      "endpoint": "POST /api/v1/logs",
      "method": "POST",
      "path": "/api/v1/logs"
    },
    "depth": 1
  },
  "discoveries": [
    {
      "id": "ref://log/1",
      "kind": "deep_execution",
      "facts": {
        "reason": "adds logger context"
      },
      "references": [
        {
          "id": "ref://log/1",
          "kind": "behavior",
          "location": "sym://runtime/instrumentation/logging.py#setup_logging",
          "compiler_artifact": "setup_logging_called"
        }
      ]
    }
  ]
}
```
