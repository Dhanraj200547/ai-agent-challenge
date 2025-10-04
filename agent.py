import os
import sys
import subprocess
import pandas as pd
import google.generativeai as genai
from argparse import ArgumentParser
import pdfplumber
import json

# --- Constants ---
MAX_ATTEMPTS = 3
MODEL_NAME = "gemini-2.5-pro" # Using a more powerful model for this complex task

SYSTEM_PROMPT = """
You are an expert Python developer specializing in complex data extraction from PDFs.
Your task is to write a Python script to parse a bank statement PDF to match a specific, sometimes unusual, CSV format.
You must only output the raw Python code for the parser file.
Do not include any explanations, markdown formatting, or any text other than the code itself.
The code must contain a function with the exact signature: `parse_pdf(pdf_path: str) -> list[dict]`
Use the `pdfplumber` library for PDF processing.
"""

# --- Helper Functions ---
def get_user_prompt(bank_name, csv_path, pdf_path, feedback=""):
    """Constructs the user-facing prompt with specific instructions."""
    expected_df = pd.read_csv(csv_path)
    csv_headers = list(expected_df.columns)
    # Use fillna('') to represent empty CSV columns as empty strings for the prompt
    csv_example_rows = expected_df.head(4).fillna('').to_string(index=False)

    try:
        with pdfplumber.open(pdf_path) as pdf:
            raw_pdf_text = "\n".join(page.extract_text() for page in pdf.pages if page.extract_text())
            pdf_text_snippet = raw_pdf_text[:4000]
    except Exception:
        pdf_text_snippet = "Could not read PDF content."

    prompt = f"""
Target Bank: {bank_name}

--- RAW PDF TEXT SNIPPET (FOR STRUCTURE ANALYSIS ONLY) ---
{pdf_text_snippet}
--- END SNIPPET ---

--- TARGET CSV FORMAT (THIS IS THE GOAL) ---
CSV Schema: {csv_headers}
Example CSV rows to match:
{csv_example_rows}

{f"Previous attempt failed. Feedback:\\n{feedback}" if feedback else ""}

**CRITICAL INSTRUCTIONS:**
1.  **IMPORTANT:** The data in the PDF snippet (e.g., dates from 2024) does NOT match the target CSV data (e.g., dates from 2025). Use the PDF snippet *only* to understand the text layout and column structure.
2.  **Primary Goal:** Your generated parser's output format must exactly match the `TARGET CSV FORMAT`.
3.  **Analyze the Target CSV:** Notice that the 'Debit Amt' and 'Credit Amt' columns in the example CSV are ALWAYS empty. The transaction amount is part of the 'Description' field. Your parser MUST replicate this.
4.  **Parsing Strategy:**
    -   Your regex should capture three groups per line: (1) the Date, (2) the entire middle section as the Description (including numbers), and (3) the final Balance.
    -   In your Python logic, you MUST hardcode 'Debit Amt' and 'Credit Amt' to be empty strings ("").
5.  **Code Requirements:**
    -   Output only valid Python code. No explanations.
    -   Function signature: `parse_pdf(pdf_path: str) -> list[dict]`
    -   The keys in your returned dictionaries must exactly match the CSV Schema.
    -   Skip any lines that do not start with a date.
"""
    return prompt

# --- Main Agent Logic ---
def main(target_bank: str):
    """Generates and tests a parser for a given bank with a self-correction loop."""
    try:
        api_key = os.environ["GEMINI_API_KEY"]
        genai.configure(api_key=api_key)
    except KeyError:
        print("ERROR: The 'GEMINI_API_KEY' environment variable is not set.")
        sys.exit(1)

    model = genai.GenerativeModel(MODEL_NAME, system_instruction=SYSTEM_PROMPT)

    pdf_path = f"data/{target_bank}/{target_bank}_sample.pdf"
    csv_path = f"data/{target_bank}/{target_bank}_sample.csv"
    parser_dir = "custom_parsers"
    parser_path = f"{parser_dir}/{target_bank}_parser.py"
    log_dir = "logs"
    log_path = f"{log_dir}/{target_bank}_parser_generation.log"

    os.makedirs(parser_dir, exist_ok=True)
    os.makedirs(log_dir, exist_ok=True)

    feedback = ""
    for attempt in range(MAX_ATTEMPTS):
        print(f"--- Attempt {attempt + 1}/{MAX_ATTEMPTS} ---")
        user_prompt = get_user_prompt(target_bank, csv_path, pdf_path, feedback)

        # 1. Generate parser code
        response = model.generate_content(user_prompt)
        generated_code = response.text.strip().replace("```python", "").replace("```", "")
        with open(parser_path, "w") as f:
            f.write(generated_code)
        print(f"Parser code generated and saved to {parser_path}")

        # 2. Log the attempt
        with open(log_path, "a") as log_file:
            log_file.write(f"\n--- Attempt {attempt + 1} ---\n")
            log_file.write(f"Generated Code:\n{generated_code}\n\n")
            if feedback:
                log_file.write(f"Feedback from Previous Attempt:\n{feedback}\n")

        # 3. Test the generated parser for STRUCTURE, not content, due to mismatched data.
        test_script = f"""
import pandas as pd
from custom_parsers.{target_bank}_parser import parse_pdf
import json

try:
    result_data = parse_pdf('{pdf_path}')
    expected_df = pd.read_csv('{csv_path}').fillna('')
    
    # Structural checks
    if not isinstance(result_data, list):
        print('ERROR: Parser did not return a list.')
        exit(1)
        
    if not all(isinstance(row, dict) for row in result_data):
        print('ERROR: Not all items in the returned list are dictionaries.')
        exit(1)

    if len(result_data) == 0:
        print('ERROR: Parser returned an empty list. No transactions were found.')
        exit(1)

    # Check if the keys of the first transaction match the expected CSV headers
    expected_keys = set(expected_df.columns)
    actual_keys = set(result_data[0].keys())

    if expected_keys != actual_keys:
        print(f'ERROR: Key mismatch. Expected {{expected_keys}}, but got {{actual_keys}}.')
        exit(1)

    print('SUCCESS: The generated parser produced the correct data structure.')
    exit(0)

except Exception as e:
    print(f'ERROR: Parser execution failed with exception: {{e}}')
    exit(1)
"""
        result = subprocess.run([sys.executable, "-c", test_script], capture_output=True, text=True)
        test_output = result.stdout + result.stderr

        # 4. Log test results and decide next step
        with open(log_path, "a") as log_file:
            log_file.write(f"Test Output:\n{test_output}\n{'='*80}\n")

        if result.returncode == 0:
            print(f"✅ Test PASSED! The generated parser produces the correct structure. See log: {log_path}")
            return
        else:
            print(f"❌ Test FAILED. The agent will attempt to self-correct. See log: {log_path}")
            feedback = test_output # Use the test output as feedback for the next attempt

    print(f"Agent failed to generate a working parser after {MAX_ATTEMPTS} attempts. Please review the log: {log_path}")

if __name__ == "__main__":
    parser = ArgumentParser(description="A self-correcting agent for parsing bank statement PDFs.")
    parser.add_argument("--target", type=str, required=True, help="The target bank name (e.g., 'icici').")
    args = parser.parse_args()
    main(args.target)

