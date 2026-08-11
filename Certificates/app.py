import io
import os
import re
import json
from datetime import datetime
import arabic_reshaper
from bidi.algorithm import get_display
from flask import Flask, render_template, request, jsonify
from werkzeug.utils import secure_filename
import pandas as pd
from PIL import Image, ImageDraw, ImageFont

# مكتبات Google Drive API
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

app = Flask(__name__, template_folder='Web', static_folder='Web')

UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


def get_drive_service():
    """تهيئة والاتصال بـ Google Drive API باستخدام الـ Service Account Key"""
    # قراءة مفتاح JSON من متغير البيئة في Vercel أو المحلي
    creds_json = os.environ.get('GOOGLE_SERVICE_ACCOUNT_KEY')
    if not creds_json:
        raise Exception("لم يتم العثور على متغير البيئة GOOGLE_SERVICE_ACCOUNT_KEY")

    info = json.loads(creds_json)
    scopes = ['https://www.googleapis.com/auth/drive']
    creds = service_account.Credentials.from_service_account_info(info, scopes=scopes)
    return build('drive', 'v3', credentials=creds)


def create_drive_folder(service, folder_name, parent_folder_id):
    """إنشاء مجلد فرعي داخل مجلد Google Drive المضلل"""
    file_metadata = {
        'name': folder_name,
        'mimeType': 'application/vnd.google-apps.folder',
        'parents': [parent_folder_id]
    }
    folder = service.files().create(body=file_metadata, fields='id').execute()
    return folder.get('id')


def upload_file_to_drive(service, file_stream, filename, parent_folder_id):
    """رفع صورة الشهادة مباشرة إلى Google Drive دون حفظها على القرص الصلب"""
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
    return render_template('index.html')


@app.route('/generate', methods=['POST'])
def generate_certificates():
    try:
        if 'template' not in request.files or 'csv' not in request.files or 'font' not in request.files:
            return jsonify({'success': False, 'message': 'يرجى رفع جميع الملفات المطلوبة.'})

        # معرف المجلد الرئيسي من Google Drive (يُرسل من الشاشة)
        drive_folder_id = request.form.get('drive_folder_id', '').strip()
        if not drive_folder_id:
            return jsonify({'success': False, 'message': 'يرجى إدخال معرف مجلد Google Drive (Folder ID).'})

        template_file = request.files['template']
        csv_file = request.files['csv']
        font_file = request.files['font']

        custom_folder_name = request.form.get('folder_name', '').strip()

        if template_file.filename == '' or csv_file.filename == '' or font_file.filename == '':
            return jsonify({'success': False, 'message': 'يرجى اختيار ملفات صالحة.'})

        # حفظ الملفات المؤقتة للعمليات الحسابية
        template_filename = secure_filename(template_file.filename) or 'template.png'
        csv_filename = secure_filename(csv_file.filename) or 'names.csv'
        font_filename = secure_filename(font_file.filename) or 'font.ttf'

        template_path = os.path.join(UPLOAD_FOLDER, template_filename)
        csv_path = os.path.join(UPLOAD_FOLDER, csv_filename)
        font_path = os.path.join(UPLOAD_FOLDER, font_filename)

        template_file.save(template_path)
        csv_file.save(csv_path)
        font_file.save(font_path)

        # الاتصال بـ Google Drive
        drive_service = get_drive_service()

        # تسمية وإنشاء مجلد الدفعة الحالية داخل Drive
        run_timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        if custom_folder_name:
            sub_folder_name = f"{clean_filename(custom_folder_name)}_{run_timestamp}"
        else:
            sub_folder_name = f"Certificates_Run_{run_timestamp}"

        # إنشاء المجلد في Google Drive
        target_folder_id = create_drive_folder(drive_service, sub_folder_name, drive_folder_id)

        # قراءة الأسماء
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

                draw.text(
                    (x_center, y_center),
                    processed_name,
                    fill='#003366',
                    font=font,
                    anchor='mm'
                )

                # تحويل الصورة إلى ذاكرة (Bytes) بدلاً من حفظها محلياً
                img_byte_arr = io.BytesIO()
                img.save(img_byte_arr, format='PNG')
                img_byte_arr.seek(0)

                safe_name = clean_filename(raw_name)
                filename = f"{safe_name}.png"

                # الرفع المباشر لـ Google Drive
                upload_file_to_drive(drive_service, img_byte_arr, filename, target_folder_id)
                count += 1

        return jsonify({
            'success': True,
            'message': f"تم توليد ورفع {count} شهادة بنجاح داخل مجلد Google Drive المسمى:\n{sub_folder_name}"
        })

    except Exception as e:
        return jsonify({'success': False, 'message': f'حدث خطأ أثناء التوليد والرفع: {str(e)}'})


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)