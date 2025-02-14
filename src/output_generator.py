from pathlib import Path
from typing import List, Dict
from utils import run_cloc

class OutputGenerator:
    @staticmethod
    def generate_tree_diagram(files: List[Path], base_path: Path, output_file: Path, title: str = None) -> None:
        """Generate a tree diagram of the files"""
        try:
            # Convert paths to relative paths and sort
            rel_paths = sorted([str(Path(f).relative_to(base_path)) for f in files])
            
            # Generate markdown
            lines = []
            if title:
                lines.append(f"# {title}\n")

            # Add list of included files
            lines.append("### Included Files:\n")
            for path in rel_paths:
                lines.append(f"- {path}")
            lines.append("\n### File Tree:\n")
            
            # Create tree structure
            tree = {}
            for path in rel_paths:
                current = tree
                parts = path.split('/')
                for part in parts[:-1]:
                    if part not in current:
                        current[part] = {}
                    current = current[part]
                current[parts[-1]] = None

            def write_tree(node, prefix=''):
                items = sorted(node.items())
                for i, (name, subtree) in enumerate(items):
                    is_last = i == len(items) - 1
                    lines.append(f"{prefix}{'└── ' if is_last else '├── '}{name}")
                    if subtree is not None:
                        write_tree(subtree, prefix + ('    ' if is_last else '│   '))

            write_tree(tree)
            
            # Write to file
            with open(output_file, 'a' if title else 'w') as f:
                f.write('\n'.join(lines) + '\n\n')

        except Exception as e:
            print(f"Error generating tree diagram: {e}")

    @staticmethod
    def generate_combined_report(primary_files: List[Path], all_files: List[Path], 
                               base_path: Path, output_file: Path,
                               primary_cloc: str, full_cloc: str) -> None:
        """Generate a combined report with both primary and full analysis"""
        output_file.parent.mkdir(exist_ok=True)

        def extract_cloc_summary(cloc_output: str) -> tuple[int, int]:
            """Extract total files and code lines from CLOC output"""
            for line in cloc_output.split('\n'):
                if line.startswith('SUM:'):
                    parts = line.split()
                    return int(parts[1]), int(parts[4])  # files, code
            return 0, 0

        def format_file_list(files: List[Path]) -> str:
            return '\n'.join(f"- {f.relative_to(base_path)}" for f in sorted(files))

        # Get statistics
        primary_files_count, primary_nsloc = extract_cloc_summary(primary_cloc)
        
        # Generate report
        report = [
            "# Code Analysis Report\n",
            f"## Primary Analysis ({primary_files_count} files, {primary_nsloc} nSLOC)\n",
            "### Files Analyzed:",
            format_file_list(primary_files),
            "\n### CLOC Analysis",
            "```",
            primary_cloc.strip(),
            "```\n"
        ]

        # Add dependency analysis if there are additional files
        if len(all_files) > len(primary_files):
            total_files_count, total_nsloc = extract_cloc_summary(full_cloc)
            dependency_files = sorted(set(all_files) - set(primary_files))
            
            report.extend([
                f"\n## Full Analysis ({total_files_count} files, {total_nsloc} nSLOC)\n",
                "### Additional Dependencies:",
                format_file_list(dependency_files),
                "\n### CLOC Analysis",
                "```",
                full_cloc.strip(),
                "```"
            ])

        # Write report
        output_file.write_text('\n'.join(report))