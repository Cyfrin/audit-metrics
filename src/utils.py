import subprocess
from pathlib import Path
from typing import List, Dict
import json

def run_cloc(files: List[Path]) -> Dict[str, int]:
    """
    Run cloc tool on the specified files and return a dictionary of file paths to line counts
    """
    try:
        # Run cloc directly on each file and parse the output
        file_stats = {}
        for file_path in files:
            result = subprocess.run(
                ['cloc', '--json', str(file_path.absolute())],
                capture_output=True,
                text=True
            )

            if result.returncode == 0:
                try:
                    cloc_data = json.loads(result.stdout)
                    # Get the code count from the Solidity or Rust section
                    if 'Solidity' in cloc_data:
                        file_stats[str(file_path)] = cloc_data['Solidity']['code']
                    elif 'Rust' in cloc_data:
                        file_stats[str(file_path)] = cloc_data['Rust']['code']
                    else:
                        # Fallback: check SUM section
                        if 'SUM' in cloc_data:
                            file_stats[str(file_path)] = cloc_data['SUM']['code']
                        else:
                            file_stats[str(file_path)] = 0
                except json.JSONDecodeError:
                    print(f"Failed to parse cloc JSON output for {file_path}")
                    print(f"Raw output: {result.stdout}")
                    file_stats[str(file_path)] = 0
            else:
                print(f"Error running cloc on {file_path}: {result.stderr}")
                file_stats[str(file_path)] = 0

        return file_stats

    except Exception as e:
        print(f"Unexpected error running cloc: {e}")
        return {}