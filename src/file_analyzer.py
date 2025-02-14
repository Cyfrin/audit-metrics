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
        """Compile glob patterns to regex patterns"""
        # If patterns is None or empty list, return pattern that matches everything
        if not patterns or (isinstance(patterns, list) and len(patterns) == 0):
            return [re.compile(".*")]

        def glob_to_regex(pattern: str) -> str:
            """Convert glob pattern to regex pattern"""
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

            # Handle directory patterns
            pattern = pattern.replace('**/', '(?:.*/)*')  # Match any directory depth
            pattern = pattern.replace('*/', '[^/]*/') # Match single directory level
            pattern = pattern.replace('*', '[^/]*')  # Match anything except /
            pattern = pattern.replace('?', '[^/]')  # Match single char except /

            # Make pattern match anywhere in the path
            return pattern

        return [re.compile(glob_to_regex(p)) for p in patterns if p.strip()]

    def _should_include_file(self, file_path: str | Path) -> bool:
        """Determine if a file should be included in analysis"""
        file_path = Path(file_path)
        # Normalize path to use forward slashes
        try:
            rel_path = str(file_path.relative_to(self.workspace_dir)).replace('\\', '/')
        except ValueError:
            rel_path = str(file_path).replace('\\', '/')

        print(f"\nChecking file: {rel_path}")
        print(f"Extensions: {self.extensions}")
        print(f"Include patterns: {[p.pattern for p in self.include_patterns]}")
        print(f"Exclude patterns: {[p.pattern for p in self.exclude_patterns]}")

        # Check extensions
        if self.extensions and not any(str(file_path).lower().endswith(ext.lower()) for ext in self.extensions):
            print(f"Excluding: {rel_path} - extension not in {self.extensions}")
            return False

        # Check excludes first - match against both relative and absolute paths
        for exclude_pattern in self.exclude_patterns:
            # Try matching against the relative path
            if exclude_pattern.search(rel_path):
                print(f"Excluding: {rel_path} - matches exclude pattern {exclude_pattern.pattern}")
                return False
            # Try matching against the absolute path
            abs_path = str(file_path.absolute()).replace('\\', '/')
            if exclude_pattern.search(abs_path):
                print(f"Excluding: {rel_path} - matches exclude pattern {exclude_pattern.pattern} (absolute path)")
                return False

        # For primary files, check include patterns only if they exist
        if hasattr(self, '_is_checking_primary') and self._is_checking_primary:
            if not self.include_patterns:
                print(f"Including: {rel_path} - no include patterns specified")
                return True
            # Check includes only if patterns exist
            for pattern in self.include_patterns:
                if pattern.search(rel_path):
                    print(f"Including: {rel_path} - matches include pattern {pattern.pattern}")
                    return True
            print(f"Excluding: {rel_path} - doesn't match any include patterns")
            return False

        # For dependencies, include everything that's not excluded
        print(f"Including: {rel_path} - dependency check")
        return True

    def find_primary_files(self, changed_files: Optional[List[str]] = None) -> List[Path]:
        """Find all primary files to analyze"""
        # Set flag for checking primary files
        self._is_checking_primary = True
        try:
            if changed_files is not None:
                print(f"\nChecking changed files: {changed_files}")
                # Filter changed files
                primary_files = [
                    Path(f) for f in changed_files
                    if self._should_include_file(f)
                ]
            else:
                print("\nScanning all files in workspace...")
                # Get all files in workspace
                all_files = []
                for root, _, files in os.walk(self.workspace_dir):
                    for file in files:
                        file_path = Path(root) / file
                        print(f"Checking file: {file_path}")
                        if self._should_include_file(file_path):
                            print(f"Including file: {file_path}")
                            all_files.append(file_path)
                        else:
                            print(f"Excluding file: {file_path} - doesn't match criteria")
                primary_files = all_files

            print(f"\nFound {len(primary_files)} primary files:")
            for file in primary_files:
                try:
                    rel_path = file.relative_to(self.workspace_dir)
                except ValueError:
                    rel_path = file
                print(f"- {rel_path}")

            return primary_files
        finally:
            # Clear the flag
            self._is_checking_primary = False

    def find_dependencies(self, primary_files: List[Path]) -> List[Path]:
        """Find all dependencies of primary files"""
        dependencies = set()
        visited = set()  # Track visited files to prevent cycles

        # Convert any string paths to Path objects
        primary_files = [Path(f) if isinstance(f, str) else f for f in primary_files]

        for file_path in primary_files:
            deps = self._find_file_dependencies(file_path, visited)
            dependencies.update(deps)

        # Remove primary files from dependencies
        dependencies = dependencies - set(primary_files)

        # Only filter out excluded files, ignore include patterns
        filtered_dependencies = []
        for dep in dependencies:
            # For dependencies, we only check extensions and excludes
            if self._should_include_file(dep):
                filtered_dependencies.append(dep)

        return sorted(filtered_dependencies)

    def _find_file_dependencies(self, file_path: Path, visited: Set[Path], depth: int = 0) -> Set[Path]:
        """Find dependencies for a single file"""
        MAX_DEPTH = 10  # Maximum recursion depth
        dependencies = set()
        file_path = Path(file_path)

        # Check recursion depth and visited files
        if depth > MAX_DEPTH or file_path in visited:
            return dependencies

        visited.add(file_path)

        # Read file content
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()

            # Find import statements based on file type
            if file_path.suffix == '.sol':
                dependencies.update(self._find_solidity_imports(content, file_path, visited, depth + 1))
            elif file_path.suffix == '.rs':
                dependencies.update(self._find_rust_imports(content, file_path))
            elif file_path.suffix == '.cairo':
                dependencies.update(self._find_cairo_imports(content, file_path))

        except Exception as e:
            print(f"Error processing {file_path}: {e}")

        return dependencies

    def _find_solidity_imports(self, content: str, file_path: Path, visited: Set[Path], depth: int) -> Set[Path]:
        """Find Solidity import statements and contract dependencies"""
        deps = set()

        try:
            # First: Find all contract declarations and inheritance
            contract_pattern = r'(?:contract|abstract contract|interface)\s+(\w+)\s+is\s+([^{]+)'
            for match in re.finditer(contract_pattern, content):
                contract_name = match.group(1)
                inherited = match.group(2)

                # Split inherited contracts and clean up names
                inherited_contracts = [c.strip() for c in inherited.split(',')]

                print(f"Found contract {contract_name} inheriting from: {inherited_contracts}")

                # Try to resolve each inherited contract
                for contract in inherited_contracts:
                    possible_paths = [
                        f"{contract}.sol",
                        f"I{contract}.sol",  # Interface
                        f"{contract}Storage.sol",  # Storage pattern
                        f"{contract}Logic.sol",  # Logic pattern
                        f"contracts/{contract}.sol",
                        f"src/{contract}.sol",
                        f"interfaces/I{contract}.sol",
                    ]

                    for possible_path in possible_paths:
                        resolved_path = self._resolve_import_path(possible_path, file_path)
                        if resolved_path and resolved_path not in visited:
                            print(f"Found dependency: {resolved_path}")
                            deps.add(resolved_path)
                            nested_deps = self._find_file_dependencies(resolved_path, visited, depth)
                            deps.update(nested_deps)
                            break  # Found the contract, stop trying other paths
                    else:
                        print(f"Warning: Could not find contract file for {contract}")

            # Second: Find import statements
            import_patterns = [
                r'import\s+"([^"]+)"',  # Standard imports
                r'import\s+{[^}]+}\s+from\s+"([^"]+)"',  # Named imports
                r'import\s+\*\s+as\s+[^"]+\s+from\s+"([^"]+)"',  # Aliased imports
                r'import\s+{[^}]+}\s+from\s+["\']([^"\']+)["\']',  # Interface imports
                r'import\s+[\'"](.*?)[\'"]',  # Direct imports
            ]

            for pattern in import_patterns:
                for match in re.finditer(pattern, content):
                    import_path = match.group(1)
                    resolved_path = self._resolve_import_path(import_path, file_path)
                    if resolved_path and resolved_path not in visited:
                        print(f"Found import: {resolved_path}")
                        deps.add(resolved_path)
                        nested_deps = self._find_file_dependencies(resolved_path, visited, depth)
                        deps.update(nested_deps)

        except Exception as e:
            print(f"Error processing Solidity imports in {file_path}: {e}")
            import traceback
            traceback.print_exc()

        return deps

    def _find_rust_imports(self, content: str, file_path: Path) -> Set[Path]:
        """Find Rust import statements and module declarations"""
        deps = set()
        try:
            # Match different types of Rust imports and module declarations
            patterns = [
                # use statements
                r'use\s+(?:crate|super|self)?::?([^:;\s]+(?:::[^:;\s]+)*)',
                # mod declarations
                r'mod\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*;',
                # extern crate statements
                r'extern\s+crate\s+([a-zA-Z_][a-zA-Z0-9_]*)',
                # use statements with curly braces
                r'use\s+(?:crate|super|self)?::?([^:;\s]+(?:::[^:;\s]+)*)::\{[^}]+\}'
            ]

            for pattern in patterns:
                for match in re.finditer(pattern, content):
                    import_path = match.group(1)
                    resolved_paths = self._resolve_rust_import_path(import_path, file_path)
                    deps.update(resolved_paths)

        except Exception as e:
            print(f"Error processing Rust imports in {file_path}: {e}")

        return deps

    def _find_cargo_root(self, current_file: Path) -> Path:
        """Find the root directory containing Cargo.toml"""
        current_dir = current_file.parent
        while current_dir != current_dir.parent:
            if (current_dir / "Cargo.toml").exists():
                return current_dir
            current_dir = current_dir.parent
        return self.workspace_dir

    def _resolve_rust_import_path(self, import_path: str, current_file: Path) -> Set[Path]:
        """Resolve Rust import paths to actual file paths"""
        resolved_paths = set()
        try:
            # Split the path into components
            path_parts = import_path.split('::')
            current_dir = current_file.parent

            # Handle different types of paths
            if import_path.startswith('crate'):
                # Start from workspace root for crate-relative paths
                current_dir = self._find_cargo_root(current_file)
                path_parts = path_parts[1:]
            elif import_path.startswith('super'):
                # Go up one directory for each 'super'
                super_count = path_parts.count('super')
                for _ in range(super_count):
                    current_dir = current_dir.parent
                path_parts = path_parts[super_count:]

            # Build the path progressively
            for part in path_parts:
                if not part or part in ('self', 'crate', 'super'):
                    continue

                # Check possible file locations
                possible_locations = [
                    current_dir / f"{part}.rs",
                    current_dir / part / "mod.rs",
                    current_dir / part / "lib.rs",
                ]

                for location in possible_locations:
                    if location.exists():
                        resolved_paths.add(location)
                        current_dir = location.parent
                        break
                else:
                    # If no file found, continue with directory for nested modules
                    current_dir = current_dir / part

        except Exception as e:
            print(f"Error resolving Rust import path {import_path}: {e}")

        return resolved_paths

    def _find_cairo_imports(self, content: str, file_path: Path) -> Set[Path]:
        """Find Cairo import statements"""
        deps = set()
        # Add Cairo-specific import pattern matching
        return deps

    def _resolve_import_path(self, import_path: str, current_file: Path) -> Optional[Path]:
        """Resolve relative import paths to absolute paths"""
        try:
            # Handle different import path styles
            if import_path.startswith('./') or import_path.startswith('../'):
                # Relative import
                resolved = (current_file.parent / import_path).resolve()
            else:
                # Try multiple base paths for absolute imports
                possible_paths = [
                    self.workspace_dir / import_path,  # Direct from workspace root
                    self.workspace_dir / 'src' / import_path,  # From src directory
                    self.workspace_dir / 'contracts' / import_path,  # From contracts directory
                    self.workspace_dir / 'interfaces' / import_path,  # From interfaces directory
                    self.workspace_dir / 'lib' / import_path,  # From lib directory
                    current_file.parent / import_path,  # From current directory
                    current_file.parent / '..' / import_path,  # From parent directory
                    current_file.parent / 'interfaces' / import_path,  # From local interfaces
                    current_file.parent / 'libraries' / import_path,  # From local libraries
                    # Try without file extension
                    self.workspace_dir / import_path.replace('.sol', '') / f"{import_path.split('/')[-1]}",
                ]

                for path in possible_paths:
                    if path.exists() and path.is_file():
                        return path
                    # Try with .sol extension if not already present
                    if not str(path).endswith('.sol'):
                        path_with_ext = path.with_suffix('.sol')
                        if path_with_ext.exists() and path_with_ext.is_file():
                            return path_with_ext

            # Check if the resolved path exists
            if 'resolved' in locals() and resolved.exists() and resolved.is_file():
                return resolved

            # Try adding .sol extension if it doesn't exist
            if 'resolved' in locals() and not str(resolved).endswith('.sol'):
                resolved_with_ext = resolved.with_suffix('.sol')
                if resolved_with_ext.exists() and resolved_with_ext.is_file():
                    return resolved_with_ext

        except Exception as e:
            print(f"Error resolving import path {import_path}: {e}")

        return None

    def _analyze_dependencies(self, file_path: str) -> Set[str]:
        """Analyze file dependencies based on file type"""
        ext = Path(file_path).suffix
        if ext == '.sol':
            return self._analyze_solidity_dependencies(file_path)
        elif ext == '.rs':
            return self._analyze_rust_dependencies(file_path)
        return set()

    def _analyze_rust_dependencies(self, file_path: str) -> Set[str]:
        """Analyze Rust file dependencies"""
        dependencies = set()
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()

            # Match use statements and mod declarations
            use_patterns = [
                r'use\s+(?:crate|super|self)?::?([\w:]+)',  # use statements
                r'mod\s+(\w+);',  # mod statements
                r'extern\s+crate\s+(\w+);'  # extern crate statements
            ]

            for pattern in use_patterns:
                matches = re.finditer(pattern, content)
                for match in matches:
                    mod_path = match.group(1)
                    # Convert module path to potential file paths
                    possible_paths = self._resolve_rust_module_path(file_path, mod_path)
                    for path in possible_paths:
                        if os.path.exists(path):
                            dependencies.add(str(path))

        except Exception as e:
            print(f"Error analyzing Rust dependencies in {file_path}: {e}")

        return dependencies

    def _resolve_rust_module_path(self, source_file: str, mod_path: str) -> List[str]:
        """Convert a Rust module path to possible file paths"""
        source_dir = os.path.dirname(source_file)
        path_parts = mod_path.split('::')

        possible_paths = []
        current_dir = source_dir

        for part in path_parts:
            # Check for both file.rs and file/mod.rs patterns
            file_path = os.path.join(current_dir, f"{part}.rs")
            mod_path = os.path.join(current_dir, part, "mod.rs")

            possible_paths.extend([file_path, mod_path])
            current_dir = os.path.join(current_dir, part)

        return possible_paths

    def _get_all_files(self) -> list[str]:
        """Get all files in the repository with proper include/exclude filtering"""
        all_files = [str(Path(self.workspace_dir) / item)
                    for item in self.repo.git.ls_files().split('\n') if item]

        # Debug output - comment out or add debug flag
        # print("\n=== All Repository Files ===")
        # print("\n".join(f"- {Path(f).relative_to(self.workspace_dir)}" for f in all_files))

        # Get environment variables
        extensions = os.getenv('EXTENSIONS', '').strip().split(',')
        includes = [p.strip() for p in os.getenv('INCLUDE', '').split(',') if p.strip()]
        excludes = [p.strip() for p in os.getenv('EXCLUDE', '').split(',') if p.strip()]

        # ... rest of the code ...

        # Remove redundant filter settings output since it's shown in main.py
        # print(f"\nFilter Settings:")
        # print(f"Extensions: {extensions}")
        # print(f"Include patterns: {[p.pattern for p in include_patterns]}")
        # print(f"Exclude patterns: {[p.pattern for p in exclude_patterns]}\n")

        # Convert paths to Path objects for better path manipulation
        files = [Path(f) for f in all_files]
        filtered_files = [str(f) for f in files if self._should_include_file(f)]

        print("\n=== Files After Filtering ===")
        print("\n".join(f"- {Path(f).relative_to(self.workspace_dir)}" for f in filtered_files))
        print("\n")

        return filtered_files