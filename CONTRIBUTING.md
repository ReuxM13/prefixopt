# Contributing to prefixopt

Thank you for your interest in contributing to **prefixopt**!
This document outlines how to report issues, suggest features, and submit code changes.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Reporting Bugs](#reporting-bugs)
- [Suggesting Features](#suggesting-features)
- [Development Setup](#development-setup)
- [Code Style](#code-style)
- [Submitting a Pull Request](#submitting-a-pull-request)
- [Running Tests](#running-tests)

---

## Code of Conduct

Please read and follow our [Code of Conduct](CODE_OF_CONDUCT.md).
All interactions in this project must remain professional and respectful.

---

## Reporting Bugs

Before opening an issue, please:

1. Check the [existing issues](../../issues) to avoid duplicates.
2. Make sure You are using the latest version of prefixopt.

When reporting a bug, please include:

- A clear and descriptive title.
- Steps to reproduce the problem.
- Expected behavior and what actually happened.
- Python version (`python --version`).
- Operating system and version.
- Any relevant input data (prefix lists, files) — anonymize if needed.
- Error output or traceback if available.

---

## Suggesting Features

Feature requests are welcome. Before opening one, please:

1. Check whether a similar request already exists in [issues](../../issues).
2. Describe the use case clearly — what problem does it solve?
3. If possible, describe the expected CLI syntax or GUI behavior.

---

## Development Setup

Requires **Python 3.9 or higher**.

```bash
# Clone the repository
git clone https://github.com/ReuxM13/prefixopt.git
cd prefixopt

# Create and activate virtual environment
python -m venv venv

# Activate (Linux / macOS)
source venv/bin/activate

# Activate (Windows)
.\venv\Scripts\activate

# Install in editable mode with development dependencies
pip install -e .

# If You want GUI support
pip install -e .[gui]
```

---

## Code Style
prefixopt follows PEP 8.

Key rules:
- Maximum line length: 100 characters.
- Use type hints for all function signatures.
- All public functions and classes must have docstrings.
- Docstrings follow the Google style.
- No commented-out code in submitted changes.
- No print() statements in production code.
- Imports must be grouped: standard library → third-party → local.
## Submitting a Pull Request
1. Fork the repository and create a new branch from main:
```Bash
git checkout -b fix/your-fix-name
# or
git checkout -b feature/your-feature-name
```

2.Make your changes.

3. Run the tests and make sure they pass:
```Bash
pytest
```

4. Commit your changes with a clear message:
```Bash
git commit -m "fix: describe what was fixed"
# or
git commit -m "feat: describe what was added"
```

5. Push your branch and open a Pull Request against `main`.

6. Fill in the Pull Request description:
- What problem does it solve?
- How was it tested?
- Any related issues?
Pull Requests that break existing tests or do not follow the code style will not be merged until the issues are resolved.

## Running Tests
```Bash
pytest
```

Tests are located in the `tests/` directory.

If You are adding a new feature, please include tests that cover the new behavior.
If You are fixing a bug, please add a regression test if possible.

---

## Questions
If You have a question that is not covered here, feel free to open an issue
with the label question.
