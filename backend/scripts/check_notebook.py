"""Static check for a notebook: does every cell have what it uses?

    uv run python -m scripts.check_notebook ../notebooks/train_vehide_yolo.ipynb

**Why this exists.** A notebook is executed top to bottom in one namespace, so a
name defined in cell 3 is available in cell 9. That is also why a missing import
hides: the cell that needs it usually runs after something else already imported
it, and only fails when the notebook is edited, reordered, or a cell is removed.

Three of those shipped in this project's training notebook, and each cost a
round trip to a GPU platform to discover:

* `normalise` used in the VIA cell, defined in a COCO cell that a rewrite had
  deleted;
* `json` used inside `locate()`, imported nowhere in that cell;
* both invisible to the rehearsal harness, because the harness pre-populated its
  namespace with `json` and `Path` for its own convenience -- a fixture that
  supplies what the code is missing cannot detect that the code is missing it.

So this walks the cells in order, tracks every name each one binds, and reports
any name a cell reads that nothing before it defined. No execution, no GPU, no
dataset: it runs in under a second and catches the entire class.
"""

from __future__ import annotations

import argparse
import ast
import builtins
import json
import sys
from pathlib import Path

#: Names Colab and Kaggle inject, or that only exist inside a notebook session.
NOTEBOOK_GLOBALS = frozenset({"get_ipython", "In", "Out", "exit", "quit", "display"})


class Scope(ast.NodeVisitor):
    """Collects the names a block of code binds and the names it reads.

    Deliberately simple: no flow analysis, no scoping of comprehensions. It errs
    towards saying a name is bound, because a false alarm here trains people to
    ignore the check, while a missed import merely returns us to the status quo.
    """

    def __init__(self) -> None:
        self.bound: set[str] = set()
        self.read: set[str] = set()

    # --- bindings ---------------------------------------------------------
    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self.bound.add(alias.asname or alias.name.split(".")[0])

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        for alias in node.names:
            self.bound.add(alias.asname or alias.name)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self.bound.add(node.name)
        # Parameters and locals are bound inside the function; treating the body
        # as one flat scope would report every parameter as undefined.
        inner = Scope()
        for argument in [*node.args.args, *node.args.kwonlyargs, *node.args.posonlyargs]:
            inner.bound.add(argument.arg)
        if node.args.vararg:
            inner.bound.add(node.args.vararg.arg)
        if node.args.kwarg:
            inner.bound.add(node.args.kwarg.arg)
        for statement in node.body:
            inner.visit(statement)
        for default in [*node.args.defaults, *[d for d in node.args.kw_defaults if d]]:
            self.visit(default)
        for decorator in node.decorator_list:
            self.visit(decorator)
        self.read |= inner.read - inner.bound

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        # ast dispatches on the node class name, so this has to exist under
        # exactly this spelling. The bodies are identical; the signatures are
        # not, which is why it is a method rather than an alias.
        self.visit_FunctionDef(node)  # type: ignore[arg-type]

    def visit_Lambda(self, node: ast.Lambda) -> None:
        inner = Scope()
        for argument in [*node.args.args, *node.args.kwonlyargs, *node.args.posonlyargs]:
            inner.bound.add(argument.arg)
        inner.visit(node.body)
        self.read |= inner.read - inner.bound

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.bound.add(node.name)
        for statement in node.body:
            self.visit(statement)
        for base in node.bases:
            self.visit(base)

    def visit_Name(self, node: ast.Name) -> None:
        if isinstance(node.ctx, ast.Store):
            self.bound.add(node.id)
        elif isinstance(node.ctx, ast.Load):
            self.read.add(node.id)
        else:  # Del
            self.read.add(node.id)

    def visit_Global(self, node: ast.Global) -> None:
        self.bound.update(node.names)

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        if node.name:
            self.bound.add(node.name)
        self.generic_visit(node)


def strip_magics(source: str) -> str:
    """Remove Jupyter magics, which are not Python and will not parse."""
    lines = []
    for line in source.splitlines():
        stripped = line.lstrip()
        if stripped.startswith(("!", "%")):
            lines.append(" " * (len(line) - len(stripped)) + "pass")
        else:
            lines.append(line)
    return "\n".join(lines)


def check(path: Path) -> int:
    notebook = json.loads(path.read_text(encoding="utf-8"))
    defined: set[str] = set(dir(builtins)) | NOTEBOOK_GLOBALS
    problems: list[str] = []

    for index, cell in enumerate(notebook["cells"]):
        if cell["cell_type"] != "code":
            continue

        source = strip_magics("".join(cell["source"]))
        try:
            tree = ast.parse(source)
        except SyntaxError as error:
            problems.append(f"cell {index}: does not parse -- {error}")
            continue

        scope = Scope()
        for statement in tree.body:
            scope.visit(statement)

        missing = sorted(name for name in scope.read - scope.bound if name not in defined)
        if missing:
            for name in missing:
                problems.append(f"cell {index}: uses {name!r}, which nothing before it defines")

        defined |= scope.bound

    code_cells = sum(1 for c in notebook["cells"] if c["cell_type"] == "code")
    print(f"{path.name}: {code_cells} code cells")
    if problems:
        print()
        for problem in problems:
            print(f"  {problem}")
        print()
        print(f"{len(problems)} problem(s). Each one is a NameError waiting for a run.")
        return 1

    print("every name a cell reads is defined by that cell or an earlier one")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("notebook", type=Path)
    arguments = parser.parse_args()
    return check(arguments.notebook)


if __name__ == "__main__":
    sys.exit(main())
