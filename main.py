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
from remove_rust_t import remove_tests_from_all_rust_files

# Get the directory containing main.py
SCRIPT_DIR = Path(__file__).parent

# Load environment variables from .env file in the project root
env_path = SCRIPT_DIR / '.env'
load_dotenv(env_path, override=True)

# Debug print to verify token loading
token = os.getenv('GITHUB_TOKEN')
if token:
    print("GitHub token loaded successfully")
else:
    print(f"Failed to load GitHub token from {env_path}")

def parse_arguments():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(description='Audit Metrics Tool')
    parser.add_argument('--url', help='GitHub URL (repository, PR, or commit comparison)')
    parser.add_argument('--remove-tests', '--remove_tests', action='store_true',
                       help='Remove test files and inline tests from Rust files',
                       dest='remove_tests')
    parser.add_argument('--dir', help='Directory to process (defaults to current directory)',
                       default='.')
    parser.add_argument('--keep-git', action='store_true',
                       help='Keep the temporary git repository after analysis')
    parser.add_argument('--clean', action='store_true',
                       help='Clean all repositories in out/repos directory and exit')
    parser.add_argument('--debug', action='store_true',
                       help='Show debug messages')

    args = parser.parse_args()
    return args

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

def cleanup_temp_directories():
    """Clean up any leftover temporary directories"""
    import shutil
    import os
    from pathlib import Path
    import stat
    import time

    temp_dir = Path(tempfile.gettempdir()) / "audit-metrics"
    if not temp_dir.exists():
        return

    def handle_error(func, path, exc_info):
        if not os.path.exists(path):
            return
        try:
            os.chmod(path, stat.S_IWRITE | stat.S_IREAD | stat.S_IEXEC)
            func(path)
        except:
            if os.name == 'nt':
                try:
                    os.system(f'rd /s /q "{path}"')
                except:
                    pass

    print(f"\nCleaning up temporary directories...")
    try:
        # Give processes time to release handles
        time.sleep(1)
        shutil.rmtree(temp_dir, onerror=handle_error)
        print(f"Successfully cleaned up: {temp_dir}")
    except Exception as e:
        print(f"Warning: Could not fully clean up temporary directories: {e}")

def handle_test_removal(directory: str, is_remote: bool = False) -> None:
    """Handle test removal for both local and remote codebases"""
    try:
        if is_remote:
            # Parse GitHub URL and clone repository
            github_info = parse_github_url(directory)
            print(f"\nParsed GitHub URL info:")
            print(f"Type: {github_info.type}")
            print(f"Owner: {github_info.owner}")
            print(f"Repo: {github_info.repo}")

            # Clone repository
            repo_handler = GitRepoHandler(github_info, debug=args.debug)
            local_path = repo_handler.clone_repo()
            print(f"\nRepository cloned to: {local_path}")

            # Remove tests
            print("\nRemoving test files and inline tests...")
            remove_tests_from_all_rust_files(local_path)

            print(f"\nTests removed successfully from: {local_path}")
            print("Note: Changes are in the cloned directory. Original repository is unchanged.")
        else:
            # Handle local directory
            print(f"\nRemoving test files and inline tests from: {directory}")
            remove_tests_from_all_rust_files(directory)
            print("Tests removed successfully.")

    except Exception as e:
        print(f"Error during test removal: {e}")
        raise

def main():
    args = parse_arguments()

    # Clean up any leftover temp directories first
    cleanup_temp_directories()

    if args.remove_tests:
        # Determine if we're dealing with a URL or local directory
        is_remote = bool(args.url)
        target = args.url if is_remote else args.dir

        handle_test_removal(target, is_remote)
        return

    if not args.url:
        parser.error('Please provide either --url or --remove-tests')
        return

    # Handle clean mode
    if args.clean:
        clean_repositories()
        return 0

    config = load_config()

    # Create output directory if it doesn't exist
    Path('out').mkdir(exist_ok=True)

    print("\nConfiguration:")
    print(f"Extensions: {config['extensions']}")
    print(f"Include patterns: {config['include']}")
    print(f"Exclude patterns: {config['exclude']}")
    print(f"Keep git repo: {args.keep_git}\n")

    try:
        # Parse GitHub URL
        github_info = parse_github_url(args.url)
        print(f"\nParsed GitHub URL info:")
        print(f"Type: {github_info.type}")
        print(f"Owner: {github_info.owner}")
        print(f"Repo: {github_info.repo}")
        if github_info.type == 'commit':
            print(f"Commit: {github_info.commit}")

        # Clone repository
        repo_handler = GitRepoHandler(github_info, debug=args.debug)
        local_path = repo_handler.clone_repo()
        print(f"\nRepository cloned to: {local_path}")

        # If analyzing Rust files, remove tests first
        if '.rs' in config['extensions']:
            print("\nRemoving Rust test files and inline tests...")
            remove_tests_from_all_rust_files(local_path)

        # Get changed files without filtering
        changed_files = repo_handler.get_changed_files()

        # Initialize file analyzer with configuration
        analyzer = FileAnalyzer(
            local_path,
            config['extensions'],
            config['include'],
            config['exclude'],
            debug=args.debug
        )

        # Find and filter primary files
        primary_files = analyzer.find_primary_files(
            changed_files if github_info.type in ['commit', 'pr', 'comparison'] else None
        )

        if not primary_files:
            print("\nNo files found matching the specified criteria.")
            return 0

        # First Analysis: Only Primary Files
        print("\nAnalyzing primary files...")
        primary_cloc_output = run_cloc(local_path, primary_files)

        # Find dependencies
        all_dependencies = analyzer.find_dependencies(primary_files)
        all_files = sorted(list(set(primary_files + all_dependencies)))

        # Generate full analysis if there are dependencies
        full_cloc_output = None
        change_analysis = None

        if all_dependencies:
            print(f"\nFound {len(all_dependencies)} dependency files:")
            for file in all_dependencies:
                print(f"- {normalize_path(Path(file).relative_to(local_path))}")

            print("\nAnalyzing all files including dependencies...")
            full_cloc_output = run_cloc(local_path, all_files)

        # Get change analysis for PRs, commits, or comparisons
        if github_info.type == 'pr':
            print("\nAnalyzing PR changes...")
            change_analysis = repo_handler.analyze_pr_changes()
        elif github_info.type == 'commit':
            print("\nAnalyzing commit changes...")
            change_analysis = repo_handler.analyze_commit_changes()
        elif github_info.type == 'comparison':
            print("\nAnalyzing comparison changes...")
            change_analysis = repo_handler.analyze_comparison_changes()
        else:
            change_analysis = None

        # Generate combined report
        OutputGenerator.generate_combined_report(
            primary_files=primary_files,
            all_files=all_files,
            base_path=Path(local_path),
            output_file=Path('out') / 'analysis_report.md',
            primary_cloc=primary_cloc_output,
            full_cloc=full_cloc_output if full_cloc_output else primary_cloc_output,
            change_analysis=change_analysis
        )

        # Print results to console
        print("\nPrimary Files Analysis Results:")
        print(primary_cloc_output)

        if full_cloc_output:
            print("\nFull Analysis Results (including dependencies):")
            print(full_cloc_output)

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