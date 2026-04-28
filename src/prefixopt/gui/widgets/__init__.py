"""
Набор переиспользуемых GUI-виджетов.
"""
from .input_panel import InputPanel
from .output_panel import OutputPanel
from .options_group import OptionsGroup
from .prefix_input_widget import PrefixInputWidget
from .progress_panel import ProgressPanel
from .split_output_panel import SplitOutputPanel

__all__ = [
    "InputPanel",
    "OutputPanel",
    "OptionsGroup",
    "PrefixInputWidget",
    "ProgressPanel",
    "SplitOutputPanel",
]