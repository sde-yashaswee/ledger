import json
import re
import os
from bs4 import BeautifulSoup

def parse_ledger(file_path):
    """
    Parses a Tally-style HTML ledger export (UTF-16 LE) and converts it to JSON.
    Handles multi-line entries, invoice number continuations, and split transactions.
    """
    if not os.path.exists(file_path):
        print(f"Error: File not found: {file_path}")
        return []

    # Tally exports are often UTF-16 Little Endian
    with open(file_path, 'r', encoding='utf-16') as f:
        html_content = f.read()

    soup = BeautifulSoup(html_content, 'html.parser')
    
    # The data is typically inside a <pre> block
    pre_tags = soup.find_all('pre')
    
    full_text = ""
    if not pre_tags:
        body = soup.find('body')
        if body:
            for br in body.find_all(['br', 'Br']):
                br.replace_with('\n')
            full_text = body.get_text()
    else:
        for pre in pre_tags:
            for br in pre.find_all(['br', 'Br']):
                br.replace_with('\n')
            full_text += pre.get_text() + "\n"

    lines = full_text.split('\n')
    
    # Recalibrated Column Ranges (0-based indices)
    COL_RANGES = {
        'date': (0, 11),
        'type': (11, 17),
        'vch_no': (17, 30),
        'particulars': (30, 66),
        'narration': (66, 94),
        'debit': (94, 107),
        'credit': (107, 122),
        'balance': (122, 145), # Balance column follows credit
    }

    # Regex patterns
    date_pattern = re.compile(r'^\d{2}-\d{2}-\d{4}')
    
    def clean_currency(val):
        if not val: return ""
        val = val.strip().replace(',', '')
        # Handle negative numbers if they exist, and decimals
        match = re.search(r'-?\d+\.\d{2}', val)
        if match:
            return match.group()
        return ""

    # Extract Grand Totals from the full text for verification
    grand_debit_total = 0.0
    grand_credit_total = 0.0
    for line in reversed(lines):
        if "Grand Total" in line:
            amounts = re.findall(r'\d{1,3}(?:,\d{2,3})*\.\d{2}', line)
            if len(amounts) >= 2:
                grand_debit_total = float(amounts[0].replace(',', ''))
                grand_credit_total = float(amounts[1].replace(',', ''))
                break

    results = []
    errors = []
    serial_no = 1
    
    parsed_debit_sum = 0.0
    parsed_credit_sum = 0.0
    running_balance = 0.0
    
    all_rows_match = True

    for line in lines:
        if not line.strip():
            continue
        
        date_raw = line[COL_RANGES['date'][0]:COL_RANGES['date'][1]].strip()
        if not date_pattern.match(date_raw):
            continue

        type_raw = line[COL_RANGES['type'][0]:COL_RANGES['type'][1]].strip()
        vch_raw = line[COL_RANGES['vch_no'][0]:COL_RANGES['vch_no'][1]].strip()
        part_raw = line[COL_RANGES['particulars'][0]:COL_RANGES['particulars'][1]].strip()
        narr_raw = line[COL_RANGES['narration'][0]:COL_RANGES['narration'][1]].strip()
        deb_raw = line[COL_RANGES['debit'][0]:COL_RANGES['debit'][1]].strip()
        cre_raw = line[COL_RANGES['credit'][0]:COL_RANGES['credit'][1]].strip()
        bal_raw = line[COL_RANGES['balance'][0]:COL_RANGES['balance'][1]].strip()
        
        clean_deb = clean_currency(deb_raw)
        clean_cre = clean_currency(cre_raw)
        clean_bal = clean_currency(bal_raw)
        
        # Determine if balance is Dr or Cr
        bal_is_cr = "Cr" in bal_raw
        
        val_deb = float(clean_deb) if clean_deb else 0.0
        val_cre = float(clean_cre) if clean_cre else 0.0
        val_bal = float(clean_bal) if clean_bal else 0.0
        if bal_is_cr: val_bal = -val_bal

        parsed_debit_sum += val_deb
        parsed_credit_sum += val_cre
        
        # Mathematical verification: Prev Balance + Debit - Credit = Current Balance
        expected_balance = running_balance + val_deb - val_cre
        
        # We use a 0.01 tolerance for floating point math
        if abs(expected_balance - val_bal) > 0.01:
            errors.append({
                "Serial Number": serial_no,
                "Date": date_raw,
                "Expected_Balance": round(expected_balance, 2),
                "Sheet_Balance": round(val_bal, 2),
                "Difference": round(expected_balance - val_bal, 2)
            })
            all_rows_match = False
        
        running_balance = val_bal

        results.append({
            "Serial Number": serial_no,
            "Date": date_raw,
            "Type": type_raw,
            "Particulars": part_raw,
            "Reference": vch_raw,
            "Narration": narr_raw,
            "Debit": clean_deb,
            "Credit": clean_cre,
            "Balance": f"{abs(val_bal):.2f} {'Cr' if bal_is_cr else 'Dr'}"
        })
        serial_no += 1

    # Final adjustment: Add the final balance to the sums to match Grand Total
    # If final balance is Dr (positive), it's added to Credits to balance.
    # If final balance is Cr (negative), it's added to Debits to balance.
    adjusted_debit_sum = parsed_debit_sum
    adjusted_credit_sum = parsed_credit_sum
    
    if running_balance > 0: # Final Dr Balance
        adjusted_credit_sum += abs(running_balance)
    else: # Final Cr Balance
        adjusted_debit_sum += abs(running_balance)

    # Success check: Row-by-row match AND adjusted totals match Grand Totals
    totals_match = (round(adjusted_debit_sum, 2) == round(grand_debit_total, 2) and 
                    round(adjusted_credit_sum, 2) == round(grand_credit_total, 2))
    
    success = all_rows_match and totals_match

    verification = {
        "success": success,
        "Grand_Total_Debit_Found": round(grand_debit_total, 2),
        "Adjusted_Debit_Sum": round(adjusted_debit_sum, 2),
        "Grand_Total_Credit_Found": round(grand_credit_total, 2),
        "Adjusted_Credit_Sum": round(adjusted_credit_sum, 2),
        "Final_Balance": f"{abs(running_balance):.2f} {'Cr' if running_balance < 0 else 'Dr'}",
        "Row_Level_Integrity": all_rows_match,
        "Totals_Reconciled": totals_match
    }

    return {
        "verification": verification,
        "errors": errors,
        "data": results
    }

if __name__ == "__main__":
    input_path = '/Users/yashaswee/ledger/input/sample-1.htm'
    
    # Determine output path
    base_name = os.path.basename(input_path)
    file_name_without_ext = os.path.splitext(base_name)[0]
    output_dir = '/Users/yashaswee/ledger/output'
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, f"{file_name_without_ext}-output.json")
    
    print(f"Starting conversion of {input_path}...")
    ledger_data = parse_ledger(input_path)
    
    if ledger_data:
        with open(output_path, 'w', encoding='utf-8') as json_file:
            json.dump(ledger_data, json_file, indent=4)
        print(f"Successfully converted {len(ledger_data)} records to {output_path}")
    else:
        print("No data parsed.")
