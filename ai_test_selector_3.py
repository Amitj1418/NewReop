#!/usr/bin/env python3
import ast
import os
import sys
import difflib
import subprocess
from pathlib import Path
from typing import List, Dict, Set, Tuple
import importlib.util


class ChangeDetector:
    """Detects changes in Python files and identifies impact on test cases."""

    def __init__(self, project_root: str = None):
        self.project_root = Path(project_root) if project_root else Path.cwd()
        self.pages_dir = self.project_root / "pages"
        self.tests_dir = self.project_root / "tests"

    def get_git_changes(self) -> Tuple[List[str], List[str]]:
        """Get modified and added files from git status."""
        try:
            # Get staged changes
            result = subprocess.run(['git', 'diff', '--cached', '--name-only'],
                                    capture_output=True, text=True, cwd=self.project_root)
            staged_files = [f for f in result.stdout.strip().split('\n') if f.endswith('.py')]

            # Get unstaged changes
            result = subprocess.run(['git', 'diff', '--name-only'],
                                    capture_output=True, text=True, cwd=self.project_root)
            unstaged_files = [f for f in result.stdout.strip().split('\n') if f.endswith('.py')]

            return staged_files, unstaged_files
        except subprocess.CalledProcessError:
            return [], []

    def extract_methods_from_file(self, file_path: Path) -> Dict[str, int]:
        """Extract all method names and their line numbers from a Python file."""
        methods = {}
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()

            tree = ast.parse(content)

            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    methods[node.name] = node.lineno
                elif isinstance(node, ast.ClassDef):
                    for class_node in node.body:
                        if isinstance(class_node, ast.FunctionDef):
                            methods[f"{node.name}.{class_node.name}"] = class_node.lineno

        except Exception as e:
            print(f"Error parsing {file_path}: {e}")

        return methods

    def get_changed_methods(self, file_path: str) -> Set[str]:
        """Identify which specific methods changed in a file."""
        changed_methods = set()

        try:
            # Get the diff for the specific file
            result = subprocess.run(['git', 'diff', '--unified=0', file_path],
                                    capture_output=True, text=True, cwd=self.project_root)
            diff_output = result.stdout

            if not diff_output:
                # Try staged changes
                result = subprocess.run(['git', 'diff', '--cached', '--unified=0', file_path],
                                        capture_output=True, text=True, cwd=self.project_root)
                diff_output = result.stdout

            # Parse diff to find changed line numbers
            changed_lines = set()
            for line in diff_output.split('\n'):
                if line.startswith('@@'):
                    # Extract line numbers from @@ -old_start,old_count +new_start,new_count @@
                    parts = line.split(' ')
                    if len(parts) >= 3:
                        new_part = parts[2]  # +new_start,new_count
                        if ',' in new_part:
                            start_line = int(new_part[1:].split(',')[0])
                            count = int(new_part.split(',')[1])
                            changed_lines.update(range(start_line, start_line + count))
                        else:
                            changed_lines.add(int(new_part[1:]))

            # Map changed lines to methods
            file_methods = self.extract_methods_from_file(Path(file_path))
            for method, line_no in file_methods.items():
                if line_no in changed_lines:
                    changed_methods.add(method)

        except Exception as e:
            print(f"Error analyzing changes in {file_path}: {e}")

        return changed_methods

    def find_test_dependencies(self, page_class: str, changed_methods: Set[str] = None) -> List[str]:
        """Find test files that use the given page class and specific methods."""
        dependent_tests = []

        # Search all test files for imports and usage
        for test_file in self.tests_dir.glob("test_*.py"):
            try:
                with open(test_file, 'r', encoding='utf-8') as f:
                    content = f.read()

                # Check if the page class is imported
                if page_class in content:
                    tree = ast.parse(content)

                    # If no specific methods changed, return the test file
                    if not changed_methods:
                        dependent_tests.append(str(test_file.relative_to(self.project_root)))
                        continue

                    # Check if specific methods are used
                    for node in ast.walk(tree):
                        if isinstance(node, ast.Attribute):
                            method_name = node.attr
                            if method_name in changed_methods:
                                dependent_tests.append(str(test_file.relative_to(self.project_root)))
                                break
                        elif isinstance(node, ast.Call):
                            if hasattr(node.func, 'attr'):
                                method_name = node.func.attr
                                if method_name in changed_methods:
                                    dependent_tests.append(str(test_file.relative_to(self.project_root)))
                                    break

            except Exception as e:
                print(f"Error analyzing test file {test_file}: {e}")

        return list(set(dependent_tests))  # Remove duplicates


class AITestSelector:
    """Main class that orchestrates intelligent test selection."""

    def __init__(self, project_root: str = None):
        self.project_root = Path(project_root) if project_root else Path.cwd()
        self.change_detector = ChangeDetector(project_root)

    def get_tests_to_run(self) -> List[str]:
        """Main method to determine which tests should be run based on changes."""
        tests_to_run = []

        # Scenario 1: Check for direct test file changes
        staged_files, unstaged_files = self.change_detector.get_git_changes()
        all_changed_files = list(set(staged_files + unstaged_files))

        for changed_file in all_changed_files:
            file_path = Path(changed_file)

            # Scenario 1: If test file changed, run only that test
            if file_path.name.startswith('test_') and file_path.suffix == '.py':
                tests_to_run.append(changed_file)
                print(f"✅ Test file changed: {changed_file}")
                continue

            # Scenario 2 & 3: If page class changed, find impacted tests
            if file_path.parent.name == 'pages' and file_path.suffix == '.py':
                page_class = file_path.stem
                print(f"🔍 Page class changed: {page_class}")

                # Get specific methods that changed
                changed_methods = self.change_detector.get_changed_methods(changed_file)

                if changed_methods:
                    print(f"📝 Changed methods: {', '.join(changed_methods)}")
                    # Scenario 3: Run tests impacted by specific method changes
                    dependent_tests = self.change_detector.find_test_dependencies(
                        page_class, changed_methods)
                else:
                    print(f"📝 Entire page class affected")
                    # Scenario 2: Run all tests using this page class
                    dependent_tests = self.change_detector.find_test_dependencies(page_class)

                tests_to_run.extend(dependent_tests)
                print(f"🎯 Impacted tests: {', '.join(dependent_tests) if dependent_tests else 'None'}")

        return list(set(tests_to_run))  # Remove duplicates

    def run_selected_tests(self, test_files: List[str] = None, dry_run: bool = False) -> int:
        """Run the selected test files using pytest."""
        if test_files is None:
            test_files = self.get_tests_to_run()

        if not test_files:
            print("🚫 No tests to run based on current changes.")
            return 0

        print(f"\n🚀 Running {len(test_files)} test file(s):")
        for test_file in test_files:
            print(f"  • {test_file}")

        if dry_run:
            print("\n🧪 DRY RUN - Tests would be executed with:")
            pytest_cmd = ['pytest'] + test_files + ['-v']
            print(f"  {' '.join(pytest_cmd)}")
            return 0

        try:
            # Run pytest with the selected test files
            result = subprocess.run(['pytest'] + test_files + ['-v'],
                                    cwd=self.project_root)
            return result.returncode
        except subprocess.CalledProcessError as e:
            print(f"❌ Error running tests: {e}")
            return 1


def main():
    """Command line interface for the AI Test Selector."""
    import argparse

    parser = argparse.ArgumentParser(description='AI-powered selective test runner')
    parser.add_argument('--dry-run', action='store_true',
                        help='Show which tests would be run without executing them')
    parser.add_argument('--project-root', type=str, default=None,
                        help='Root directory of the project (default: current directory)')
    parser.add_argument('--list-only', action='store_true',
                        help='Only list the tests that would be run')

    args = parser.parse_args()

    selector = AITestSelector(args.project_root)

    if args.list_only:
        tests = selector.get_tests_to_run()
        if tests:
            print("Tests to run:")
            for test in tests:
                print(f"  • {test}")
        else:
            print("No tests to run based on current changes.")
        return 0

    return selector.run_selected_tests(dry_run=args.dry_run)


if __name__ == '__main__':
    sys.exit(main())