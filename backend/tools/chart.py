"""DataWise Tool Layer: Charting and Visualization Tools.

Deterministic, pure functions for generating bar, line, and pie charts using matplotlib.
All charts are exported to disk as standalone PNG image files.
"""

from pathlib import Path
import tempfile
import uuid
import matplotlib
# Use headless backend for non-interactive server environments
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from backend.core.exceptions import ToolInputError
from backend.config import WORKSPACE_DIR


def _validate_column_exists(df: pd.DataFrame, column: str, role: str = "Column") -> None:
    """Validate that specified column exists in the DataFrame."""
    if column not in df.columns:
        raise ToolInputError(
            f"{role} '{column}' does not exist in dataset. Available columns: {list(df.columns)}"
        )


def _get_target_file(output_dir: Path | str | None, prefix: str) -> Path:
    """Generate target file path inside specified or default charts directory."""
    if output_dir:
        target_dir = Path(output_dir).resolve()
    else:
        target_dir = (WORKSPACE_DIR / "charts").resolve()
    target_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{prefix}_{uuid.uuid4().hex[:8]}.png"
    return target_dir / filename


def bar_chart(
    df: pd.DataFrame,
    x: str,
    y: str,
    title: str = "Bar Chart",
    output_dir: Path | str | None = None,
) -> Path:
    """Generate a bar chart from DataFrame columns and save to disk.

    Args:
        df: Input DataFrame.
        x: Column name for categorical X-axis.
        y: Column name for numeric Y-axis values.
        title: Plot title.
        output_dir: Optional directory to store chart artifact.

    Returns:
        Resolved Path to generated PNG image file.

    Raises:
        ToolInputError: If x or y column is missing.
    """
    _validate_column_exists(df, x, role="X-axis column")
    _validate_column_exists(df, y, role="Y-axis column")

    target_path = _get_target_file(output_dir, prefix="bar")

    fig, ax = plt.subplots(figsize=(10, 6))
    try:
        # Convert to string for x labels and float for y values
        x_vals = df[x].astype(str)
        y_vals = pd.to_numeric(df[y], errors="coerce").fillna(0)

        ax.bar(x_vals, y_vals, color="#3b82f6", edgecolor="#1d4ed8", alpha=0.85)
        ax.set_title(title, fontsize=14, fontweight="bold", pad=12)
        ax.set_xlabel(str(x), fontsize=11)
        ax.set_ylabel(str(y), fontsize=11)
        plt.xticks(rotation=45, ha="right")
        plt.tight_layout()
        fig.savefig(target_path, dpi=150)
    finally:
        plt.close(fig)

    return target_path


def line_chart(
    df: pd.DataFrame,
    x: str,
    y: str,
    title: str = "Line Chart",
    output_dir: Path | str | None = None,
) -> Path:
    """Generate a line chart from DataFrame columns and save to disk.

    Args:
        df: Input DataFrame.
        x: Column name for X-axis (e.g. sequence, date).
        y: Column name for numeric Y-axis.
        title: Plot title.
        output_dir: Optional directory to store chart artifact.

    Returns:
        Resolved Path to generated PNG image file.

    Raises:
        ToolInputError: If x or y column is missing.
    """
    _validate_column_exists(df, x, role="X-axis column")
    _validate_column_exists(df, y, role="Y-axis column")

    target_path = _get_target_file(output_dir, prefix="line")

    fig, ax = plt.subplots(figsize=(10, 6))
    try:
        x_vals = df[x].astype(str)
        y_vals = pd.to_numeric(df[y], errors="coerce").fillna(0)

        ax.plot(x_vals, y_vals, marker="o", color="#10b981", linewidth=2)
        ax.set_title(title, fontsize=14, fontweight="bold", pad=12)
        ax.set_xlabel(str(x), fontsize=11)
        ax.set_ylabel(str(y), fontsize=11)
        plt.xticks(rotation=45, ha="right")
        plt.grid(True, linestyle="--", alpha=0.5)
        plt.tight_layout()
        fig.savefig(target_path, dpi=150)
    finally:
        plt.close(fig)

    return target_path


def pie_chart(
    df: pd.DataFrame,
    labels: str,
    values: str,
    title: str = "Pie Chart",
    output_dir: Path | str | None = None,
) -> Path:
    """Generate a pie chart from DataFrame columns and save to disk.

    Args:
        df: Input DataFrame.
        labels: Column name for categorical slice labels.
        values: Column name for numeric slice proportions.
        title: Plot title.
        output_dir: Optional directory to store chart artifact.

    Returns:
        Resolved Path to generated PNG image file.

    Raises:
        ToolInputError: If labels or values column is missing.
    """
    _validate_column_exists(df, labels, role="Labels column")
    _validate_column_exists(df, values, role="Values column")

    target_path = _get_target_file(output_dir, prefix="pie")

    fig, ax = plt.subplots(figsize=(8, 8))
    try:
        lbls = df[labels].astype(str)
        vals = pd.to_numeric(df[values], errors="coerce").fillna(0)

        # Drop any zero or negative values for valid pie chart
        valid_mask = vals > 0
        lbls = lbls[valid_mask]
        vals = vals[valid_mask]

        if len(vals) == 0:
            raise ToolInputError(f"No positive numeric values found in column '{values}' for pie chart.")

        ax.pie(vals, labels=lbls, autopct="%1.1f%%", startangle=140)
        ax.set_title(title, fontsize=14, fontweight="bold", pad=12)
        plt.tight_layout()
        fig.savefig(target_path, dpi=150)
    finally:
        plt.close(fig)

    return target_path
