import os
import io
import re
import json
from datetime import datetime
from flask import Flask, request, jsonify, send_from_directory
from werkzeug.utils import secure_filename

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
WEB_DIR = os.path.join(BASE_DIR, 'Web')

app = Flask(__name__, static_folder=WEB_DIR, static_url_path='')
UPLOAD_FOLDER = '/tmp'

@app.route('/')
def index():
    index_file = os.path.join(WEB_DIR, 'index.html')
    if os.path.exists(index_file):
        return send_from_directory(WEB_DIR, 'index.html')
    return "ملف index.html غير موجود داخل مجلد Web", 404

@app.route('/generate', methods=['POST'])
def generate_certificates():
    try:
        import pandas as pd
        from PIL import Image, ImageDraw, ImageFont
        import arabic_reshaper
        from bidi.algorithm import get_display
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaIoBaseUpload

        if 'template' not in request.files or 'csv' not in request.files or 'font' not in request.files:
            return jsonify({'success': False, 'message': 'يرجى رفع جميع الملفات المطلوبة.'})

        drive_folder_id = request.form.get('drive_folder_id', '').strip()
        if not drive_folder_id:
            return jsonify({'success': False, 'message': 'يرجى إدخال معرف مجلد Google Drive.'})

        creds_json = os.environ.get('GOOGLE_SERVICE_ACCOUNT_KEY')
        if not creds_json:
            return jsonify({'success': False, 'message': 'لم يتم ضبط متغير البيئة GOOGLE_SERVICE_ACCOUNT_KEY.'})

        info = json.loads(creds_json)
        scopes = ['https://www.googleapis.com/auth/drive']
        creds = service_account.Credentials.from_service_account_info(info, scopes=scopes)
        drive_service = build('drive', 'v3', credentials=creds)

        template_file = request.files['template']
        csv_file = request.files['csv']
        font_file = request.files['font']
        custom_folder_name = request.form.get('folder_name', '').strip()

        template_path = os.path.join(UPLOAD_FOLDER, secure_filename(template_file.filename) or 'template.png')
        csv_path = os.path.join(UPLOAD_FOLDER, secure_filename(csv_file.filename) or 'names.csv')
        font_path = os.path.join(UPLOAD_FOLDER, secure_filename(font_file.filename) or 'font.ttf')

        template_file.save(template_path)
        csv_file.save(csv_path)
        font_file.save(font_path)

        run_timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        clean_custom = re.sub(r'[\\/*?:"<>|]', '', str(custom_folder_name)).strip() if custom_folder_name else ''
        sub_folder_name = f"{clean_custom}_{run_timestamp}" if clean_custom else f"Certificates_Run_{run_timestamp}"

        # إنشاء المجلد مع دعم المشاركة والـ Shared Drives
        folder_metadata = {
            'name': sub_folder_name,
            'mimeType': 'application/vnd.google-apps.folder',
            'parents': [drive_folder_id]
        }
        target_folder = drive_service.files().create(
            body=folder_metadata, 
            fields='id',
            supportsAllDrives=True
        ).execute()
        target_folder_id = target_folder.get('id')

        df = pd.read_csv(csv_path, encoding='utf-8-sig')
        names = df[df.columns[0]].dropna().astype(str).str.strip()

        count = 0
        for raw_name in names:
            if not raw_name or raw_name.lower() == 'nan':
                continue

            reshaped_text = arabic_reshaper.reshape(raw_name)
            processed_name = get_display(reshaped_text)

            with Image.open(template_path) as img:
                draw = ImageDraw.Draw(img)
                font = ImageFont.truetype(font_path, size=120)

                x_center = img.width / 2
                y_center = img.height / 2

                draw.text((x_center, y_center), processed_name, fill='#003366', font=font, anchor='mm')

                img_byte_arr = io.BytesIO()
                img.save(img_byte_arr, format='PNG')
                img_byte_arr.seek(0)

                safe_filename = re.sub(r'[\\/*?:"<>|]', '', str(raw_name)).strip() + ".png"
                
                media = MediaIoBaseUpload(img_byte_arr, mimetype='image/png', resumable=True)
                
                # الرفع مع خاصية supportsAllDrives لتجاوز حصة التخزين
                drive_service.files().create(
                    body={'name': safe_filename, 'parents': [target_folder_id]},
                    media_body=media,
                    fields='id',
                    supportsAllDrives=True
                ).execute()

                count += 1

        return jsonify({'success': True, 'message': f"تم توليد ورفع {count} شهادة بنجاح داخل المجلد:\n{sub_folder_name}"})

    except Exception as e:
        return jsonify({'success': False, 'message': f'حدث خطأ: {str(e)}'})

if __name__ == '__main__':
    app.run(debug=True)
