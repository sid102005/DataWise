"""Unit and security tests for DataWise aggregation tools (backend/tools/aggregate.py)."""

import json
from pathlib import Path
import pandas as pd
import pytest

from backend.tools.aggregate import (
    groupby_aggregate,
    sort_values,
    top_n,
)
from backend.core.exceptions import ToolInputError

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SAMPLE_CSV = REPO_ROOT / "tests" / "fixtures" / "sample.csv"
EXPECTED_PROFILE = REPO_ROOT / "tests" / "fixtures" / "expected_sample_profile.json"


@pytest.fixture
def sample_df() -> pd.DataFrame:
    """Load clean instance of Phase 1 canonical sample.csv."""
    return pd.read_csv(SAMPLE_CSV)


@pytest.fixture
def ground_truth() -> dict:
    """Load ground truth profile."""
    with open(EXPECTED_PROFILE, "r", encoding="utf-8") as f:
        return json.load(f)


# ==================== groupby_aggregate tests ====================

def test_groupby_aggregate_canonical(sample_df):
    """Test group by Region summing Purchase."""
    grouped = groupby_aggregate(sample_df, by="Region", metric="Purchase", agg="sum")
    assert len(grouped) == 4
    assert set(grouped["Region"]) == {"North", "South", "East", "West"}
    assert "Purchase" in grouped.columns


def test_groupby_aggregate_validation_rejection(sample_df):
    """[FIX F5] Nonexistent grouping column, metric, or non-numeric sum raises ToolInputError."""
    with pytest.raises(ToolInputError) as exc_info:
        groupby_aggregate(sample_df, by="NonexistentRegion", metric="Purchase", agg="sum")
    assert "Column 'NonexistentRegion' does not exist" in str(exc_info.value)

    with pytest.raises(ToolInputError) as exc_info:
        groupby_aggregate(sample_df, by="Region", metric="GhostMetric", agg="sum")
    assert "Column 'GhostMetric' does not exist" in str(exc_info.value)

    # Trying to sum non-numeric text column
    with pytest.raises(ToolInputError) as exc_info:
        groupby_aggregate(sample_df, by="Region", metric="Name", agg="sum")
    assert "Cannot compute 'sum' on non-numeric metric" in str(exc_info.value)


# ==================== sort_values and top_n tests ====================

def test_sort_values_and_top_n_matches_ground_truth(sample_df, ground_truth):
    """Sort Purchase descending + top_n(10) matches ground truth top-10 exactly in order."""
    sorted_df = sort_values(sample_df, column="Purchase", ascending=False)
    top10_df = top_n(sorted_df, n=10)

    assert len(top10_df) == 10
    actual_top10 = top10_df["Purchase"].tolist()
    expected_top10 = [item["purchase"] for item in ground_truth["top_10_purchases"]]

    assert actual_top10 == expected_top10
    assert actual_top10 == [
        9850.5,
        9420.0,
        8900.25,
        8650.0,
        8200.75,
        7950.0,
        7600.5,
        7350.0,
        7100.25,
        6850.0,
    ]


def test_top_n_edge_case_n_greater_than_len(sample_df):
    """[EDGE CASE] top_n with n > len(df) returns all rows without error."""
    assert len(sample_df) == 50
    result_df = top_n(sample_df, n=1000)
    assert len(result_df) == 50
    assert len(result_df) == len(sample_df)


def test_top_n_invalid_n(sample_df):
    """top_n with n <= 0 raises ToolInputError."""
    with pytest.raises(ToolInputError) as exc_info:
        top_n(sample_df, n=0)
    assert "must be a positive integer" in str(exc_info.value)

    with pytest.raises(ToolInputError) as exc_info:
        top_n(sample_df, n=-5)
    assert "must be a positive integer" in str(exc_info.value)


def test_sort_values_validation_rejection(sample_df):
    """[FIX F5] Nonexistent sort column raises ToolInputError."""
    with pytest.raises(ToolInputError) as exc_info:
        sort_values(sample_df, column="bogus_col", ascending=False)
    assert "Column 'bogus_col' does not exist" in str(exc_info.value)
