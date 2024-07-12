import os
import pandas as pd
from flask import current_app as app
from werkzeug.utils import secure_filename

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

def process_files(files, process_function, **kwargs):
    processed_files = []
    error_files = []
    for file in files:
        if allowed_file(file.filename):
            filename = secure_filename(file.filename)
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(file_path)
            try:
                output_filename = process_function(file_path, **kwargs)
                processed_files.append(output_filename)
            except Exception as e:
                app.logger.error(f"Error processing file {filename}: {e}")
                error_files.append(filename)
        else:
            error_files.append(file.filename)
    return processed_files, error_files

def generate_combined_excel(processed_files, output_filename):
    combined_df = pd.concat([pd.read_csv(os.path.join(app.config['UPLOAD_FOLDER'], f)) for f in processed_files])
    combined_output_path = os.path.join(app.config['PROCESSED_FOLDER'], output_filename)
    combined_df.to_excel(combined_output_path, index=False)
    return output_filename
