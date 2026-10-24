"""DataWise Tool Layer: Transformation Tools.

Deterministic, pure functions for column renaming, row filtering, column
dropping, column addition, and constrained derived column arithmetic (no
raw eval/exec).
"""

from typing import Any
import pandas as pd

from backend.core.exceptions import ToolInputError


def _validate_column_exists(df: pd.DataFrame, column: str) -> None:
    """Validate that a column exists in the DataFrame."""
    if column not in df.columns:
        raise ToolInputError(
            f"Column '{column}' does not exist in dataset. "
            f"Available columns: {list(df.columns)}"
        )


def drop_column(df: pd.DataFrame, column: str) -> pd.DataFrame:
    """Remove a single column from the DataFrame.

    Args:
        df: Input DataFrame.
        column: Name of the column to remove.

    Returns:
        DataFrame with the specified column removed.

    Raises:
        ToolInputError: If column does not exist in the DataFrame.
    """
    _validate_column_exists(df, column)
    return df.drop(columns=[column])


def select_columns(df: pd.DataFrame, columns: list[str] | str) -> pd.DataFrame:
    """Keep only the listed columns, in the order given.

    Args:
        df: Input DataFrame.
        columns: Column name or list of column names to keep.

    Returns:
        DataFrame containing only the requested columns.

    Raises:
        ToolInputError: If columns is empty or any name does not exist.
    """
    cols = [columns] if isinstance(columns, str) else list(columns)
    if not cols:
        raise ToolInputError("select_columns requires at least one column name.")
    for col in cols:
        _validate_column_exists(df, col)
    # Preserve requested order; drop duplicates while keeping first occurrence
    seen: set[str] = set()
    ordered: list[str] = []
    for col in cols:
        if col not in seen:
            seen.add(col)
            ordered.append(col)
    return df.loc[:, ordered].copy()


def add_column(
    df: pd.DataFrame,
    column: str,
    default_value: Any = None,
) -> pd.DataFrame:
    """Add a new column to the DataFrame with an optional constant default.

    If the column already exists it is left unchanged (idempotent).

    Args:
        df: Input DataFrame.
        column: Name of the new column to add.
        default_value: Constant fill value for all rows (default: None / NaN).

    Returns:
        DataFrame with the new column appended.
    """
    if column in df.columns:
        # Idempotent: column already present — treat as no-op success
        return df.copy()
    result_df = df.copy()
    result_df[column] = default_value
    return result_df


def rename_columns(df: pd.DataFrame, mapping: dict[str, str]) -> pd.DataFrame:
    """Rename columns in a DataFrame based on a dictionary mapping.

    Args:
        df: Input DataFrame.
        mapping: Dictionary mapping old column names to new names.

    Returns:
        DataFrame with renamed columns.

    Raises:
        ToolInputError: If any source column in mapping does not exist in DataFrame.
    """
    for old_col in mapping.keys():
        _validate_column_exists(df, old_col)

    return df.rename(columns=mapping)


def filter_rows(
    df: pd.DataFrame,
    column: str,
    operator: str,
    value: Any,
) -> tuple[pd.DataFrame, int]:
    """Filter DataFrame rows based on a column condition.

    Args:
        df: Input DataFrame.
        column: Column to evaluate.
        operator: Comparison operator ('>', '>=', '<', '<=', '==', '!=', 'equals',
                  'contains', 'startswith', 'endswith', 'in', 'not in').
        value: Target value to compare against.

    Returns:
        Tuple of (filtered_df, number_of_rows_removed).

    Raises:
        ToolInputError: If column does not exist or operator is unsupported.
    """
    _validate_column_exists(df, column)

    op = operator.lower().strip()
    series = df[column]

    try:
        if op in {"==", "=", "equals"}:
            mask = series == value
        elif op == "!=":
            mask = series != value
        elif op == ">":
            mask = series > value
        elif op == ">=":
            mask = series >= value
        elif op == "<":
            mask = series < value
        elif op == "<=":
            mask = series <= value
        elif op == "contains":
            mask = series.astype(str).str.contains(str(value), na=False)
        elif op == "startswith":
            mask = series.astype(str).str.startswith(str(value), na=False)
        elif op == "endswith":
            mask = series.astype(str).str.endswith(str(value), na=False)
        elif op == "in":
            items = value if isinstance(value, (list, tuple, set)) else [value]
            mask = series.isin(items)
        elif op == "not in":
            items = value if isinstance(value, (list, tuple, set)) else [value]
            mask = ~series.isin(items)
        else:
            supported = (
                "==, !=, >, >=, <, <=, equals, contains, "
                "startswith, endswith, in, not in"
            )
            raise ToolInputError(
                f"Unsupported filter operator '{operator}'. Supported: {supported}."
            )
    except ToolInputError:
        raise
    except Exception as e:
        raise ToolInputError(
            f"Error applying filter '{column} {operator} {value}': {str(e)}"
        )

    filtered_df = df[mask].reset_index(drop=True)
    n_removed = len(df) - len(filtered_df)
    return filtered_df, n_removed


def add_derived_column(
    df: pd.DataFrame,
    new_column: str,
    expression_spec: dict[str, Any],
) -> pd.DataFrame:
    """Create a new column using a constrained, safe arithmetic specification.

    SECURITY GUARANTEE:
    Raw strings are NEVER evaluated with eval() or exec(). The operation must
    be declared as a structured dictionary matching:
    {"op": "multiply|add|subtract|divide", "a": <col_name|scalar>, "b": <col_name|scalar>}

    Args:
        df: Input DataFrame.
        new_column: Name of the column to create.
        expression_spec: Constrained operation specification.

    Returns:
        DataFrame with new column appended.

    Raises:
        ToolInputError: If specification is malformed, uses an unknown operator,
                        or references nonexistent columns.
    """
    if not isinstance(expression_spec, dict):
        raise ToolInputError("expression_spec must be a dictionary.")

    required_keys = {"op", "a", "b"}
    if not required_keys.issubset(expression_spec.keys()):
        raise ToolInputError(
            f"expression_spec must contain keys 'op', 'a', and 'b'. "
            f"Got: {list(expression_spec.keys())}"
        )

    op = str(expression_spec["op"]).lower().strip()
    allowed_ops = {"multiply", "*", "add", "+", "subtract", "-", "divide", "/"}
    if op not in allowed_ops:
        raise ToolInputError(
            f"Unsupported arithmetic operator '{op}'. "
            f"Allowed: multiply, add, subtract, divide."
        )

    # Resolve operand 'a'
    raw_a = expression_spec["a"]
    val_a: Any
    if isinstance(raw_a, str):
        if raw_a in df.columns:
            val_a = df[raw_a]
        else:
            try:
                val_a = float(raw_a)
            except ValueError:
                raise ToolInputError(
                    f"Operand 'a' references nonexistent column '{raw_a}'."
                )
    elif isinstance(raw_a, (int, float)):
        val_a = raw_a
    else:
        raise ToolInputError(f"Invalid operand 'a' type: {type(raw_a).__name__}")

    # Resolve operand 'b'
    raw_b = expression_spec["b"]
    val_b: Any
    if isinstance(raw_b, str):
        if raw_b in df.columns:
            val_b = df[raw_b]
        else:
            try:
                val_b = float(raw_b)
            except ValueError:
                raise ToolInputError(
                    f"Operand 'b' references nonexistent column '{raw_b}'."
                )
    elif isinstance(raw_b, (int, float)):
        val_b = raw_b
    else:
        raise ToolInputError(f"Invalid operand 'b' type: {type(raw_b).__name__}")

    result_df = df.copy()

    try:
        if op in {"multiply", "*"}:
            result_df[new_column] = val_a * val_b
        elif op in {"add", "+"}:
            result_df[new_column] = val_a + val_b
        elif op in {"subtract", "-"}:
            result_df[new_column] = val_a - val_b
        elif op in {"divide", "/"}:
            result_df[new_column] = val_a / val_b
    except Exception as e:
        raise ToolInputError(
            f"Failed to calculate derived column '{new_column}': {str(e)}"
        )

    return result_df
