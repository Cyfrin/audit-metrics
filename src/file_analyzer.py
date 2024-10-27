import os
from pathlib import Path
from typing import List, Set, Dict, Optional
import re

class FileAnalyzer:
    def __init__(self, workspace_dir: str, extensions: List[str], include_patterns: List[str], exclude_patterns: List[str]):
        self.workspace_dir = Path(workspace_dir)
        self.extensions = extensions
        self.include_patterns = self._compile_patterns(include_patterns)
        self.exclude_patterns = self._compile_patterns(exclude_patterns)

    def _compile_patterns(self, patterns: List[str]) -> List[re.Pattern]:
        if not patterns:
            return [re.compile(".*")] if patterns == [] else []

        def glob_to_regex(pattern: str) -> str:
            if not pattern:
                return ".*"

            pattern = pattern.replace('\\', '/')
            pattern = (
                pattern
                .replace('.', r'\.')
                .replace('+', r'\+')
                .replace('(', r'\(')
                .replace(')', r'\)')
                .replace('|', r'\|')
                .replace('^', r'\^')
                .replace('$', r'\$')
                .replace('{', r'\{')
                .replace('}', r'\}')
                .replace('[', r'\[')
                .replace(']', r'\]')
            )
            pattern = pattern.replace('*', '.*').replace('?', '.')
            return pattern

        return [re.compile(glob_to_regex(p)) for p in patterns]

    def _should_include_file(self, file_path: str | Path) -> bool:
        file_path = Path(file_path)
        # Normalize path to use forward slashes
        try:
            rel_path = str(file_path.relative_to(self.workspace_dir)).replace('\\', '/')
        except ValueError:
            # If file_path is already relative, use it as is
            rel_path = str(file_path).replace('\\', '/')

        # Check extensions
        if self.extensions and not any(str(file_path).lower().endswith(ext.lower()) for ext in self.extensions):
            return False

        # Check excludes first - now with more detailed path matching
        for exclude_pattern in self.exclude_patterns:
            if exclude_pattern.search(rel_path):
                return False
            # Also check against absolute path for thorough exclusion
            if exclude_pattern.search(str(file_path.absolute()).replace('\\', '/')):
                return False

        # If no include patterns, include everything not excluded
        if not self.include_patterns:
            return True

        # Check includes
        return any(include_pattern.search(rel_path) for include_pattern in self.include_patterns)


    def find_primary_files(self, changed_files: Optional[List[str]] = None) -> List[Path]:
        """Find all primary files to analyze"""
        if changed_files is not None:
            # Filter changed files
            primary_files = [
                Path(f) for f in changed_files
                if self._should_include_file(f)
            ]
        else:
            # Get all files in workspace
            all_files = []
            for root, _, files in os.walk(self.workspace_dir):
                for file in files:
                    file_path = Path(root) / file
                    if self._should_include_file(file_path):
                        all_files.append(file_path)
            primary_files = all_files

        print(f"\nFound {len(primary_files)} primary files:")
        for file in primary_files:
            try:
                rel_path = file.relative_to(self.workspace_dir)
            except ValueError:
                rel_path = file
            print(f"- {rel_path}")

        return primary_files

    def find_dependencies(self, primary_files: List[Path]) -> List[Path]:
        """Find all dependencies of primary files and filter out excluded ones"""
        dependencies = set()

        # Convert any string paths to Path objects
        primary_files = [Path(f) if isinstance(f, str) else f for f in primary_files]

        for file_path in primary_files:
            deps = self._find_file_dependencies(file_path)
            dependencies.update(deps)

        # Remove primary files from dependencies
        dependencies = dependencies - set(primary_files)

        # Filter out excluded files
        filtered_dependencies = []
        for dep in dependencies:
            if self._should_include_file(dep):
                filtered_dependencies.append(dep)

        return sorted(filtered_dependencies)

    def _find_file_dependencies(self, file_path: Path) -> Set[Path]:
        """Find dependencies for a single file"""
        dependencies = set()
        file_path = Path(file_path)

        # Read file content
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()

            # Find import statements based on file type
            if file_path.suffix == '.sol':
                dependencies.update(self._find_solidity_imports(content, file_path))
            elif file_path.suffix == '.rs':
                dependencies.update(self._find_rust_imports(content, file_path))
            elif file_path.suffix == '.cairo':
                dependencies.update(self._find_cairo_imports(content, file_path))

        except Exception as e:
            print(f"Error processing {file_path}: {e}")

        return dependencies

    def _find_solidity_imports(self, content: str, file_path: Path) -> Set[Path]:
        """Find Solidity import statements"""
        deps = set()
        import_patterns = [
            r'import\s+"([^"]+)"',
            r'import\s+{[^}]+}\s+from\s+"([^"]+)"',
            r'import\s+\*\s+as\s+[^"]+\s+from\s+"([^"]+)"'
        ]

        for pattern in import_patterns:
            for match in re.finditer(pattern, content):
                import_path = match.group(1)
                resolved_path = self._resolve_import_path(import_path, file_path)
                if resolved_path:
                    deps.add(resolved_path)

        return deps

    def _find_rust_imports(self, content: str, file_path: Path) -> Set[Path]:
        """Find Rust import statements"""
        deps = set()
        # Add Rust-specific import pattern matching
        return deps

    def _find_cairo_imports(self, content: str, file_path: Path) -> Set[Path]:
        """Find Cairo import statements"""
        deps = set()
        # Add Cairo-specific import pattern matching
        return deps

    def _resolve_import_path(self, import_path: str, current_file: Path) -> Optional[Path]:
        """Resolve relative import paths to absolute paths"""
        try:
            if import_path.startswith('./') or import_path.startswith('../'):
                # Relative import
                resolved = (current_file.parent / import_path).resolve()
            else:
                # Package import (from project root)
                resolved = (self.workspace_dir / import_path).resolve()

            # Check if the file exists and is valid
            if resolved.exists() and resolved.is_file():
                return resolved

            # Try adding .sol extension if it doesn't exist
            if not import_path.endswith('.sol'):
                resolved_with_ext = resolved.with_suffix('.sol')
                if resolved_with_ext.exists() and resolved_with_ext.is_file():
                    return resolved_with_ext

        except Exception as e:
            print(f"Error resolving import path {import_path}: {e}")

        return None