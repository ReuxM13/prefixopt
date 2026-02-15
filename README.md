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

### Who is the utility for?
Operations Engineers (Ops): optimize, add, merge, stats.
Security guards (Sec): diff (audit), intersect (conflicts), filter (clearing feeds).
Pentesters / Researchers: exclude (scope management), split (goal preparation), check.

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

### Detailed descriptions of commands

| Command | Logic / Math | Goal | Output Format | Key Nuance |
| :--- | :--- | :--- | :--- | :--- |
| **`optimize`** | `Aggr(Sort(Set(A)))` | **Compression**<br>Shrink ACLs, remove duplicates. | CIDR List | Performs full cycle: Sort - Remove Nested - Aggregate. |
| **`add`** | `Optimize(A + {new})` | **Editing**<br>Add a new IP and re-optimize immediately. | CIDR List | Automatically merges the new item into existing subnets. |
| **`filter`** | `A - {Bogons}` | **Sanitization**<br>Remove private, local, and reserved IPs. | Clean List | Does *not* aggregate, only removes unwanted items. |
| **`merge`** | `Optimize(A ∪ B ...)` | **Union**<br>Combine multiple feeds into one master list. | CIDR List | Supports `--keep-comments` (deduplication without aggregation). |
| **`intersect`** | `A ∩ B` | **Conflict Analysis**<br>Find common zones or overlapping rules. | Report<br>(Exact + Partial) | Visualizes exactly which prefix from Source A overlaps with Source B. |
| **`exclude`** | `A \ B` | **Subtraction**<br>Remove whitelist from blacklist. | Fragments List | Mathematically punches holes in networks, splitting them. |
| **`diff`** | `(B \ A) ∪ (A \ B)` | **Audit**<br>What changed since the last version? | Patch (`+`, `-`, `=`) | Semantic comparison (understands that two `/24` equal one `/23`). |
| **`check`** | `Target ∈ Set` | **Lookup**<br>Is this IP covered by our rules? | Parent Networks | Finds all supernets containing the target IP. |
| **`split`** | `Subnet(A, len)` | **De-aggregation**<br>Slice networks into smaller chunks. | Subnets List | Useful for scanning scopes (e.g. split `/16` into `/24`s). |
| **`stats`** | `Count(A)` | **Analytics**<br>Compression ratio, unique IPs count. | Metrics Table | Calculates actual unique IPs, ignoring overlaps. |

---

## To-Do
- [x] Allow reading input from standard input (pipes) instead of requiring a file argument (e.g., `cat list.txt | prefixopt optimize`).
- [x] Integrate the `ijson` library to parse huge JSON files without loading them entirely into RAM.
- [x] Refactor package structure to allow clean imports (e.g., `import prefixopt`).
- [x] Expose core functions (`optimize`, `filter`, `subtract`) as a stable public API.
- [ ] Implement colorized output for IPv4 (e.g., green) and IPv6 (e.g., purple, mask is gray) addresses when printing to stdout using `Rich`.
- [ ] Tree View for `check`. Visualize prefix hierarchy. Instead of a flat list, display how the target IP/subnet fits into supernets using a graphical tree structure (`rich.tree`).

---

## License
This project is distributed under the *MIT License*. See the `LICENSE` file for details.

![Tests](https://github.com/ReuxM13/prefixopt/actions/workflows/tests.yml/badge.svg)