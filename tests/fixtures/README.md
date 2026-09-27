# Canonical Test Fixtures Ground Truth

This directory contains the immutable, canonical test fixtures for the DataWise project.
All subsequent development phases (Phase 2 through Phase 7) MUST reuse these exact fixtures
and test their output against the audited ground truth numbers documented here.

---

## 1. Primary Dataset: `sample.csv`, `sample.xlsx`, `sample.json`

The three files represent the identical logical dataset of customer transactions across CSV, Excel, and JSON formats.

### Global Dimensions
- **Total Rows:** `50`
- **Total Columns:** `6`
- **Column Names:** `["Customer_ID", "Name", "Age", "Date", "Purchase", "Region"]`
- **Unique Rows:** `46`
- **Duplicate Rows:** `4` (`8.0%` duplicate rate)

### Exact Duplicate Row Placement (0-Indexed Data Rows)
1. **Index 25:** Exact duplicate of index 11 (`Customer_ID: 1012`, `Laura Croft`, `Age: 33`, `Date: 21/03/2024`, `Purchase: 5950.00`, `Region: West`)
2. **Index 35:** Exact duplicate of index 13 (`Customer_ID: 1014`, `Nancy Wheeler`, `Age: 22`, `Date: 2024-04-02`, `Purchase: 4800.00`, `Region: South`)
3. **Index 45:** Exact duplicate of index 15 (`Customer_ID: 1016`, `Pam Beesly`, `Age: 30`, `Date: 2024-04-12`, `Purchase: 4300.00`, `Region: West`)
4. **Index 49:** Exact duplicate of index 20 (`Customer_ID: 1021`, `Ursula Buffay`, `Age: 36`, `Date: 12/05/2024`, `Purchase: 3150.00`, `Region: North`)

*Design Decision:* None of the duplicate rows originate from the top-10 purchase tiers, nor do any contain missing Age values. This ensures that top-N queries and null statistics remain strictly deterministic regardless of whether deduplication executes before or after other operations.

### Missing Value (Null) Distribution
- `Customer_ID`: `0` missing
- `Name`: `0` missing
- `Age`: `6` missing (`12.0%` null rate)
  - 0-Indexed row indices with null Age: `5, 12, 18, 27, 36, 44` (Customers `1006, 1013, 1019, 1026, 1034, 1042`)
- `Date`: `0` missing
- `Purchase`: `0` missing
- `Region`: `0` missing

### Date Format Distribution (Mixed Formats for Clarification Testing)
- Total rows with `YYYY-MM-DD` (ISO): `33`
- Total rows with `DD/MM/YYYY`: `17`
- Demonstrates realistic real-world data quality issues requiring format inference and ambiguity detection.

### Categorical Distribution (`Region`)
- `North`: `13`
- `South`: `13`
- `West`: `13`
- `East`: `11`
- Total: `50` rows across `4` distinct regions (>= 3 required).

### Unambiguous Top 10 Purchases
No two values in the top-10 purchases are identical:
1. **Rank 1:** `$9,850.50` (`Customer_ID: 1001`, Alice Smith)
2. **Rank 2:** `$9,420.00` (`Customer_ID: 1002`, Bob Jones)
3. **Rank 3:** `$8,900.25` (`Customer_ID: 1003`, Charlie Brown)
4. **Rank 4:** `$8,650.00` (`Customer_ID: 1004`, Diana Prince)
5. **Rank 5:** `$8,200.75` (`Customer_ID: 1005`, Evan Wright)
6. **Rank 6:** `$7,950.00` (`Customer_ID: 1007`, George Clark)
7. **Rank 7:** `$7,600.50` (`Customer_ID: 1008`, Hannah Abbott)
8. **Rank 8:** `$7,350.00` (`Customer_ID: 1009`, Ian Malcolm)
9. **Rank 9:** `$7,100.25` (`Customer_ID: 1010`, Julia Roberts)
10. **Rank 10:** `$6,850.00` (`Customer_ID: 1011`, Kevin Bacon)

All rank 11–50 values are strictly `< $6,500.00`.

---

## 2. Structural Error Fixture: `malformed.csv`

Used for negative testing of Stage 1 (Data Understanding) and Input Manager:
- Contains inconsistent delimiters, ragged rows (e.g. 3 columns instead of 6), and unclosed quotes.
- Expected behavior: Parser safely flags parsing exception / malformed structure without crashing the server.

---

## 3. Extension Rejection Fixture: `oversized_placeholder.txt`

Used for file rejection testing:
- Contains text with `.txt` extension.
- Expected behavior: InputManager rejects with `400 Bad Request` or `ErrorResponse` indicating unsupported format.

---

## 4. Security Fixture: `path_traversal_attempt.csv`

Used for Phase 2 security testing:
- A valid 2-row CSV dataset.
- Test Scenario: When uploaded via HTTP multipart with a simulated malicious filename header such as `filename="../../../etc/evil.csv"`, the InputManager MUST sanitize the filename and store it only inside the dedicated session workspace folder (`workspace/sessions/{session_id}/`), completely ignoring any directory traversal sequences.
