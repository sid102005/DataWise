"""DataWise Tool Layer: Aggregation and Sorting Tools.

Deterministic, pure functions for grouping, sorting, and top-N extraction.
"""

from typing import Literal
import pandas as pd

from backend.core.exceptions import ToolInputError


def _validate_columns_exist(df: pd.DataFrame, columns: list[str] | str) -> list[str]:
    """Helper to validate column existence and prevent injection or KeyErrors."""
    cols = [columns] if isinstance(columns, str) else list(columns)
    available = set(df.columns)
    for col in cols:
        if col not in available:
            raise ToolInputError(
                f"Column '{col}' does not exist in dataset. Available columns: {list(df.columns)}"
            )
    return cols


def groupby_aggregate(
    df: pd.DataFrame,
    by: list[str] | str,
    metric: str,
    agg: str = "sum",
) -> pd.DataFrame:
    """Group by specified columns and compute aggregate statistics on a metric.

    Args:
        df: Input DataFrame.
        by: Column name or list of columns to group by.
        metric: Column to aggregate.
        agg: Aggregation function ('sum', 'avg', 'mean', 'count', 'min', 'max').

    Returns:
        Aggregated DataFrame with grouping columns and aggregated metric.

    Raises:
        ToolInputError: If grouping column or metric does not exist, or agg is unsupported.
    """
    by_cols = _validate_columns_exist(df, by)
    _validate_columns_exist(df, metric)

    agg_clean = agg.lower().strip()
    agg_mapping = {
        "sum": "sum",
        "avg": "mean",
        "mean": "mean",
        "count": "count",
        "min": "min",
        "max": "max",
    }
    if agg_clean not in agg_mapping:
        supported = ", ".join(sorted(agg_mapping.keys()))
        raise ToolInputError(
            f"Unsupported aggregation '{agg}'. Supported aggregations: {supported}."
        )

    # Check numeric constraint for arithmetic aggregations
    if agg_clean in {"sum", "avg", "mean"} and not pd.api.types.is_numeric_dtype(df[metric]):
        raise ToolInputError(
            f"Cannot compute '{agg}' on non-numeric metric column '{metric}'."
        )

    pandas_agg = agg_mapping[agg_clean]
    try:
        aggregated_df = df.groupby(by_cols, as_index=False)[metric].agg(pandas_agg)
    except Exception as e:
        raise ToolInputError(f"Groupby aggregation failed: {str(e)}")

    return aggregated_df.reset_index(drop=True)


def sort_values(
    df: pd.DataFrame,
    column: str,
    ascending: bool = True,
) -> pd.DataFrame:
    """Sort a DataFrame by a specified column.

    Args:
        df: Input DataFrame.
        column: Column to sort by.
        ascending: True for ascending order, False for descending.

    Returns:
        Sorted DataFrame with reset index.

    Raises:
        ToolInputError: If column does not exist.
    """
    _validate_columns_exist(df, column)
    return df.sort_values(by=column, ascending=ascending).reset_index(drop=True)


def top_n(
    df: pd.DataFrame,
    n: int,
) -> pd.DataFrame:
    """Return top N rows from a DataFrame.

    EDGE CASE SPECIFICATION:
    If n >= len(df), all rows are returned safely without error.

    Args:
        df: Input DataFrame.
        n: Number of rows to return (must be >= 1).

    Returns:
        Truncated DataFrame containing at most N rows.

    Raises:
        ToolInputError: If n is not a positive integer.
    """
    if not isinstance(n, int) or n < 1:
        raise ToolInputError(f"Parameter 'n' must be a positive integer >= 1. Got: {n}")

    # Documented behavior: if n >= len(df), return all rows
    return df.head(n).reset_index(drop=True)
