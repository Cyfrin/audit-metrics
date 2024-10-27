# Audit Metrics Tool

A Python-based tool for analyzing GitHub repositories, pull requests, and commit comparisons.
It helps identify and analyze Solidity files and their dependencies, generating metrics and visualizations useful for code audits.

## Features

- Analyzes GitHub repositories, pull requests, or commit comparisons
- Identifies primary Solidity files and their dependencies
- Generates tree diagrams of file structures
- Produces code metrics using CLOC (Count Lines of Code)
- Configurable file extensions, include/exclude patterns
- Supports custom filtering of files and dependencies

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
EXTENSIONS=.sol
INCLUDE=
EXCLUDE=node_modules/*,*/@openzeppelin/*,*/solmate/*
```

## Usage

Run the tool with a GitHub URL:

```bash
python main.py --url <github-url>
```

The URL can be:
- Repository URL: `https://github.com/owner/repo`
- Pull Request URL: `https://github.com/owner/repo/pull/123`
- Commit comparison URL: `https://github.com/owner/repo/compare/commit1...commit2`

## Configuration

Configure the tool through environment variables in `.env`:

- `GITHUB_TOKEN`: Your GitHub Personal Access Token (required)
- `EXTENSIONS`: Comma-separated list of file extensions to analyze (default: `.sol`)
- `INCLUDE`: Comma-separated list of patterns to include
- `EXCLUDE`: Comma-separated list of patterns to exclude

## Output

The tool generates output in the `out` directory:

- `files_primary.md`: Tree diagram of primary files
- `metrics.md`: Tree diagram of all files including dependencies
- `files_to_analyze.txt`: List of files analyzed
- `cloc_analysis.txt`: CLOC analysis results

## Example

```bash
python main.py --url https://github.com/owner/repo/pull/123
```

Sample output:
```
Configuration:
Extensions: ['.sol']
Include patterns: []
Exclude patterns: ['node_modules/*']

Parsed GitHub URL info:
Type: pull
Owner: owner
Repo: repo

Repository cloned to: /tmp/repo
...
```

## Contributing

1. Fork the repository
2. Create your feature branch
3. Commit your changes
4. Push to the branch
5. Create a new Pull Request

## License

[Insert your license here]

## Troubleshooting

Common issues:

1. `GITHUB_TOKEN not found`: Ensure you have created a `.env` file with your GitHub token
2. `cloc: command not found`: Install CLOC using your package manager
3. Clone errors: Check your GitHub token has sufficient permissions