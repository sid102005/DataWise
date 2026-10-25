"""Generate simple chart-friendly tabular fixtures under test_files/tabular/."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

OUT = Path(__file__).resolve().parent.parent / "test_files" / "tabular"
OUT.mkdir(parents=True, exist_ok=True)


def main() -> None:
    sales = pd.DataFrame(
        {
            "Region": ["North", "South", "East", "West"],
            "Sales": [12500, 9800, 15200, 11000],
            "Orders": [42, 35, 51, 38],
        }
    )
    sales.to_csv(OUT / "sales_by_region.csv", index=False)
    sales.to_json(OUT / "sales_by_region.json", orient="records", indent=2)
    sales.to_excel(OUT / "sales_by_region.xlsx", index=False)

    monthly = pd.DataFrame(
        {
            "Month": ["Jan", "Feb", "Mar", "Apr", "May", "Jun"],
            "Revenue": [8200, 9100, 10500, 9900, 11200, 12050],
        }
    )
    monthly.to_csv(OUT / "monthly_revenue.csv", index=False)

    products = pd.DataFrame(
        {
            "Product": ["Widget A", "Widget B", "Widget C", "Service Pack", "Add-on"],
            "Units": [120, 85, 60, 40, 25],
        }
    )
    products.to_csv(OUT / "product_mix.csv", index=False)

    # Multi-row store data — charts should group by Region
    store = pd.DataFrame(
        {
            "Region": ["North", "North", "South", "South", "East", "East", "West", "West"],
            "Store": ["A1", "A2", "B1", "B2", "C1", "C2", "D1", "D2"],
            "Sales": [4200, 3800, 5100, 2900, 6100, 4500, 3300, 4100],
        }
    )
    store.to_csv(OUT / "store_sales.csv", index=False)

    readme = OUT / "CHARTS_README.md"
    readme.write_text(
        """# Chart & conversion test files

Use these clean files for **charts** and **format conversion** (CSV ↔ JSON ↔ Excel).

| File | Best prompts |
| :--- | :--- |
| `sales_by_region.csv` / `.json` / `.xlsx` | `bar chart of Sales by Region` · `pie chart of Sales by Region` · `convert this csv to json` |
| `monthly_revenue.csv` | `line chart of Revenue by Month` |
| `product_mix.csv` | `pie chart of Units by Product` · `bar chart of Units by Product` |
| `store_sales.csv` | `bar chart of Sales by Region` (auto-aggregates stores) |
| `messy_customers.*` | ML clean first, then chart if you want |

## Conversion prompts

Upload any of the above, then:

- `convert this csv to json`
- `convert this json to csv`
- `convert to xlsx` / `convert to excel`
- `save as json`

You can leave the UI export dropdown as CSV — the **prompt overrides** it for convert requests.

## Chart prompts

- `bar chart of Sales by Region`
- `pie chart of Units by Product`
- `line chart of Revenue by Month`
- `plot a bar chart`
""",
        encoding="utf-8",
    )
    print(f"Wrote chart fixtures to {OUT}")


if __name__ == "__main__":
    main()
