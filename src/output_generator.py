from pathlib import Path
from typing import List, Dict
from utils import run_cloc

class OutputGenerator:
    @staticmethod
    def generate_tree_diagram(files: List[Path], root_path: Path, output_file: Path):
        """Generate a markdown tree diagram of the files with SLOC information"""
        tree_structure = {}

        # Get SLOC counts using cloc
        file_stats = run_cloc(files)

        # Build tree structure
        for file_path in files:
            rel_path = file_path.relative_to(root_path)
            parts = list(rel_path.parts)

            # Build tree
            current = tree_structure
            for part in parts[:-1]:
                if part not in current:
                    current[part] = {}
                current = current[part]
            current[parts[-1]] = None

        # Generate markdown content
        content = ["# Project Analysis\n"]

        # Add directory structure
        content.append("## Directory Structure\n")
        content.extend(OutputGenerator._generate_tree_lines(tree_structure))

        # Add SLOC table
        content.append("\n## Code Analysis\n")
        content.append("| File | Lines of Code |")
        content.append("|------|---------------|")

        total_sloc = 0
        for file_path in sorted(files):
            rel_path = file_path.relative_to(root_path)
            sloc = file_stats.get(str(file_path), 0)
            total_sloc += sloc
            content.append(f"| {rel_path} | {sloc:,} |")

        # Add total SLOC
        content.append("|**Total**|**{:,}**|".format(total_sloc))

        # Write to file
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write('\n'.join(content))

    @staticmethod
    def _generate_tree_lines(tree: Dict, prefix: str = '', is_last: bool = True) -> List[str]:
        """Generate lines for the tree diagram"""
        lines = []
        items = list(tree.items())

        for i, (name, subtree) in enumerate(items):
            is_last_item = i == len(items) - 1

            # Create the prefix for the current line
            current_prefix = prefix + ('└── ' if is_last_item else '├── ')
            lines.append(current_prefix + name)

            if subtree is not None:
                # Create the prefix for subtree lines
                subtree_prefix = prefix + ('    ' if is_last_item else '│   ')
                lines.extend(OutputGenerator._generate_tree_lines(subtree, subtree_prefix, is_last_item))

        return lines