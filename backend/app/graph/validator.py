"""Sequential code validation service for DAG code blocks.

Performs static AST analysis and sequential flow verification across experiment
graph nodes in topological order to guarantee that:
1. Every node contains valid Python syntax.
2. All referenced symbols (variables, classes, functions, imports) are defined
   before use (either locally, in upstream dependencies, or via the runtime harness).
3. Specific uninitialized runtime symbols (such as `device` in `model = MLP().to(device)`)
   are detected and flagged with concrete line numbers and remediation fixes.
4. Provides auto-remediation to safely inject missing framework definitions
   (e.g., deterministic device setup, seeds, architecture fallbacks).
"""
from __future__ import annotations

import ast
import builtins
import re
from typing import Any

from .models import (
    DAGNode,
    GraphValidationReport,
    GraphVersion,
    NodeScopeSummary,
    ValidationIssue,
)

PYTHON_BUILTINS = set(dir(builtins)) | {
    "__name__", "__doc__", "__file__", "__package__", "__annotations__",
}

STANDARD_HARNESS_SYMBOLS = {
    "CRISISGRID_SEED", "PYTHONHASHSEED",
    "report_metric", "crisisgrid_metrics",
    "os", "sys", "json", "random",
}


class SymbolScopeVisitor(ast.NodeVisitor):
    """AST visitor to extract top-level definitions, imports, and free references."""

    def __init__(self) -> None:
        # Stack of local symbol scopes
        self.scope_stack: list[set[str]] = [set()]
        self.top_level_defs: set[str] = set()
        self.imported_modules: set[str] = set()
        # List of (symbol_name, line_number)
        self.free_loads: list[tuple[str, int]] = []

    # --- Imports ---
    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            name = alias.asname or alias.name.split(".")[0]
            self.scope_stack[-1].add(name)
            self.imported_modules.add(alias.name)
            if len(self.scope_stack) == 1:
                self.top_level_defs.add(name)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        for alias in node.names:
            name = alias.asname or alias.name
            self.scope_stack[-1].add(name)
            module = node.module or ""
            self.imported_modules.add(f"{module}.{alias.name}" if module else alias.name)
            if len(self.scope_stack) == 1:
                self.top_level_defs.add(name)

    # --- Classes ---
    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.scope_stack[-1].add(node.name)
        if len(self.scope_stack) == 1:
            self.top_level_defs.add(node.name)
        # Class bases are evaluated in outer scope
        for base in node.bases:
            self.visit(base)
        # Class body has its own scope
        self.scope_stack.append(set())
        for stmt in node.body:
            self.visit(stmt)
        self.scope_stack.pop()

    # --- Functions ---
    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_func(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_func(node)

    def _visit_func(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        self.scope_stack[-1].add(node.name)
        if len(self.scope_stack) == 1:
            self.top_level_defs.add(node.name)

        # Default argument values are evaluated in outer scope
        for d in node.args.defaults:
            self.visit(d)
        for d in node.args.kw_defaults:
            if d:
                self.visit(d)

        # Function body has its own scope with arguments
        local_args = {a.arg for a in node.args.args}
        local_args.update({a.arg for a in node.args.kwonlyargs})
        local_args.update({a.arg for a in node.args.posonlyargs})
        if node.args.vararg:
            local_args.add(node.args.vararg.arg)
        if node.args.kwarg:
            local_args.add(node.args.kwarg.arg)

        self.scope_stack.append(local_args)
        for stmt in node.body:
            self.visit(stmt)
        self.scope_stack.pop()

    # --- Lambdas ---
    def visit_Lambda(self, node: ast.Lambda) -> None:
        local_args = {a.arg for a in node.args.args}
        if node.args.vararg:
            local_args.add(node.args.vararg.arg)
        if node.args.kwarg:
            local_args.add(node.args.kwarg.arg)
        self.scope_stack.append(local_args)
        self.visit(node.body)
        self.scope_stack.pop()

    # --- Comprehensions ---
    def visit_ListComp(self, node: ast.ListComp) -> None:
        self._visit_comp(node.generators, [node.elt])

    def visit_SetComp(self, node: ast.SetComp) -> None:
        self._visit_comp(node.generators, [node.elt])

    def visit_DictComp(self, node: ast.DictComp) -> None:
        self._visit_comp(node.generators, [node.key, node.value])

    def visit_GeneratorExp(self, node: ast.GeneratorExp) -> None:
        self._visit_comp(node.generators, [node.elt])

    def _visit_comp(self, generators: list[ast.comprehension], elts: list[ast.AST]) -> None:
        self.scope_stack.append(set())
        for gen in generators:
            self.visit(gen.iter)
            self._record_target_names(gen.target)
            for if_expr in gen.ifs:
                self.visit(if_expr)
        for elt in elts:
            self.visit(elt)
        self.scope_stack.pop()

    # --- Assignments ---
    def visit_Assign(self, node: ast.Assign) -> None:
        self.visit(node.value)
        for target in node.targets:
            self._record_target_names(target)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if node.value:
            self.visit(node.value)
        self._record_target_names(node.target)

    def visit_AugAssign(self, node: ast.AugAssign) -> None:
        self.visit(node.value)
        self._record_target_names(node.target)

    def visit_For(self, node: ast.For) -> None:
        self.visit(node.iter)
        self._record_target_names(node.target)
        for stmt in node.body:
            self.visit(stmt)
        for stmt in node.orelse:
            self.visit(stmt)

    def visit_With(self, node: ast.With) -> None:
        for item in node.items:
            self.visit(item.context_expr)
            if item.optional_vars:
                self._record_target_names(item.optional_vars)
        for stmt in node.body:
            self.visit(stmt)

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        if node.type:
            self.visit(node.type)
        if node.name:
            self.scope_stack[-1].add(node.name)
            if len(self.scope_stack) == 1:
                self.top_level_defs.add(node.name)
        for stmt in node.body:
            self.visit(stmt)

    def _record_target_names(self, target: ast.AST) -> None:
        if isinstance(target, ast.Name):
            self.scope_stack[-1].add(target.id)
            if len(self.scope_stack) == 1:
                self.top_level_defs.add(target.id)
        elif isinstance(target, (ast.Tuple, ast.List)):
            for elt in target.elts:
                self._record_target_names(elt)

    # --- Name references ---
    def visit_Name(self, node: ast.Name) -> None:
        if isinstance(node.ctx, ast.Store):
            self.scope_stack[-1].add(node.id)
            if len(self.scope_stack) == 1:
                self.top_level_defs.add(node.id)
        elif isinstance(node.ctx, ast.Load):
            is_local = any(node.id in s for s in self.scope_stack)
            if not is_local and node.id not in PYTHON_BUILTINS:
                self.free_loads.append((node.id, node.lineno))


class SequentialCodeValidator:
    """Validates experiment DAG code blocks individually and sequentially."""

    @classmethod
    def analyze_node_ast(
        cls,
        node_id: str,
        node_name: str,
        code: str,
        parameters: dict[str, Any] | None = None,
    ) -> tuple[NodeScopeSummary, list[ValidationIssue]]:
        """Extract defined and referenced symbols from node code via AST."""
        params = parameters or {}
        summary = NodeScopeSummary(node_id=node_id)
        issues: list[ValidationIssue] = []

        try:
            tree = ast.parse(code)
        except SyntaxError as syn_err:
            issues.append(
                ValidationIssue(
                    node_id=node_id,
                    node_name=node_name,
                    severity="error",
                    category="syntax_error",
                    line_number=syn_err.lineno,
                    message=f"Syntax error at line {syn_err.lineno}: {syn_err.msg}",
                    suggested_fix="Check syntax and indentation in this node code block.",
                )
            )
            return summary, issues

        visitor = SymbolScopeVisitor()
        visitor.visit(tree)

        # Include node parameters as defined symbols
        defined = set(visitor.top_level_defs)
        defined.update(params.keys())

        # Collect unique referenced symbols with line numbers
        unique_free_loads: dict[str, int] = {}
        for sym, lineno in visitor.free_loads:
            if sym not in unique_free_loads:
                unique_free_loads[sym] = lineno

        summary.defined_symbols = sorted(defined)
        summary.referenced_symbols = sorted(unique_free_loads.keys())
        summary.imported_modules = sorted(visitor.imported_modules)

        return summary, issues

    @classmethod
    def validate_graph(
        cls,
        graph: GraphVersion,
        harness_symbols: set[str] | None = None,
    ) -> GraphValidationReport:
        """Validate entire DAG sequentially in topological execution order."""
        available_harness = set(harness_symbols or STANDARD_HARNESS_SYMBOLS)
        issues: list[ValidationIssue] = []
        node_scopes: dict[str, NodeScopeSummary] = {}
        node_map = {n.id: n for n in graph.nodes}
        execution_order = graph.execution_order or [n.id for n in graph.nodes]

        # First pass: analyze all nodes individually to map definitions and references
        node_defined_all: dict[str, set[str]] = {}
        node_referenced_all: dict[str, dict[str, int]] = {}

        for node_id in execution_order:
            node = node_map.get(node_id)
            if not node:
                continue

            summary, node_issues = cls.analyze_node_ast(
                node_id=node.id,
                node_name=node.name,
                code=node.code,
                parameters=node.parameters,
            )
            issues.extend(node_issues)
            node_scopes[node.id] = summary
            node_defined_all[node.id] = set(summary.defined_symbols)

            # Map of sym -> first line number
            ref_lines: dict[str, int] = {}
            try:
                tree = ast.parse(node.code)
                vis = SymbolScopeVisitor()
                vis.visit(tree)
                for sym, lineno in vis.free_loads:
                    if sym not in ref_lines:
                        ref_lines[sym] = lineno
            except Exception:
                pass
            node_referenced_all[node.id] = ref_lines

        # Second pass: sequential scope flow validation
        cumulative_scope: set[str] = set(available_harness)
        symbol_origin: dict[str, str] = {}  # symbol -> defining node_id

        # Track downstream definitions to detect ordering violations
        all_future_definitions: dict[str, str] = {}
        for nid, defs in node_defined_all.items():
            for d in defs:
                if d not in all_future_definitions:
                    all_future_definitions[d] = nid

        remediated_codes: dict[str, str] = {}

        for node_id in execution_order:
            node = node_map.get(node_id)
            if not node:
                continue

            ref_map = node_referenced_all.get(node.id, {})
            current_defined = node_defined_all.get(node.id, set())
            missing_in_node: list[str] = []

            for sym, lineno in ref_map.items():
                # 1. Defined in current node or parameters
                if sym in current_defined:
                    continue
                # 2. Builtin
                if sym in PYTHON_BUILTINS:
                    continue
                # 3. Available in cumulative upstream scope
                if sym in cumulative_scope:
                    if sym == "device" and sym not in current_defined:
                        issues.append(
                            ValidationIssue(
                                node_id=node.id,
                                node_name=node.name,
                                severity="warning",
                                category="scope_isolation_gap",
                                symbol="device",
                                line_number=lineno,
                                message=(
                                    f"Variable 'device' is defined upstream in '{symbol_origin.get(sym, 'upstream')}' "
                                    f"but not declared locally in '{node.id}'. In isolated container runs, "
                                    f"declare 'device' locally or rely on runner context chaining."
                                ),
                                suggested_fix="device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')",
                            )
                        )
                    continue

                # The symbol is unresolved!
                missing_in_node.append(sym)

                # Check if it was defined in a downstream node (dependency order violation)
                if sym in all_future_definitions and all_future_definitions[sym] != node.id:
                    downstream_id = all_future_definitions[sym]
                    issues.append(
                        ValidationIssue(
                            node_id=node.id,
                            node_name=node.name,
                            severity="error",
                            category="dependency_order_violation",
                            symbol=sym,
                            line_number=lineno,
                            message=(
                                f"Symbol '{sym}' is referenced at line {lineno} in '{node.id}', "
                                f"but is defined in downstream node '{downstream_id}'. "
                                f"Check dependency edge or reorder nodes."
                            ),
                            suggested_fix=f"Add dependency edge from '{downstream_id}' to '{node.id}' or define '{sym}' upstream.",
                        )
                    )
                elif sym == "device":
                    issues.append(
                        ValidationIssue(
                            node_id=node.id,
                            node_name=node.name,
                            severity="error",
                            category="undefined_symbol",
                            symbol="device",
                            line_number=lineno,
                            message=(
                                f"Variable 'device' is referenced at line {lineno} (e.g., '.to(device)') "
                                f"but is not defined in this node or upstream context."
                            ),
                            suggested_fix="device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')",
                        )
                    )
                elif sym == "seed":
                    issues.append(
                        ValidationIssue(
                            node_id=node.id,
                            node_name=node.name,
                            severity="warning",
                            category="undefined_symbol",
                            symbol="seed",
                            line_number=lineno,
                            message=f"Variable 'seed' is referenced at line {lineno} without local declaration.",
                            suggested_fix="seed = globals().get('SEED', 42)",
                        )
                    )
                elif sym in {"torch", "nn", "optim", "np", "F"}:
                    issues.append(
                        ValidationIssue(
                            node_id=node.id,
                            node_name=node.name,
                            severity="error",
                            category="missing_import",
                            symbol=sym,
                            line_number=lineno,
                            message=f"Module '{sym}' is referenced at line {lineno} without an import statement.",
                            suggested_fix=f"import {sym}" if sym != "nn" else "import torch.nn as nn",
                        )
                    )
                else:
                    issues.append(
                        ValidationIssue(
                            node_id=node.id,
                            node_name=node.name,
                            severity="error",
                            category="undefined_symbol",
                            symbol=sym,
                            line_number=lineno,
                            message=(
                                f"Variable/symbol '{sym}' is referenced at line {lineno} in '{node.id}' "
                                f"but neither defined nor imported in this node or any upstream dependency."
                            ),
                            suggested_fix=f"Define '{sym}' or pass it via node parameters.",
                        )
                    )

            if missing_in_node:
                node_scopes[node.id].missing_symbols = sorted(missing_in_node)
                # Generate auto-remediated code for this node
                remed_code = cls.auto_remediate_node_code(
                    node_id=node.id,
                    code=node.code,
                    missing_symbols=set(missing_in_node),
                    parameters=node.parameters,
                )
                remediated_codes[node.id] = remed_code

            # Accumulate definitions for downstream nodes
            for d in current_defined:
                cumulative_scope.add(d)
                symbol_origin[d] = node.id

        # Third pass: Sequential dry-run simulation
        sim_valid, sim_err = cls.simulate_sequential_execution(graph)

        total_errors = sum(1 for i in issues if i.severity == "error")
        total_warnings = sum(1 for i in issues if i.severity == "warning")

        return GraphValidationReport(
            is_valid=(total_errors == 0 and sim_valid),
            can_auto_remediate=bool(remediated_codes),
            total_errors=total_errors,
            total_warnings=total_warnings,
            issues=issues,
            node_scopes=node_scopes,
            sequential_execution_valid=sim_valid,
            sequential_simulation_error=sim_err,
            remediated_code_by_node=remediated_codes,
        )

    @classmethod
    def auto_remediate_node_code(
        cls,
        node_id: str,
        code: str,
        missing_symbols: set[str],
        parameters: dict[str, Any] | None = None,
    ) -> str:
        """Inject safe missing declarations into node code."""
        params = parameters or {}
        injections: list[str] = []

        # Missing imports
        if "torch" in missing_symbols or "nn" in missing_symbols or "device" in missing_symbols:
            if "import torch" not in code:
                injections.append("import torch")
            if "nn" in missing_symbols and "import torch.nn as nn" not in code:
                injections.append("import torch.nn as nn")

        if "np" in missing_symbols and "import numpy as np" not in code:
            injections.append("import numpy as np")

        # Missing device
        if "device" in missing_symbols:
            injections.append(
                'device = torch.device("cuda" if torch.cuda.is_available() else "cpu")'
            )

        # Missing seed
        if "seed" in missing_symbols:
            configured_seed = params.get("seed", 42)
            injections.append(f"seed = globals().get('SEED', {configured_seed})")

        # Missing batch_size
        if "batch_size" in missing_symbols and "batch_size" not in code:
            bs = params.get("batch_size", 64)
            injections.append(f"batch_size = {bs}")

        # Missing learning_rate
        if "learning_rate" in missing_symbols and "learning_rate" not in code:
            lr = params.get("learning_rate", 0.001)
            injections.append(f"learning_rate = {lr}")

        # Missing epochs
        if "epochs" in missing_symbols and "epochs" not in code:
            ep = params.get("epochs", 10)
            injections.append(f"epochs = {ep}")

        # Missing MLP model definition
        if "MLP" in missing_symbols and "class MLP" not in code:
            injections.append(
                "import torch.nn as nn\n\n"
                "class MLP(nn.Module):\n"
                "    def __init__(self, in_features=3 * 32 * 32, num_classes=10):\n"
                "        super().__init__()\n"
                "        self.net = nn.Sequential(\n"
                "            nn.Flatten(),\n"
                "            nn.Linear(in_features, 128),\n"
                "            nn.ReLU(),\n"
                "            nn.Linear(128, num_classes),\n"
                "        )\n\n"
                "    def forward(self, x):\n"
                "        return self.net(x)"
            )

        if not injections:
            return code

        injection_block = "\n".join(injections) + "\n\n"

        # Find best insertion point (after initial header comments)
        lines = code.split("\n")
        insert_idx = 0
        while insert_idx < len(lines) and (
            lines[insert_idx].startswith("#") or not lines[insert_idx].strip()
        ):
            insert_idx += 1

        new_lines = (
            lines[:insert_idx]
            + ["# [Auto-Remediated] Injected missing runtime definitions", injection_block]
            + lines[insert_idx:]
        )
        return "\n".join(new_lines)

    @classmethod
    def simulate_sequential_execution(
        cls,
        graph: GraphVersion,
    ) -> tuple[bool, str | None]:
        """Simulate sequential compilation of all graph nodes in topological order."""
        node_map = {n.id: n for n in graph.nodes}
        execution_order = graph.execution_order or [n.id for n in graph.nodes]

        combined_code_lines = [
            "# === Simulated Sequential Execution Harness ===",
            "import os, sys, random, json",
            "try:",
            "    import numpy as np",
            "except ImportError: pass",
            "try:",
            "    import torch",
            "    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')",
            "except ImportError: pass",
            "SEED = 42",
            "seed = 42",
            "crisisgrid_metrics = {}",
            "def report_metric(k, v): crisisgrid_metrics[k] = float(v)",
            "",
        ]

        for node_id in execution_order:
            node = node_map.get(node_id)
            if not node:
                continue
            combined_code_lines.append(f"# === Node: {node.id} ===")
            for k, v in node.parameters.items():
                if not k.startswith("_"):
                    combined_code_lines.append(f"{k} = {repr(v)}")
            combined_code_lines.append(node.code)
            combined_code_lines.append("")

        combined_code = "\n".join(combined_code_lines)

        try:
            ast.parse(combined_code)
            return True, None
        except SyntaxError as syn_err:
            return False, f"Sequential syntax error at line {syn_err.lineno}: {syn_err.msg}"
        except Exception as exc:
            return False, f"Simulation error: {exc}"
