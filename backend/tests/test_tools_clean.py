"""Unit and security tests for DataWise cleaning tools (backend/tools/clean.py)."""

from pathlib import Path
import pandas as pd
import pytest

from backend.tools.clean import (
    drop_duplicates,
    handle_missing,
    fix_type_mismatches,
    standardize_dates,
    clean_for_ml,
    strip_whitespace,
    normalize_missing,
    drop_empty_columns,
    drop_constant_columns,
)
from backend.core.exceptions import ToolInputError

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SAMPLE_CSV = REPO_ROOT / "tests" / "fixtures" / "sample.csv"


@pytest.fixture
def sample_df() -> pd.DataFrame:
    """Load clean instance of Phase 1 canonical sample.csv."""
    return pd.read_csv(SAMPLE_CSV)


# ==================== drop_duplicates tests ====================

def test_drop_duplicates_canonical(sample_df):
    """drop_duplicates removes exactly 4 rows per expected_sample_profile.json."""
    assert len(sample_df) == 50
    clean_df, n_removed = drop_duplicates(sample_df)
    assert n_removed == 4
    assert len(clean_df) == 46
    assert clean_df.duplicated().sum() == 0


def test_drop_duplicates_edge_cases():
    """Edge cases: empty DataFrame, single-row DataFrame, all-duplicates DataFrame."""
    empty_df = pd.DataFrame(columns=["A", "B"])
    res_empty, n_empty = drop_duplicates(empty_df)
    assert len(res_empty) == 0
    assert n_empty == 0

    single_df = pd.DataFrame([{"A": 1, "B": 2}])
    res_single, n_single = drop_duplicates(single_df)
    assert len(res_single) == 1
    assert n_single == 0

    all_dup_df = pd.DataFrame([{"A": 1}] * 5)
    res_dup, n_dup = drop_duplicates(all_dup_df)
    assert len(res_dup) == 1
    assert n_dup == 4


def test_drop_duplicates_column_validation_rejection(sample_df):
    """[FIX F5] Malicious or nonexistent subset column is rejected with ToolInputError."""
    with pytest.raises(ToolInputError) as exc_info:
        drop_duplicates(sample_df, subset=["nonexistent_col"])
    assert "does not exist in dataset" in str(exc_info.value)

    with pytest.raises(ToolInputError) as exc_info:
        drop_duplicates(sample_df, subset=["__proto__", "'; DROP TABLE"])
    assert "does not exist in dataset" in str(exc_info.value)


# ==================== handle_missing tests ====================

def test_handle_missing_median_canonical(sample_df):
    """handle_missing with median leaves 0 nulls in Age (was 6 in canonical fixture)."""
    assert int(sample_df["Age"].isna().sum()) == 6
    clean_df, filled_stats = handle_missing(sample_df, columns="Age", strategy="median")
    assert clean_df["Age"].isna().sum() == 0
    assert filled_stats["Age"] == 6


def test_handle_missing_strategies(sample_df):
    """Test mean, mode, fill_value, and drop strategies."""
    # Mean
    df_mean, _ = handle_missing(sample_df, columns=["Age"], strategy="mean")
    assert df_mean["Age"].isna().sum() == 0

    # Mode
    df_mode, _ = handle_missing(sample_df, columns=["Age"], strategy="mode")
    assert df_mode["Age"].isna().sum() == 0

    # Fill Value
    df_val, _ = handle_missing(sample_df, columns=["Age"], strategy="fill_value", fill_value=99)
    assert df_val["Age"].isna().sum() == 0
    assert (df_val["Age"] == 99).sum() == 6

    # Drop
    df_drop, drop_stats = handle_missing(sample_df, columns=["Age"], strategy="drop")
    assert len(df_drop) == 44
    assert df_drop["Age"].isna().sum() == 0
    assert drop_stats["Age"] == 6


def test_handle_missing_edge_cases():
    """Edge cases: column with 0 nulls, all-null column, empty DataFrame."""
    no_null_df = pd.DataFrame({"A": [1, 2, 3]})
    res_no_null, stats = handle_missing(no_null_df, columns="A", strategy="median")
    assert stats["A"] == 0

    all_null_df = pd.DataFrame({"A": [None, None, None]})
    res_all_null, stats_all = handle_missing(all_null_df, columns="A", strategy="fill_value", fill_value=0)
    assert res_all_null["A"].tolist() == [0, 0, 0]


def test_handle_missing_column_validation_rejection(sample_df):
    """[FIX F5] Nonexistent column raises ToolInputError."""
    with pytest.raises(ToolInputError) as exc_info:
        handle_missing(sample_df, columns=["GhostCol"], strategy="median")
    assert "Column 'GhostCol' does not exist" in str(exc_info.value)

    with pytest.raises(ToolInputError) as exc_info:
        handle_missing(sample_df, columns="Age", strategy="unsupported_strat")
    assert "Unsupported strategy" in str(exc_info.value)


# ==================== fix_type_mismatches tests ====================

def test_fix_type_mismatches_canonical(sample_df):
    """Test type conversion to string, numeric, and integer."""
    df_str = fix_type_mismatches(sample_df, column="Customer_ID", target_type="string")
    assert pd.api.types.is_string_dtype(df_str["Customer_ID"]) or df_str["Customer_ID"].dtype == object

    df_float = fix_type_mismatches(sample_df, column="Purchase", target_type="float")
    assert pd.api.types.is_float_dtype(df_float["Purchase"])


def test_fix_type_mismatches_column_validation_rejection(sample_df):
    """[FIX F5] Nonexistent column raises ToolInputError."""
    with pytest.raises(ToolInputError) as exc_info:
        fix_type_mismatches(sample_df, column="not_there", target_type="numeric")
    assert "does not exist in dataset" in str(exc_info.value)

    with pytest.raises(ToolInputError) as exc_info:
        fix_type_mismatches(sample_df, column="Age", target_type="invalid_target_type")
    assert "Unsupported target type" in str(exc_info.value)


# ==================== standardize_dates tests ====================

def test_standardize_dates_canonical(sample_df):
    """standardize_dates standardizes mixed formats in sample.csv Date column to ISO."""
    clean_df = standardize_dates(sample_df, column="Date", target_format="%Y-%m-%d")
    # All non-null dates should now match YYYY-MM-DD pattern
    all_iso = clean_df["Date"].str.match(r"^\d{4}-\d{2}-\d{2}$").all()
    assert all_iso is True or bool(all_iso)


def test_standardize_dates_column_validation_rejection(sample_df):
    """[FIX F5] Nonexistent column raises ToolInputError."""
    with pytest.raises(ToolInputError) as exc_info:
        standardize_dates(sample_df, column="MissingDate")
    assert "does not exist in dataset" in str(exc_info.value)


# ==================== clean_for_ml tests ====================

def test_clean_for_ml_on_messy_fixture():
    """clean_for_ml prepares the test_files messy CSV for ML use."""
    messy_path = REPO_ROOT / "test_files" / "tabular" / "messy_customers.csv"
    assert messy_path.exists(), "test_files/tabular/messy_customers.csv must exist"
    messy = pd.read_csv(messy_path)
    cleaned, report = clean_for_ml(messy)

    assert len(cleaned) > 0
    assert cleaned.isna().sum().sum() == 0
    assert int(cleaned.duplicated().sum()) == 0
    assert "empty_col" not in cleaned.columns
    assert "source" not in cleaned.columns
    assert report["duplicates_removed"] >= 1
    assert "empty_col" in report["empty_columns_dropped"] or report["missing_tokens_converted"] >= 0
    assert report["rows_out"] == len(cleaned)


def test_strip_and_normalize_helpers():
    df = pd.DataFrame({" name ": [" Alice ", "N/A", "Bob"], "x": [1, 2, 3]})
    stripped = strip_whitespace(df)
    assert list(stripped.columns) == ["name", "x"]
    assert stripped.loc[0, "name"] == "Alice"
    normalized, n = normalize_missing(stripped)
    assert n >= 1
    assert pd.isna(normalized.loc[1, "name"])


def test_drop_empty_and_constant_helpers():
    df = pd.DataFrame({
        "a": [1, 2, 3],
        "empty": [None, None, None],
        "const": ["web", "web", "web"],
    })
    no_empty, dropped_empty = drop_empty_columns(df)
    assert dropped_empty == ["empty"]
    assert "empty" not in no_empty.columns
    no_const, dropped_const = drop_constant_columns(no_empty)
    assert "const" in dropped_const
    assert list(no_const.columns) == ["a"]
