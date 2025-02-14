from dataclasses import dataclass
from urllib.parse import urlparse
import re
import os
import git
import shutil
from pathlib import Path
import tempfile
from remove_rust_t import remove_tests_from_all_rust_files

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

        # Handle commit URLs
        if 'commit' in path_parts:
            commit_idx = path_parts.index('commit')
            if len(path_parts) <= commit_idx + 1:
                raise ValueError("Invalid commit URL")
            return GitHubInfo(
                type='commit',
                owner=owner,
                repo=repo,
                commit=path_parts[commit_idx + 1]
            )

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
        self.temp_analysis_dir = None

        # Get GitHub token once during initialization
        self.github_token = os.getenv('GITHUB_TOKEN')
        if not self.github_token:
            print("Debug: Environment variables:", {k: v for k, v in os.environ.items() if 'TOKEN' in k})
            raise ValueError("GITHUB_TOKEN not found in environment variables")

    def _setup_workspace(self) -> Path:
        """Create a temporary directory for the repository"""
        workspace = Path(tempfile.gettempdir()) / "audit-metrics" / f"{self.github_info.owner}_{self.github_info.repo}"
        workspace.parent.mkdir(exist_ok=True)

        # Clean up existing workspace if it exists
        if workspace.exists():
            shutil.rmtree(workspace)

        workspace.mkdir()
        return workspace

    def clone_repo(self) -> str:
        """Clone repository and handle different GitHub URL types"""
        try:
            # Setup workspace
            self.workspace_dir = self._setup_workspace()

            # Create clone URL with token
            clone_url = f"https://{self.github_token}@github.com/{self.github_info.owner}/{self.github_info.repo}.git"

            print(f"Cloning repository from https://github.com/{self.github_info.owner}/{self.github_info.repo}.git...")

            # Clone repository
            self.repo = git.Repo.clone_from(clone_url, self.workspace_dir)

            # Handle different URL types
            if self.github_info.type == 'pr':
                self._handle_pr_fetch()
            elif self.github_info.type == 'comparison':
                self._handle_comparison_fetch()
            elif self.github_info.type == 'commit':
                print(f"Checking out commit: {self.github_info.commit}")
                self.repo.git.checkout(self.github_info.commit)
            else:
                # For regular repository, checkout default branch
                try:
                    default_branch = self.repo.git.symbolic_ref('refs/remotes/origin/HEAD').replace('refs/remotes/origin/', '')
                    print(f"Detected default branch: {default_branch}")
                    self.repo.git.checkout(default_branch)
                except git.GitCommandError:
                    print("Could not detect default branch, using current HEAD")

            return str(self.workspace_dir)

        except git.GitCommandError as e:
            print(f"Git operation failed: {e}")
            print(f"Git command that failed: {e.command}")
            print(f"Git error message:\n  {e.stderr}")
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
        """Handle fetching for commit comparison"""
        try:
            print("Fetching comparison commits...")

            # Clean up commit hashes (remove quotes and extra characters)
            base_commit = self.github_info.base_commit.strip("'\"")
            head_commit = self.github_info.head_commit.strip("'\"")

            print(f"Base commit: {base_commit}")
            print(f"Head commit: {head_commit}")

            # Fetch the specific commits
            self.repo.remote().fetch(base_commit)
            self.repo.remote().fetch(head_commit)

            # Checkout head commit
            self.repo.git.checkout(head_commit)

        except Exception as e:
            print(f"Error during comparison fetch: {e}")
            raise

    def _get_comparison_changed_files(self) -> list[str]:
        """Get files changed between the comparison commits"""
        try:
            # Clean up commit hashes
            base_commit = self.github_info.base_commit.strip("'\"")
            head_commit = self.github_info.head_commit.strip("'\"")

            # Use the specific commits for diff
            diff_str = self.repo.git.diff('--name-only', base_commit, head_commit)

            changed_files = [
                str(Path(self.workspace_dir) / f.strip())
                for f in diff_str.split('\n')
                if f.strip()
            ]

            print("\nChanged files in comparison:")
            for file in changed_files:
                print(f"- {Path(file).relative_to(self.workspace_dir)}")

            return changed_files

        except Exception as e:
            print(f"Error getting comparison changed files: {e}")
            import traceback
            traceback.print_exc()
            return []

    def get_changed_files(self) -> list[str]:
        """Get list of changed files based on the type of analysis"""
        if self.github_info.type == 'repo':
            return self._get_all_files()
        elif self.github_info.type == 'pr':
            return self._get_pr_changed_files()
        elif self.github_info.type == 'comparison':
            return self._get_comparison_changed_files()
        elif self.github_info.type == 'commit':
            return self._get_commit_changed_files()
        return []

    def _get_all_files(self) -> list[str]:
        """Get all files in the repository"""
        all_files = [str(Path(self.workspace_dir) / item)
                    for item in self.repo.git.ls_files().split('\n') if item]

        # Debug output only if verbose mode is enabled
        # print("\n=== All Repository Files ===")
        # print("\n".join(f"- {Path(f).relative_to(self.workspace_dir)}" for f in all_files))

        return all_files

    def _get_pr_changed_files(self) -> list[str]:
        """Get files changed in the pull request"""
        try:
            # Fetch PR information using GitHub API
            pr_info = self._get_pr_info()
            base_branch = pr_info['base']['ref']
            base_sha = pr_info['base']['sha']
            head_sha = pr_info['head']['sha']

            # Fetch both base and PR head
            self.repo.remotes.origin.fetch([
                f'+refs/heads/{base_branch}:refs/remotes/origin/{base_branch}',
                f'+refs/pull/{self.github_info.pr_number}/head:refs/remotes/origin/pr/{self.github_info.pr_number}'
            ])

            # Get the diff between base and PR head
            diff_str = self.repo.git.diff('--name-only', base_sha, head_sha)

            return [
                str(Path(self.workspace_dir) / f.strip())
                for f in diff_str.split('\n')
                if f.strip()
            ]

        except Exception as e:
            print(f"Error getting PR changed files: {str(e)}")
            import traceback
            traceback.print_exc()
            return []

    def _get_pr_info(self):
        """Get PR information using GitHub API"""
        import requests

        headers = {
            'Authorization': f'token {os.getenv("GITHUB_TOKEN")}',
            'Accept': 'application/vnd.github.v3+json'
        }

        url = f'https://api.github.com/repos/{self.github_info.owner}/{self.github_info.repo}/pulls/{self.github_info.pr_number}'

        response = requests.get(url, headers=headers)
        if response.status_code != 200:
            raise Exception(f"Failed to get PR info: {response.status_code} - {response.text}")

        return response.json()

    def _get_commit_changed_files(self) -> list[str]:
        """Get files changed in a specific commit"""
        try:
            # Get the parent commit
            commit = self.repo.commit(self.github_info.commit)
            parent = commit.parents[0] if commit.parents else None
            
            if parent:
                # Get diff between parent and commit
                diff_str = self.repo.git.diff('--name-only', parent.hexsha, commit.hexsha)
            else:
                # For initial commit, get all files in the commit
                diff_str = self.repo.git.show('--name-only', '--pretty=format:', commit.hexsha)
            
            changed_files = [
                str(Path(self.workspace_dir) / f.strip())
                for f in diff_str.split('\n')
                if f.strip()
            ]
            
            print("\nChanged files in commit:")
            for file in changed_files:
                print(f"- {Path(file).relative_to(self.workspace_dir)}")
            
            return changed_files
            
        except Exception as e:
            print(f"Error getting commit changed files: {e}")
            import traceback
            traceback.print_exc()
            return []

    def prepare_workspace(self) -> str:
        """Prepare workspace for analysis, including test removal"""
        # Clone the repository first
        self._clone_repository()

        # Create a temporary directory for analysis
        self.temp_analysis_dir = tempfile.mkdtemp()

        # Copy repository contents to temporary directory
        shutil.copytree(self.workspace_dir, self.temp_analysis_dir, dirs_exist_ok=True)

        # Remove tests from the temporary directory
        print("Removing test files and inline tests for accurate analysis...")
        remove_tests_from_all_rust_files(self.temp_analysis_dir)

        return self.temp_analysis_dir

    def cleanup(self):
        """Clean up temporary directories and handle locked files"""
        import time
        from pathlib import Path
        import shutil
        import os
        import stat

        def handle_error(func, path, exc_info):
            """Error handler for permission issues"""
            if not os.path.exists(path):
                return

            # Get error details
            error = exc_info[1]
            if isinstance(error, (OSError, PermissionError)):
                try:
                    # Make file writable
                    os.chmod(path, stat.S_IWRITE | stat.S_IREAD | stat.S_IEXEC)
                    # Retry the operation
                    func(path)
                except Exception as e:
                    print(f"Warning: Failed to remove {path}: {e}")
                    # On Windows, try using system commands as last resort
                    if os.name == 'nt':
                        try:
                            os.system(f'rd /s /q "{path}"')
                        except:
                            pass

        try:
            # Clean up analysis directory first
            if self.temp_analysis_dir and os.path.exists(self.temp_analysis_dir):
                print(f"Cleaning up temporary analysis directory: {self.temp_analysis_dir}")
                shutil.rmtree(self.temp_analysis_dir, onerror=handle_error)

            # Close git repo
            if self.repo:
                try:
                    self.repo.git.clear_cache()
                    self.repo.close()
                except Exception as e:
                    print(f"Warning: Error closing git repo: {e}")
                self.repo = None

            # Wait a moment before cleaning workspace
            time.sleep(1)

            # Clean up workspace directory
            if self.workspace_dir and os.path.exists(self.workspace_dir):
                print(f"Cleaning up workspace directory: {self.workspace_dir}")
                shutil.rmtree(self.workspace_dir, onerror=handle_error)

            # Clean up parent temp directory if empty
            if self.workspace_dir:
                parent_dir = Path(self.workspace_dir).parent
                try:
                    if parent_dir.exists() and not any(parent_dir.iterdir()):
                        parent_dir.rmdir()
                except Exception as e:
                    print(f"Warning: Could not remove parent directory: {e}")

        except Exception as e:
            print(f"Warning: Error during cleanup: {e}")
            # Try one last time with system commands on Windows
            if os.name == 'nt':
                if self.temp_analysis_dir:
                    os.system(f'rd /s /q "{self.temp_analysis_dir}"')
                if self.workspace_dir:
                    os.system(f'rd /s /q "{self.workspace_dir}"')

def clone_repository(github_info: GitHubInfo) -> str:
    """Helper function to clone a repository"""
    handler = GitRepoHandler(github_info)
    return handler.clone_repo()