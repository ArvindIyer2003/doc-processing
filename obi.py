import os
import pdfplumber
import pandas as pd
import re
from flask import current_app as app

def process_obi_file(file_path, customer_name=''):
    try:
        # Extract text from the PDF using pdfplumber
        with pdfplumber.open(file_path) as pdf:
            all_text = ""
            for page in pdf.pages:
                text = page.extract_text()
                all_text += text + "\n"  # add a newline to separate pages (adjust as needed)
        lst = all_text.split('\n')
        hbi=''
        pattern_5=re.compile(r'(Passwort:\w+)')
        for line in all_text.split('\n'):
            if pattern_5.match(line):
                hbi=line
        if lst[0] != 'O R D E R' and hbi:
            # Processing for OBI-Lux Tools
            # Extracting order number
            matches = lst[2].split()[-1]
            # Extracting vendor
            vendor = lst[3]
            s = vendor.split()
            if 'Order' in s:
                vendor = lst[2]
                eg = vendor.split(' Order')
                vendor = eg[0]
            # Compiling data into a dictionary
            from collections import defaultdict
            data_dict = defaultdict(str)
            data_dict['Po No'] = matches
            data_dict['Vendor_Code'] = vendor

            # Extracting table data with regex
            original_pattern = re.compile(
                r'\d{1}?\s?'       # match a sequence of digits followed by spaces
                r'\d+\s+'           # match another sequence of digits followed by spaces
                r'\w+(\s+\w+)*\s*'  # match words with optional additional words separated by spaces, followed by optional spaces
            )

            combined_pattern = re.compile(
                fr'{original_pattern.pattern}'  # include the original pattern as mandatory
                r'(?:(?:\d{4}-\d{2}-\d{2}|\b\w+\b|\s)+)?'  # optionally match dates, words, or spaces
                r'\b\d{1,4}\.\d{2}\b'  # match a decimal number with 1-4 digits before the decimal point and 2 digits after
            )

            res = []
            for line in all_text.split('\n'):
                if combined_pattern.findall(line):
                    res.append(line)
            df = []
            for i in range(len(res)):
                val = res[i].split()
                tmp = []
                tmp.append(val[1])
                for i in range(len(val)-6, len(val)):
                    tmp.append(val[i])
                df.append(tmp)

            # Creating DataFrame
            data = pd.DataFrame(df, columns=['Item_No', 'Ship Date', 'Quantity', 'Unit Price', 'Package', 'Price unit Qty', 'Total'])
            data = data.drop(columns=['Package'])
            data['Unit Price'] = data['Unit Price'].astype(str).str.replace(',', '.')
            data['Total'] = data['Total'].astype(str).str.replace('.', '')
            data['Total'] = data['Total'].astype(str).str.replace(',', '.')
            if customer_name:
                data['Customer'] = 'CUST0028'
            # Adding additional details
            details = [data_dict.copy() for _ in range(len(data))]
            details_df = pd.DataFrame(details)
            df_final = pd.concat([data, details_df], ignore_index=False, sort=False, axis=1)
            # Saving final CSV
            final_output_path = os.path.join(app.config['UPLOAD_FOLDER'], f'{matches}.csv')
            df_final.to_csv(final_output_path, index=False)
            return f'{matches}.csv'
        elif lst[0] == 'O R D E R':
            regex_patterns = (
            (r'(Supplier-No.: (\d+))', 'Supplier-No'),
            (r'(Order-No.: (\d+))', 'Order-No'),
            (r'(Dated: (\d{2}.\d{2}.\d{2}))', 'Date')
            )
            compiled_patterns = [(re.compile(pattern), label) for pattern, label in regex_patterns]
            mat = []
            for pattern, label in compiled_patterns:
                matc= pattern.search(all_text)
                if matc:
                    mat.append(matc.group(2))
            matches_tuple = tuple(mat)
            if not matches_tuple:
                raise ValueError("No matches found for required fields.")
            from collections import defaultdict
            d = defaultdict(lambda: '')
            list = ['Supplier-No','Order-No','Date']
            for i in range(len(matches_tuple)):
                d[list[i]] = matches_tuple[i]
            pattern_1=re.compile(r'(\d{3,}\s(.*)[A-Z]{3}$)')
            pattern_3=re.compile(r'^EUROMATE\b.*')
            matches=[]
            ans=''
            for line in all_text.split('\n'):
                if pattern_1.match(line):
                    matches.append(line)
                if pattern_3.match(line):
                    ans=line
            li=[]
            for i in range(len(matches)):
                tex=matches[i].split()
                li.append(tex[-2])
            pattern_2 = r'\d+(\.\d+)?(?=/)'
            for i in range(len(li)):
                te=li[i]
                match = re.search(pattern_2, te)
                if match:
                    number = match.group()
                    li[i]=number
            df=[]
            for i in range(len(matches)):
                val=matches[i].split()
                tmp=[]
                tmp.append(val[0])
                tmp.append(val[-4])
                tmp.append(li[i])
                df.append(tmp)
            data = pd.DataFrame(df,columns=['Item_No','Quantity','Price'])
            if customer_name:
                if ans:
                    data['Customer'] = 'CUST0027'
                else:
                    data['Customer']='CUST0028'
            details = [d.copy() for _ in range(len(data))]
            a = pd.DataFrame(details)
            df_merged = pd.concat([data,a], ignore_index=False, sort=False,axis=1)
            df_merged['Date'] = df_merged['Date'].astype(str).str.replace('.', '-')
            import numpy as np
            df_merged['Ship-No']=np.nan
            final_output_path = os.path.join(app.config['UPLOAD_FOLDER'], f'{matches_tuple[0]}_euromate.csv')
            df_merged.to_csv(final_output_path, index=False)
            return f'{matches_tuple[0]}_euromate.csv'
        else:
            raise ValueError(f"Unsupported customer name: {customer_name}")
    except Exception as e:
        app.logger.error(f"Error processing OBI file: {e}")
        raise e



