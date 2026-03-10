# HATA — Hierarchical Arc Type Analysis

![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue)
![License: MIT](https://img.shields.io/badge/License-MIT-green)

A tool for classifying directed arcs in complex networks into four hierarchical types:

- **BOND** — Strong connections embedded within tight communities; removing them does not alter community structure.
- **Silk** — Pendant arcs where one endpoint has degree 1; removal isolates that node.
- **Local Bridge** — Cross-cluster connections linking nearby communities.
- **Global Bridge** — Long-range connections linking distant communities; removal may disconnect the network.

HATA extends the [HETA](https://github.com/canslab1/HETA) framework (designed for undirected graphs) to **directed networks** by replacing the "common friends" concept with directional ego networks (outgoing/incoming).

## Overview

Many real-world networks are inherently directed — information flows, citation graphs, food webs, and online social interactions all have asymmetric relationships. While HETA can classify edges in undirected networks, directed arcs require a fundamentally different approach to neighborhood overlap computation.

HATA addresses this by constructing separate outgoing and incoming ego networks for each arc endpoint, enabling the classification of directed arcs into the same four hierarchical types. This extension preserves the parameter-free, topology-driven philosophy of HETA while correctly handling the asymmetry of directed connections.

## Features

- **Parameter-free** — Classification is driven entirely by network topology; no community labels, edge weights, or manual thresholds required.
- **Directed network support** — Handles directed arcs using separate outgoing/incoming ego networks.
- **Multi-scale analysis** — Ego networks expand layer by layer, capturing both local and global structural information.
- **Statistically adaptive thresholds** — R1 threshold derived from degree-preserving random directed null models.
- **Multi-format input** — Supports Pajek (.net), GML, GraphML, edge list, and adjacency list formats.
- **Dual interface** — Both a PySide6 GUI and a full-featured CLI.
- **Parallel processing** — Random network generation can use multiple CPU cores.
- **Rich output** — Excel workbooks, CSV arc classification tables (Gephi/Cytoscape compatible), and multiple plot types.

## Installation

**Requirements:** Python 3.10+

```bash
git clone https://github.com/canslab1/HATA.git
cd HATA
pip install -r requirements.txt
```

### Dependencies

| Package | Purpose |
|---------|---------|
| NetworkX | Network analysis |
| NumPy / SciPy | Numerical computing & clustering |
| Matplotlib | Visualization |
| PySide6 | Qt-based GUI |
| openpyxl | Excel output |

## Usage

### GUI Mode

```bash
python run_hata.py
```

Launches a desktop application with two tabs:

- **Arc Analysis** — Load a single directed network, configure parameters, view classification results and various plots.
- **Suite Experiment** — Batch-analyze a predefined set of networks and compare their fingerprints.

### CLI Mode

```bash
# Analyze a single directed network
python run_hata.py analyze -i nets/leader.net

# With options
python run_hata.py analyze -i nets/leader.net -t 100 -p    # 100 random networks, parallel mode
python run_hata.py analyze -i nets/leader.net -q 2          # Quick mode (limit to 2 layers)
python run_hata.py analyze -i nets/leader.net --export-csv   # Export arc classification CSV

# Run suite experiment
python run_hata.py suite --name DEMO --run --dir nets/
```

### CLI Options

| Option | Description |
|--------|-------------|
| `-i`, `--input` | Path to network file |
| `-t`, `--times` | Number of random networks for null model (default: 1000) |
| `-q`, `--quick` | Quick mode: limit analysis layers |
| `-p`, `--parallel` | Parallel random network generation |
| `-w`, `--workers` | Number of parallel workers |
| `-d`, `--debug` | Enable debug output |
| `--show-detail` | Save detail layer plots |
| `--show-betweenness` | Save arc betweenness centrality plot |
| `--show-pagerank` | Save PageRank-based weighting plot |
| `--show-degree` | Save degree distribution plot (in/out) |
| `--show-clustering` | Save network clustering plot |
| `--export-csv` | Export arc classification as CSV (for Gephi/Cytoscape) |

## Supported Network Formats

| Extension | Format |
|-----------|--------|
| `.net` | Pajek |
| `.gml` | GML |
| `.graphml` | GraphML |
| `.edgelist`, `.edges` | Edge List |
| `.adjlist` | Adjacency List |

## Algorithm Overview

```
Read directed network → Split into weakly connected components
  → Build outgoing/incoming multi-layer ego networks
  → Compute neighborhood overlap for each arc at each layer
  → Generate degree-preserving random directed networks (null model)
  → Derive R1 threshold from null model
  → Phase 1: Identify SILK (degree-1 endpoints)
  → Phase 2: Classify BOND vs LOCAL_BRIDGE (R1 + R2 thresholds, layer-by-layer refinement)
  → Phase 3: Remaining unclassified arcs → GLOBAL_BRIDGE
  → Phase 4: Node information entropy & structural importance
  → Phase 5: Network fingerprint output
```

## Project Structure

```
HATA/
├── run_hata.py              # Entry point (GUI / CLI)
├── hata/
│   ├── __init__.py          # Package metadata
│   ├── constants.py         # Configuration constants
│   ├── engine.py            # Core HATA algorithm
│   ├── cli.py               # Command-line interface
│   ├── plotting.py          # Matplotlib visualizations
│   ├── excel_writer.py      # Excel / CSV output
│   └── gui/
│       ├── main_window.py   # PySide6 main window
│       ├── link_analysis_tab.py   # Single network analysis tab
│       ├── suite_experiment_tab.py # Batch experiment tab
│       ├── worker.py        # QThread background workers
│       └── plot_canvas.py   # Matplotlib-Qt integration
├── nets/                    # Sample directed networks
└── requirements.txt
```

## Output

- **Excel (.xlsx)** — Arc classification details, random network statistics, node entropy
- **CSV** — Arc classification table (importable by Gephi / Cytoscape)
- **PNG** — Network plots, betweenness, PageRank, degree distribution, clustering, fingerprint charts

## Authors

- **Chung-Yuan Huang** (黃崇源) — Department of Computer Science and Information Engineering, Chang Gung University, Taiwan (gscott@mail.cgu.edu.tw)
- **Wei-Chien-Benny Chin** — Department of Urban Planning and Design, University of Malaya, Malaysia (wcchin.88@gmail.com)

## Citation

If you use this software in your research, please cite:

> Huang, C.-Y. & Chin, W. C. B. (2020). Distinguishing Arc Types to Understand Complex Network Strength Structures and Hierarchical Connectivity Patterns. *IEEE Access*, 8, 71021–71040. https://doi.org/10.1109/ACCESS.2020.2986017

See `CITATION.cff` for machine-readable citation metadata.

## References

1. Huang, C.-Y. & Chin, W. C. B. (2020). Distinguishing Arc Types to Understand Complex Network Strength Structures and Hierarchical Connectivity Patterns. *IEEE Access*, 8, 71021–71040. https://doi.org/10.1109/ACCESS.2020.2986017

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.
