#!/usr/bin/env python3
"""
Generate Agent Functions Registry for Notion Database.

This script scans the codebase and creates JSON entries for each function
to be added to the Notion Agent Functions database.

Each entry includes:
- Function name and signature
- Module path
- Docstring
- Full source code (for page body)
- Metadata (async, decorators, args)

Output: var/pending_notion_writes/agent_functions/
"""

import ast
import json
import hashlib
import os
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional


# Configuration
CORE_DIRECTORIES = [
    "music_workflow",
    "shared_core",
    "services",
    "scripts",
    "sync_framework",
]

EXCLUDED_PATTERNS = [
    "__pycache__",
    ".git",
    "venv",
    ".venv",
    "node_modules",
    "tests",
    "test_",
    "_backup",
    ".backup",
]

OUTPUT_DIR = Path("var/pending_notion_writes/agent_functions")


def extract_function_source(file_path: Path, node: ast.FunctionDef) -> str:
    """Extract the complete source code for a function."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        start_line = node.lineno - 1
        end_line = getattr(node, 'end_lineno', node.lineno + 20)

        return ''.join(lines[start_line:end_line])
    except Exception:
        return ""


def get_function_signature(node: ast.FunctionDef) -> str:
    """Generate function signature string."""
    args = []

    # Regular args
    for arg in node.args.args:
        arg_str = arg.arg
        if arg.annotation:
            try:
                arg_str += f": {ast.unparse(arg.annotation)}"
            except:
                pass
        args.append(arg_str)

    # *args
    if node.args.vararg:
        args.append(f"*{node.args.vararg.arg}")

    # **kwargs
    if node.args.kwarg:
        args.append(f"**{node.args.kwarg.arg}")

    # Return type
    return_type = ""
    if node.returns:
        try:
            return_type = f" -> {ast.unparse(node.returns)}"
        except:
            pass

    prefix = "async " if isinstance(node, ast.AsyncFunctionDef) else ""
    return f"{prefix}def {node.name}({', '.join(args)}){return_type}"


def extract_functions_from_file(file_path: Path) -> List[Dict[str, Any]]:
    """Extract all functions from a Python file."""
    functions = []

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        tree = ast.parse(content)

        # Get module-level docstring
        module_docstring = ast.get_docstring(tree) or ""

        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue

            # Skip dunder methods
            if node.name.startswith('__') and node.name.endswith('__'):
                continue

            # Extract function info
            func_info = {
                "name": node.name,
                "file_path": str(file_path),
                "module": str(file_path).replace("./", "").replace(".py", "").replace("/", "."),
                "line_start": node.lineno,
                "line_end": getattr(node, 'end_lineno', node.lineno),
                "signature": get_function_signature(node),
                "docstring": ast.get_docstring(node) or "",
                "is_async": isinstance(node, ast.AsyncFunctionDef),
                "is_private": node.name.startswith('_'),
                "num_args": len(node.args.args),
                "decorators": [],
                "source_code": extract_function_source(file_path, node),
            }

            # Extract decorators
            for decorator in node.decorator_list:
                try:
                    func_info["decorators"].append(ast.unparse(decorator))
                except:
                    pass

            functions.append(func_info)

    except Exception as e:
        print(f"Error processing {file_path}: {e}")

    return functions


def generate_function_id(func_info: Dict[str, Any]) -> str:
    """Generate a unique ID for a function."""
    key = f"{func_info['module']}.{func_info['name']}"
    return hashlib.sha256(key.encode()).hexdigest()[:12]


def create_notion_entry(func_info: Dict[str, Any]) -> Dict[str, Any]:
    """Create a Notion database entry for a function."""
    func_id = generate_function_id(func_info)

    # Determine category based on module
    module = func_info["module"]
    if "music_workflow" in module:
        category = "Music Workflow"
    elif "shared_core" in module:
        category = "Shared Core"
    elif "services" in module:
        category = "Services"
    elif "scripts" in module:
        category = "Scripts"
    elif "sync_framework" in module:
        category = "Sync Framework"
    else:
        category = "Other"

    # Determine tags
    tags = []
    if func_info["is_async"]:
        tags.append("async")
    if func_info["is_private"]:
        tags.append("private")
    if "notion" in module.lower():
        tags.append("notion")
    if "spotify" in module.lower():
        tags.append("spotify")
    if "eagle" in module.lower():
        tags.append("eagle")
    if "djay" in module.lower():
        tags.append("djay-pro")
    if "fingerprint" in module.lower() or "fingerprint" in func_info["name"].lower():
        tags.append("fingerprint")
    if "webhook" in module.lower():
        tags.append("webhook")
    if "sync" in func_info["name"].lower():
        tags.append("sync")

    # Build the entry
    entry = {
        "type": "create_page",
        "database": "Agent-Functions",
        "function_id": func_id,
        "properties": {
            "Name": func_info["name"],
            "Module": func_info["module"],
            "Category": category,
            "Tags": ", ".join(tags) if tags else "general",
            "Signature": func_info["signature"][:2000],  # Notion limit
            "Is Async": func_info["is_async"],
            "Is Private": func_info["is_private"],
            "Num Args": func_info["num_args"],
            "File Path": func_info["file_path"],
            "Line Start": func_info["line_start"],
            "Line End": func_info["line_end"],
            "Status": "Active",
        },
        "page_body": {
            "docstring": func_info["docstring"],
            "source_code": func_info["source_code"],
            "decorators": func_info["decorators"],
        },
        "created_by": "Claude Code Agent (Opus 4.5)",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    return entry


def scan_codebase() -> List[Dict[str, Any]]:
    """Scan the codebase and extract all functions."""
    all_functions = []

    for core_dir in CORE_DIRECTORIES:
        core_path = Path(core_dir)
        if not core_path.exists():
            continue

        for py_file in core_path.rglob("*.py"):
            # Skip excluded patterns
            if any(pattern in str(py_file) for pattern in EXCLUDED_PATTERNS):
                continue

            functions = extract_functions_from_file(py_file)
            all_functions.extend(functions)

    return all_functions


def main():
    """Main entry point."""
    print("=" * 60)
    print("AGENT FUNCTIONS REGISTRY GENERATOR")
    print("=" * 60)
    print()

    # Scan codebase
    print("Scanning codebase...")
    functions = scan_codebase()
    print(f"Found {len(functions)} functions")

    # Filter to non-private functions (or include all based on requirements)
    # For comprehensive registry, include all non-dunder functions
    print(f"  Public functions: {len([f for f in functions if not f['is_private']])}")
    print(f"  Private functions: {len([f for f in functions if f['is_private']])}")
    print(f"  Async functions: {len([f for f in functions if f['is_async']])}")
    print()

    # Create output directory
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Generate Notion entries
    print("Generating Notion entries...")
    entries = []
    for func in functions:
        entry = create_notion_entry(func)
        entries.append(entry)

        # Write individual JSON file
        filename = f"{entry['function_id']}_{func['name']}.json"
        filepath = OUTPUT_DIR / filename
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(entry, f, indent=2, ensure_ascii=False)

    print(f"Generated {len(entries)} entries in {OUTPUT_DIR}")
    print()

    # Summary by category
    by_category = {}
    for entry in entries:
        cat = entry["properties"]["Category"]
        by_category[cat] = by_category.get(cat, 0) + 1

    print("By category:")
    for cat, count in sorted(by_category.items(), key=lambda x: -x[1]):
        print(f"  {cat}: {count}")

    # Write summary manifest
    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_functions": len(entries),
        "by_category": by_category,
        "output_directory": str(OUTPUT_DIR),
    }

    manifest_path = OUTPUT_DIR / "_manifest.json"
    with open(manifest_path, 'w') as f:
        json.dump(manifest, f, indent=2)

    print()
    print(f"Manifest written to {manifest_path}")
    print("=" * 60)


if __name__ == "__main__":
    main()
