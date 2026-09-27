import pytest
from pathlib import Path
import pandas as pd
from backend.processors.tabular import TabularProcessor
from backend.models.schemas import Plan, Objective, ObjectiveCategory

def test_tabular_processor_cache_invalidation(tmp_path):
    # Setup test file
    df = pd.DataFrame({
        "ID": [1, 2],
        "Name": ["Alice", "Bob"],
        "Phone": ["555-1234", "555-5678"]
    })
    file_path = tmp_path / "test.csv"
    df.to_csv(file_path, index=False)
    
    processor = TabularProcessor()
    
    # 1. Profile loads into cache
    profile1 = processor.profile(file_path)
    assert any(c["name"] == "Phone" for c in profile1["columns"]), "Phone column should be in initial profile"
    
    # 2. Execute a drop column operation
    # A step dropping the Phone column
    from backend.models.schemas import Step
    plan = Plan(
        plan_id="p-1",
        session_id="s-1",
        objectives=[Objective(category=ObjectiveCategory.TRANSFORM, description="drop Phone", target_columns=["Phone"])],
        steps=[
            Step(
                step_number=1,
                tool_name="drop_column",
                description="Drop the Phone column",
                parameters={"column": "Phone"},
                expected_output="Phone column removed"
            )
        ]
    )
    
    result = processor.execute(file_path, plan, output_dir=tmp_path)
    assert "Phone" not in result["final_df"].columns, "Execute result must not have Phone"
    
    # 3. Profile again -> must see the cached update!
    profile2 = processor.profile(file_path)
    assert not any(c["name"] == "Phone" for c in profile2["columns"]), "Phone column must be absent from subsequent profile calls"
