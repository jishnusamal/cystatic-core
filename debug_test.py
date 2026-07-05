"""Debug the actual test case."""

from textwrap import dedent
from schemas.ir import DiffIR, FileDiff, DiffHunk, DiffLine
from language_adapters.python.python_adapter import PythonAdapter
from language_adapters.ir import NodeType, EdgeType

def make_diff(file_path: str, new_content: str) -> DiffIR:
    lines_new = new_content.splitlines(keepends=True)
    diff_lines = [
        DiffLine(
            line_type="added",
            content=line,
            source_line_no=None,
            target_line_no=i + 1,
        )
        for i, line in enumerate(lines_new)
    ]
    hunk = DiffHunk(
        file_path=file_path,
        source_start=0,
        source_length=0,
        target_start=1,
        target_length=len(lines_new),
        added_lines=list(range(1, len(lines_new) + 1)),
        removed_lines=[],
        lines=diff_lines,
    )
    file_diff = FileDiff(
        file_path=file_path,
        added_lines=set(range(1, len(lines_new) + 1)),
        removed_lines=set(),
        hunks=[hunk],
    )
    return DiffIR(files=[file_diff])

code = dedent("""
    class Base:
        def save(self):
            pass

    class Child(Base):
        def save(self):
            super().save()
""")

adapter = PythonAdapter()
diff = make_diff("app.py", code)
graph = adapter.analyze(diff, file_contents={"app.py": code})

print(f"Nodes: {len(graph.nodes)}")
print(f"Edges: {len(graph.edges)}")

# Try to get Child.save
child_save = graph.get_node(NodeType.METHOD, "save", "app.py", class_name="Child")
print(f"\nChild.save: {child_save}")

# Try to get Base.save
base_save = graph.get_node(NodeType.METHOD, "save", "app.py", class_name="Base")
print(f"Base.save: {base_save}")

# Get all methods
methods = graph.get_nodes_by_type(NodeType.METHOD)
print(f"\nAll methods:")
for m in methods:
    print(f"  {m.name} (class={m.class_name})")

# Get edges from whichever exists
save_method = child_save or base_save
if save_method:
    edges = graph.get_edges_from(save_method)
    print(f"\nEdges from {save_method.class_name}.{save_method.name}:")
    for edge in edges:
        if edge.edge_type == EdgeType.CALLS:
            print(f"  CALLS: {edge.target.name} (call_type={edge.call_type})")
else:
    print("\nNo save method found!")