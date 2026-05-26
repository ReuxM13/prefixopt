<p align="center">
  <img src="static\banner.png" alt="prefixOptimizer Banner" width="100%">
</p>

# prefixopt

## Table of Contents

- [Description](#description)
- [Who is it for](#who-is-it-for)
- [Installation](#installation)
- [Quick Examples](#quick-examples)
- [Graphical User Interface (GUI)](#graphical-user-interface-gui)
- [Technical Implementation](#technical-implementation)
- [Command Reference](#command-reference)
- [Contributing](#contributing)
- [License](#license)

---

## Description

**prefixopt** is a high-performance CLI utility for network engineers and security professionals who work with large IP prefix lists.

It automates the most common and error-prone tasks involved in prefix list maintenance: deduplication, CIDR aggregation, bogon filtering, semantic comparison, overlap detection, and network subtraction (hole punching).

Whether You are cleaning up firewall rules, preparing scan scopes, auditing infrastructure changes, or normalizing threat feeds, **prefixopt** helps turn noisy and inconsistent input into clean, reliable output.

### Key capabilities

- **Optimization** — Removes duplicate and nested prefixes automatically. Example: a `/32` is discarded if it is already covered by a parent `/24`.
- **Aggregation** — Merges adjacent subnets into a larger supernet whenever the aggregation is mathematically valid.
- **Filtering** — Removes unwanted address space such as Bogons, Private networks (RFC 1918), Loopbacks, Multicast, and other non-routable ranges.
- **Subtraction** — Excludes one list from another, automatically splitting larger networks into smaller fragments when needed.
- **Semantic comparison** — Compares prefix lists by their actual address space rather than by text representation. This makes it possible to detect real changes even when the CIDR notation differs.
- **Intersection analysis** — Detects exact matches and partial overlaps between two or more sources.
- **Flexible parsing** — Extracts IPs, CIDRs, and IP ranges (for example, `10.0.0.1 - 10.0.0.50`) from arbitrary text-based sources such as logs, router configs, raw CSV, and JSON.
- **STDIN / pipe support** — Follows the UNIX philosophy and works well in pipelines. Supported commands: `optimize`, `filter`, `stats`, `check`, `split`, `exclude`.

  Example:
  ```bash
  cat logs.txt | prefixopt optimize
  ```

---

## Who is it for?

- **Operations Engineers (Ops)** — `optimize`, `add`, `merge`, `stats`
- **Security Analysts (Blue Team)** — `diff` for infrastructure audits, `intersect` for rule conflict analysis, `filter` for threat feed sanitization
- **Pentesters and Researchers (Red Team)** — `exclude` for scope management, `split` for scanner target slicing, `check` for quick coverage validation

---

## Installation

Requires Python 3.9 or higher.

```bash
# Clone the repository
git clone https://github.com/ReuxM13/prefixopt.git
cd prefixopt

# Install
pip install -e .
```

---

## Quick Examples

<p align="left">
  <img src="static\usage.png" alt="prefixopt using" width="100%">
</p>

<p align="left">
  <img src="static\GUI.png" alt="prefixopt GUI" width="100%">
</p>

```bash
# Clean and aggregate a messy list
prefixopt optimize messy_ips.txt -o clean_acls.txt

# Merge two lists while preserving line comments (#) and avoiding aggregation
prefixopt merge list1.txt list2.txt --keep-comments

# Tag all new prefixes from list1 during a merge
prefixopt merge list1.txt base.txt --keep-comments --append-comment "Client X"

# Find overlaps between two files (or internal overlaps within a single file)
prefixopt intersect blacklist.txt whitelist.txt

# Subtract a scope (prohibit scanning of specific IPs)
prefixopt exclude out_of_scope.txt target_scope.txt

# Strictly validate a list (fail if host bits are set in a network address)
prefixopt optimize config.txt --strict
```

---

## Graphical User Interface (GUI)

The GUI is an optional component built with PySide6.

```bash
pip install prefixopt[gui]
prefixopt gui
```

The GUI provides all the same operations through a tabbed interface, with:
- Real-time progress and cancel support for long-running tasks
- HTML-formatted reports for diff, intersect, stats, and check
- Keyboard shortcuts: `Ctrl+R` to run, `Ctrl+O` to open a file, `Ctrl+S` to save output, `Ctrl+Tab` / `Ctrl+Shift+Tab` to switch tabs
- Automatic dark / light theme detection
- Paged output for large result sets

---

## Technical Implementation

The architecture is built on a modular principle (Core / CLI / Data).

- **Performance** — Linear complexity O(N) algorithms are used for nested removal and aggregation (stack-based), which allows processing part (up to 10 million lines) of the BGP Full View table in a few minutes.
- **Memory** — Data reading and filtering are implemented via generators to minimize RAM consumption.
- **Safety** — Inside the pipeline, work is done only with IPv4Network/IPv6Network objects; string operations are excluded. Hard limits on input data size are implemented to prevent OOM.

#### Limitations

- **Memory Overhead** — The utility is written in pure Python. Due to overhead on ipaddress objects, processing lists larger than 8–10 million lines may require significant RAM (starting from 8–10 GB).
- **Big Data** — The tool is not designed for real-time big data processing. It is a utility for configurations and access lists, not for traffic analytics.

---

## Command Reference

| Command | Logic / Math | Goal | Output Format | Key Nuance |
| :--- | :--- | :--- | :--- | :--- |
| **`optimize`** | `Aggr(Sort(Set(A)))` | **Compression** — Shrink ACLs, remove duplicates. | CIDR List | Performs full cycle: Sort – Remove Nested – Aggregate. |
| **`add`** | `Optimize(A + {new})` | **Editing** — Add a new IP and re-optimize immediately. | CIDR List | Automatically merges the new item into existing subnets. |
| **`filter`** | `A - {Bogons}` | **Sanitization** — Remove private, local, and reserved IPs. | Clean List | Does *not* aggregate, only removes unwanted items. |
| **`merge`** | `Optimize(A ∪ B ...)` | **Union** — Combine multiple feeds into one master list. | CIDR List | Supports `--keep-comments` (deduplication without aggregation) and `--append-comment`. |
| **`intersect`** | `A ∩ B` | **Conflict Analysis** — Find common zones or overlapping rules. | Report (Exact + Partial) | Visualizes exactly which prefix from Source A overlaps with Source B. |
| **`exclude`** | `A \ B` | **Subtraction** — Remove whitelist from blacklist. | Fragments List | Mathematically punches holes in networks, splitting them. |
| **`diff`** | `(B \ A) ∪ (A \ B)` | **Audit** — What changed since the last version? | Patch (`+`, `-`, `=`) | Semantic comparison (understands that two `/24` equal one `/23`). |
| **`check`** | `Target ∈ Set` | **Lookup** — Is this IP covered by our rules? | Parent Networks | Finds all supernets containing the target IP. |
| **`split`** | `Subnet(A, len)` | **De-aggregation** — Slice networks into smaller chunks. | Subnets List | Useful for scanning scopes (e.g. split `/16` into `/24`s). |
| **`stats`** | `Count(A)` | **Analytics** — Compression ratio, unique IPs count. | Metrics Table | Calculates actual unique IPs, ignoring overlaps. |

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup, code style, and pull request guidelines.

All contributors must follow our [Code of Conduct](CODE_OF_CONDUCT.md).  
To report a security vulnerability, see [SECURITY.md](SECURITY.md).

---

## License

This project is distributed under the *MIT License*. See the `LICENSE` file for details.
