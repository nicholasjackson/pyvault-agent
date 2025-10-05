#!/usr/bin/env python3
"""
Deployment script for PyVault Agent to PyPI.

This script handles:
- Version validation
- Package building
- Publishing to PyPI (test and production)
- Git tagging

Requirements:
- twine: pip install twine
- build: pip install build
- Git repository with clean working directory

Usage:
    python deploy.py --version 0.1.0 --test    # Deploy to test PyPI
    python deploy.py --version 0.1.0           # Deploy to production PyPI
"""

import argparse
import subprocess
import sys
import os
import re
from pathlib import Path


class Colors:
    """ANSI color codes for terminal output."""
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    MAGENTA = '\033[95m'
    CYAN = '\033[96m'
    WHITE = '\033[97m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'
    END = '\033[0m'


def print_colored(message: str, color: str = Colors.WHITE) -> None:
    """Print a colored message to stdout."""
    print(f"{color}{message}{Colors.END}")


def print_step(step: str) -> None:
    """Print a step header."""
    print_colored(f"\n🚀 {step}", Colors.CYAN + Colors.BOLD)


def print_success(message: str) -> None:
    """Print a success message."""
    print_colored(f"✅ {message}", Colors.GREEN)


def print_error(message: str) -> None:
    """Print an error message."""
    print_colored(f"❌ {message}", Colors.RED)


def print_warning(message: str) -> None:
    """Print a warning message."""
    print_colored(f"⚠️  {message}", Colors.YELLOW)


def run_command(command: str, check: bool = True) -> subprocess.CompletedProcess:
    """Run a shell command and return the result."""
    print_colored(f"$ {command}", Colors.MAGENTA)
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            check=check
        )
        if result.stdout:
            print(result.stdout.strip())
        return result
    except subprocess.CalledProcessError as e:
        print_error(f"Command failed with exit code {e.returncode}")
        if e.stderr:
            print_error(f"Error: {e.stderr.strip()}")
        if check:
            sys.exit(1)
        return e


def validate_version(version: str) -> bool:
    """Validate version format (semantic versioning)."""
    pattern = r'^\d+\.\d+\.\d+(?:-[a-zA-Z0-9]+(?:\.[a-zA-Z0-9]+)*)?$'
    return bool(re.match(pattern, version))


def get_current_version() -> str:
    """Get current version from pyproject.toml."""
    pyproject_path = Path("pyproject.toml")
    if not pyproject_path.exists():
        print_error("pyproject.toml not found")
        sys.exit(1)

    content = pyproject_path.read_text()
    version_match = re.search(r'version\s*=\s*"([^"]+)"', content)
    if not version_match:
        print_error("Could not find version in pyproject.toml")
        sys.exit(1)

    return version_match.group(1)


def update_version(new_version: str) -> None:
    """Update version in pyproject.toml and __init__.py."""
    print_step("Updating version files")

    # Update pyproject.toml
    pyproject_path = Path("pyproject.toml")
    content = pyproject_path.read_text()
    content = re.sub(
        r'version\s*=\s*"[^"]+"',
        f'version = "{new_version}"',
        content
    )
    pyproject_path.write_text(content)
    print_success(f"Updated version in pyproject.toml to {new_version}")

    # Update __init__.py
    init_path = Path("vault_agent/__init__.py")
    if init_path.exists():
        content = init_path.read_text()
        content = re.sub(
            r'__version__\s*=\s*"[^"]+"',
            f'__version__ = "{new_version}"',
            content
        )
        init_path.write_text(content)
        print_success(f"Updated version in __init__.py to {new_version}")


def check_git_status() -> None:
    """Check if git working directory is clean."""
    print_step("Checking git status")

    result = run_command("git status --porcelain", check=False)
    if result.stdout.strip():
        print_warning("Working directory has uncommitted changes:")
        print(result.stdout)
        response = input("Continue anyway? (y/N): ")
        if response.lower() != 'y':
            print_error("Deployment cancelled")
            sys.exit(1)
    else:
        print_success("Working directory is clean")


def clean_build_artifacts() -> None:
    """Clean previous build artifacts."""
    print_step("Cleaning build artifacts")

    artifacts = ["build/", "dist/", "*.egg-info/"]
    for artifact in artifacts:
        run_command(f"rm -rf {artifact}", check=False)

    print_success("Build artifacts cleaned")


def run_tests() -> None:
    """Run tests before deployment."""
    print_step("Running tests")

    # Check if pytest is available
    result = run_command("which pytest", check=False)
    if result.returncode != 0:
        print_warning("pytest not found, skipping tests")
        return

    # Run unit tests only (not functional tests that require Vault)
    result = run_command("pytest tests/test_cache.py -v", check=False)
    if result.returncode != 0:
        print_error("Tests failed")
        response = input("Continue deployment anyway? (y/N): ")
        if response.lower() != 'y':
            sys.exit(1)
    else:
        print_success("Tests passed")


def build_package() -> None:
    """Build the package."""
    print_step("Building package")

    run_command("python -m build")
    print_success("Package built successfully")


def upload_to_pypi(test: bool = False) -> None:
    """Upload package to PyPI."""
    repository = "testpypi" if test else "pypi"
    repository_name = "Test PyPI" if test else "PyPI"

    print_step(f"Uploading to {repository_name}")

    # Check if twine is available
    result = run_command("which twine", check=False)
    if result.returncode != 0:
        print_error("twine not found. Install with: pip install twine")
        sys.exit(1)

    if test:
        upload_cmd = "twine upload --repository testpypi dist/*"
    else:
        upload_cmd = "twine upload dist/*"

    run_command(upload_cmd)
    print_success(f"Package uploaded to {repository_name}")

    # Print installation instructions
    if test:
        print_colored(f"\n📦 Test installation:", Colors.BLUE + Colors.BOLD)
        print_colored(f"pip install --index-url https://test.pypi.org/simple/ pyvault-agent", Colors.BLUE)
    else:
        print_colored(f"\n📦 Installation:", Colors.BLUE + Colors.BOLD)
        print_colored(f"pip install pyvault-agent", Colors.BLUE)


def create_git_tag(version: str) -> None:
    """Create and push git tag."""
    print_step("Creating git tag")

    tag_name = f"v{version}"

    # Check if tag already exists
    result = run_command(f"git tag -l {tag_name}", check=False)
    if result.stdout.strip():
        print_warning(f"Tag {tag_name} already exists")
        return

    # Create tag
    run_command(f"git tag -a {tag_name} -m 'Release version {version}'")
    print_success(f"Created tag {tag_name}")

    # Push tag
    response = input("Push tag to remote? (y/N): ")
    if response.lower() == 'y':
        run_command(f"git push origin {tag_name}")
        print_success(f"Pushed tag {tag_name} to remote")


def main():
    """Main deployment function."""
    parser = argparse.ArgumentParser(description="Deploy PyVault Agent to PyPI")
    parser.add_argument(
        "--version",
        help="Version to deploy (e.g., 0.1.0)",
        required=True
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="Deploy to Test PyPI instead of production"
    )
    parser.add_argument(
        "--skip-tests",
        action="store_true",
        help="Skip running tests"
    )
    parser.add_argument(
        "--skip-git-check",
        action="store_true",
        help="Skip git status check"
    )
    parser.add_argument(
        "--no-tag",
        action="store_true",
        help="Don't create git tag"
    )

    args = parser.parse_args()

    # Validate version format
    if not validate_version(args.version):
        print_error(f"Invalid version format: {args.version}")
        print_error("Use semantic versioning (e.g., 1.0.0, 1.0.0-beta1)")
        sys.exit(1)

    print_colored(f"\n🎯 Deploying PyVault Agent v{args.version}", Colors.CYAN + Colors.BOLD)
    print_colored(f"Target: {'Test PyPI' if args.test else 'Production PyPI'}", Colors.CYAN)

    try:
        # Pre-deployment checks
        if not args.skip_git_check:
            check_git_status()

        # Update version
        current_version = get_current_version()
        if current_version != args.version:
            print_colored(f"Updating version from {current_version} to {args.version}", Colors.YELLOW)
            update_version(args.version)
        else:
            print_success(f"Version already set to {args.version}")

        # Run tests
        if not args.skip_tests:
            run_tests()

        # Build and deploy
        clean_build_artifacts()
        build_package()
        upload_to_pypi(test=args.test)

        # Create git tag for production releases
        if not args.test and not args.no_tag:
            create_git_tag(args.version)

        print_colored(f"\n🎉 Deployment successful!", Colors.GREEN + Colors.BOLD)
        print_colored(f"PyVault Agent v{args.version} is now available!", Colors.GREEN)

    except KeyboardInterrupt:
        print_error("\nDeployment cancelled by user")
        sys.exit(1)
    except Exception as e:
        print_error(f"Deployment failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()