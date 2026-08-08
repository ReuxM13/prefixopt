"""
Data-access layer: turn raw text/files into IP network objects.

Currently this package contains a single module, :mod:`file_reader`, which
handles parsing of plain text, CSV and JSON inputs from disk, STDIN or
in-memory strings. The GUI has a parallel text-parsing helper in
``gui.services._load_with_comments``.
"""
