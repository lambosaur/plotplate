"""Layout-templated matplotlib panels for multi-panel figures assembled in LaTeX.

Typical use inside a panel notebook::

    import plotplate as pp

    panel = pp.Layout.load("layout.yaml").panel("A")
    fig = panel.figure()
    ax_roc = panel.axes(fig, "roc")
    ...
    panel.save(fig)
"""

from .config import list_journals, load_journal
from .geometry import Rect, in_to_mm, mm_to_in, mm_to_pt, pt_to_mm
from .layout import AxesSpec, Issue, Layout, PanelSpec
from .panel import Panel, SaveReport
from .style import palette

try:
    from ._version import __version__
except ImportError:
    from importlib.metadata import PackageNotFoundError, version

    try:
        __version__ = version("plotplate")
    except PackageNotFoundError:
        __version__ = "0.0.0+unknown"

__all__ = [
    "AxesSpec",
    "Issue",
    "Layout",
    "Panel",
    "PanelSpec",
    "Rect",
    "SaveReport",
    "__version__",
    "in_to_mm",
    "list_journals",
    "load_journal",
    "mm_to_in",
    "mm_to_pt",
    "palette",
    "pt_to_mm",
]
