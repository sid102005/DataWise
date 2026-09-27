"""Unit and security tests for DataWise charting tools (backend/tools/chart.py)."""

from pathlib import Path
import pandas as pd
import pytest

from backend.tools.chart import bar_chart, line_chart, pie_chart
from backend.core.exceptions import ToolInputError

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SAMPLE_CSV = REPO_ROOT / "tests" / "fixtures" / "sample.csv"


@pytest.fixture
def sample_df() -> pd.DataFrame:
    """Load clean instance of Phase 1 canonical sample.csv."""
    return pd.read_csv(SAMPLE_CSV)


def test_bar_chart_generation(sample_df, tmp_path: Path):
    """Test generating a bar chart and verifying file existence and non-zero size."""
    chart_path = bar_chart(
        sample_df,
        x="Region",
        y="Purchase",
        title="Purchases by Region",
        output_dir=tmp_path,
    )
    assert chart_path.exists()
    assert chart_path.is_file()
    assert chart_path.stat().st_size > 0
    assert chart_path.suffix == ".png"


def test_bar_chart_validation_rejection(sample_df, tmp_path: Path):
    """[FIX F5] Nonexistent X or Y column raises ToolInputError."""
    with pytest.raises(ToolInputError) as exc_info:
        bar_chart(sample_df, x="GhostX", y="Purchase", output_dir=tmp_path)
    assert "does not exist in dataset" in str(exc_info.value)

    with pytest.raises(ToolInputError) as exc_info:
        bar_chart(sample_df, x="Region", y="GhostY", output_dir=tmp_path)
    assert "does not exist in dataset" in str(exc_info.value)


def test_line_chart_generation(sample_df, tmp_path: Path):
    """Test generating a line chart and verifying file existence and non-zero size."""
    chart_path = line_chart(
        sample_df.head(10),
        x="Name",
        y="Purchase",
        title="Top Purchases",
        output_dir=tmp_path,
    )
    assert chart_path.exists()
    assert chart_path.is_file()
    assert chart_path.stat().st_size > 0
    assert chart_path.suffix == ".png"


def test_line_chart_validation_rejection(sample_df, tmp_path: Path):
    """[FIX F5] Nonexistent column raises ToolInputError."""
    with pytest.raises(ToolInputError) as exc_info:
        line_chart(sample_df, x="BadCol", y="Purchase", output_dir=tmp_path)
    assert "does not exist in dataset" in str(exc_info.value)


def test_pie_chart_generation(sample_df, tmp_path: Path):
    """Test generating a pie chart and verifying file existence and non-zero size."""
    # Aggregate by Region first for clean pie chart
    region_totals = sample_df.groupby("Region", as_index=False)["Purchase"].sum()
    chart_path = pie_chart(
        region_totals,
        labels="Region",
        values="Purchase",
        title="Regional Purchase Share",
        output_dir=tmp_path,
    )
    assert chart_path.exists()
    assert chart_path.is_file()
    assert chart_path.stat().st_size > 0
    assert chart_path.suffix == ".png"


def test_pie_chart_validation_rejection(sample_df, tmp_path: Path):
    """[FIX F5] Nonexistent column raises ToolInputError."""
    with pytest.raises(ToolInputError) as exc_info:
        pie_chart(sample_df, labels="FakeLabel", values="Purchase", output_dir=tmp_path)
    assert "does not exist in dataset" in str(exc_info.value)
