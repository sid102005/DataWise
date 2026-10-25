# Chart & conversion test files

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
