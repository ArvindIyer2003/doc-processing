from flask import Flask, request, url_for, send_file, render_template, jsonify
from werkzeug.utils import secure_filename
import os
import threading
import nest_asyncio
from common import allowed_file, process_files, generate_combined_excel
from adeo import process_adeo_file
from obi import process_obi_file
from cams import CAMS_file
from kfintech import kfintech_file

nest_asyncio.apply()

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['PROCESSED_FOLDER'] = 'processed'
app.config['ALLOWED_EXTENSIONS'] = {'pdf'}
app.secret_key = 'supersecretkey'

for folder in [app.config['UPLOAD_FOLDER'], app.config['PROCESSED_FOLDER']]:
    if not os.path.exists(folder):
        os.makedirs(folder)

@app.route('/')
def upload_form():
    return render_template('upload.html')

@app.route('/upload', methods=['POST'])
def upload_folder():
    folder_type = request.form.get('folder_type')
    customer_name = request.form.get('customer_name', '')  # Get customer_name if provided (for OBI)
    password = request.form.get('password', '')  # Get the password from the form

    files = request.files.getlist('files[]')

    if not folder_type or not files:
        return jsonify({'message': 'Please select a folder type and upload files.'}), 400

    response = {'message': 'Files processed successfully', 'error_files': []}

    if folder_type == 'adeo':
        processed_files, error_files = process_files(files, process_adeo_file)
    elif folder_type == 'obi':
        processed_files, error_files = process_files(files, process_obi_file, customer_name=customer_name)
    elif folder_type == 'CAMS':
        processed_files, error_files = process_files(files, CAMS_file, password=password)
    elif folder_type == 'KFINTECH':
        processed_files, error_files = process_files(files, kfintech_file, password=password)
    else:
        return jsonify({'message': 'Invalid folder type selected.'}), 400

    if processed_files:
        combined_excel = generate_combined_excel(processed_files, f'{folder_type}_combined_output.xlsx')
        response['download_url'] = url_for('download_file', filename=combined_excel)

    response['error_files'] = error_files

    return jsonify(response)

@app.route('/download/<filename>')
def download_file(filename):
    return send_file(os.path.join(app.config['PROCESSED_FOLDER'], filename), as_attachment=True)

if __name__ == '__main__':
    app.run(debug=True)
