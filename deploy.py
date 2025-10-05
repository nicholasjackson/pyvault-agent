#!/usr/bin/env python3
"""
Simple deployment script for PyVault Agent to PyPI.
"""

import subprocess
import sys
import os


def run_command(command):
    """Run a shell command."""
    print(f"$ {command}")
    result = subprocess.run(command, shell=True)
    if result.returncode != 0:
        print(f"Command failed with exit code {result.returncode}")
        sys.exit(1)


def main():
    print("Building and uploading PyVault Agent...")

    # Check for PyPI token
    pypi_token = os.getenv("PYPI_TOKEN")
    if not pypi_token:
        print("Error: PYPI_TOKEN environment variable not set")
        print("Set it with: export PYPI_TOKEN=pypi-your_token_here")
        sys.exit(1)

    # Clean previous builds
    run_command("rm -rf dist/ *.egg-info/")

    # Build package
    run_command("uv build")

    # Upload to PyPI
    run_command(f"uv publish --token {pypi_token}")

    print("✅ Package uploaded successfully!")


if __name__ == "__main__":
    main()
