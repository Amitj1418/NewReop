#!/usr/bin/env python3
import ast
import os
import sys
import subprocess
from pathlib import Path
from typing import List, Dict, Set, Tuple, Optional
import re
import argparse


class GitChangeDetector:
    """Detects git changes with precise method-level analysis."""

    def __init__(self, project_root: str = None):
        self.project_root = Path(project_root) if project_root else Path.cwd()

    def get_changed_files(self) -> List[str]:
        """Get list of changed files from git diff."""
        try:
            # Check unstaged changes
            result = subprocess.run(['git', 'diff', '--name-only'],
                                    capture_output=True, text=True, cwd=self.project_root)
            unstaged = [f for f in result.stdout.strip().split('\n') if f and f.endswith('.py')]

            # Check staged changes
            result = subprocess.run(['git', 'diff', '--cached', '--name-only'],
                                    capture_output=True, text=True, cwd=self.project_root)
            staged = [f for f in result.stdout.strip().split('\n') if f and f.endswith('.py')]

            return list(set(unstaged + staged))

        except subprocess.CalledProcessError:
            print("❌ Error: Not a git repository or git not available")
            return []


class CodeAnalyzer:
    """Analyzes Python code structure and changes."""

    @staticmethod
    def extract_functions_and_classes(file_path: Path) -> Dict[str, Dict]:
        """Extract all functions and classes with their line numbers."""
        if not file_path.exists():
            return {}

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()

            tree = ast.parse(content)
            elements = {}

            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    elements[node.name] = {
                        'type': 'function',
                        'line': node.lineno,
                        'class': None
                    }
                elif isinstance(node, ast.ClassDef):
                    elements[node.name] = {
                        'type': 'class',
                        'line': node.lineno,
                        'class': None
                    }
                    # Get class methods
                    for class_node in node.body:
                        if isinstance(class_node, ast.FunctionDef):
                            elements[f"{node.name}.{class_node.name}"] = {
                                'type': 'method',
                                'line': class_node.lineno,
                                'class': node.name,
                                'method': class_node.name
                            }

            return elements

        except Exception as e:
            print(f"⚠️ Error parsing {file_path}: {e}")
            return {}

    @staticmethod
    def get_changed_methods(file_path: str, project_root: Path) -> Set[str]:
        """Get specific methods/functions that changed in a file."""
        changed_methods = set()

        try:
            # Get diff with context
            result = subprocess.run(['git', 'diff', '--unified=5', file_path],
                                    capture_output=True, text=True, cwd=project_root)

            if not result.stdout:
                # Try staged changes
                result = subprocess.run(['git', 'diff', '--cached', '--unified=5', file_path],
                                        capture_output=True, text=True, cwd=project_root)

            diff_content = result.stdout
            if not diff_content:
                return changed_methods

            # Extract changed line numbers
            changed_lines = set()
            lines = diff_content.split('\n')
            current_line = 0

            for line in lines:
                if line.startswith('@@'):
                    # Extract new file line numbers
                    match = re.search(r'\+(\d+),?(\d+)?', line)
                    if match:
                        start = int(match.group(1))
                        count = int(match.group(2)) if match.group(2) else 1
                        current_line = start
                elif line.startswith('+') and not line.startswith('+++'):
                    changed_lines.add(current_line)
                    current_line += 1
                elif line.startswith('-') and not line.startswith('---'):
                    # Don't increment for removed lines
                    pass
                elif not line.startswith('-'):
                    current_line += 1

            # Map changed lines to methods
            file_elements = CodeAnalyzer.extract_functions_and_classes(Path(file_path))

            # Create method ranges
            sorted_elements = sorted(file_elements.items(), key=lambda x: x[1]['line'])

            for i, (name, info) in enumerate(sorted_elements):
                start_line = info['line']
                # Find end line (next element's start or end of file)
                if i < len(sorted_elements) - 1:
                    end_line = sorted_elements[i + 1][1]['line'] - 1
                else:
                    try:
                        with open(file_path, 'r') as f:
                            end_line = len(f.readlines())
                    except:
                        end_line = start_line + 50  # fallback

                # Check if any changed line falls in this method's range
                if any(start_line <= line <= end_line for line in changed_lines):
                    if info['type'] == 'method':
                        changed_methods.add(info['method'])
                    else:
                        changed_methods.add(name)

        except Exception as e:
            print(f"⚠️ Error analyzing changes in {file_path}: {e}")

        return changed_methods


class TestImpactAnalyzer:
    """Analyzes which tests are impacted by code changes."""

    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.tests_dir = project_root / "tests"

    def find_all_test_files(self) -> List[Path]:
        """Find all test files in the tests directory."""
        test_files = []
        if self.tests_dir.exists():
            for test_file in self.tests_dir.glob("test_*.py"):
                test_files.append(test_file)
        return test_files

    def analyze_test_dependencies(self, test_file: Path) -> Dict[str, Set[str]]:
        """Analyze which page classes and methods a test file uses."""
        dependencies = {}

        try:
            with open(test_file, 'r', encoding='utf-8') as f:
                content = f.read()

            tree = ast.parse(content)

            # Find imports from pages
            imported_pages = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module and 'pages' in node.module:
                    for alias in node.names:
                        imported_pages.add(alias.name)

            # For each imported page, find which methods are called
            for page_class in imported_pages:
                used_methods = set()

                # Find method calls on page objects
                for node in ast.walk(tree):
                    if isinstance(node, ast.Attribute):
                        # Check if it's a method call on a page object
                        if isinstance(node.value, ast.Attribute):
                            if hasattr(node.value, 'attr') and 'page' in node.value.attr.lower():
                                used_methods.add(node.attr)
                        elif isinstance(node.value, ast.Name):
                            if 'page' in node.value.id.lower():
                                used_methods.add(node.attr)

                if used_methods:
                    dependencies[page_class] = used_methods

        except Exception as e:
            print(f"⚠️ Error analyzing test dependencies in {test_file}: {e}")

        return dependencies

    def find_impacted_tests(self, changed_page: str, changed_methods: Set[str] = None) -> List[str]:
        """Find tests impacted by changes in a page class."""
        impacted_tests = []

        for test_file in self.find_all_test_files():
            dependencies = self.analyze_test_dependencies(test_file)

            # Check if this test uses the changed page
            page_name = changed_page.replace('_Page', '').replace('_page', '').replace('.py', '')

            for imported_page, used_methods in dependencies.items():
                if page_name.lower() in imported_page.lower():
                    if changed_methods is None:
                        # Entire page changed, include all tests using this page
                        impacted_tests.append(str(test_file.relative_to(self.project_root)))
                    else:
                        # Check if any changed method is used by this test
                        if changed_methods.intersection(used_methods):
                            impacted_tests.append(str(test_file.relative_to(self.project_root)))

        return impacted_tests


class AITestSelector:
    """Main AI-powered test selector."""

    def __init__(self, project_root: str = None):
        self.project_root = Path(project_root) if project_root else Path.cwd()
        self.git_detector = GitChangeDetector(project_root)
        self.impact_analyzer = TestImpactAnalyzer(self.project_root)

    def select_tests(self) -> List[str]:
        """Main method to select which tests should run."""
        changed_files = self.git_detector.get_changed_files()

        if not changed_files:
            print("🚫 No changed files detected")
            return []

        tests_to_run = []

        print(f"🔍 Analyzing {len(changed_files)} changed file(s):")

        for changed_file in changed_files:
            print(f"  📝 {changed_file}")

            # Scenario 1: Direct test file changes
            if changed_file.startswith('tests/') and changed_file.endswith('.py'):
                tests_to_run.append(changed_file)
                print(f"    ✅ Test file changed → Run: {changed_file}")
                continue

            # Scenario 2 & 3: Page class changes
            if changed_file.startswith('pages/') and changed_file.endswith('.py'):
                page_name = Path(changed_file).stem
                print(f"    🔍 Page class changed: {page_name}")

                # Get specific changed methods
                changed_methods = CodeAnalyzer.get_changed_methods(changed_file, self.project_root)

                if changed_methods:
                    print(f"    📋 Changed methods: {', '.join(changed_methods)}")
                    # Scenario 3: Method-level impact analysis
                    impacted = self.impact_analyzer.find_impacted_tests(page_name, changed_methods)
                else:
                    print(f"    📋 Entire page affected")
                    # Scenario 2: Page-level impact analysis
                    impacted = self.impact_analyzer.find_impacted_tests(page_name, None)

                tests_to_run.extend(impacted)
                if impacted:
                    print(f"    🎯 Impacted tests: {', '.join(impacted)}")
                else:
                    print(f"    ℹ️  No tests directly impacted")

        return list(set(tests_to_run))  # Remove duplicates

    def run_tests(self, test_files: List[str] = None, dry_run: bool = False) -> int:
        """Run the selected tests."""
        if test_files is None:
            test_files = self.select_tests()

        if not test_files:
            print("\n🚫 No tests to run based on current changes")
            return 0

        print(f"\n🚀 Selected {len(test_files)} test file(s):")
        for test in test_files:
            print(f"  • {test}")

        if dry_run:
            print(f"\n🧪 DRY RUN - Would execute:")
            print(f"  pytest {' '.join(test_files)} -v")
            return 0

        try:
            print(f"\n▶️  Running tests...")
            result = subprocess.run(['pytest'] + test_files + ['-v'],
                                    cwd=self.project_root)
            return result.returncode
        except Exception as e:
            print(f"❌ Error running tests: {e}")
            return 1


def main():
    """Command line interface."""
    parser = argparse.ArgumentParser(
        description='AI-powered selective test runner',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python ai_test_selector.py                    # Run selected tests
  python ai_test_selector.py --list-only       # Show which tests would run
  python ai_test_selector.py --dry-run         # Show pytest command
        """
    )

    parser.add_argument('--list-only', action='store_true',
                        help='Only show which tests would be selected')
    parser.add_argument('--dry-run', action='store_true',
                        help='Show pytest command without running it')
    parser.add_argument('--project-root', type=str, default=None,
                        help='Project root directory (default: current)')

    args = parser.parse_args()

    selector = AITestSelector(args.project_root)

    if args.list_only:
        tests = selector.select_tests()
        if tests:
            print(f"\n📋 Tests to run ({len(tests)}):")
            for test in tests:
                print(f"  • {test}")
        else:
            print("\n🚫 No tests to run")
        return 0

    return selector.run_tests(dry_run=args.dry_run)


if __name__ == '__main__':
    sys.exit(main())