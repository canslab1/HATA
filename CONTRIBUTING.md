# Contributing to HATA

Thank you for your interest in contributing to HATA! This document provides guidelines for contributing to this project.

## How to Contribute

### Reporting Issues

- Use the [GitHub Issues](https://github.com/canslab1/HATA/issues) page to report bugs or request features.
- When reporting a bug, please include:
  - Python version (`python --version`)
  - Operating system
  - Steps to reproduce the issue
  - Expected vs. actual behavior
  - Relevant error messages or screenshots

### Submitting Changes

1. **Fork** the repository on GitHub.
2. **Clone** your fork locally:
   ```bash
   git clone https://github.com/YOUR_USERNAME/HATA.git
   cd HATA
   ```
3. **Create a branch** for your changes:
   ```bash
   git checkout -b feature/your-feature-name
   ```
4. **Make your changes** and test them.
5. **Commit** with a clear message:
   ```bash
   git commit -m "Add: brief description of your change"
   ```
6. **Push** to your fork:
   ```bash
   git push origin feature/your-feature-name
   ```
7. Open a **Pull Request** on GitHub.

## Development Setup

```bash
git clone https://github.com/canslab1/HATA.git
cd HATA
pip install -r requirements.txt
python run_hata.py  # Verify the GUI launches correctly
```

## Code Style

- Follow [PEP 8](https://peps.python.org/pep-0008/) conventions.
- Use type hints where practical.
- Keep functions focused and reasonably sized.
- Document non-obvious algorithms with comments referencing the paper.

## Project Architecture

| Module | Responsibility |
|--------|---------------|
| `hata/engine.py` | Core HATA algorithm (5-phase arc classification) |
| `hata/cli.py` | Command-line interface |
| `hata/plotting.py` | Matplotlib visualizations |
| `hata/excel_writer.py` | Excel and CSV output |
| `hata/constants.py` | Configuration constants and datasets |
| `hata/gui/` | PySide6 graphical interface |

## Questions?

Feel free to open an issue for any questions about the codebase or contribution process.
