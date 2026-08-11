import io
import os
import re
import json
from datetime import datetime
from flask import Flask, request, jsonify, send_from_directory
from werkzeug.utils import secure_filename
import pandas as pd
from PIL import Image, ImageDraw, ImageFont

# مكتبات معالجة النص العربي
import arabic_reshaper
from bidi.algorithm import get_display

# مكتبات Google Drive API
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

# تحديد المسارات
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
WEB_DIR = os.path.join(BASE_DIR, 'Web')

app = Flask(__name__, static_folder=WEB_DIR, static_url_path='')

# مجلد المؤقت الخاص بـ Vercel
UPLOAD_FOLDER = '/tmp'

def get_drive_service():
    creds_json = os.environ.get('GOOGLE_SERVICE_ACCOUNT_KEY')
    if not creds_json:
        raise Exception("لم يتم العثور على متغير البيئة GOOGLE_SERVICE_ACCOUNT_KEY")

    info = json.loads(creds_json)
    scopes = ['https://www.googleapis.com/auth/drive']
    creds = service_account.Credentials.from_service_account_info(info, scopes=scopes)
    return build('drive', 'v3', credentials=creds)

def create_drive_folder(service, folder_name, parent_folder_id):
    file_metadata = {
        'name': folder_name,
        'mimeType': 'application/vnd.google-apps.folder',
        'parents': [parent_folder_id]
    }
    folder = service.files().create(body=file_metadata, fields='id').execute()
    return folder.get('id')

def upload_file_to_drive(service, file_stream, filename, parent_folder_id):
    file_metadata = {
        'name': filename,
        'parents': [parent_folder_id]
    }
    media = MediaIoBaseUpload(file_stream, mimetype='image/png', resumable=True)
    service.files().create(body=file_metadata, media_body=media, fields='id').execute()

def process_arabic_text(text):
    reshaped_text = arabic_reshaper.reshape(text)
    return get_display(reshaped_text)

def clean_filename(name):
    return re.sub(r'[\\/*?:"<>|]', '', str(name)).strip()

@app.route('/')
def index():
    # التأكد من وجود ملف index.html في مجلد Web
    if os.path.exists(os.path.join(WEB_DIR, 'index.html')):
        return send_from_directory(WEB_DIR, 'index.html')
    return "مرحباً! ملف index.html غير موجود داخل مجلد Web.", 404

@app.route('/generate', methods=['POST'])
def generate_certificates():
    try:
        if 'template' not in request.files or 'csv' not in request.files or 'font' not in request.files:
            return jsonify({'success': False, 'message': 'يرجى رفع جميع الملفات المطلوبة.'})

        drive_folder_id = request.form.get('drive_folder_id', '').strip()
        if not drive_folder_id:
            return jsonify({'success': False, 'message': 'يرجى إدخال معرف مجلد Google Drive.'})

        template_file = request.files['template']
        csv_file = request.files['csv']
        font_file = request.files['font']

        custom_folder_name = request.form.get('folder_name', '').strip()

        # حفظ الملفات مباشرة في /tmp
        template_path = os.path.join(UPLOAD_FOLDER, secure_filename(template_file.filename) or 'template.png')
        csv_path = os.path.join(UPLOAD_FOLDER, secure_filename(csv_file.filename) or 'names.csv')
        font_path = os.path.join(UPLOAD_FOLDER, secure_filename(font_file.filename) or 'font.ttf')

        template_file.save(template_path)
        csv_file.save(csv_path)
        font_file.save(font_path)

        drive_service = get_drive_service()

        run_timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        sub_folder_name = f"{clean_filename(custom_folder_name)}_{run_timestamp}" if custom_folder_name else f"Certificates_Run_{run_timestamp}"

        target_folder_id = create_drive_folder(drive_service, sub_folder_name, drive_folder_id)

        df = pd.read_csv(csv_path, encoding='utf-8-sig')
        names = df[df.columns[0]].dropna().astype(str).str.strip()

        count = 0
        for raw_name in names:
            if not raw_name or raw_name.lower() == 'nan':
                continue

            processed_name = process_arabic_text(raw_name)

            with Image.open(template_path) as img:
                draw = ImageDraw.Draw(img)
                font = ImageFont.truetype(font_path, size=120)

                x_center = img.width / 2
                y_center = img.height / 2

                draw.text((x_center, y_center), processed_name, fill='#003366', font=font, anchor='mm')

                img_byte_arr = io.BytesIO()
                img.save(img_byte_arr, format='PNG')
                img_byte_arr.seek(0)

                upload_file_to_drive(drive_service, img_byte_arr, f"{clean_filename(raw_name)}.png", target_folder_id)
                count += 1

        return jsonify({'success': True, 'message': f"تم توليد ورفع {count} شهادة بنجاح داخل المجلد:\n{sub_folder_name}"})

    except Exception as e:
        return jsonify({'success': False, 'message': f'حدث خطأ: {str(e)}'})

if __name__ == '__main__':
    app.run(debug=True)
