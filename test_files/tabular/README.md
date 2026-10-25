# Tabular test files (CSV / JSON / Excel)

Messy customer data for testing **ML cleaning** and other tabular prompts.

| File | Format |
| :--- | :--- |
| `messy_customers.csv` | CSV |
| `messy_customers.json` | JSON |
| `messy_customers.xlsx` | Excel spreadsheet |

## Deliberate mess

- Leading/trailing spaces in headers and names  
- Missing tokens: blank, `N/A`, `null`, `-`, `?`  
- Duplicate rows  
- Mixed date formats  
- Numeric values stored as text  
- Empty column (`empty_col`)  
- Constant column (`source` = always `web`)  

## Prompts to try

- `clean this for ML`
- `clean this CSV so I can use it in my ML project`
- `prepare this data for machine learning`
- `sort by Age ascending`
- `show only name and age columns`
- `filter rows where age > 30`

See [`USAGE_GUIDE.md`](../../USAGE_GUIDE.md) for the full checklist.
