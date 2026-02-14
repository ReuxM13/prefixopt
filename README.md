<p align="center">
  <img src="static\banner.png" alt="prefixOptimizer Banner" width="100%">
</p>

[🇷🇺 Читать на русском](README_RU.md)
# prefixopt

## Description

`prefixopt` is a tool for network engineers and security specialists. It allows automating routine tasks for processing IP address lists: removing duplicates, aggregating subnets, filtering garbage (Bogons), finding intersections, semantically comparing lists, as well as excluding one or more subnets/addresses from a list.

Allows organizing scattered lists of IP addresses:
- Optimization: Automatic removal of duplicates and nested networks (e.g., removing /32 if a covering /24 exists).
- Aggregation: Merging adjacent subnets into supernet.
- Filtering: Cleaning lists from Bogons, private networks (RFC1918), Loopback, and Multicast.
- Subtraction: Excluding specific addresses or subnets from the general list with automatic range splitting.
- Comparison: Semantic comparison of two lists (shows which subnets were added or removed).
- Versatility: The parser automatically extracts prefixes from any text files (logs, equipment configurations, CSV, JSON).
- Pipe Support (STDIN): Supports UNIX-way pipelining. You can pass data via standard input instead of files.
  Supported commands: `optimize`, `filter`, `stats`, `check`, `split`, `exclude`.
  Example: `cat logs.txt | prefixopt optimize`

---

## Installation

Requires Python 3.9 or higher.

```bash
# Clone the repository
git clone https://github.com/ReuxM13/prefixopt.git
cd prefixopt

# Create and activate virtual environment (optional)
python -m venv venv

# Activate venv
.\venv\Scripts\activate # Windows
source venv/bin/activate # Linux

# Install in editable mode (recommended)
pip install -e .
```

## Usage example

<p align="left">
  <img src="static\usage.png" alt="prefixopt using" width="100%">
</p>

---

## Technical Implementation
The architecture is built on a modular principle (Core / CLI / Data).

- Performance: Linear complexity O(N) algorithms are used for nested removal and aggregation (stack-based), which allows processing part (up to 10 million lines) of the BGP Full View table in a few minutes.
- Memory: Data reading and filtering are implemented via generators to minimize RAM consumption.
- Safety: Inside the pipeline, work is done only with IPv4Network/IPv6Network objects; string operations are excluded. Hard limits on input data size are implemented to prevent OOM.

### Limitations
- Memory Overhead: The utility is written in pure Python. Due to overhead on ipaddress objects, processing lists larger than 8-10 million lines may require significant RAM (starting from 8-10GB).
- Big Data: The tool is not designed for real-time big data processing. It is a utility for configurations and access lists, not for traffic analytics.

---

## To-Do
- [x] Allow reading input from standard input (pipes) instead of requiring a file argument (e.g., `cat list.txt | prefixopt optimize`).
- [x] Integrate the `ijson` library to parse huge JSON files without loading them entirely into RAM.
- [ ] Refactor package structure to allow clean imports (e.g., `import prefixopt`).
- [ ] Expose core functions (`optimize`, `filter`, `subtract`) as a stable public API.
- [ ] Add type stubs and documentation for library usage.
- [ ] Implement colorized output for IPv4 (e.g., green) and IPv6 (e.g., purple, mask is gray) addresses when printing to stdout using `Rich`.
- [ ] Tree View for `check`. Visualize prefix hierarchy. Instead of a flat list, display how the target IP/subnet fits into supernets using a graphical tree structure (`rich.tree`).

---

## License
This project is distributed under the *MIT License*. See the `LICENSE` file for details.

![Tests](https://github.com/ReuxM13/prefixopt/actions/workflows/tests.yml/badge.svg)