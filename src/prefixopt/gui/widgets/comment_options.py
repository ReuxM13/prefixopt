"""
Reusable mixin for tabs that expose append-comment controls.

The mixin assumes the host widget provides two attributes:
    * ``append_comment``        - a QLineEdit for the new comment text.
    * ``keep_existing_comments``- a QCheckBox that controls whether old
                                  comments are kept or replaced.

Centralising the enable/disable logic here keeps the per-tab code consistent
and avoids subtle state bugs (for example the checkbox must be disabled while
the comment field is empty).
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtWidgets import QCheckBox, QLineEdit


class CommentAnnotationMixin:
    """Shared helpers for the "append comment" GUI controls."""

    # These are declared for type-checkers only; concrete tabs assign real
    # Qt widgets in their _init_ui methods.
    append_comment: QLineEdit
    keep_existing_comments: QCheckBox

    def get_append_comment(self) -> Optional[str]:
        """Return the trimmed append-comment text, or ``None`` when empty."""
        text = self.append_comment.text().strip()
        return text or None

    def update_comment_options_state(
        self, keep: bool, append_requires_keep: bool = False
    ) -> None:
        """Refresh widget enable-states based on current option values.

        Args:
            keep: Whether "keep comments" mode is active.
            append_requires_keep: When True (e.g. for merge), the append field
                is only editable if comments are being kept. For operations like
                optimize/filter/split, append can stand alone and the field is
                always enabled.
        """
        has_append = bool(self.append_comment.text().strip())
        # The append field is enabled if comments are kept OR the operation
        # allows append without keep mode.
        append_enabled = keep or not append_requires_keep
        self.append_comment.setEnabled(append_enabled)
        # Keeping existing comments only makes sense when there is a comment to
        # append; otherwise the checkbox is disabled and unchecked.
        self.keep_existing_comments.setEnabled(has_append)
        if not has_append:
            self.keep_existing_comments.setChecked(False)
