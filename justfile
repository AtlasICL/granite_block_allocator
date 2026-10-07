# Granite Block Allocator task runner. Run `just` to list the recipes.
#
# Works on macOS, Linux and Windows (PowerShell). Recipes use the virtual
# environment in ./venv, which `just setup` creates.

set windows-shell := ["powershell.exe", "-NoLogo", "-NoProfile", "-Command"]

# Python inside the virtual environment, and the system Python used to create it.
python := if os_family() == "windows" { "./venv/Scripts/python.exe" } else { "./venv/bin/python" }
system_python := if os_family() == "windows" { "python" } else { "python3" }

# The executable icon must be a .ico on Windows; other platforms build without one.
icon_flag := if os_family() == "windows" { "--icon assets/icon.ico" } else { "" }
exe_name := "GraniteBlockAllocator"

# List the available recipes
default:
    @{{just_executable()}} --list --unsorted

# Create ./venv and install the pinned runtime and development dependencies
[group('setup')]
setup:
    {{system_python}} -m venv venv
    {{python}} -m pip install --upgrade pip
    {{python}} -m pip install -r requirements-dev.txt

# List dependencies that have newer versions than the pinned ones
[group('setup')]
outdated:
    {{python}} -m pip list --outdated

# Start the app from source
[group('dev')]
run:
    {{python}} main.py

# Run the tests; extra arguments go to unittest, e.g. `just test -k Balancing`
[group('dev')]
test *args:
    {{python}} -m unittest discover -s test {{args}}

# Lint with ruff
[group('dev')]
lint:
    {{python}} -m ruff check .

# Format the code and apply safe lint fixes
[group('dev')]
fmt:
    {{python}} -m ruff format .
    {{python}} -m ruff check --fix .

# Check formatting without changing anything
[group('dev')]
fmt-check:
    {{python}} -m ruff format --check .

# Type-check with mypy
[group('dev')]
typecheck:
    {{python}} -m mypy

# Run everything CI runs: lint, format check, type-check and tests
[group('dev')]
check: lint fmt-check typecheck test

# Build the one-file executable into dist/ (runs the tests first)
[group('build')]
compile: test
    {{python}} -m PyInstaller --noconfirm --clean --onefile --windowed --name {{exe_name}} {{icon_flag}} --add-data "assets/icon.png:assets" main.py
    @echo "Built dist/{{exe_name}}"

# Delete build output and tool caches
[group('build')]
clean:
    {{system_python}} -c "import pathlib, shutil; root = pathlib.Path('.'); caches = [p for p in root.rglob('__pycache__') if 'venv' not in p.parts]; junk = [root / 'build', root / 'dist', root / '.mypy_cache', root / '.ruff_cache', *root.glob('*.spec'), *caches]; [shutil.rmtree(p) if p.is_dir() else p.unlink() for p in junk if p.exists()]"

# Print the app version
[group('release')]
version:
    @{{python}} -c "import allocator; print(allocator.__version__)"

# Set the app version in allocator/__init__.py, e.g. `just bump 0.3.0`
[group('release')]
bump new_version:
    {{python}} -c "import pathlib, re, sys; v = '{{new_version}}'; re.fullmatch(r'\d+\.\d+\.\d+', v) or sys.exit('Use a version like 0.3.0, not ' + v); p = pathlib.Path('allocator/__init__.py'); p.write_text(re.sub(r'__version__ = .*', '__version__ = ' + chr(34) + v + chr(34), p.read_text()))"
    @echo "Version set to {{new_version}}. Commit it, then run: just release {{new_version}}"

# Tag the current commit as v<version> and push the tag; GitHub Actions then builds and publishes the .exe
[group('release')]
[confirm("This pushes a version tag to GitHub, which publishes a release. Continue?")]
release version: check
    {{python}} -c "import subprocess, sys, allocator; v = allocator.__version__; v == '{{version}}' or sys.exit('allocator.__version__ is ' + v + ', not {{version}}. Run: just bump {{version}}'); subprocess.run(['git', 'status', '--porcelain', '--untracked-files=no'], capture_output=True, text=True, check=True).stdout.strip() and sys.exit('Commit or stash your changes before releasing.')"
    git tag -a v{{version}} -m "Release {{version}}"
    git push origin v{{version}}
    @echo "Pushed v{{version}}. Follow the build at https://github.com/AtlasICL/granite_block_allocator/actions"
