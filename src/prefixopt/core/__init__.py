"""
Core package: pure algorithms over IPv4/IPv6 networks.

Everything in this package deliberately knows nothing about files, the CLI,
or the GUI. Functions accept and return plain ``IPv4Network``/``IPv6Network``
objects (aliased as :data:`IPNet`), which keeps the logic trivial to unit
test and reuse from any front-end.

Reading order for a new contributor:
    1. ``ip_utils``       - shared types and helpers.
    2. ``pipeline``       - orchestrator that chains operations together.
    3. ``operations/``    - one algorithm per file (sort, nest, aggregate, ...).
    4. ``ip_counter``     - metrics/statistics built on top of the operations.
"""
