"""Chart generation helpers using matplotlib/seaborn."""
from __future__ import annotations

import io
import logging
from typing import Any

logger = logging.getLogger(__name__)


def render_to_bytes(fig: Any) -> bytes:
    """Render a matplotlib Figure to PNG bytes."""
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight")
    buf.seek(0)
    return buf.read()


def bar_chart(labels: list[str], values: list[int | float], title: str = "", xlabel: str = "", ylabel: str = "") -> bytes:
    """Simple horizontal bar chart."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import seaborn as sns

        sns.set_theme(style="darkgrid")
        fig, ax = plt.subplots(figsize=(8, max(3, len(labels) * 0.4)))
        ax.barh(labels[::-1], values[::-1])
        if title:
            ax.set_title(title)
        if xlabel:
            ax.set_xlabel(xlabel)
        if ylabel:
            ax.set_ylabel(ylabel)
        plt.tight_layout()
        result = render_to_bytes(fig)
        plt.close(fig)
        return result
    except Exception as e:
        logger.error("Chart generation failed: %s", e)
        raise
