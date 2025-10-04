# Bank Statement Parser Agent

## Overview

This Python agent automatically generates a custom parser for any bank statement PDF. It uses a self-correcting loop to generate Python code, test it against sample CSV data, and refine the parser up to 3 times. The generated parser function, `parse_pdf(pdf_path: str) -> pd.DataFrame`, returns a pandas DataFrame that exactly matches the expected CSV schema. This allows evaluators to run the agent on new bank statements without manual code changes.

## Agent Architecture

The agent operates in a self-correction loop. It begins by reading a sample PDF to understand its text structure and a target CSV file to understand the desired output format. It then constructs a detailed prompt, including this context, and instructs the Gemini model to generate a Python parser. Immediately after creation, the agent saves the parser and executes a test to validate that the parser's output structure (e.g., dictionary keys, return types) matches the target CSV schema. If the test fails, the agent captures the error output, adds it as feedback to the prompt, and asks the model to generate a corrected version. This cycle repeats up to three times until the test passes or the attempts are exhausted.

### Agent Diagram (Loop Description)

```
┌───────────┐
│  PLAN     │
│ Generate  │
│  LLM     │
└─────┬─────┘
      │
      ▼
┌───────────┐
│ GENERATE  │
│  Parser   │
└─────┬─────┘
      │
      ▼
┌───────────┐
│  TEST     │
│ Compare   │
│ DataFrame │
└─────┬─────┘
      │ Fail? ── Yes ──▶ Feedback → PLAN
      │
      ▼
     Done
```

---

## Setup Instructions

### 1. Clone Repository

```bash
git clone https://github.com/apurv-korefi/ai-agent-challenge.git
cd ai-agent-challenge
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
# If requirements.txt not provided:
pip install pandas pdfplumber google-generativeai
```

### 3. Set API Key

```bash
export GEMINI_API_KEY="your_gemini_api_key_here"
```

*(Windows CMD: `set GEMINI_API_KEY=your_key`)*

### 4. Run Agent

Generate a parser for a target bank (e.g., ICICI):

```bash
python agent.py --target icici
```

This will:

* Read `data/icici/icici_sample.pdf` and `data/icici/icici_sample.csv`
* Generate `custom_parsers/icici_parser.py`
* Run automated contract tests and self-correct up to 3 times if needed
* Log results to `logs/icici_parser_generation.log`

### 5. Test New Bank

To generate a parser for a new bank (e.g., SBI):

1. Place a sample PDF and CSV in `data/sbi/sbi_sample.pdf` and `data/sbi/sbi_sample.csv`.
2. Run:

```bash
python agent.py --target sbi
```

The agent will automatically generate `custom_parsers/sbi_parser.py` and test it.

---

### Notes

* The agent ensures the generated parser strictly adheres to the CSV schema.
* Logs in `logs/` capture every attempt, including the generated code and test results.
* The parser uses `pdfplumber` and regex for robust extraction of dates, amounts, and descriptions.

---

