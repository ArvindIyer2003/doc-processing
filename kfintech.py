from flask import Flask, request, url_for, send_file, render_template, jsonify
from werkzeug.utils import secure_filename
import os
import threading
import nest_asyncio
import pandas as pd
import pdfplumber
import tabula
import re
from collections import defaultdict
import fitz
import logging
from flask import current_app as app

def decrypt_and_extract_text(input_pdf_path, password=None):
    try:
        # Open encrypted PDF file with PyMuPDF
        pdf_document = fitz.open(input_pdf_path)

        # Check if the PDF is encrypted
        if pdf_document.is_encrypted:
            # Authenticate and decrypt the PDF
            if password and pdf_document.authenticate(password):
                # Save the decrypted PDF
                decrypted_pdf_path = input_pdf_path.replace('.pdf', '_decrypted.pdf')
                pdf_document.save(decrypted_pdf_path)
                logging.info("File decrypted successfully.")

                # Extract text from decrypted PDF
                extracted_text = extract_text_from_pdf(decrypted_pdf_path)
                return extracted_text
            elif not password:
                logging.error("Password is required to decrypt the file.")
                raise ValueError("Password is required to decrypt the file.")
            else:
                logging.error("Incorrect password or unable to decrypt.")
                raise ValueError("Incorrect password or unable to decrypt.")
        else:
            logging.info("File is not encrypted.")

            # Extract text directly from the PDF
            extracted_text = extract_text_from_pdf(input_pdf_path)
            return extracted_text

    except Exception as e:
        logging.error(f"Error processing file: {e}")
        raise e
    finally:
        if 'pdf_document' in locals():
            pdf_document.close()
def extract_text_from_pdf(pdf_path):
    text = ""
    with fitz.open(pdf_path) as pdf_document:
        for page_num in range(len(pdf_document)):
            page = pdf_document.load_page(page_num)
            text += page.get_text()
    return text
def kfintech_file(file_path, password=None):
    try:
        extracted_text = decrypt_and_extract_text(file_path, password=password)
        if extracted_text:
            pattern = re.compile(
                r'PAN: (.*?)(Closing Unit Balance:)',  # Capture PAN number and content between "PAN:" and "Closing balance:"
                re.DOTALL  # Make the dot match newlines
            )

            matches = pattern.findall(extracted_text)
            extracted_content = []
            for match in matches:
                folio_number, content = match
                extracted_content.append(f"PAN: {folio_number.strip()}\nContent:\n{content.strip()}\n")

            extracted_text_without_function = "\n".join(extracted_content).strip()
            text_with_spaces = extracted_text_without_function.replace('\n', ' ')
            processed_text=text_with_spaces.replace(' PAN:', '\nPAN:')
            clean_text = re.sub(r'\s+NAV.*$', '', processed_text, flags=re.MULTILINE)
            date_pattern = r'(\d{2}-\w{3}-\d{4})'
            parts = re.split(date_pattern, clean_text)
        
            # Initialize variables
            cleaned_text = parts[0].strip()
            previous_date = None
            
            # Process the text
            for i in range(1, len(parts), 2):
                current_date = parts[i]
                details = parts[i + 1].strip()
                # Check if details start with 'PAN:' or the line starts with a date
                if (current_date and not cleaned_text.strip().endswith(current_date)):
                    cleaned_text += '\n' + current_date + ' ' + details
                else:
                    cleaned_text += ' ' + details
                
                previous_date = current_date
            
            # Print the cleaned text
            clean=cleaned_text.strip()
            pattern = r'\b\d{2}-[A-Za-z]{3}-\d{4}\s+(PAN: [A-Z]{5}[0-9]{4}[A-Z])'
            result = re.sub(pattern, r'\1', clean)
            final=result.strip()  # Strip to remove extra whitespace around the text
            start_pattern = re.compile(r'^PAN:')
            end_pattern = re.compile(r'^Closing Unit Balance:')
            date_pattern = re.compile(r'\b\d{2}-[A-Za-z]{3}-\d{4}\b')  # Pattern for DD-MMM-YYYY format
            date_range_pattern = re.compile(r'\b\d{2}-[A-Za-z]{3}-\d{4}\b\s+(.*)\s+\b\d{2}-[A-Za-z]{3}-\d{4}\b')
            folio_pattern = re.compile(r'Folio No :(.*)KYC :')
            pan_pattern = re.compile(r'PAN:\s*([A-Za-z]{5}\d{4}[A-Za-z])')
            
            # Flag to track whether we are within the desired lines
            within_lines = False
            extracted_lines = []
            for line in final.split('\n'):
                if start_pattern.match(line):
                    if extracted_lines and extracted_lines[-1] != "":
                        extracted_lines.append("")  # Add an empty line as delimiter
                    within_lines = True
                if within_lines and not date_range_pattern.search(line):  # Exclude lines matching date range pattern
                    extracted_lines.append(line.strip())
                if end_pattern.match(line):
                    within_lines = False
            
            # Create a new list of sections based on the delimiter
            sections = []
            current_section = []
            
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
                skip_section = False
                for line in section:
                    if date_range_pattern.search(line):
                        skip_section = True
                        break
                    if folio_pattern.search(line):
                        folio_number = folio_pattern.search(line).group(1)
                    if pan_pattern.search(line):
                        pan_number = pan_pattern.search(line).group(1)
                    if date_pattern.match(line):
                        if date_range_pattern.match(line):  # Check again to skip "date to date" expressions
                            continue
                        else:
                            filtered_section.append(line)
                if filtered_section and not skip_section:
                    filtered_sections.append((folio_number, pan_number, filtered_section))
            date_pattern_n = re.compile(r"^\d{2}-[A-Za-z]{3}-\d{4}$")
            for i in range(len(filtered_sections)):
                filtered_sections[i] = (
                    filtered_sections[i][0],
                    filtered_sections[i][1],
                    [entry for entry in filtered_sections[i][2] if not date_pattern_n.match(entry)]
                )
            df_rows = []
            for folio_number, pan_number, section in filtered_sections:
                i = 0
                while i < len(section):
                    line = section[i]
                    parts = line.split()
                    date = parts[0]
                    transaction_parts = []
                    numeric_parts = []
                    
                    for part in parts[1:]:
                        if re.match(r'^\([-+]?(?:\d{1,3}(?:,\d{2,3})*|\d+)(?:\.\d+)?\)$|^\([-+]?(?:\d{1,3}(?:,\d{2,3})*|\d+)\.\d+\)$', part):  # Check for numbers in parentheses
                            numeric_parts.append(part.strip('()'))  # Remove parentheses
                            if part.startswith('(') and part.endswith(')'):  # Check if it's a negative number in parentheses
                                numeric_parts[-1] = '-' + numeric_parts[-1]  # Add negative sign
                        elif re.match(r'^[-+]?(?:\d{1,3}(?:,\d{2,3})*|\d+)(?:\.\d+)?$', part):  # Check for regular numbers
                            numeric_parts.append(part)
                        else:
                            transaction_parts.append(part)  # Add non-numeric parts to transaction parts
                    
                    transaction = " ".join(transaction_parts)
                    
                    # Check if transaction contains only "To"
                    if transaction.strip().lower() == "to":
                        i += 2  # Skip this line and the next line
                        continue
                    amount = numeric_parts[0] if len(numeric_parts) > 0 else ''
                    units = numeric_parts[1] if len(numeric_parts) > 1 else ''
                    nav = numeric_parts[2] if len(numeric_parts) > 2 else ''
                    unit_balance = numeric_parts[3] if len(numeric_parts) > 3 else ''
                    
                    # Append row to df_rows
                    df_rows.append([folio_number, pan_number, date, transaction, amount, units, nav, unit_balance])
                    
                    i += 1
    
            # Create DataFrame df
            df = pd.DataFrame(df_rows, columns=['Folio Number', 'PAN Number', 'Date', 'Transaction', 'Amount', 'Units', 'NAV', 'Unit_Balance'])
            final_output_path = os.path.join(app.config['UPLOAD_FOLDER'], 'habi.csv')
            df.to_csv(final_output_path, index=False)
            return 'habi.csv'
    except Exception as e:
        app.logger.error(f"Error processing file: {e}")
        raise e

