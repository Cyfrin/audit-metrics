import os
import re

def remove_inline_tests(file_path):
    """Remove inline tests from a Rust file at file_path."""
    with open(file_path, 'r') as file:
        lines = file.readlines()

    in_test_block = False
    brace_depth = 0
    result_lines = []

    for line in lines:
        # Detect the start of a #[cfg(test)] or #[test] block
        if re.match(r'\s*#\[(cfg\(test\)|test)\]', line):
            in_test_block = True
            continue

        # Track braces to handle nested blocks within #[cfg(test)] blocks
        if in_test_block:
            brace_depth += line.count('{')
            brace_depth -= line.count('}')
            # End the test block when all braces are closed
            if brace_depth <= 0:
                in_test_block = False
                brace_depth = 0
            continue

        # Add line if outside of test blocks
        if not in_test_block:
            result_lines.append(line)

    # Rewrite the file without the test blocks
    with open(file_path, 'w') as file:
        file.writelines(result_lines)


def remove_tests_from_all_rust_files(directory):
    """Recursively remove inline tests from all .rs files in the directory."""
    for root, _, files in os.walk(directory):
        for file in files:
            file_path = os.path.join(root, file)
            
            # Only process Rust and Cairo files
            if file.endswith('.rs') or file.endswith('.cairo'):
                if 'test' in file:
                    os.remove(file_path)
                    print(f"REMOVED: {file_path}")
                else:
                    remove_inline_tests(file_path)
                    print(f"Processed: {file_path}")


# Replace '.' with the path to your directory, or use os.getcwd() for current directory
# remove_tests_from_all_rust_files('.')