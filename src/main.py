import os
import errno
import stat
import time
import shutil
import argparse
import re
import tempfile
from typing import List
from dotenv import load_dotenv
from pathlib import Path
from git_handler import parse_github_url, GitRepoHandler
from file_analyzer import FileAnalyzer
from output_generator import OutputGenerator
import subprocess

def parse_arguments():
    parser = argparse.ArgumentParser(description='Audit Metrics Tool')
    parser.add_argument('--url', help='GitHub URL (repository, PR, or commit comparison)')
    parser.add_argument('--keep-git', action='store_true', help='Keep the temporary git repository after analysis')
    parser.add_argument('--clean', action='store_true', help='Clean all repositories in out/repos directory and exit')
    return parser.parse_args()

def handle_remove_readonly(func, path, exc):
    """Handle read-only files during deletion"""
    excvalue = exc[1]
    if func in (os.rmdir, os.remove, os.unlink) and excvalue.errno == errno.EACCES:
        # Change file access mode
        os.chmod(path, stat.S_IRWXU | stat.S_IRWXG | stat.S_IRWXO)
        # Retry operation
        func(path)
    else:
        raise

def clean_repositories():
    """Clean all repositories in the audit-metrics directory"""
    audit_metrics_dir = Path(tempfile.gettempdir()) / "audit-metrics"

    if audit_metrics_dir.exists():
        max_attempts = 3
        attempt = 0
        while attempt < max_attempts:
            try:
                print(f"Attempting to clean {audit_metrics_dir}")
                # Use the error handler for read-only files
                shutil.rmtree(audit_metrics_dir, onerror=handle_remove_readonly)
                print(f"Successfully cleaned audit-metrics directory: {audit_metrics_dir}")
                break
            except Exception as e:
                attempt += 1
                if attempt == max_attempts:
                    print(f"Failed to clean directory after {max_attempts} attempts: {e}")
                    print("Please close any applications that might be using these files and try again.")
                else:
                    print(f"Attempt {attempt} failed, retrying after short delay...")
                    time.sleep(1)  # Wait a second before retrying
    else:
        print("No audit-metrics directory found to clean")

def load_config():
    load_dotenv(override=True)
    github_token = os.getenv('GITHUB_TOKEN')
    if not github_token:
        raise ValueError("GITHUB_TOKEN is required in .env file")

    def prepare_patterns(patterns_str: str, default: str = '') -> List[str]:
        if not patterns_str:
            return [p.strip() for p in default.split(',') if p.strip()]
        return [p.strip() for p in patterns_str.split(',') if p.strip()]

    return {
        'github_token': github_token,
        'extensions': prepare_patterns(os.getenv('EXTENSIONS', '.sol')),
        'include': prepare_patterns(os.getenv('INCLUDE', '')),
        'exclude': prepare_patterns(os.getenv('EXCLUDE', ''))
    }

def normalize_path(path: Path) -> str:
    """Normalize path string to use forward slashes"""
    return str(path).replace('\\', '/')

def run_cloc(directory: str, files: List[Path]) -> str:
    """Run cloc tool on the specified files"""
    # Create a temporary file with the list of files to analyze
    files_list = Path('out') / 'files_to_analyze.txt'
    with open(files_list, 'w') as f:
        for file_path in files:
            f.write(normalize_path(file_path) + '\n')

    # Run cloc with the files list
    try:
        result = subprocess.run(
            ['cloc', '--list-file=' + str(files_list)],
            capture_output=True,
            text=True
        )
        return result.stdout
    except subprocess.CalledProcessError as e:
        print(f"Error running cloc: {e}")
        return ""

def main():
    args = parse_arguments()

    # Handle clean mode
    if args.clean:
        clean_repositories()
        return 0

    # Require URL for normal operation
    if not args.url:
        print("Error: --url is required unless --clean is specified")
        return 1

    config = load_config()

    # Create output directory if it doesn't exist
    Path('out').mkdir(exist_ok=True)

    print("\nConfiguration:")
    print(f"Extensions: {config['extensions']}")
    print(f"Include patterns: {config['include']}")
    print(f"Exclude patterns: {config['exclude']}")
    print(f"Keep git repo: {args.keep_git}\n")

    try:
        # Parse GitHub URL - no branch or commit args
        github_info = parse_github_url(args.url)
        print(f"Parsed GitHub URL info:")
        print(f"Type: {github_info.type}")
        print(f"Owner: {github_info.owner}")
        print(f"Repo: {github_info.repo}")

        # Clone repository
        repo_handler = GitRepoHandler(github_info)
        local_path = repo_handler.clone_repo()
        print(f"\nRepository cloned to: {local_path}")

        # Get changed files
        changed_files = repo_handler.get_changed_files()
        if changed_files:
            print("\nChanged files:")
            for file in changed_files:
                print(f"- {normalize_path(Path(file).relative_to(local_path))}")

        # Initialize file analyzer
        analyzer = FileAnalyzer(
            local_path,
            config['extensions'],
            config['include'],
            config['exclude']
        )

        # Find primary files
        primary_files = analyzer.find_primary_files(changed_files if github_info.type != 'repo' else None)
        print(f"\nFound {len(primary_files)} primary files")
        print("Primary files:")
        for file in primary_files:
            print(f"- {normalize_path(Path(file).relative_to(local_path))}")

        # Generate primary files tree diagram
        OutputGenerator.generate_tree_diagram(
            primary_files,
            Path(local_path),
            Path('out') / 'files_primary.md'
        )

        # Find dependencies
        all_dependencies = analyzer.find_dependencies(primary_files)
        print(f"\nFound {len(all_dependencies)} dependency files")
        print("Dependency files:")
        for file in all_dependencies:
            print(f"- {normalize_path(Path(file).relative_to(local_path))}")

        # Generate all files tree diagram
        all_files = sorted(list(set(primary_files + all_dependencies)))
        OutputGenerator.generate_tree_diagram(
            all_files,
            Path(local_path),
            Path('out') / 'metrics.md'
        )

        # Run cloc analysis
        print("\nRunning cloc analysis...")
        cloc_output = run_cloc(local_path, all_files)
        print("\nCloc Analysis Results:")
        print(cloc_output)

        # Save cloc output
        with open(Path('out') / 'cloc_analysis.txt', 'w') as f:
            f.write(cloc_output)

    except Exception as e:
        print(f"Error: {e}")
        return 1
    finally:
        if 'repo_handler' in locals() and not args.keep_git:
            repo_handler.cleanup()
        elif args.keep_git:
            print(f"\nRepository kept at: {local_path}")

if __name__ == '__main__':
    main()