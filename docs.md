# Ledger Pro: Verification & Technical Summary

## Audit & Reconciliation Logic
Ledger Pro implements a rigorous mathematical audit to ensure data integrity during the conversion from fixed-width HTML to programmable formats.

### 1. Verification Mechanism
- **Row-Level Integrity**: For every transaction, the system calculates: 
  `Expected Balance = Previous Balance + Debit - Credit`.
- **Validation**: This is compared against the "Balance" column on the sheet. Any difference > 0.01 triggers an entry in the `errors` object.
- **Grand Reconciliation**: The final running balance is factored into the total sums to reconcile against the "Grand Total" found at the bottom of the ledger.

### 2. Output Structure
The generated JSON contains three primary sections:
- `verification`: High-level success flags and reconciled totals.
- `errors`: Specific details on any mathematical discrepancies found.
- `data`: The cleaned array of transaction records.

### 3. Record Filtering
- **Date Inheritance**: Rows without a date but containing financial values (like discount adjustments) inherit the date from the previous valid transaction.
- **Noise Filtering**: Automatically ignores "Totals b/d", "Totals c/o", and structural report headers to prevent double-counting.

## Technical Details
- **Parser Engine**: Python State-Machine with Fixed-Width Slicing.
- **GUI Framework**: Tkinter (Native Cross-Platform).
- **Dependencies**: `beautifulsoup4`, `pandas`, `openpyxl`.
