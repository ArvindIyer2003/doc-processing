import pdfplumber
import re
import pandas as pd
import os
from flask import current_app as app

def CAMS_file(file_path, password=None):
    try:
        text = ""
        with pdfplumber.open(file_path, password=password) as pdf:
            for page in pdf.pages:
                text += page.extract_text() + "\n"
        start_pattern = re.compile(r'^Folio No:')
        end_pattern = re.compile(r'^Closing Unit Balance:')
        date_pattern = re.compile(r'\b\d{2}-[A-Za-z]{3}-\d{4}\b')  # Pattern for DD-MMM-YYYY format
        date_pattern_2 = re.compile(r'\b\d{2}-[A-Za-z]{3}-\d{4}\b\s+(.*)\s+\b\d{2}-[A-Za-z]{3}-\d{4}\b')
        folio_pattern = re.compile(r'Folio No:(.*?)(?:PAN:\s*([A-Za-z]{5}\d{4}[A-Za-z])|KYC:)')
        pan_pattern = re.compile(r'PAN:\s*([A-Za-z]{5}\d{4}[A-Za-z])')
        within_lines = False
        extracted_lines = []
        for line in text.split('\n'):
            if start_pattern.match(line):
                if extracted_lines and extracted_lines[-1] != "":
                    extracted_lines.append("")  # Add an empty line as delimiter
                within_lines = True
            if within_lines and not end_pattern.match(line):
                extracted_lines.append(line.strip())
            if end_pattern.match(line):
                within_lines = False
        sections = []
        current_section = []
        folio_numbers = []
        pan_numbers = []
        
        for line in extracted_lines:
            if line == "":
                if current_section:  # Only append if there are lines in the current section
                    sections.append(current_section)
                    current_section = []  # Reset current_section for the next section
            else:
                current_section.append(line)
        
        # Append the last section if it exists
        if current_section:
            sections.append(current_section)
        filtered_sections = []
        for section in sections:
            filtered_section = []
            folio_number = None
            pan_number = None
            for line in section:
                if folio_pattern.search(line):
                    folio_number = folio_pattern.search(line).group(1).strip()
                if pan_pattern.search(line):
                    pan_number = pan_pattern.search(line).group(1)
                if date_pattern.match(line):
                    if date_pattern_2.match(line):  # Check again to skip "date to date" expressions
                        continue
                    else:
                        filtered_section.append(line)
            if filtered_section:
                filtered_sections.append((folio_number, pan_number, filtered_section))
        df_rows = []

    # Extract data and format it for DataFrame
        for folio_number, pan_number, section in filtered_sections:
            for line in section:
                parts = line.split()
                date = parts[0]
                transaction_parts = []
                numeric_parts = []
                for part in parts[1:]:
                    if re.match(r'^\([-+]?[0-9]*\.?[0-9]+(?:,\d{3})*(?:\.\d+)?\)$', part):  # Check for numbers in parentheses
                        numeric_parts.append(part.strip('()'))  # Remove parentheses
                        if part.startswith('(') and part.endswith(')'):  # Check if it's a negative number in parentheses
                            numeric_parts[-1] = '-' + numeric_parts[-1]  # Add negative sign
                    elif re.match(r'^[-+]?[0-9]*\.?[0-9]+(?:,\d{3})*(?:\.\d+)?$', part):  # Check for regular numbers
                        numeric_parts.append(part)
                    else:
                        transaction_parts.append(part)  # Add non-numeric parts to transaction parts
                
                transaction = " ".join(transaction_parts)
                
                amount = numeric_parts[0] if len(numeric_parts) > 0 else ''
                units = numeric_parts[1] if len(numeric_parts) > 1 else ''
                nav = numeric_parts[2] if len(numeric_parts) > 2 else ''
                unit_balance = numeric_parts[3] if len(numeric_parts) > 3 else ''
                
                df_rows.append([folio_number, pan_number, date, transaction, amount, units, nav, unit_balance])
    
        # Create a DataFrame
        df = pd.DataFrame(df_rows, columns=['Folio Number', 'PAN Number', 'Date', 'Transaction', 'Amount', 'Units', 'NAV', 'Unit_Balance'])
        final_output_path = os.path.join(app.config['UPLOAD_FOLDER'], 'habi.csv')
        df.to_csv(final_output_path, index=False)
        return 'habi.csv'
    except Exception as e:
        app.logger.error(f"Error processing file: {e}")
        raise e
