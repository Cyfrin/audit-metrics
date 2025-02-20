# Audit Metrics Tool

Audit Metrics Tool is a Python-based utility designed to analyze GitHub repositories, pull requests, and commit comparisons.
It identifies primary source files, analyzes their dependencies, and generates actionable metrics, making it an essential tool for code audits, dependency tracking, and repository analysis.

## Features

- Analyzes GitHub repositories, pull requests, or commit comparisons
- Identifies primary source files and their dependencies
- Generates tree diagrams of file structures
- Produces code metrics using CLOC (Count Lines of Code)
- Advanced pattern matching for file inclusion/exclusion
- Supports custom filtering of files and dependencies
- Automatic test removal for Rust codebases
- Detailed change analysis for PRs, commits, and commit comparisons

## Prerequisites

- Python 3.7+
- Git
- [CLOC](https://github.com/AlDanial/cloc) installed and available in PATH
- GitHub Personal Access Token

## Installation

1. Clone this repository:
```bash
git clone <repository-url>
cd audit-metrics-tool
```

2. Install required Python packages:
```bash
pip install -r requirements.txt
```

3. Create a `.env` file in the project root:
```env
GITHUB_TOKEN=your_github_token_here
EXTENSIONS=.sol,.rs
INCLUDE=
EXCLUDE=*/test/*,test/*,.t.sol,Test.sol,Mock.sol,*/mock/*,forge-std/*,*/script/*
```

## Usage

### Analyzing Code

Run the tool with a GitHub URL:

```bash
python main.py --url <github-url>
```

For pull requests, commits, and commit comparisons, the tool performs a detailed change analysis that includes:
- Total number of files changed
- Number of additions and deletions
- Per-file change statistics
- Filtered changes based on configured patterns

### Pattern Matching

The tool supports advanced pattern matching for file inclusion/exclusion:

- Directory patterns:
  - `*/test/*` matches any file in a test directory at any depth
  - `test/*` matches files directly under the test directory
  - `*/mock/*` matches any file in a mock directory at any depth

- File patterns:
  - `*.t.sol` matches test files with .t.sol extension
  - `Test.sol` matches files named Test.sol
  - `Mock.sol` matches files named Mock.sol

Patterns are case-insensitive and support both forward and backward slashes.

### Test Removal

The tool can remove test files and inline tests from Rust files. This includes:
- Removing files with 'test' in their name
- Removing inline test modules marked with #[cfg(test)] or #[test]
- Excluding test-only code blocks

You can use the --remove-tests flag to:
- Clean tests from a local directory
- Clone and clean tests from a remote repository

For local directory:

```bash
python main.py --remove-tests [--dir <directory>]
```

For remote repository:

```bash
python main.py --remove-tests --url <github-url>
```

### Usage Examples

The URL can be:
- Repository URL: `https://github.com/owner/repo`
- Pull Request URL: `https://github.com/owner/repo/pull/123`
- Commit comparison URL: `https://github.com/owner/repo/compare/commit1...commit2`

```bash
# full repository
python main.py --url https://github.com/Cyfrin/cyfrin-attester

# pull request
python main.py --url https://github.com/Cyfrin/cyfrin-attester/pull/2

# commit comparison
python main.py --url https://github.com/Cyfrin/chainlink-gmx-automation/compare/f64416650341d1262cc63ccf4e4aff114c98d922...9f7f875fe034e4c430b64933e316831b5b5077fe

# full repository at a specific commit
python main.py --url https://github.com/Cyfrin/chainlink-gmx-automation/tree/d8603d2654513f57eb0471239966449d7f693426

# changes in single commit
python main.py --url https://github.com/Cyfrin/chainlink-gmx-automation/commit/d8603d2654513f57eb0471239966449d7f693426

# rust repository
python main.py --url https://github.com/Cyfrin/aderyn

# clone rust repo and remove tests on local
python main.py --remove-test --url https://github.com/Cyfrin/aderyn
```

## Configuration

Configure the tool through environment variables in `.env`:

- `GITHUB_TOKEN`: Your GitHub Personal Access Token (required)
- `EXTENSIONS`: Comma-separated list of file extensions to analyze (e.g., `.sol,.rs`)
- `INCLUDE`: Comma-separated list of patterns to include
- `EXCLUDE`: Comma-separated list of patterns to exclude (supports advanced pattern matching)

## Output

The tool generates output in the `out` directory:

- `analysis_report.md`: Complete analysis report including:
  - List of primary files analyzed
  - Dependencies (if any)
  - CLOC analysis results
  - Total files and nSLOC counts
  - Change analysis for PRs, commits, and comparisons:
    - Files changed with additions/deletions
    - Total changes per file
    - Changes filtered by configured patterns

## Contributing

1. Fork the repository
2. Create your feature branch
3. Commit your changes
4. Push to the branch
5. Create a new Pull Request
