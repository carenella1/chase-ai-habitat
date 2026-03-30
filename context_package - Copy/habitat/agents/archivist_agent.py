import os
import json
import ast
from datetime import datetime


class ArchivistAgent:

    def __init__(self):

        os.makedirs("knowledge", exist_ok=True)

        self.project_root = os.getcwd()

        self.blueprint_json_path = "knowledge/system_blueprint.json"
        self.blueprint_md_path = "knowledge/system_blueprint.md"
        self.tree_path = "knowledge/project_tree.txt"

    # --------------------------------------------------
    # PUBLIC ENTRYPOINT
    # --------------------------------------------------

    def export_system_snapshot(self):

        print("\n[Archivist] Exporting system snapshot...")

        tree = self._generate_project_tree()
        files = self._scan_python_files()

        blueprint = {
            "project": "Chase AI Habitat",
            "generated_at": datetime.utcnow().isoformat(),
            "project_root": self.project_root,
            "files": files,
            "agents": self._extract_agents(files),
            "ui_components": self._extract_ui(files),
            "memory_system": {
                "database": "data/memory.db",
                "tables": ["memories", "research_threads"],
                "tiers": ["ephemeral", "long_term"]
            },
            "cognition_logging": {
                "file": "knowledge/cognition_log.json"
            }
        }

        self._write_json(blueprint)
        self._write_markdown(blueprint)
        self._write_tree(tree)

        print("[Archivist] System snapshot complete.\n")

    # --------------------------------------------------
    # PROJECT TREE
    # --------------------------------------------------

    def _generate_project_tree(self):

        tree_lines = []

        for root, dirs, files in os.walk(self.project_root):

            level = root.replace(self.project_root, "").count(os.sep)

            indent = " " * 4 * level

            tree_lines.append(f"{indent}{os.path.basename(root)}/")

            subindent = " " * 4 * (level + 1)

            for f in files:

                if ".git" in root:
                    continue

                tree_lines.append(f"{subindent}{f}")

        return tree_lines

    # --------------------------------------------------
    # PYTHON FILE SCAN
    # --------------------------------------------------

    def _scan_python_files(self):

        python_files = []

        for root, dirs, files in os.walk(self.project_root):

            for file in files:

                if not file.endswith(".py"):
                    continue

                if ".venv" in root or "__pycache__" in root:
                    continue

                path = os.path.join(root, file)

                try:

                    info = self._analyze_python_file(path)

                    python_files.append(info)

                except Exception:

                    continue

        return python_files

    # --------------------------------------------------
    # PYTHON FILE ANALYSIS
    # --------------------------------------------------

    def _analyze_python_file(self, path):

        with open(path, "r", encoding="utf-8") as f:
            source = f.read()

        tree = ast.parse(source)

        classes = []
        functions = []

        for node in ast.walk(tree):

            if isinstance(node, ast.ClassDef):
                classes.append(node.name)

            if isinstance(node, ast.FunctionDef):
                functions.append(node.name)

        return {
            "path": path.replace(self.project_root + "\\", ""),
            "classes": classes,
            "functions": functions
        }

    # --------------------------------------------------
    # AGENT EXTRACTION
    # --------------------------------------------------

    def _extract_agents(self, files):

        agents = []

        for file in files:

            path = file["path"]

            if "agent" in path.lower():

                agents.append({
                    "file": path,
                    "classes": file["classes"]
                })

        return agents

    # --------------------------------------------------
    # UI COMPONENT EXTRACTION
    # --------------------------------------------------

    def _extract_ui(self, files):

        ui = []

        for file in files:

            path = file["path"]

            if "ui" in path.lower() or "run_ui" in path.lower():
                ui.append(path)

        return ui

    # --------------------------------------------------
    # WRITE JSON
    # --------------------------------------------------

    def _write_json(self, blueprint):

        with open(self.blueprint_json_path, "w") as f:
            json.dump(blueprint, f, indent=2)

    # --------------------------------------------------
    # WRITE MARKDOWN
    # --------------------------------------------------

    def _write_markdown(self, blueprint):

        lines = []

        lines.append("# Chase AI Habitat — System Blueprint\n")
        lines.append(f"Generated: {blueprint['generated_at']}\n")

        lines.append("## Project Overview\n")
        lines.append("Chase AI Habitat is a multi-agent AI cognition system.\n")

        lines.append("### Memory System\n")
        lines.append("- SQLite database: data/memory.db\n")
        lines.append("- Tables: memories, research_threads\n")
        lines.append("- Tiers: ephemeral, long_term\n")

        lines.append("\n### Cognition Logging\n")
        lines.append("- knowledge/cognition_log.json\n")

        lines.append("\n### Agents\n")

        for agent in blueprint["agents"]:
            lines.append(f"- {agent['file']}")

        lines.append("\n### Python Modules\n")

        for file in blueprint["files"]:

            lines.append(f"\n**{file['path']}**")

            if file["classes"]:
                lines.append(f"Classes: {', '.join(file['classes'])}")

            if file["functions"]:
                lines.append(f"Functions: {', '.join(file['functions'])}")

        with open(self.blueprint_md_path, "w") as f:
            f.write("\n".join(lines))

    # --------------------------------------------------
    # WRITE PROJECT TREE
    # --------------------------------------------------

    def _write_tree(self, tree_lines):

        with open(self.tree_path, "w") as f:
            f.write("\n".join(tree_lines))