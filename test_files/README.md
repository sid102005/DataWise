# DataWise test files

Test inputs are split by file kind:

```text
test_files/
├── tabular/      ← CSV, JSON, Excel (ML cleaning)
└── documents/    ← PDF, DOCX, TXT, MD (document extraction)
```

## `tabular/` — spreadsheet-style data

| File | Format |
| :--- | :--- |
| `messy_customers.csv` | CSV |
| `messy_customers.json` | JSON |
| `messy_customers.xlsx` | Excel |

Use for: `clean this for ML`, filters, sorts, column select, groupby.

## `documents/` — document extraction

| File | Format |
| :--- | :--- |
| `sample_report.pdf` | PDF |
| `sample_invoice.docx` | Word |
| `sample_report.txt` | Plain text |
| `sample_overview.md` | Markdown |

Use for: extract text/tables/entities, redact, summarize, headings, page split, etc.

Regenerate documents:

```powershell
.venv\Scripts\python.exe scripts\generate_document_test_files.py
```

Full prompts and how-to: [`USAGE_GUIDE.md`](../USAGE_GUIDE.md) (and `USAGE_GUIDE.pdf`).
