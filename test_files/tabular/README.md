# Tabular test files (CSV / JSON / Excel)

## ML cleaning (messy)

| File | Format |
| :--- | :--- |
| `messy_customers.csv` | CSV |
| `messy_customers.json` | JSON |
| `messy_customers.xlsx` | Excel |

Prompts: `clean this for ML`, `sort by Age ascending`, `filter rows where age > 30`

## Charts & conversion (clean)

Generate/refresh with:

```powershell
.venv\Scripts\python.exe scripts\generate_chart_fixtures.py
```

| File | Try these prompts |
| :--- | :--- |
| `sales_by_region.csv` / `.json` / `.xlsx` | `bar chart of Sales by Region` · `pie chart of Sales by Region` · `convert this csv to json` |
| `monthly_revenue.csv` | `line chart of Revenue by Month` |
| `product_mix.csv` | `pie chart of Units by Product` |
| `store_sales.csv` | `bar chart of Sales by Region` (groups stores) |

### Format conversion

Prompt overrides the UI export dropdown:

- `convert this csv to json`
- `convert this json to csv`
- `convert to xlsx` / `save as excel`

Then open the **Downloads** tab for the converted file. Charts appear under **Charts**.

See also [`CHARTS_README.md`](CHARTS_README.md) and [`USAGE_GUIDE.md`](../../USAGE_GUIDE.md).
