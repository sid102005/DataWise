"""Unit and security tests for DataWise transformation tools (backend/tools/transform.py)."""

from pathlib import Path
import pandas as pd
import pytest

from backend.tools.transform import (
    rename_columns,
    filter_rows,
    add_derived_column,
)
from backend.core.exceptions import ToolInputError

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SAMPLE_CSV = REPO_ROOT / "tests" / "fixtures" / "sample.csv"


@pytest.fixture
def sample_df() -> pd.DataFrame:
    """Load clean instance of Phase 1 canonical sample.csv."""
    return pd.read_csv(SAMPLE_CSV)


# ==================== rename_columns tests ====================

def test_rename_columns_canonical(sample_df):
    """Test column renaming."""
    renamed = rename_columns(sample_df, {"Customer_ID": "client_id", "Purchase": "total_spent"})
    assert "client_id" in renamed.columns
    assert "total_spent" in renamed.columns
    assert "Customer_ID" not in renamed.columns
    assert len(renamed) == len(sample_df)


def test_rename_columns_validation_rejection(sample_df):
    """[FIX F5] Renaming nonexistent column raises ToolInputError."""
    with pytest.raises(ToolInputError) as exc_info:
        rename_columns(sample_df, {"bogus_col": "new_name"})
    assert "Column 'bogus_col' does not exist" in str(exc_info.value)


# ==================== filter_rows tests ====================

def test_filter_rows_canonical(sample_df):
    """Test filter_rows with comparison and equality operators."""
    # Equality: Region == 'North' (13 rows in sample.csv)
    df_north, removed = filter_rows(sample_df, column="Region", operator="==", value="North")
    assert len(df_north) == 13
    assert removed == 37
    assert (df_north["Region"] == "North").all()

    # Numeric comparison: Purchase > 8000 (Top 5 rows in sample.csv)
    df_high, removed_high = filter_rows(sample_df, column="Purchase", operator=">", value=8000)
    assert len(df_high) == 5
    assert removed_high == 45


def test_filter_rows_validation_rejection(sample_df):
    """[FIX F5] Nonexistent column or invalid operator raises ToolInputError."""
    with pytest.raises(ToolInputError) as exc_info:
        filter_rows(sample_df, column="MissingCol", operator="==", value="test")
    assert "Column 'MissingCol' does not exist" in str(exc_info.value)

    with pytest.raises(ToolInputError) as exc_info:
        filter_rows(sample_df, column="Region", operator="INVALID_OP", value="test")
    assert "Unsupported filter operator" in str(exc_info.value)


# ==================== add_derived_column tests ====================

def test_add_derived_column_canonical(sample_df):
    """Test safe arithmetic derivation (multiply, add, subtract, divide)."""
    # Multiply: Purchase * 2
    df_derived = add_derived_column(
        sample_df,
        new_column="double_purchase",
        expression_spec={"op": "multiply", "a": "Purchase", "b": 2.0},
    )
    assert "double_purchase" in df_derived.columns
    assert df_derived["double_purchase"].iloc[0] == sample_df["Purchase"].iloc[0] * 2.0

    # Add two columns / scalars
    df_add = add_derived_column(
        sample_df,
        new_column="purchase_plus_100",
        expression_spec={"op": "add", "a": "Purchase", "b": 100},
    )
    assert df_add["purchase_plus_100"].iloc[0] == sample_df["Purchase"].iloc[0] + 100


def test_add_derived_column_security_rejection(sample_df):
    """[SECURITY] Rejection of malicious expressions, raw strings, and eval attempts."""
    # Malicious injection attempt in operator or operands
    with pytest.raises(ToolInputError) as exc_info:
        add_derived_column(
            sample_df,
            new_column="hack",
            expression_spec={"op": "eval", "a": "__import__('os').system('calc')", "b": 1},
        )
    assert "Unsupported arithmetic operator" in str(exc_info.value)

    # Passing raw string instead of constrained dictionary
    with pytest.raises(ToolInputError) as exc_info:
        add_derived_column(
            sample_df,
            new_column="hack",
            expression_spec="Purchase * 2",  # type: ignore
        )
    assert "expression_spec must be a dictionary" in str(exc_info.value)

    # Referencing nonexistent column operand
    with pytest.raises(ToolInputError) as exc_info:
        add_derived_column(
            sample_df,
            new_column="hack",
            expression_spec={"op": "multiply", "a": "GhostColumn", "b": 2},
        )
    assert "nonexistent column 'GhostColumn'" in str(exc_info.value)
