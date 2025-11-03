import os
import re
import tempfile
import zipfile
from collections import defaultdict
from flask import Flask, request, render_template, send_file, jsonify, session, redirect, url_for
from werkzeug.utils import secure_filename
import pandas as pd
from PyPDF2 import PdfReader, PdfWriter

app = Flask(__name__, template_folder="templates", static_folder="static")
app.config['MAX_CONTENT_LENGTH'] = 200 * 1024 * 1024  # 200 MB
app.config['SECRET_KEY'] = 'change_this_secret_for_prod'

DEMO_USER = "vishal"
DEMO_PASS = "1234"

def clean_filename(name: str) -> str:
    return re.sub(r'[\\/*?:"<>|]', '_', name.strip())

@app.route('/')
def home():
    if 'user' not in session:
        return redirect(url_for('login'))
    return render_template('index.html', user=session.get('user','vishal'))

@app.route('/login', methods=['GET'])
def login():
    if 'user' in session:
        return redirect(url_for('home'))
    return render_template('login.html')

@app.route('/login', methods=['POST'])
def do_login():
    data = request.get_json() or {}
    username = data.get('username','').strip()
    password = data.get('password','')
    if username == DEMO_USER and password == DEMO_PASS:
        session['user'] = username
        return jsonify({'success': True})
    return jsonify({'success': False, 'error': 'Invalid credentials'}), 401

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('login'))

@app.route('/convert', methods=['POST'])
def convert():
    if 'user' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    if 'pdf' not in request.files or 'excel' not in request.files:
        return jsonify({'error': 'Both PDF and Excel files are required.'}), 400
    pdf_file = request.files['pdf']
    excel_file = request.files['excel']
    pdf_filename = secure_filename(pdf_file.filename)
    excel_filename = secure_filename(excel_file.filename)
    if not pdf_filename.lower().endswith('.pdf'):
        return jsonify({'error': 'Uploaded file is not a PDF.'}), 400
    if not (excel_filename.lower().endswith('.xlsx') or excel_filename.lower().endswith('.xls')):
        return jsonify({'error': 'Uploaded file is not an Excel (.xlsx/.xls).'}), 400
    with tempfile.TemporaryDirectory() as tmpdir:
        pdf_path = os.path.join(tmpdir, pdf_filename)
        excel_path = os.path.join(tmpdir, excel_filename)
        pdf_file.save(pdf_path)
        excel_file.save(excel_path)
        try:
            df = pd.read_excel(excel_path)
        except Exception as e:
            return jsonify({'error': f'Could not read Excel file: {str(e)}'}), 400
        if df.shape[1] < 1:
            return jsonify({'error': 'Excel file must have at least one column with names.'}), 400
        names = df.iloc[:, 0].fillna('').astype(str).tolist()
        try:
            reader = PdfReader(pdf_path)
        except Exception as e:
            return jsonify({'error': f'Could not read PDF file: {str(e)}'}), 400
        num_pages = len(reader.pages)
        if len(names) != num_pages:
            return jsonify({'error': f'Number of names ({len(names)}) does not match number of pages in PDF ({num_pages}).'}), 400
        output_folder = os.path.join(tmpdir, 'output_pdfs')
        os.makedirs(output_folder, exist_ok=True)
        name_counts = defaultdict(int)
        for i, name in enumerate(names):
            writer = PdfWriter()
            writer.add_page(reader.pages[i])
            if not name.strip():
                name = f'Page_{i+1:03}'
            clean_name = clean_filename(name)
            name_counts[clean_name] += 1
            if name_counts[clean_name] > 1:
                clean_name = f"{clean_name}_{name_counts[clean_name]}"
            filename = f"{clean_name}.pdf"
            output_path = os.path.join(output_folder, filename)
            with open(output_path, 'wb') as f:
                writer.write(f)
        zip_path = os.path.join(tmpdir, 'zistal_output.zip')
        with zipfile.ZipFile(zip_path, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
            for root, _, files in os.walk(output_folder):
                for fname in files:
                    full = os.path.join(root, fname)
                    zf.write(full, arcname=fname)
        return send_file(zip_path, as_attachment=True, download_name='zistal_output.zip')
        
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
