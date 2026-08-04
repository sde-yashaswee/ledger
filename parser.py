import json
import re
import os
import uuid
from bs4 import BeautifulSoup

def parse_ledger(file_path):
    """
    Parses a Tally-style HTML ledger export (UTF-16 LE) and converts it to JSON.
    Handles multi-line entries, invoice number continuations, and split transactions.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Error: File not found at {file_path}")

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

    current_date = None
    
    for line in lines:
        if not line.strip():
            continue
        
        # Slicing
        date_raw = line[COL_RANGES['date'][0]:COL_RANGES['date'][1]].strip()
        deb_raw = line[COL_RANGES['debit'][0]:COL_RANGES['debit'][1]].strip()
        cre_raw = line[COL_RANGES['credit'][0]:COL_RANGES['credit'][1]].strip()
        
        # IGNORE structural text and noise
        if any(x in line for x in ["Totals b/d", "Totals c/o", "contd.", "L E D G E R", "Account :", "Page", "Debit Balance", "Credit Balance", "Grand Total", "Total"]):
            continue
        if "---" in line or "===" in line:
            continue
        if "Date" in line and "Particulars" in line:
            continue

        clean_deb = clean_currency(deb_raw)
        clean_cre = clean_currency(cre_raw)

        # VALIDATION LOGIC:
        # 1. If it has a date, update the current_date and process.
        # 2. If it has NO date but HAS a debit/credit value, use the current_date and process.
        # 3. Otherwise, skip (it's a text-only continuation or noise).
        
        has_date = bool(date_pattern.match(date_raw))
        has_value = bool(clean_deb or clean_cre)
        
        if has_date:
            current_date = date_raw
        elif has_value and current_date:
            # This is a split transaction or adjustment line without a date
            # Inherit the date from the previous record
            pass
        else:
            # Noise or text-only continuation with no financial value
            continue

        # Extract remaining fields
        type_raw = line[COL_RANGES['type'][0]:COL_RANGES['type'][1]].strip()
        vch_raw = line[COL_RANGES['vch_no'][0]:COL_RANGES['vch_no'][1]].strip()
        part_raw = line[COL_RANGES['particulars'][0]:COL_RANGES['particulars'][1]].strip()
        narr_raw = line[COL_RANGES['narration'][0]:COL_RANGES['narration'][1]].strip()
        bal_raw = line[COL_RANGES['balance'][0]:COL_RANGES['balance'][1]].strip()
        
        clean_bal = clean_currency(bal_raw)
        
        # Determine if balance is Dr or Cr
        bal_is_cr = "Cr" in bal_raw
        
        val_deb = float(clean_deb) if clean_deb else 0.0
        val_cre = float(clean_cre) if clean_cre else 0.0
        val_bal = float(clean_bal) if clean_bal else 0.0
        if bal_is_cr: val_bal = -val_bal

        parsed_debit_sum += val_deb
        parsed_credit_sum += val_cre
        
        # Mathematical verification
        expected_balance = running_balance + val_deb - val_cre
        
        # 0.01 tolerance
        if abs(expected_balance - val_bal) > 0.01:
            errors.append({
                "Serial Number": serial_no,
                "Date": current_date,
                "Expected_Balance": round(expected_balance, 2),
                "Sheet_Balance": round(val_bal, 2),
                "Difference": round(expected_balance - val_bal, 2)
            })
            all_rows_match = False
        
        running_balance = val_bal

        results.append({
            "Serial Number": serial_no,
            "Date": current_date,
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

    # =========================================================================
    # FIFO BILL ALGORITHM (Integrated from Apps Script)
    # =========================================================================
    
    total_bills = sum(1 for r in results if r["Debit"])
    
    running_balance_num = 0.0
    queue = []
    last_invoice_id = None
    invoice_counter = 0

    for row in results:
        deb_val = float(row['Debit']) if row['Debit'] else 0.0
        cre_val = float(row['Credit']) if row['Credit'] else 0.0
        
        running_balance_num += (deb_val - cre_val)
        
        if deb_val > 0:
            invoice_counter += 1
            queue.append({
                "id": str(uuid.uuid4()),
                "serial": invoice_counter,
                "date": row['Date'],
                "amount": deb_val,
                "balance": deb_val
            })
            
        payment = cre_val
        while payment > 0 and queue:
            oldest = queue[0]
            if payment >= oldest["balance"]:
                payment -= oldest["balance"]
                queue.pop(0)
            else:
                oldest["balance"] -= payment
                payment = 0
                
        serial = ""
        bill_date = ""
        bill_amount = ""
        bill_balance = ""
        
        if queue:
            current = queue[0]
            bill_balance = current["balance"]
            if last_invoice_id != current["id"]:
                serial = f"{current['serial']} / {total_bills}"
                bill_date = current["date"]
                bill_amount = current["amount"]
                last_invoice_id = current["id"]
        else:
            last_invoice_id = None
            
        row["Running Balance"] = round(running_balance_num, 2)
        row["Bill Date"] = bill_date
        row["Bill Value"] = f"{bill_amount:.2f}" if bill_amount != "" else ""
        row["B Wise Bc"] = f"{bill_balance:.2f}" if bill_balance != "" else ""
        row["Bill Serial"] = serial

    return {
        "verification": verification,
        "errors": errors,
        "data": results
    }

if __name__ == "__main__":
    input_path = '/Users/yashaswee/ledger/input/sample-2.htm'
    
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
