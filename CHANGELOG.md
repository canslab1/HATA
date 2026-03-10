# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## v2.0.0 (2026-01-01)

Complete rewrite from Python 2.7 to Python 3.

### Added
- PySide6 graphical user interface with real-time progress display
- Command-line interface with `analyze` and `suite` subcommands
- Parallel random network generation via `ProcessPoolExecutor`
- Excel output for analysis results and suite experiments
- Network fingerprint JSON storage with correlation table
- Multi-format network file support: Pajek (.net), GML, GraphML, edge list, adjacency list
- CSV edge classification export for Gephi/Cytoscape interoperability
- Comprehensive error handling and cache corruption recovery

### Changed
- All global variables replaced with explicit function parameters
- Progress reporting via callbacks (supports both GUI and CLI)
- Modern Python APIs: f-strings, dataclasses, type hints

## v1.0.0 (2012)

Original implementation by Chung-Yuan Huang and Wei-Chien-Benny Chin.

- Core algorithm: hierarchical ego-network arc type analysis for directed networks
- Four arc types: BOND, SILK, LOCAL BRIDGE, GLOBAL BRIDGE
- Statistical adaptive thresholds from random null models
- Pajek (.net) file I/O
- Matplotlib visualization
