from dataclasses import dataclass
from urllib.parse import urlparse
import re
import os
import git
import shutil
from pathlib import Path
import tempfile

@dataclass
class GitHubInfo:
    type: str  # 'repo', 'pr', or 'comparison'
    owner: str
    repo: str
    branch: str = None
    commit: str = None
    pr_number: int = None
    base_commit: str = None
    head_commit: str = None
    local_path: str = None

class GitHubURLParser:
    def __init__(self, url: str, branch: str = None, commit: str = None):
        self.url = url
        self.specified_branch = branch
        self.specified_commit = commit

    def parse(self) -> GitHubInfo:
        """Parse GitHub URL and return structured information"""
        # Clean up the URL
        url = self.url.strip().rstrip('/')

        # Remove token if present in the URL
        url = re.sub(r'https://.*?@github\.com', 'https://github.com', url)

        # Parse URL components
        parsed = urlparse(url)
        path_parts = [p for p in parsed.path.split('/') if p]

        if not parsed.netloc.endswith('github.com'):
            raise ValueError("Not a GitHub URL")

        if len(path_parts) < 2:
            raise ValueError("Invalid GitHub URL format")

        owner = path_parts[0]
        repo = path_parts[1]

        # Handle different URL types
        if len(path_parts) == 2:
            # Basic repository URL
            return GitHubInfo(
                type='repo',
                owner=owner,
                repo=repo,
                branch=self.specified_branch or 'main',
                commit=self.specified_commit
            )

        if 'pull' in path_parts or 'pulls' in path_parts:
            # Pull request URL
            pr_idx = path_parts.index('pull' if 'pull' in path_parts else 'pulls')
            if len(path_parts) <= pr_idx + 1:
                raise ValueError("Invalid pull request URL")
            return GitHubInfo(
                type='pr',
                owner=owner,
                repo=repo,
                pr_number=int(path_parts[pr_idx + 1])
            )

        if 'compare' in path_parts:
            # Commit comparison URL
            compare_idx = path_parts.index('compare')
            if len(path_parts) <= compare_idx + 1:
                raise ValueError("Invalid comparison URL")

            comparison = path_parts[compare_idx + 1]
            # Handle different comparison formats
            if '...' in comparison:
                base, head = comparison.split('...')
            elif '..' in comparison:
                base, head = comparison.split('..')
            else:
                raise ValueError("Invalid comparison format")

            return GitHubInfo(
                type='comparison',
                owner=owner,
                repo=repo,
                base_commit=base,
                head_commit=head
            )

        # If we reach here, treat as repository URL with specific branch/commit
        return GitHubInfo(
            type='repo',
            owner=owner,
            repo=repo,
            branch=self.specified_branch or 'main',
            commit=self.specified_commit
        )

def parse_github_url(url: str) -> GitHubInfo:
    """Helper function to parse GitHub URLs"""
    # Extract branch/commit from URL if present
    branch = None
    commit = None

    if '/tree/' in url:
        base_url, ref = url.split('/tree/', 1)
        if '/' in ref:
            ref = ref.split('/')[0]
        branch = ref
        url = base_url
    elif '/commit/' in url:
        base_url, ref = url.split('/commit/', 1)
        if '/' in ref:
            ref = ref.split('/')[0]
        commit = ref
        url = base_url

    parser = GitHubURLParser(url, branch, commit)
    return parser.parse()

class GitRepoHandler:
    def __init__(self, github_info: GitHubInfo):
        self.github_info = github_info
        self.repo = None
        self.workspace_dir = None
        self.github_token = os.getenv('GITHUB_TOKEN')

    def _get_clone_url(self) -> str:
        """Get clone URL with authentication if token is available"""
        if self.github_token:
            return f"https://{self.github_token}@github.com/{self.github_info.owner}/{self.github_info.repo}.git"
        return f"https://github.com/{self.github_info.owner}/{self.github_info.repo}.git"

    def _setup_workspace(self) -> str:
        """Create a temporary directory for the repository"""
        workspace = Path(tempfile.gettempdir()) / "audit-metrics" / f"{self.github_info.owner}_{self.github_info.repo}"
        workspace.parent.mkdir(exist_ok=True)

        # Clean up existing workspace if it exists
        if workspace.exists():
            shutil.rmtree(workspace)

        workspace.mkdir()
        return str(workspace)

    def clone_repo(self) -> str:
        """Clone the repository and checkout the appropriate ref"""
        self.workspace_dir = self._setup_workspace()
        clone_url = self._get_clone_url()

        try:
            # Print URL without token for security
            print(f"Cloning repository from https://github.com/{self.github_info.owner}/{self.github_info.repo}.git...")
            self.repo = git.Repo.clone_from(clone_url, self.workspace_dir)

            if self.github_info.type == 'repo':
                self._handle_repo_checkout()
            elif self.github_info.type == 'pr':
                self._handle_pr_fetch()
            elif self.github_info.type == 'comparison':
                self._handle_comparison_fetch()

            self.github_info.local_path = self.workspace_dir
            return self.workspace_dir

        except git.GitCommandError as e:
            print(f"Git operation failed: {e}")
            self.cleanup()
            raise
        except Exception as e:
            print(f"An error occurred: {e}")
            self.cleanup()
            raise

    def _handle_repo_checkout(self):
        """Handle checkout for regular repository"""
        if self.github_info.commit:
            print(f"Checking out commit: {self.github_info.commit}")
            self.repo.git.checkout(self.github_info.commit)
        else:
            try:
                # First try to get the default branch from remote
                self.repo.git.remote('set-head', 'origin', '--auto')
                default_branch = self.repo.git.symbolic_ref('refs/remotes/origin/HEAD').replace('refs/remotes/origin/', '')
                print(f"Detected default branch: {default_branch}")
                branch = self.github_info.branch or default_branch
            except git.GitCommandError as e:
                print(f"Could not detect default branch: {e}")
                # Try master as fallback before main
                try:
                    self.repo.git.checkout('master')
                    branch = 'master'
                except git.GitCommandError:
                    print("Falling back to 'main' branch")
                    branch = 'main'

            print(f"Checking out branch: {branch}")
            try:
                self.repo.git.checkout(branch)
            except git.GitCommandError as e:
                print(f"Failed to checkout branch {branch}: {e}")
                # List available branches and checkout the first one as last resort
                remote_branches = [ref.name for ref in self.repo.remote().refs]
                if remote_branches:
                    first_branch = remote_branches[0].replace('origin/', '')
                    print(f"Attempting to checkout first available branch: {first_branch}")
                    self.repo.git.checkout(first_branch)
                else:
                    raise

    def _handle_pr_fetch(self):
        """Handle fetch for pull request"""
        print(f"Fetching PR #{self.github_info.pr_number}")
        try:
            # Modify the fetch command to use explicit refspec
            fetch_command = f"+refs/pull/{self.github_info.pr_number}/head:refs/remotes/origin/pr/{self.github_info.pr_number}"
            print(f"Executing fetch command: git fetch origin {fetch_command}")

            self.repo.remote().fetch(refspec=fetch_command)

            # Try to fetch the default branch
            try:
                print("Fetching default branch...")
                # First, try to get the default branch name
                default_branch = self.repo.git.symbolic_ref('refs/remotes/origin/HEAD').replace('refs/remotes/origin/', '')
                print(f"Detected default branch: {default_branch}")
                self.repo.remote().fetch(default_branch)
            except git.GitCommandError as e:
                print(f"Warning: Could not fetch default branch: {e}")

            # Checkout the PR using the full reference
            checkout_ref = f"origin/pr/{self.github_info.pr_number}"
            print(f"Checking out: {checkout_ref}")
            self.repo.git.checkout(checkout_ref)

        except git.GitCommandError as e:
            print(f"Error during PR fetch: {e}")
            print(f"Git command that failed: {e.command}")
            print(f"Git error message: {e.stderr}")
            raise
        except Exception as e:
            print(f"Unexpected error during PR fetch: {str(e)}")
            raise

    def _handle_comparison_fetch(self):
        """Handle fetch for comparison"""
        print("Fetching comparison commits...")
        try:
            # Fetch all refs first to ensure we have all necessary history
            print("Fetching all refs...")
            self.repo.remote().fetch('--all')

            print(f"Fetching base commit: {self.github_info.base_commit}")
            self.repo.git.fetch('origin', self.github_info.base_commit)
            print(f"Fetching head commit: {self.github_info.head_commit}")
            self.repo.git.fetch('origin', self.github_info.head_commit)

            # Verify both commits exist
            try:
                base_commit = self.repo.commit(self.github_info.base_commit)
                head_commit = self.repo.commit(self.github_info.head_commit)
                print(f"Base commit {base_commit.hexsha} and head commit {head_commit.hexsha} verified")
            except git.BadName as e:
                print(f"Could not find one of the commits: {e}")
                # Try to handle abbreviated commit hashes
                if len(self.github_info.base_commit) < 40 or len(self.github_info.head_commit) < 40:
                    try:
                        base_commit = self.repo.git.rev_parse(self.github_info.base_commit)
                        head_commit = self.repo.git.rev_parse(self.github_info.head_commit)
                        print(f"Resolved commits using rev-parse: {base_commit}, {head_commit}")
                    except git.GitCommandError:
                        raise ValueError("Could not resolve commit hashes")

            # Create and checkout a temporary branch for the head commit
            temp_branch = f"comparison_{self.github_info.head_commit[:7]}"

            # Check if the temporary branch already exists
            try:
                if temp_branch in self.repo.heads:
                    print(f"Removing existing temporary branch {temp_branch}")
                    self.repo.delete_head(temp_branch, force=True)

                print(f"Creating and checking out temporary branch {temp_branch}")
                self.repo.git.checkout(self.github_info.head_commit, b=temp_branch)
            except git.GitCommandError as e:
                print(f"Failed to create temporary branch: {e}")
                # Fallback: try to checkout the commit directly
                print("Falling back to direct commit checkout")
                self.repo.git.checkout(self.github_info.head_commit)

        except git.GitCommandError as e:
            print(f"Git operation failed during comparison fetch: {e}")
            print(f"Git command that failed: {e.command}")
            print(f"Git error message: {e.stderr}")
            raise
        except Exception as e:
            print(f"Unexpected error during comparison fetch: {str(e)}")
            raise

    def get_changed_files(self) -> list[str]:
        """Get list of changed files based on the type of analysis"""
        if self.github_info.type == 'repo':
            return self._get_all_files()
        elif self.github_info.type == 'pr':
            return self._get_pr_changed_files()
        elif self.github_info.type == 'comparison':
            return self._get_comparison_changed_files()
        return []

    def _get_all_files(self) -> list[str]:
        """Get all files in the repository with proper include/exclude filtering"""
        all_files = [str(Path(self.workspace_dir) / item)
                    for item in self.repo.git.ls_files().split('\n') if item]

        print("\n=== All Repository Files ===")
        print("\n".join(f"- {Path(f).relative_to(self.workspace_dir)}" for f in all_files))

        # Get environment variables
        extensions = os.getenv('EXTENSIONS', '').strip().split(',')
        includes = [p.strip() for p in os.getenv('INCLUDE', '').split(',') if p.strip()]
        excludes = [p.strip() for p in os.getenv('EXCLUDE', '').split(',') if p.strip()]

        def glob_to_regex(pattern: str) -> str:
            if not pattern:
                return ".*"  # Match everything if pattern is empty

            # Replace directory separators with forward slashes
            pattern = pattern.replace('\\', '/')

            # Escape special regex characters except * and ?
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

            # Convert glob patterns to regex patterns
            pattern = pattern.replace('*', '.*').replace('?', '.')

            return pattern

        # Compile regex patterns
        include_patterns = [re.compile(glob_to_regex(p)) for p in includes] if includes else [re.compile(".*")]
        exclude_patterns = [re.compile(glob_to_regex(p)) for p in excludes] if excludes else []

        print(f"\nFilter Settings:")
        print(f"Extensions: {extensions}")
        print(f"Include patterns: {[p.pattern for p in include_patterns]}")
        print(f"Exclude patterns: {[p.pattern for p in exclude_patterns]}\n")

        # Convert paths to Path objects for better path manipulation
        files = [Path(f) for f in all_files]

        def should_include_file(file_path: Path) -> bool:
            # Normalize path to use forward slashes
            rel_path = str(file_path.relative_to(self.workspace_dir)).replace('\\', '/')

            # Check extensions
            if extensions and not any(str(file_path).lower().endswith(ext.lower()) for ext in extensions):
                # print(f"Skipping {rel_path} - extension not in {extensions}")
                return False

            # Check excludes first
            for exclude_pattern in exclude_patterns:
                if exclude_pattern.search(rel_path):
                    # print(f"Skipping {rel_path} - matches exclude pattern '{exclude_pattern.pattern}'")
                    return False

            # Check includes
            for include_pattern in include_patterns:
                if include_pattern.search(rel_path):
                    # print(f"Including {rel_path} - matches include pattern '{include_pattern.pattern}'")
                    return True

            # print(f"Skipping {rel_path} - doesn't match any include patterns")
            return False

        filtered_files = [str(f) for f in files if should_include_file(f)]

        print("\n=== Files After Filtering ===")
        print("\n".join(f"- {Path(f).relative_to(self.workspace_dir)}" for f in filtered_files))
        print("\n")

        return filtered_files

    def _get_pr_changed_files(self) -> list[str]:
        """Get files changed in the pull request with filtering"""
        try:
            # Get the default branch name or fallback to main
            try:
                default_branch = self.repo.git.symbolic_ref('refs/remotes/origin/HEAD').replace('refs/remotes/origin/', '')
            except git.GitCommandError:
                print("Warning: Could not detect default branch, falling back to 'main'")
                default_branch = 'main'

            print(f"Using {default_branch} as base branch for comparison")

            # Get the PR commit
            pr_ref = f"origin/pr/{self.github_info.pr_number}"
            pr_commit = self.repo.commit(pr_ref)
            print(f"PR HEAD commit: {pr_commit.hexsha}")

            try:
                # Try to get the merge base
                merge_base = self.repo.git.merge_base(f'origin/{default_branch}', pr_commit.hexsha).strip()
                print(f"Found merge base commit: {merge_base}")
                diff_str = self.repo.git.diff(f'{merge_base}...{pr_commit.hexsha}', name_only=True)
            except git.GitCommandError as e:
                print(f"Warning: Could not find merge base, falling back to direct diff: {e}")
                # Fallback to comparing with the current HEAD~1
                diff_str = self.repo.git.diff('HEAD~1', name_only=True)

            all_changed_files = [
                str(Path(self.workspace_dir) / f.strip())
                for f in diff_str.split('\n')
                if f.strip()
            ]

            print("\n=== Changed Files in PR ===")
            print("\n".join(f"- {Path(f).relative_to(self.workspace_dir)}" for f in all_changed_files))

            # Reuse the _get_all_files method's filtering logic
            temp_files = self._get_all_files()
            filtered_changed_files = [f for f in all_changed_files if f in temp_files]

            print("\n=== Final Files for Analysis (PR) ===")
            print("\n".join(f"- {Path(f).relative_to(self.workspace_dir)}" for f in filtered_changed_files))
            print("\n")

            return filtered_changed_files

        except Exception as e:
            print(f"Error getting changed files: {str(e)}")
            import traceback
            traceback.print_exc()
            return []

    def _get_comparison_changed_files(self) -> list[str]:
        """Get files changed between the comparison commits with filtering"""
        diff_index = self.repo.commit(self.github_info.head_commit).diff(self.github_info.base_commit)
        all_changed_files = [str(Path(self.workspace_dir) / item.a_path) for item in diff_index]

        print("\n=== Changed Files in Comparison ===")
        print("\n".join(f"- {Path(f).relative_to(self.workspace_dir)}" for f in all_changed_files))

        # Reuse the _get_all_files method's filtering logic
        temp_files = self._get_all_files()
        filtered_changed_files = [f for f in all_changed_files if f in temp_files]

        print("\n=== Final Files for Analysis (Comparison) ===")
        print("\n".join(f"- {Path(f).relative_to(self.workspace_dir)}" for f in filtered_changed_files))
        print("\n")

        return filtered_changed_files

    def cleanup(self):
        """Clean up the workspace with retry and force on Windows"""
        if not self.workspace_dir or not os.path.exists(self.workspace_dir):
            return

        if self.repo:
            try:
                self.repo.git.clear_cache()
                self.repo.close()
            except:
                pass
            self.repo = None

        def on_error(func, path, exc_info):
            """Error handler for shutil.rmtree"""
            import stat
            # If permission error, try to change permissions
            if isinstance(exc_info[1], PermissionError):
                try:
                    os.chmod(path, stat.S_IWRITE)
                    func(path)
                except:
                    pass

        # Wait a bit before trying to remove
        import time
        time.sleep(1)

        try:
            shutil.rmtree(self.workspace_dir, onerror=on_error)
        except Exception as e:
            print(f"Warning: Could not fully remove temporary directory: {e}")
            # On Windows, try using system commands as last resort
            if os.name == 'nt':
                try:
                    os.system(f'rd /s /q "{self.workspace_dir}"')
                except:
                    pass

def clone_repository(github_info: GitHubInfo) -> str:
    """Helper function to clone a repository"""
    handler = GitRepoHandler(github_info)
    return handler.clone_repo()