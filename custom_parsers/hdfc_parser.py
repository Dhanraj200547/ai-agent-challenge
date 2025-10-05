
import pdfplumber
import re
from decimal import Decimal, InvalidOperation

def parse_pdf(pdf_path: str) -> list[dict]:
    """
    Parses an HDFC bank statement PDF to extract transaction data.

    Args:
        pdf_path: The file path to the PDF statement.

    Returns:
        A list of dictionaries, where each dictionary represents a transaction
        matching the target CSV format.
    """
    transactions_interim = []
    full_text = ""

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text(x_tolerance=2, y_tolerance=2)
            if text:
                full_text += text
                # Add a marker to distinguish page ends from normal line breaks
                full_text += "\n---PAGE_BREAK---\n"

    lines = full_text.split('\n')

    date_pattern = re.compile(r'^\d{2}/\d{2}/\d{2}$')
    amount_pattern = re.compile(r'^-?[\d,]+\.\d{2}$')

    in_transactions_section = False
    last_balance = None

    for line in lines:
        line = line.strip()

        if "Date Narration Chq./Ref.No. ValueDt" in line:
            in_transactions_section = True
            continue
        
        if "---PAGE_BREAK---" in line or not in_transactions_section or not line:
            continue
        
        if line.startswith('*Closingbalance') or line.startswith('Stateaccountbranch'):
            in_transactions_section = False
            continue

        parts = line.split()
        if not parts:
            continue
        
        is_transaction_line = date_pattern.match(parts[0])

        if is_transaction_line:
            try:
                # Case 1: Full line with both withdrawal and deposit columns present
                balance_str = parts[-1]
                deposit_str = parts[-2]
                withdrawal_str = parts[-3]
                value_dt_str = parts[-4]
                
                if (amount_pattern.match(balance_str) and
                    amount_pattern.match(deposit_str) and
                    amount_pattern.match(withdrawal_str) and
                    date_pattern.match(value_dt_str) and
                    len(parts) >= 7):
                    
                    date_str = parts[0]
                    ref_no_str = parts[-5]
                    narration = ' '.join(parts[1:-5])
                    
                    transactions_interim.append({
                        "date": date_str, "narration": narration, "ref_no": ref_no_str,
                        "value_dt": value_dt_str, "withdrawal": withdrawal_str,
                        "deposit": deposit_str, "balance": balance_str
                    })
                    last_balance = Decimal(balance_str.replace(',', ''))
                    continue

                # Case 2: Partial line where one of the amount columns is missing
                balance_str = parts[-1]
                amount_str = parts[-2]
                value_dt_str = parts[-3]
                
                if (amount_pattern.match(balance_str) and
                    amount_pattern.match(amount_str) and
                    date_pattern.match(value_dt_str) and
                    len(parts) >= 6):
                    
                    date_str = parts[0]
                    ref_no_str = parts[-4]
                    narration = ' '.join(parts[1:-4])
                    current_balance = Decimal(balance_str.replace(',', ''))
                    
                    withdrawal = "0.00"
                    deposit = "0.00"

                    # Determine if it's a withdrawal or deposit by comparing balances
                    if last_balance is not None:
                        if current_balance > last_balance:
                            deposit = amount_str
                        else:
                            withdrawal = amount_str
                    else:
                        # Guess for the first transaction if state isn't available
                        if 'fee' in narration.lower() or 'charge' in narration.lower():
                            withdrawal = amount_str
                        else:
                            deposit = amount_str
                    
                    transactions_interim.append({
                        "date": date_str, "narration": narration, "ref_no": ref_no_str,
                        "value_dt": value_dt_str, "withdrawal": withdrawal,
                        "deposit": deposit, "balance": balance_str
                    })
                    last_balance = current_balance
                    continue
            except (IndexError, InvalidOperation):
                pass

        # If it's not a new transaction line, it is a continuation of the previous narration
        if transactions_interim:
            # Avoid appending junk lines that might be part of headers on new pages
            if "PageNo.:" not in line and "AccountBranch :" not in line:
                 transactions_interim[-1]['narration'] += ' ' + line

    # Format the interim data into the final required structure
    final_transactions = []
    for tx in transactions_interim:
        try:
            withdrawal_val = Decimal(tx['withdrawal'].replace(',', ''))
        except (InvalidOperation, KeyError):
            withdrawal_val = Decimal('0.0')

        # The target 'Withdrawal Amt.' column holds either the withdrawal or deposit amount
        transaction_amount = tx['withdrawal'] if withdrawal_val != Decimal('0.0') else tx['deposit']

        final_transactions.append({
            'Date': tx['date'],
            'Narration': tx['narration'].strip(),
            'Chq/Ref.No': tx['ref_no'].lstrip('0'),
            'Value Date': tx['value_dt'],
            'Withdrawal Amt.': transaction_amount,
            'Closing Balance': tx['balance']
        })

    return final_transactions
