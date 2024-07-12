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

def process_adeo_file(file_path):
    # Your existing process_file code renamed to process_adeo_file
    try:
        text = ""
        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages:
                text += page.extract_text() + "\n"

        regex_patterns = (
            (r'(CO\d*\d)', 'PO No'),
            (r'(Type : (\w*\w))', 'Type'),
            (r'(Supplier : (\d+))', 'Supplier'),
            (r'(Validation date : (\d{2}/\d{2}/\d{4}))', 'Validation date'),
            (r'(Purchase Incoterm Place : (\d{2}/\d{2}/\d{4}))', 'Purchase Incoterm Place'),
            (r'(Ordered for : (\d+))', 'Ordered for'),
            (r'(Amount : (?:(\d+)(\s+))?(\d+(\.\d+)?)\s+([a-zA-Z]+))', 'Amount'),
            (r'(Amount : (?:\d+\s+)?(\d+(\.\d+)?)\s+([a-zA-Z]+))', 'Currency'),
            (r'(Delivery to : (\d+))', 'Delivery to'),
            (r'(Blanket Order No : (\w+))', 'Blanket Order No')
        )
        compiled_patterns = [(re.compile(pattern), label) for pattern, label in regex_patterns]
        habi = ''
        matches = []
        for pattern, label in compiled_patterns:
            match = pattern.search(text)
            if match:
                if label == 'PO No':
                    matches.append(match.group(1))
                    habi = match.group(1)
                elif label == 'Currency':
                    matches.append(match.group(4))
                elif label == 'Amount':
                    if match.group(3):
                        thousands = match.group(2)
                        hundreds = match.group(4)
                        total = thousands + hundreds
                        matches.append(total)
                    else:
                        hundreds = match.group(4)
                        matches.append(hundreds)
                else:
                    matches.append(match.group(2))
        if not matches:
            raise ValueError("No matches found for required fields.")
        matches_tuple = tuple(matches)
        d = defaultdict(lambda: '')
        list = ['PO No', 'Type', 'Supplier', 'Validation date', 'Purchase Incoterm Place', 'Ordered for', 'Amount', 'Currency', 'Delivery to', 'Blanket Order No']
        for i in range(len(matches_tuple)):
            d[list[i]] = matches_tuple[i]
        output_csv_path = os.path.join(app.config['UPLOAD_FOLDER'], 'tables.csv')
        tabula.convert_into(file_path, output_csv_path, output_format="csv", pages='all', stream=True)
        df_tables = pd.read_csv(output_csv_path, encoding='latin-1')
        if len(df_tables) > 33:
            df_subset = df_tables.iloc[33:]
            df_subset.drop(df_subset.columns[df_subset.columns.str.contains('unnamed', case=False)], axis=1, inplace=True)
            two_row = df_subset.drop(columns=['Supplier Ref.', 'Description', 'GTIN', 'Dim. l*w*h cm', 'Weight Kg', 'Quantity','Amount'])
            two_row.rename(columns={
                'PCB': 'Quantity',
                'Price' : 'Total',
                'Nb Master': 'Price',
            }, inplace=True)
            df_sub = df_tables.iloc[:33]
            df_sub.drop(df_sub.columns[df_sub.columns.str.contains('unnamed', case=False)], axis=1, inplace=True)
            one_row = df_sub.drop(columns=['Supplier Ref.', 'Description', 'GTIN', 'Dim. l*w*h cm', 'Weight Kg', 'PCB', 'Nb Master'])
            one_row.rename(columns = {
                'Amount':'Total',
            },inplace = True)
            data = pd.concat([one_row, two_row], ignore_index=False, sort=False, axis=0)
        else:
            df_tables.drop(df_tables.columns[df_tables.columns.str.contains('unnamed', case=False)], axis=1, inplace=True)
            df_tables.rename(columns = {
                'Amount':'Total',
            },inplace = True)
            data = df_tables.drop(columns=['Supplier Ref.', 'Description', 'GTIN', 'Dim. l*w*h cm', 'Weight Kg', 'PCB', 'Nb Master'])
        df_tables = data
        df_tables.dropna(inplace=True)
        df_tables['Customer Ref.'] = df_tables['Customer Ref.'].astype(int)
        df_tables.reset_index(drop=True, inplace=True)
        details = [d.copy() for _ in range(len(df_tables))]
        df_2 = pd.DataFrame(details)
        df_final = pd.concat([df_2, df_tables], ignore_index=False, sort=False, axis=1)
        df_final.rename(columns={
            'ADEO Key': 'Item_No',
            'Ordered for': 'BU',
            'Delivery to': 'BU_Delivery',
            'Validation date': 'Buyer_PO_Date',
            'Purchase Incoterm Place': 'Ship_Date',
            'Supplier': 'Supplier_Code',
            'Price': 'Unit_Price',
            'Quantity': 'Qty'
        }, inplace=True)
        first_half = df_final[['PO No', 'Supplier_Code', 'BU', 'BU_Delivery', 'Buyer_PO_Date', 'Ship_Date', 'Item_No', 'Unit_Price', 'Qty','Total']]
        first_half['Qty'] = first_half['Qty'].astype(str)
        first_half['Qty'] = first_half['Qty'].str.replace(r'\s+(\d)', r'\1', regex=True)
        first_half['Unit_Price'] = first_half['Unit_Price'].astype(str)
        first_half['Unit_Price'] = first_half['Unit_Price'].str.replace(r'\s+(\d)', r'\1', regex=True)
        first_half['Total'] = first_half['Total'].astype(str)
        first_half['Total'] = first_half['Total'].str.replace(r'\s+(\d)', r'\1', regex=True)
        second_half = df_final[['Type', 'Amount', 'Currency', 'Blanket Order No', 'Customer Ref.']]
        format = pd.concat([first_half, second_half], ignore_index=False, sort=False, axis=1)
        final_output_path = os.path.join(app.config['UPLOAD_FOLDER'], f'{habi}.csv')
        format.to_csv(final_output_path, index=False)
        return f'{habi}.csv'
    except Exception as e:
        raise ValueError(f"Error processing ADEO file: {e}")