# DataWise ML cleaning test files

Use these messy tabular files to verify **Clean for ML** on CSV, JSON, and spreadsheet (XLSX).

## Files

| File | Format |
| :--- | :--- |
| messy_customers.csv | CSV |
| messy_customers.json | JSON |
| messy_customers.xlsx | Excel spreadsheet |

## Deliberate mess included

- Leading/trailing spaces in headers and names
- Missing tokens: blank, N/A, 
ull, -, ?, missing
- Duplicate rows
- Mixed date formats
- Numeric values stored as text
- An all-empty / placeholder column (empty_col)
- A constant column (source = always web)

## How to test in the UI

1. Start DataWise (backend + Streamlit).
2. Upload one of the files above.
3. Prompt examples:
   - clean this for ML
   - clean this CSV so I can use it in my ML project
   - prepare this data for machine learning
4. Confirm the result has: no nulls, no duplicates, no empty/constant columns, standardized dates, and download the cleaned file.

## Expected cleanup effects

- Duplicate rows removed
- Missing tokens turned into imputed values (median/mode)
- empty_col dropped
- source dropped (constant / no ML signal)
- ge / purchase coerced to numeric where possible
- signup_date standardized to ISO YYYY-MM-DD
- Whitespace stripped from text fields
