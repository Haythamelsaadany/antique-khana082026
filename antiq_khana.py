import streamlit as st
import os
import sqlite3
import pandas as pd
import datetime
import bcrypt
import qrcode
import shutil
import zipfile
from io import BytesIO
from PIL import Image
import random
import math
import urllib.parse
import re
from typing import List, Optional
import requests
import tempfile
import platform
import io
import json
import hashlib
import uuid
import sys
import base64
import subprocess  # <--- تمت إضافتها لضمان عمل البحث عن Tesseract

# ======================== نظام الترخيص ========================
OWNER_PHONE = "01223999366"

def get_machine_fingerprint():
    try:
        mac_int = uuid.getnode()
        mac_hex = ':'.join(('%012x' % mac_int)[i:i+2] for i in range(0, 12, 2))
        return mac_hex
    except:
        fallback = platform.node() + os.path.dirname(sys.executable)
        return hashlib.md5(fallback.encode()).hexdigest()

def get_secret_key():
    hash_obj = hashlib.sha256(OWNER_PHONE.encode())
    return base64.urlsafe_b64encode(hash_obj.digest()[:32])

SECRET_KEY = get_secret_key()

# استخدام Fernet فقط إذا كانت cryptography مثبتة، وإلا استخدم بديلاً بسيطاً
try:
    from cryptography.fernet import Fernet
    cipher = Fernet(SECRET_KEY)
    def encrypt_data(data):
        return cipher.encrypt(json.dumps(data).encode())
    def decrypt_data(encrypted):
        return json.loads(cipher.decrypt(encrypted).decode())
    CRYPTO_AVAILABLE = True
except ImportError:
    CRYPTO_AVAILABLE = False
    # بديل بسيط باستخدام base64 (غير آمن لكنه يعمل)
    def encrypt_data(data):
        return base64.b64encode(json.dumps(data).encode())
    def decrypt_data(encrypted):
        return json.loads(base64.b64decode(encrypted).decode())

def generate_license_file(phone_number, output_file="license.key"):
    machine_id = get_machine_fingerprint()
    data = {"phone": phone_number, "machine": machine_id, "expiry": "2099-12-31"}
    encrypted = encrypt_data(data)
    with open(output_file, "wb") as f:
        f.write(encrypted)
    return True

def verify_license():
    license_file = "license.key"
    if not os.path.exists(license_file):
        return False, "License file not found. Please contact the developer."
    try:
        with open(license_file, "rb") as f:
            encrypted = f.read()
        data = decrypt_data(encrypted)
        if data.get("phone") != OWNER_PHONE:
            return False, "Invalid license phone number."
        current_machine = get_machine_fingerprint()
        if data.get("machine") != current_machine:
            return False, "License not for this machine."
        if data.get("expiry") < datetime.datetime.now().strftime("%Y-%m-%d"):
            return False, "License expired."
        return True, "Valid"
    except Exception as e:
        return False, f"License error: {str(e)}"

# ======================== الثوابت ========================
DB_NAME = 'gallery_pro.db'
IMG_FOLDER = "images"
THUMB_FOLDER = "thumbnails"
BACKUP_FOLDER = "backups"
ITEMS_PER_PAGE = 24

os.makedirs(IMG_FOLDER, exist_ok=True)
os.makedirs(THUMB_FOLDER, exist_ok=True)
os.makedirs(BACKUP_FOLDER, exist_ok=True)

# ======================== إعداد الصفحة ========================
st.set_page_config(page_title="Antiq Khana - نظام إدارة التحف", page_icon="🏛️", layout="wide")
if "item" in st.query_params:
    st.session_state.pending_item = st.query_params["item"]

# ======================== التحقق من الترخيص (مع إمكانية التجاوز في السحابة) ========================
if "license_checked" not in st.session_state:
    # في بيئة Streamlit Cloud، يمكن تخطي الترخيص لتسهيل النشر
    if os.environ.get("STREAMLIT_SERVER") or os.environ.get("STREAMLIT_CLOUD"):
        st.session_state.license_checked = True
    else:
        valid, msg = verify_license()
        if not valid:
            st.error(f"⚠️ {msg}")
            st.markdown(f"<div style='text-align:center; padding:2rem;'><h3>هذا البرنامج مرخص فقط لمالكه الحصري</h3><p>للحصول على ترخيص صحيح، يرجى الاتصال برقم الدعم: <strong>{OWNER_PHONE}</strong></p></div>", unsafe_allow_html=True)
            st.stop()
        st.session_state.license_checked = True

# ======================== CSS ========================
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Tajawal:wght@300;400;500;700&display=swap');
html, body, [class*="css"] { font-family: 'Tajawal', sans-serif; }
.main { background: linear-gradient(135deg, #f5f7fa 0%, #e9ecef 100%); }
.stButton > button {
    background: linear-gradient(90deg, #8e44ad, #9b59b6);
    color: white; border: none; border-radius: 8px;
    padding: 0.5rem 1rem; font-weight: 500;
    transition: all 0.3s ease;
}
.stButton > button:hover {
    transform: translateY(-2px);
    box-shadow: 0 5px 15px rgba(142,68,173,0.3);
}
.brand-title {
    text-align: center; padding: 1rem;
    background: linear-gradient(135deg, #8e44ad, #c0392b);
    border-radius: 12px; color: white; margin-bottom: 1.5rem;
    font-size: 1.8rem; font-weight: bold;
}
.footer {
    text-align: center;
    margin-top: 3rem;
    padding: 1rem;
    font-size: 0.8rem;
    color: #6c757d;
    border-top: 1px solid #dee2e6;
}
.result-card {
    background-color: #f8f9fa;
    border-radius: 12px;
    padding: 12px;
    margin-bottom: 16px;
    box-shadow: 0 2px 6px rgba(0,0,0,0.1);
    transition: all 0.2s;
}
.result-card:hover {
    transform: translateY(-3px);
    box-shadow: 0 6px 12px rgba(0,0,0,0.15);
}
</style>
""", unsafe_allow_html=True)

# ======================== المكتبات الاختيارية ========================
try:
    import cv2
    import numpy as np
    OPENCV_AVAILABLE = True
except ImportError:
    OPENCV_AVAILABLE = False

try:
    import imagehash
    from PIL import Image as PIL_Image
    IMAGEHASH_AVAILABLE = True
except ImportError:
    IMAGEHASH_AVAILABLE = False

try:
    import pytesseract
    from PIL import Image as PIL_Image
    TESSERACT_AVAILABLE = True
except ImportError:
    TESSERACT_AVAILABLE = False

try:
    import gspread
    from oauth2client.service_account import ServiceAccountCredentials
    GSHEET_AVAILABLE = True
except ImportError:
    GSHEET_AVAILABLE = False

# ======================== دوال معالجة الصورة ========================
def process_uploaded_image(uploaded_file):
    try:
        img = PIL_Image.open(uploaded_file)
        if img.mode in ('RGBA', 'P'):
            img = img.convert('RGB')
        output = io.BytesIO()
        img.save(output, format='JPEG', quality=85)
        output.seek(0)
        return output
    except Exception as e:
        st.error(f"خطأ في معالجة الصورة: {e}")
        return None

def load_image_as_cv2(img_path_or_url):
    if not OPENCV_AVAILABLE:
        return None
    try:
        if img_path_or_url.startswith('http'):
            resp = requests.get(img_path_or_url, timeout=10)
            img_array = np.frombuffer(resp.content, np.uint8)
            img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
        else:
            img = cv2.imread(img_path_or_url)
        if img is None:
            return None
        return img
    except Exception:
        return None

def compute_orb_features(img_cv2):
    if not OPENCV_AVAILABLE or img_cv2 is None:
        return None, None
    orb = cv2.ORB_create(nfeatures=2000)
    kp, des = orb.detectAndCompute(img_cv2, None)
    return kp, des

def match_features(des1, des2, ratio_thresh=0.75):
    if not OPENCV_AVAILABLE or des1 is None or des2 is None or len(des1) < 2 or len(des2) < 2:
        return 0, []
    bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=False)
    matches = bf.knnMatch(des1, des2, k=2)
    good = []
    for m, n in matches:
        if m.distance < ratio_thresh * n.distance:
            good.append(m)
    return len(good), good

def compute_phash_similarity(img_path_or_url, query_img):
    if not IMAGEHASH_AVAILABLE:
        return 100
    try:
        if img_path_or_url.startswith('http'):
            resp = requests.get(img_path_or_url, timeout=10)
            img1 = PIL_Image.open(io.BytesIO(resp.content))
        else:
            img1 = PIL_Image.open(img_path_or_url)
        img2 = PIL_Image.open(query_img)
        if img1.mode != 'RGB': img1 = img1.convert('RGB')
        if img2.mode != 'RGB': img2 = img2.convert('RGB')
        img1.thumbnail((256,256))
        img2.thumbnail((256,256))
        hash1 = imagehash.phash(img1)
        hash2 = imagehash.phash(img2)
        return hash1 - hash2
    except:
        return 100

# ======================== دوال قاعدة البيانات ========================
def upgrade_database():
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(antiques)")
        existing = [col[1] for col in cursor.fetchall()]
        for col in ['description','thumb_path','date_added','code','category','note','sold','sold_date','invoice_id', 'serial_number']:
            if col not in existing:
                conn.execute(f"ALTER TABLE antiques ADD COLUMN {col} TEXT")
        new_columns = {
            'dimensions': 'TEXT', 'material': 'TEXT', 'material_main': 'TEXT', 'children': 'TEXT',
            'place_of_origin': 'TEXT', 'historical_period': 'TEXT', 'condition': 'TEXT',
            'price_source': 'TEXT', 'room': 'TEXT', 'image_urls': 'TEXT',
            'art_classification': 'TEXT', 'subject': 'TEXT', 'art_symbols': 'TEXT', 'ruler': 'TEXT'
        }
        for col, col_type in new_columns.items():
            if col not in existing:
                conn.execute(f"ALTER TABLE antiques ADD COLUMN {col} {col_type}")
        if 'country' not in existing:
            conn.execute("ALTER TABLE antiques ADD COLUMN country TEXT")
        conn.execute("UPDATE antiques SET price=0.0 WHERE price IS NULL")
        conn.execute("UPDATE antiques SET sold='0' WHERE sold IS NULL")
        conn.execute('''CREATE TABLE IF NOT EXISTS item_images (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_id TEXT NOT NULL,
            image_path TEXT NOT NULL,
            thumb_path TEXT NOT NULL,
            sort_order INTEGER DEFAULT 0,
            FOREIGN KEY (item_id) REFERENCES antiques(id) ON DELETE CASCADE
        )''')
        conn.execute('''CREATE TABLE IF NOT EXISTS sales (
            invoice_id TEXT PRIMARY KEY, customer_name TEXT, customer_phone TEXT,
            customer_address TEXT, item_id TEXT, item_name TEXT, price REAL,
            discount REAL, total REAL, sale_date TEXT, status TEXT
        )''')
        conn.execute('''CREATE TABLE IF NOT EXISTS customers (
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, phone TEXT,
            address TEXT, first_purchase TEXT
        )''')
        cursor.execute("PRAGMA table_info(sales)")
        sales_cols = [c[1] for c in cursor.fetchall()]
        if 'discount' not in sales_cols:
            conn.execute("ALTER TABLE sales ADD COLUMN discount REAL DEFAULT 0")
        if 'total' not in sales_cols:
            conn.execute("ALTER TABLE sales ADD COLUMN total REAL DEFAULT 0")

def init_db():
    with sqlite3.connect(DB_NAME) as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS antiques (
            id TEXT PRIMARY KEY, name TEXT NOT NULL, serial_number TEXT, code TEXT,
            category TEXT, note TEXT, description TEXT, price REAL, country TEXT,
            date_added TEXT, sold TEXT DEFAULT '0', sold_date TEXT, invoice_id TEXT,
            dimensions TEXT, material TEXT, material_main TEXT, children TEXT,
            place_of_origin TEXT, historical_period TEXT, condition TEXT,
            price_source TEXT, room TEXT, image_urls TEXT,
            art_classification TEXT, subject TEXT, art_symbols TEXT, ruler TEXT
        )''')
        conn.execute('''CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL, role TEXT NOT NULL
        )''')
        conn.execute('''CREATE TABLE IF NOT EXISTS logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT, action TEXT,
            item_id TEXT, timestamp TEXT
        )''')
        conn.execute('''CREATE TABLE IF NOT EXISTS item_images (
            id INTEGER PRIMARY KEY AUTOINCREMENT, item_id TEXT NOT NULL,
            image_path TEXT NOT NULL, thumb_path TEXT NOT NULL,
            sort_order INTEGER DEFAULT 0,
            FOREIGN KEY (item_id) REFERENCES antiques(id) ON DELETE CASCADE
        )''')
        conn.execute('''CREATE TABLE IF NOT EXISTS sales (
            invoice_id TEXT PRIMARY KEY, customer_name TEXT, customer_phone TEXT,
            customer_address TEXT, item_id TEXT, item_name TEXT, price REAL,
            discount REAL, total REAL, sale_date TEXT, status TEXT
        )''')
        conn.execute('''CREATE TABLE IF NOT EXISTS customers (
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, phone TEXT,
            address TEXT, first_purchase TEXT
        )''')
        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE username='admin'")
        if not cur.fetchone():
            hashed = bcrypt.hashpw("admin123".encode(), bcrypt.gensalt())
            conn.execute("INSERT INTO users (username, password, role) VALUES (?,?,?)",
                         ("admin", hashed, "admin"))
        cur.execute("SELECT COUNT(*) FROM antiques")
        if cur.fetchone()[0] == 0:
            now = datetime.datetime.now().isoformat()
            samples = [
                ("ANT001", "تمثال فرعوني", "SN001", "ANT001", "تماثيل", "ملاحظة", "تمثال للإله حورس - حالة ممتازة", 450.0, "مصر", now, "0", None, None, "30x20x10cm", "برونز", "برونز", "لا", "مصر", "الأسرة 19", "ممتاز", "خبير", "غرفة 1", "", "فن مصري قديم", "عبادة حورس", "صقر، عنخ", "حورس"),
                ("ANT002", "مصحف عثماني", "SN002", "ANT002", "مخطوطات", "ملاحظة", "مصحف نادر مكتوب بخط اليد", 1200.0, "تركيا", now, "0", None, None, "25x18cm", "جلد وذهب", "جلد", "لا", "تركيا", "القرن 18", "جيد", "خبير", "غرفة 2", "", "فن إسلامي", "مخطوطة دينية", "زخارف نباتية، تذهيب", "السلطان أحمد"),
                ("ANT003", "عملة ذهبية يونانية", "SN003", "ANT003", "عملات", "ملاحظة", "عملة الإسكندر الأكبر", 850.0, "اليونان", now, "0", None, None, "3cm", "ذهب", "ذهب", "لا", "اليونان", "القرن 4 ق.م", "ممتاز", "خبير", "غرفة 3", "", "فن يوناني قديم", "صورة الإسكندر", "قرون الأمان", "الإسكندر الأكبر"),
                ("ANT004", "خنجر عربي قديم", "SN004", "ANT004", "أسلحة", "ملاحظة", "خنجر جنبي مرصع", 320.0, "اليمن", now, "0", None, None, "40cm", "فضة ونحاس", "فضة", "لا", "اليمن", "القرن 17", "جيد", "خبير", "غرفة 1", "", "فن إسلامي", "سلاح تقليدي", "نقوش عربية", "لا يوجد"),
                ("ANT005", "إناء صيني", "SN005", "ANT005", "خزف", "ملاحظة", "إناء مزخرف بالتنين", 680.0, "الصين", now, "0", None, None, "25x15cm", "بورسلين", "بورسلين", "لا", "الصين", "أسرة مينغ", "ممتاز", "خبير", "غرفة 4", "", "فن صيني", "تنين", "تنين، سحب", "الإمبراطور يونغلي")
            ]
            # 27 عموداً في INSERT تطابق 27 قيمة في كل عينة
            conn.executemany("""INSERT INTO antiques (
                id, name, serial_number, code, category, note, description, price, country,
                date_added, sold, sold_date, invoice_id, dimensions, material, material_main,
                children, place_of_origin, historical_period, condition, price_source, room,
                image_urls, art_classification, subject, art_symbols, ruler
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", samples)
    upgrade_database()

def log_action(username, action, item_id=""):
    try:
        with sqlite3.connect(DB_NAME) as conn:
            conn.execute("INSERT INTO logs (username, action, item_id, timestamp) VALUES (?,?,?,?)",
                         (username, action, item_id, datetime.datetime.now().isoformat()))
    except:
        pass

def save_single_image(uploaded_file, item_id, sort_order):
    processed = process_uploaded_image(uploaded_file)
    if processed is None:
        return None, None
    orig = os.path.join(IMG_FOLDER, f"{item_id}_{sort_order}.jpg")
    with open(orig, 'wb') as f:
        f.write(processed.getvalue())
    img = PIL_Image.open(processed)
    thumb = img.copy()
    thumb.thumbnail((300,300))
    thumb_path = os.path.join(THUMB_FOLDER, f"{item_id}_{sort_order}.jpg")
    thumb.save(thumb_path, "JPEG", quality=70)
    return orig, thumb_path

def save_multiple_images(uploaded_files, item_id):
    if not uploaded_files:
        return
    with sqlite3.connect(DB_NAME) as conn:
        conn.execute("DELETE FROM item_images WHERE item_id=?", (item_id,))
        for idx, file in enumerate(uploaded_files):
            orig, thumb = save_single_image(file, item_id, idx)
            if orig and thumb:
                conn.execute("INSERT INTO item_images (item_id, image_path, thumb_path, sort_order) VALUES (?,?,?,?)",
                             (item_id, orig, thumb, idx))

def get_item_images(item_id) -> List[dict]:
    with sqlite3.connect(DB_NAME) as conn:
        df_local = pd.read_sql("SELECT image_path, thumb_path FROM item_images WHERE item_id=? ORDER BY sort_order", conn, params=(item_id,))
        local_images = df_local.to_dict('records')
        if local_images:
            return local_images
        cur = conn.cursor()
        cur.execute("SELECT image_urls FROM antiques WHERE id=?", (item_id,))
        row = cur.fetchone()
        if row and row[0]:
            urls = row[0].split('||')
            return [{'image_path': url, 'thumb_path': url} for url in urls if url]
    return []

def get_item_image_urls(item_id) -> List[str]:
    images = get_item_images(item_id)
    valid = []
    for img in images:
        p = img['image_path']
        if p.startswith('http') or os.path.exists(p):
            valid.append(p)
    return valid

def update_item_image_urls(item_id, urls_list: List[str]):
    with sqlite3.connect(DB_NAME) as conn:
        urls_str = '||'.join(urls_list)
        conn.execute("UPDATE antiques SET image_urls=? WHERE id=?", (urls_str, item_id))

def delete_item_images(item_id):
    images = get_item_images(item_id)
    for img in images:
        if 'image_path' in img and img['image_path'].startswith(IMG_FOLDER):
            if os.path.exists(img['image_path']):
                os.remove(img['image_path'])
            if os.path.exists(img['thumb_path']):
                os.remove(img['thumb_path'])
    with sqlite3.connect(DB_NAME) as conn:
        conn.execute("DELETE FROM item_images WHERE item_id=?", (item_id,))

# ======================== دوال البحث النصي (OCR) - تم إصلاحها بالكامل ========================
def set_tesseract_path(path):
    if path and os.path.exists(path):
        pytesseract.pytesseract.tesseract_cmd = path
        st.session_state.tesseract_path = path
        return True
    return False

def is_tesseract_ready():
    if not TESSERACT_AVAILABLE:
        return False, "مكتبة pytesseract غير مثبتة. قم بتثبيتها: pip install pytesseract"
    try:
        # 1. محاولة البحث التلقائي في PATH باستخدام shutil (يعمل على ويندوز ولينكس)
        tesseract_path = shutil.which('tesseract')
        if tesseract_path:
            pytesseract.pytesseract.tesseract_cmd = tesseract_path
            version = pytesseract.get_tesseract_version()
            return True, f"✅ Tesseract مثبت (الإصدار {version}) - المسار: {tesseract_path}"
        
        # 2. قائمة بالمسارات الافتراضية لأنظمة التشغيل المختلفة
        possible_paths = [
            # مسارات ويندوز الشائعة
            r'C:\Program Files\Tesseract-OCR\tesseract.exe',
            r'C:\Program Files (x86)\Tesseract-OCR\tesseract.exe',
            # مسارات لينكس (Streamlit Cloud)
            '/usr/bin/tesseract',
            '/app/.apt/usr/bin/tesseract',
            '/usr/local/bin/tesseract',
            '/bin/tesseract',
            '/opt/conda/bin/tesseract'
        ]
        
        for path in possible_paths:
            if os.path.exists(path):
                pytesseract.pytesseract.tesseract_cmd = path
                version = pytesseract.get_tesseract_version()
                return True, f"✅ Tesseract مثبت (الإصدار {version}) - المسار: {path}"
        
        # 3. محاولة أخيرة: تشغيل الأمر مباشرة باستخدام subprocess
        try:
            result = subprocess.run(['tesseract', '--version'], capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                pytesseract.pytesseract.tesseract_cmd = 'tesseract'
                version = pytesseract.get_tesseract_version()
                return True, f"✅ Tesseract مثبت (الإصدار {version}) - تم العثور عليه في PATH"
        except:
            pass
        
        return False, "❌ Tesseract غير مثبت: لم يتم العثور على الملف التنفيذي في أي مسار معروف. تأكد من تثبيت Tesseract على جهازك."
    except Exception as e:
        return False, f"❌ خطأ في التحقق من Tesseract: {str(e)}"

def extract_text_from_image(image_file) -> str:
    ready, msg = is_tesseract_ready()
    if not ready:
        return f"❌ {msg}"
    try:
        img = PIL_Image.open(image_file)
        if img.mode == 'RGBA':
            img = img.convert('RGB')
        try:
            text = pytesseract.image_to_string(img, lang='ara+eng')
        except:
            text = pytesseract.image_to_string(img, lang='eng')
        text = re.sub(r'\s+', ' ', text).strip()
        return text
    except Exception as e:
        return f"❌ خطأ في OCR: {str(e)}"

def search_by_image_text(uploaded_image) -> pd.DataFrame:
    if uploaded_image is None:
        return pd.DataFrame()
    with st.spinner("جاري استخراج النص من الصورة..."):
        extracted_text = extract_text_from_image(uploaded_image)
    if extracted_text.startswith("❌"):
        st.error(extracted_text)
        return pd.DataFrame()
    if not extracted_text:
        st.warning("لم يتم التعرف على أي نص في الصورة.")
        return pd.DataFrame()
    st.success(f"✅ النص المستخرج: {extracted_text[:200]}...")
    keywords = [w for w in re.findall(r'[\w\u0600-\u06FF]+', extracted_text) if len(w) > 2]
    if not keywords:
        st.info("لا توجد كلمات ذات معنى كافية للبحث.")
        return pd.DataFrame()
    with sqlite3.connect(DB_NAME) as conn:
        df = pd.read_sql("SELECT * FROM antiques", conn)
    if df.empty:
        return pd.DataFrame()
    text_columns = ['name', 'description', 'category', 'art_classification', 'subject', 'art_symbols', 'ruler', 'note', 'place_of_origin']
    existing_cols = [col for col in text_columns if col in df.columns]
    def match_score(row):
        score = 0
        for kw in keywords:
            for col in existing_cols:
                val = str(row.get(col, ''))
                if kw in val:
                    score += 1
        return score
    df['match_score'] = df.apply(match_score, axis=1)
    results = df[df['match_score'] > 0].sort_values('match_score', ascending=False)
    return results

# ======================== البحث البصري المتقدم ========================
def search_by_visual_features(uploaded_image, min_matches=10):
    if not OPENCV_AVAILABLE:
        st.warning("OpenCV غير مثبت. جاري استخدام pHash كبديل...")
        return search_by_phash_fallback(uploaded_image, threshold=15)
    
    uploaded_bytes = uploaded_image.read()
    uploaded_image.seek(0)
    img_array = np.frombuffer(uploaded_bytes, np.uint8)
    query_img_cv = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
    if query_img_cv is None:
        st.error("فشل في قراءة الصورة المرفوعة.")
        return []
    
    kp_q, des_q = compute_orb_features(query_img_cv)
    if des_q is None or len(des_q) < 10:
        st.warning("الصورة المرفوعة تحتوي على نقاط مميزة قليلة جداً، حاول استخدام صورة أوضح أو جرب البحث النصي.")
        return []
    
    with sqlite3.connect(DB_NAME) as conn:
        items = pd.read_sql("SELECT id FROM antiques", conn)
    
    results = []
    progress = st.progress(0)
    total = len(items)
    for idx, (_, row) in enumerate(items.iterrows()):
        item_id = row['id']
        img_urls = get_item_image_urls(item_id)
        best_match = 0
        best_img = None
        for img_url in img_urls:
            img_cv = load_image_as_cv2(img_url)
            if img_cv is None:
                continue
            kp_db, des_db = compute_orb_features(img_cv)
            if des_db is None:
                continue
            matches, _ = match_features(des_q, des_db)
            if matches > best_match:
                best_match = matches
                best_img = img_url
        if best_match >= min_matches:
            results.append((item_id, best_match, best_img))
        progress.progress((idx+1)/total)
    progress.empty()
    results.sort(key=lambda x: x[1], reverse=True)
    return results

def search_by_phash_fallback(uploaded_image, threshold=15):
    if not IMAGEHASH_AVAILABLE:
        st.error("لا توجد مكتبة مناسبة للبحث البصري. قم بتثبيت opencv-python-headless أو imagehash")
        return []
    with sqlite3.connect(DB_NAME) as conn:
        items = pd.read_sql("SELECT id FROM antiques", conn)
    results = []
    for _, row in items.iterrows():
        item_id = row['id']
        img_urls = get_item_image_urls(item_id)
        best_diff = 100
        best_img = None
        for img_url in img_urls:
            diff = compute_phash_similarity(img_url, uploaded_image)
            if diff < best_diff:
                best_diff = diff
                best_img = img_url
        if best_diff <= threshold:
            similarity = max(0, 100 - best_diff)
            results.append((item_id, similarity, best_img))
    results.sort(key=lambda x: x[1], reverse=True)
    return results

# ======================== دوال QR والنسخ الاحتياطي ========================
def get_qr(item_data: dict):
    item_id = item_data.get('id', '')
    image_urls = get_item_image_urls(item_id) if item_id else []
    first_img_url = image_urls[0] if image_urls else "لا توجد صورة مسجلة"
    qr_text = f"""
🏛️ ANTIQ KHANA - DETAILS 🏛️
Name        : {item_data.get('name', 'غير محدد')}
Code        : {item_data.get('code', item_data.get('id', 'غير محدد'))}
Category    : {item_data.get('category', 'غير محدد')}
Origin      : {item_data.get('place_of_origin', item_data.get('country', 'غير محدد'))}
Material    : {item_data.get('material', 'غير محدد')}
Period      : {item_data.get('historical_period', 'غير محدد')}
Room        : {item_data.get('room', 'غير محدد')}
Art Class   : {item_data.get('art_classification', 'غير محدد')}
Subject     : {item_data.get('subject', 'غير محدد')}
Art Symbols : {item_data.get('art_symbols', 'غير محدد')}
Ruler       : {item_data.get('ruler', 'غير محدد')}
Status      : {'SOLD' if item_data.get('sold') == '1' else 'AVAILABLE'}
Description : {str(item_data.get('description', ''))[:150]}...
Image URL   : {first_img_url}
    """
    qr = qrcode.make(qr_text.strip())
    buf = BytesIO()
    qr.save(buf, format="PNG")
    return buf.getvalue()

def create_backup():
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_zip = os.path.join(BACKUP_FOLDER, f"backup_{ts}.zip")
    with zipfile.ZipFile(backup_zip, 'w') as zipf:
        if os.path.exists(DB_NAME):
            zipf.write(DB_NAME)
        for folder in [IMG_FOLDER, THUMB_FOLDER]:
            for root, _, files in os.walk(folder):
                for file in files:
                    zipf.write(os.path.join(root, file))
    return backup_zip

def reset_database_data():
    try:
        with sqlite3.connect(DB_NAME) as conn:
            conn.execute("DELETE FROM antiques")
            conn.execute("DELETE FROM sales")
            conn.execute("DELETE FROM customers")
            conn.execute("DELETE FROM logs")
            conn.execute("DELETE FROM item_images")
        for folder in [IMG_FOLDER, THUMB_FOLDER]:
            if os.path.exists(folder):
                shutil.rmtree(folder)
            os.makedirs(folder, exist_ok=True)
        log_action(st.session_state.get("username","system"), "Reset database")
        init_db()
        return True
    except Exception as e:
        st.error(f"Error resetting: {e}")
        return False

# ======================== دوال الذكاء الاصطناعي (Gemini) ========================
try:
    import google.generativeai as genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False

def get_gemini_model(api_key):
    try:
        genai.configure(api_key=api_key)
        model_names = ['gemini-2.0-flash-exp','gemini-1.5-flash','gemini-1.5-pro']
        for m in model_names:
            try:
                model = genai.GenerativeModel(m)
                model.generate_content("test")
                return model
            except:
                continue
        models = genai.list_models()
        for model in models:
            if 'generateContent' in model.supported_generation_methods:
                return genai.GenerativeModel(model.name)
    except:
        pass
    return None

def analyze_image_with_gemini(image_path, api_key):
    if not GEMINI_AVAILABLE or not api_key:
        return "❌ Gemini not available"
    try:
        model = get_gemini_model(api_key)
        if model is None:
            return "❌ No model"
        if image_path.startswith('http'):
            response = requests.get(image_path)
            img = PIL_Image.open(BytesIO(response.content))
        else:
            img = PIL_Image.open(image_path)
        prompt = "Analyze this antique: type, materials, period, condition, estimated value (USD)."
        response = model.generate_content([prompt, img])
        return response.text
    except Exception as e:
        return f"Error: {str(e)[:200]}"

def suggest_intelligent_price(name, category, origin, description, current_price, gemini_key=None):
    MIN_PRICE = 50.0
    base_price = MIN_PRICE
    rare_keywords = ['rare','antique','vintage','ancient']
    bonus = 0
    for kw in rare_keywords:
        if kw in name.lower():
            bonus += 50
        if description and kw in description.lower():
            bonus += 30
    base_price += bonus
    if category and 'rare' in category.lower():
        base_price += 200
    if origin and any(x in origin.lower() for x in ['egypt','france','italy','greece','china']):
        base_price += 150
    estimated = current_price * 1.2 if current_price and current_price >= MIN_PRICE else base_price
    if gemini_key and GEMINI_AVAILABLE:
        try:
            genai.configure(api_key=gemini_key)
            model = get_gemini_model(gemini_key)
            if model:
                prompt = f"Suggest reasonable USD price for '{name}' ({category}, {origin})"
                resp = model.generate_content(prompt)
                match = re.search(r'\d+(?:\.\d+)?', resp.text)
                if match:
                    estimated = float(match.group(0))
        except:
            pass
    return round(estimated, 2)

def ai_generate_description(name, category, origin):
    templates = [
        f"Beautiful {category or 'antique'} piece from {origin or 'unknown origin'}, named '{name}', with fine details.",
        f"Rare {category or 'antique'} masterpiece from {origin or 'ancient land'}, '{name}' is unique.",
        f"Collectible item from {origin or 'historical region'}, '{name}' in excellent condition."
    ]
    return random.choice(templates)

def generate_invoice_id():
    today = datetime.datetime.now().strftime("%Y%m%d")
    with sqlite3.connect(DB_NAME) as conn:
        cur = conn.cursor()
        cur.execute("SELECT MAX(CAST(SUBSTR(invoice_id, -4) AS INTEGER)) FROM sales WHERE invoice_id LIKE ?", (f"INV-{today}-%",))
        res = cur.fetchone()[0]
        next_seq = 1 if res is None else res + 1
    return f"INV-{today}-{next_seq:04d}"

def create_html_invoice(inv):
    price = float(inv['price'])
    discount = float(inv['discount'])
    total = float(inv['total'])
    return f"""
    <!DOCTYPE html><html dir="rtl"><head><meta charset="UTF-8"><title>فاتورة {inv['invoice_id']}</title>
    <style>
        body{{font-family:'Segoe UI',sans-serif;background:#f5f5f5;padding:20px;}}
        .invoice{{max-width:800px;margin:auto;background:white;border-radius:10px;padding:20px;box-shadow:0 0 10px rgba(0,0,0,0.1);}}
        .header{{text-align:center;border-bottom:2px solid #8e44ad;}}
        .info td{{padding:5px;}}
        .items table{{width:100%;border-collapse:collapse;}}
        .items th,.items td{{border:1px solid #ddd;padding:8px;text-align:center;}}
        .items th{{background:#8e44ad;color:white;}}
        .total{{font-weight:bold;margin-top:15px;}}
        .highlight{{color:#c0392b;}}
    </style></head>
    <body>
    <div class="invoice">
        <div class="header"><h1>🏛️ Antiq Khana</h1><p>فاتورة بيع</p></div>
        <div class="info">\n<table>\n
            <tr><td style="font-weight:bold;">رقم الفاتورة:</td><td>{inv['invoice_id']}</td></tr>
            <tr><td style="font-weight:bold;">التاريخ:</td><td>{inv['sale_date']}</td></tr>
            <tr><td style="font-weight:bold;">العميل:</td><td>{inv['customer_name']}</td></tr>
            <tr><td style="font-weight:bold;">الهاتف:</td><td>{inv['customer_phone']}</td></tr>
        </table></div>
        <div class="items"><h3>تفاصيل البند</h3>\n<table>\n<thead><tr><th>القطعة</th><th>السعر</th><th>الخصم</th><th>الإجمالي</th></tr></thead>
        <tbody><tr><td>{inv['item_name']}</td><td>{price:.2f} $</td><td class="highlight">- {discount:.2f} $</td><td>{total:.2f} $</td></tr>
        </tbody></table></div>
        <div class="total">الإجمالي النهائي: {total:.2f} دولار</div>
        <div class="footer">شكراً لثقتكم</div>
    </div></body></html>
    """

def sell_item(item_id, customer_name, customer_phone, customer_address, discount=0):
    with sqlite3.connect(DB_NAME) as conn:
        df = pd.read_sql("SELECT * FROM antiques WHERE id=? AND sold='0'", conn, params=(item_id,))
        if df.empty:
            return False, "Item not found or already sold", 0, None
        item = df.iloc[0]
        price = float(item['price'])
        total = price - discount
        inv_id = generate_invoice_id()
        sale_date = datetime.datetime.now().isoformat()
        conn.execute("""INSERT INTO sales (invoice_id, customer_name, customer_phone, customer_address,
                         item_id, item_name, price, discount, total, sale_date, status)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                     (inv_id, customer_name, customer_phone, customer_address,
                      item_id, item['name'], price, discount, total, sale_date, 'completed'))
        conn.execute("UPDATE antiques SET sold='1', sold_date=?, invoice_id=? WHERE id=?", (sale_date, inv_id, item_id))
        conn.execute("INSERT OR IGNORE INTO customers (name, phone, address, first_purchase) VALUES (?,?,?,?)",
                     (customer_name, customer_phone, customer_address, sale_date))
    log_action(st.session_state.get("username","system"), f"Sold {item_id} - {inv_id}")
    return True, inv_id, total, item

def create_search_urls(search_term):
    encoded = urllib.parse.quote(search_term)
    return (f"https://www.google.com/search?q={encoded}",
            f"https://www.amazon.com/s?k={encoded}",
            f"https://www.ebay.com/sch/i.html?_nkw={encoded}&LH_Sold=1")

# ======================== دوال Google Sheets ========================
def load_from_google_sheets(sheet_url: str, sheet_name: str = "Sheet1", credentials_file: str = "credentials.json"):
    if not GSHEET_AVAILABLE:
        st.error("gspread not installed")
        return None
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_name(credentials_file, scope)
        client = gspread.authorize(creds)
        sheet = client.open_by_url(sheet_url)
        worksheet = sheet.worksheet(sheet_name)
        data = worksheet.get_all_records()
        df = pd.DataFrame(data)
        df.columns = df.columns.str.strip().str.lower()
        image_col = None
        for col in df.columns:
            if col in ['images', 'image', 'الصور', 'صورة']:
                image_col = col
                break
        if image_col:
            df['image_urls'] = df[image_col].apply(lambda x: parse_image_urls(x) if isinstance(x, str) else [])
            df['image_urls_str'] = df['image_urls'].apply(lambda urls: '||'.join(urls))
        else:
            df['image_urls_str'] = ''
        return df
    except Exception as e:
        st.error(f"Google Sheets error: {e}")
        return None

def parse_image_urls(cell_value) -> List[str]:
    if not isinstance(cell_value, str):
        return []
    urls = re.split(r'[;/,\s]+', cell_value)
    result = []
    for url in urls:
        url = url.strip()
        if url and (url.startswith('http://') or url.startswith('https://')):
            result.append(url)
    return result

def import_from_gsheet_to_db(df: pd.DataFrame):
    if df is None or df.empty:
        return 0
    id_col = 'code' if 'code' in df.columns else ('id' if 'id' in df.columns else None)
    if not id_col:
        st.error("No 'code' or 'id' column")
        return 0
    count = 0
    with sqlite3.connect(DB_NAME) as conn:
        for _, row in df.iterrows():
            item_id = str(row[id_col])
            cur = conn.cursor()
            cur.execute("SELECT id FROM antiques WHERE id=?", (item_id,))
            exists = cur.fetchone()
            name = str(row.get('name', ''))
            serial_number = str(row.get('serial_number', ''))
            category = str(row.get('category', ''))
            description = str(row.get('description', ''))
            price = float(row.get('price', 0.0))
            place_of_origin = str(row.get('place_of_origin', row.get('country', '')))
            dimensions = str(row.get('dimensions', ''))
            material = str(row.get('material', ''))
            material_main = str(row.get('material_main', ''))
            children = str(row.get('children', ''))
            historical_period = str(row.get('historical_period', ''))
            condition = str(row.get('condition', ''))
            price_source = str(row.get('price_source', ''))
            room = str(row.get('room', ''))
            note = str(row.get('note', ''))
            image_urls_str = row.get('image_urls_str', '')
            art_classification = str(row.get('art_classification', ''))
            subject = str(row.get('subject', ''))
            art_symbols = str(row.get('art_symbols', ''))
            ruler = str(row.get('ruler', ''))
            if exists:
                conn.execute("""UPDATE antiques SET
                    name=?, serial_number=?, category=?, description=?, price=?, place_of_origin=?, dimensions=?,
                    material=?, material_main=?, children=?, historical_period=?, condition=?,
                    price_source=?, room=?, note=?, image_urls=?,
                    art_classification=?, subject=?, art_symbols=?, ruler=?
                    WHERE id=?""",
                    (name, serial_number, category, description, price, place_of_origin, dimensions,
                     material, material_main, children, historical_period, condition,
                     price_source, room, note, image_urls_str,
                     art_classification, subject, art_symbols, ruler, item_id))
            else:
                date_added = datetime.datetime.now().isoformat()
                conn.execute("""INSERT INTO antiques
                    (id, name, serial_number, code, category, note, description, price, country, date_added, sold,
                     dimensions, material, material_main, children, place_of_origin, historical_period,
                     condition, price_source, room, image_urls,
                     art_classification, subject, art_symbols, ruler)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (item_id, name, serial_number, item_id, category, note, description, price, place_of_origin,
                     date_added, '0', dimensions, material, material_main, children, place_of_origin,
                     historical_period, condition, price_source, room, image_urls_str,
                     art_classification, subject, art_symbols, ruler))
            count += 1
        conn.commit()
    return count

# ======================== عرض النتائج المشتركة ========================
def display_search_result(row, similarity_score=None, score_type="نقاط التشابه"):
    with st.container(border=True):
        col_img, col_info = st.columns([1, 2])
        with col_img:
            img_urls = get_item_image_urls(row['id'])
            if img_urls:
                st.image(img_urls[0], use_container_width=True)
            else:
                st.image("https://via.placeholder.com/150?text=No+Image", use_container_width=True)
        with col_info:
            st.subheader(row['name'])
            st.write(f"**الكود:** {row['id']}")
            st.write(f"**الفئة:** {row.get('category', 'غير محدد')}")
            st.write(f"**المادة:** {row.get('material', 'غير محدد')}")
            st.write(f"**المكان:** {row.get('place_of_origin', row.get('country', 'غير محدد'))}")
            if similarity_score is not None:
                st.write(f"**{score_type}:** {similarity_score}")
            if st.button(f"📖 عرض التفاصيل", key=f"searchres_{row['id']}"):
                go_to_details(row['id'])

# ======================== صفحات التطبيق ========================
def show_gallery():
    st.markdown('<div class="brand-title">🏛️ Antiq Khana | Antique Gallery</div>', unsafe_allow_html=True)
    st.header("🖼️ Collectibles Gallery")
    with sqlite3.connect(DB_NAME) as conn:
        show_sold = st.checkbox("Show sold items", value=True)
        if show_sold:
            df = pd.read_sql("SELECT * FROM antiques", conn)
        else:
            df = pd.read_sql("SELECT * FROM antiques WHERE sold='0'", conn)
    if df.empty:
        st.info("No items available. Add new items or reset database to load samples.")
        return

    col1, col2 = st.columns(2)
    with col1:
        search = st.text_input("🔍 Search (name/code)")
    with col2:
        sort_by = st.selectbox("📊 Sort by", ["Price (Ascending)", "Price (Descending)", "Latest"])

    with st.expander("🔎 Filters"):
        colA, colB, colC = st.columns(3)
        with colA:
            cat_filter = st.multiselect("Category", df['category'].dropna().unique())
        with colB:
            art_cat_filter = st.multiselect("Art Classification", df['art_classification'].dropna().unique())
        with colC:
            subject_filter = st.multiselect("Subject", df['subject'].dropna().unique())
        colD, colE, colF = st.columns(3)
        with colD:
            origin_filter = st.multiselect("Country / Origin", df['place_of_origin'].dropna().unique())
        with colE:
            art_symbols_filter = st.multiselect("Art Symbols", df['art_symbols'].dropna().unique())
        with colF:
            ruler_filter = st.multiselect("Ruler", df['ruler'].dropna().unique())

    query = "SELECT * FROM antiques WHERE 1=1"
    params = []
    if not show_sold:
        query += " AND sold='0'"
    if search:
        query += " AND (name LIKE ? OR code LIKE ?)"
        params.extend([f"%{search}%", f"%{search}%"])
    if cat_filter:
        query += f" AND category IN ({','.join('?'*len(cat_filter))})"
        params.extend(cat_filter)
    if art_cat_filter:
        query += f" AND art_classification IN ({','.join('?'*len(art_cat_filter))})"
        params.extend(art_cat_filter)
    if subject_filter:
        query += f" AND subject IN ({','.join('?'*len(subject_filter))})"
        params.extend(subject_filter)
    if origin_filter:
        query += f" AND place_of_origin IN ({','.join('?'*len(origin_filter))})"
        params.extend(origin_filter)
    if art_symbols_filter:
        query += f" AND art_symbols IN ({','.join('?'*len(art_symbols_filter))})"
        params.extend(art_symbols_filter)
    if ruler_filter:
        query += f" AND ruler IN ({','.join('?'*len(ruler_filter))})"
        params.extend(ruler_filter)

    if sort_by == "Price (Ascending)":
        order = "price ASC"
    elif sort_by == "Price (Descending)":
        order = "price DESC"
    else:
        order = "date_added DESC"
    query += f" ORDER BY {order}"

    with sqlite3.connect(DB_NAME) as conn:
        filtered_df = pd.read_sql(query, conn, params=params)

    total_pages = max(1, math.ceil(len(filtered_df) / ITEMS_PER_PAGE))
    page = st.session_state.gallery_page
    page = max(0, min(page, total_pages-1))
    start = page * ITEMS_PER_PAGE
    end = min(start + ITEMS_PER_PAGE, len(filtered_df))

    col_prev, col_info, col_next = st.columns([1,2,1])
    with col_prev:
        if st.button("⬅️ Previous", disabled=(page==0)):
            st.session_state.gallery_page = page-1
            st.rerun()
    with col_info:
        st.write(f"Page {page+1} of {total_pages} (Total {len(filtered_df)} items)")
    with col_next:
        if st.button("Next ➡️", disabled=(page+1>=total_pages)):
            st.session_state.gallery_page = page+1
            st.rerun()

    page_df = filtered_df.iloc[start:end]
    cols = st.columns(3)
    for idx, (_, row) in enumerate(page_df.iterrows()):
        with cols[idx % 3]:
            with st.container(border=True):
                img_urls = get_item_image_urls(row['id'])
                img = img_urls[0] if img_urls else None
                if img and (img.startswith('http') or os.path.exists(img)):
                    st.image(img, use_container_width=True)
                else:
                    st.image("https://via.placeholder.com/300?text=No+Image", use_container_width=True)
                st.subheader(row['name'])
                if st.session_state.role in ['admin','editor']:
                    st.write(f"💰 ${row['price']:.2f} | 🏷️ {row['category'] or 'General'}")
                else:
                    st.write(f"🏷️ {row['category'] or 'General'}")
                if row.get('code'):
                    st.caption(f"📦 Code: {str(row['code'])}")
                if row.get('place_of_origin'):
                    st.caption(f"📍 {str(row['place_of_origin'])[:50]}")
                if row.get('art_symbols'):
                    st.caption(f"🔣 {str(row['art_symbols'])[:30]}")
                if row['sold'] == '1':
                    st.markdown("❌ **Sold**", unsafe_allow_html=True)
                else:
                    st.markdown("✅ **Available**", unsafe_allow_html=True)
                if st.button(f"📖 Details", key=f"det_{row['id']}_{idx}"):
                    go_to_details(row['id'])

def show_details():
    if st.session_state.get("pending_item") and not st.session_state.selected_item_id:
        st.session_state.selected_item_id = st.session_state.pending_item
        st.session_state.page = "details"
        st.session_state.pending_item = None
        st.rerun()
    if not st.session_state.selected_item_id:
        go_back_to_main()
        return
    with sqlite3.connect(DB_NAME) as conn:
        df = pd.read_sql("SELECT * FROM antiques WHERE id=?", conn, params=(st.session_state.selected_item_id,))
    if df.empty:
        st.error("Item not found")
        go_back_to_main()
        return
    row = df.iloc[0]
    st.title(f"📌 Details: {row['name']}")
    img_urls = get_item_image_urls(row['id'])
    if img_urls:
        st.subheader("📸 Image Gallery")
        sel = st.session_state.get("img_index", 0)
        if sel >= len(img_urls): sel = 0
        current = img_urls[sel]
        if current.startswith('http') or os.path.exists(current):
            st.image(current, use_container_width=True)
        else:
            st.image("https://via.placeholder.com/500?text=Image+Not+Found", use_container_width=True)
        col1, col2, col3 = st.columns([1,2,1])
        with col1:
            if st.button("◀ Previous") and sel > 0:
                st.session_state.img_index = sel - 1
                st.rerun()
        with col3:
            if st.button("Next ▶") and sel < len(img_urls)-1:
                st.session_state.img_index = sel + 1
                st.rerun()
        with col2:
            st.write(f"Image {sel+1} of {len(img_urls)}")
        thumbs = st.columns(min(5, len(img_urls)))
        for i, u in enumerate(img_urls):
            with thumbs[i % 5]:
                st.image(u, use_container_width=True)
                if st.button(f"🎯", key=f"thumb_{i}"):
                    st.session_state.img_index = i
                    st.rerun()
    else:
        st.image("https://via.placeholder.com/500?text=No+Images", use_container_width=True)

    st.image(get_qr(row.to_dict()), width=250, caption="QR Code with all details + image link")

    with st.expander("📋 Item Information"):
        col1, col2 = st.columns(2)
        with col1:
            st.write(f"**Code:** {row['id']}")
            st.write(f"**Name:** {row['name']}")
            st.write(f"**Serial Number:** {row.get('serial_number') or '-'}")
            st.write(f"**Category:** {row['category'] or '-'}")
            st.write(f"**Place of Origin:** {row['place_of_origin'] or row['country'] or '-'}")
            st.write(f"**Dimensions:** {row['dimensions'] or '-'}")
            st.write(f"**Material:** {row['material'] or '-'}")
        with col2:
            st.write(f"**Main Material:** {row['material_main'] or '-'}")
            st.write(f"**Children pieces:** {row['children'] or '-'}")
            st.write(f"**Historical Period:** {row['historical_period'] or '-'}")
            st.write(f"**Condition:** {row['condition'] or '-'}")
            st.write(f"**Price Source:** {row['price_source'] or '-'}")
            st.write(f"**Room/Location:** {row['room'] or '-'}")
            if st.session_state.role in ['admin','editor']:
                st.write(f"**Price:** ${row['price']:.2f}")
            else:
                st.write("**Price:** viewers only")
            st.write(f"**Status:** {'❌ Sold' if row['sold']=='1' else '✅ Available'}")
        st.write("**Note:**", row['note'] or "-")
        st.write("**Description:**", row['description'] or "-")
        st.markdown("**📌 Additional Art Information**")
        col3, col4 = st.columns(2)
        with col3:
            st.write(f"**Art Classification:** {row.get('art_classification') or '-'}")
            st.write(f"**Subject:** {row.get('subject') or '-'}")
        with col4:
            st.write(f"**Art Symbols:** {row.get('art_symbols') or '-'}")
            st.write(f"**Ruler:** {row.get('ruler') or '-'}")
        if row['sold'] == '1':
            st.write(f"**Sale Date:** {row['sold_date']} | **Invoice:** {row['invoice_id']}")

    st.markdown("---")
    st.subheader("🌐 External Search")
    term = f"{row['name']} {row['category']} {row['place_of_origin']}".strip()
    g_url, a_url, e_url = create_search_urls(term)
    col_g, col_a, col_e = st.columns(3)
    with col_g: st.link_button("🔍 Google", g_url, use_container_width=True)
    with col_a: st.link_button("🛒 Amazon", a_url, use_container_width=True)
    with col_e: st.link_button("📦 eBay", e_url, use_container_width=True)

    if st.session_state.role in ['admin','editor']:
        st.markdown("---")
        st.subheader("🤖 AI Features")
        with st.expander("✨ Price & Description"):
            gem_key = st.text_input("Gemini API Key (optional)", type="password", key="gem_price", value=st.session_state.gemini_api_key)
            if gem_key != st.session_state.gemini_api_key:
                st.session_state.gemini_api_key = gem_key
            if st.button("Suggest Price & Description"):
                new_price = suggest_intelligent_price(row['name'], row['category'], row['place_of_origin'], row['description'], row['price'], st.session_state.gemini_api_key)
                new_desc = ai_generate_description(row['name'], row['category'], row['place_of_origin'])
                st.info(f"**Suggested Price:** ${new_price:.2f}\n**Suggested Description:** {new_desc}")
                if st.button("Apply"):
                    with sqlite3.connect(DB_NAME) as conn:
                        conn.execute("UPDATE antiques SET price=?, description=? WHERE id=?", (new_price, new_desc, row['id']))
                    st.success("Updated!")
                    st.rerun()
        with st.expander("🔍 Image Analysis (Gemini)"):
            if img_urls:
                gem_key2 = st.text_input("Gemini Key", type="password", key="gem_vision", value=st.session_state.gemini_api_key)
                if gem_key2 != st.session_state.gemini_api_key:
                    st.session_state.gemini_api_key = gem_key2
                if st.button("Analyze First Image"):
                    with st.spinner("Analyzing..."):
                        res = analyze_image_with_gemini(img_urls[0], st.session_state.gemini_api_key)
                        st.code(res, language="markdown")
            else:
                st.warning("No images")

    if st.session_state.role in ['admin','editor']:
        with st.expander("✏️ Edit Item & Images"):
            with st.form("edit_form"):
                new_name = st.text_input("Name", row['name'])
                new_serial = st.text_input("Serial", row.get('serial_number',''))
                new_code = st.text_input("Code", row.get('code',''))
                new_cat = st.text_input("Category", row.get('category',''))
                new_desc = st.text_area("Description", row.get('description',''))
                new_note = st.text_area("Note", row.get('note',''))
                new_price = st.number_input("Price", float(row['price'] or 0.0), step=0.5)
                new_origin = st.text_input("Place of Origin", row.get('place_of_origin',''))
                new_dim = st.text_input("Dimensions", row.get('dimensions',''))
                new_material = st.text_input("Material", row.get('material',''))
                new_material_main = st.text_input("Main Material", row.get('material_main',''))
                new_children = st.text_input("Children", row.get('children',''))
                new_period = st.text_input("Period", row.get('historical_period',''))
                new_condition = st.text_input("Condition", row.get('condition',''))
                new_price_source = st.text_input("Price Source", row.get('price_source',''))
                new_room = st.text_input("Room", row.get('room',''))
                new_art_class = st.text_input("Art Classification", row.get('art_classification',''))
                new_subject = st.text_input("Subject", row.get('subject',''))
                new_art_symbols = st.text_input("Art Symbols", row.get('art_symbols',''))
                new_ruler = st.text_input("Ruler", row.get('ruler',''))
                new_images = st.file_uploader("Replace images", type=['jpg','png','jpeg','webp','bmp','tiff','jfif'], accept_multiple_files=True)
                if st.form_submit_button("Save"):
                    with sqlite3.connect(DB_NAME) as conn:
                        conn.execute("""UPDATE antiques SET
                            name=?, serial_number=?, code=?, category=?, description=?, note=?, price=?,
                            place_of_origin=?, dimensions=?, material=?, material_main=?, children=?,
                            historical_period=?, condition=?, price_source=?, room=?,
                            art_classification=?, subject=?, art_symbols=?, ruler=?
                            WHERE id=?""",
                            (new_name, new_serial, new_code, new_cat, new_desc, new_note, new_price,
                             new_origin, new_dim, new_material, new_material_main, new_children,
                             new_period, new_condition, new_price_source, new_room,
                             new_art_class, new_subject, new_art_symbols, new_ruler, row['id']))
                    if new_images:
                        delete_item_images(row['id'])
                        save_multiple_images(new_images, row['id'])
                        update_item_image_urls(row['id'], [])
                    st.success("Saved")
                    st.rerun()
    if st.button("🔙 Back to Gallery"):
        go_back_to_main()

def show_image_search():
    st.markdown('<div class="brand-title">🔍 بحث بالصورة</div>', unsafe_allow_html=True)
    search_type = st.radio("اختر نوع البحث:", ["نصي (OCR)", "بصري (نقاط التشابه ORB)"], horizontal=True)
    uploaded_img = st.file_uploader("📸 اختر صورة للبحث", type=['jpg','png','jpeg','webp','bmp','tiff','jfif'])
    if uploaded_img is not None:
        col1, col2 = st.columns([1,2])
        with col1:
            st.image(uploaded_img, caption="الصورة المرفوعة", use_container_width=True)
        with col2:
            if st.button("🔎 ابدأ البحث", use_container_width=True, type="primary"):
                if search_type == "نصي (OCR)":
                    ready, msg = is_tesseract_ready()
                    if not ready:
                        st.error(msg)
                        return
                    results_df = search_by_image_text(uploaded_img)
                    if results_df.empty:
                        st.warning("❌ لم يتم العثور على قطع مطابقة نصياً.")
                    else:
                        st.success(f"✅ تم العثور على {len(results_df)} نتيجة (نصية)")
                        for _, row in results_df.iterrows():
                            display_search_result(row)
                else:  # بصري
                    if not OPENCV_AVAILABLE and not IMAGEHASH_AVAILABLE:
                        st.error("مكتبات البحث البصري غير مثبتة. قم بتشغيل: pip install opencv-python-headless imagehash")
                        return
                    with st.spinner("جاري مقارنة الصور (قد يستغرق قليلاً)..."):
                        visual_results = search_by_visual_features(uploaded_img, min_matches=10)
                    if not visual_results:
                        st.warning("❌ لم يتم العثور على قطع مشابهة بصرياً.")
                    else:
                        st.success(f"✅ تم العثور على {len(visual_results)} قطع مشابهة بصرياً (كلما زاد العدد كان التشابه أقوى)")
                        for item_id, matches, _ in visual_results:
                            with sqlite3.connect(DB_NAME) as conn:
                                row = pd.read_sql("SELECT * FROM antiques WHERE id=?", conn, params=(item_id,)).iloc[0]
                            score_label = "نقاط التشابه (ORB)" if OPENCV_AVAILABLE else "درجة التشابه (pHash)"
                            display_search_result(row, similarity_score=matches, score_type=score_label)

def show_add_item():
    if st.session_state.role not in ['admin','editor']:
        st.error("Unauthorized")
        return
    st.header("✨ Add New Antique Item")
    with st.form("add_form"):
        col1, col2 = st.columns(2)
        with col1:
            code = st.text_input("Code *")
            name = st.text_input("Name *")
            serial = st.text_input("Serial number")
            cat = st.text_input("Category")
            desc = st.text_area("Description")
            dim = st.text_input("Dimensions")
            mat = st.text_input("Material")
            origin = st.text_input("Place of Origin")
        with col2:
            mat_main = st.text_input("Main Material")
            children = st.text_input("Children pieces")
            period = st.text_input("Historical Period")
            cond = st.selectbox("Condition", ["", "Excellent", "Very Good", "Good", "Fair", "Needs Restoration"])
            price = st.number_input("Price (USD)", min_value=0.0, step=0.5)
            price_src = st.text_input("Price Source")
            room = st.text_input("Room/Location")
            note = st.text_area("Additional Notes")
            images = st.file_uploader("Images", type=['jpg','png','jpeg','webp','bmp','tiff','jfif'], accept_multiple_files=True)
            img_urls_text = st.text_area("Image URLs (separate with / or ;)")
        st.markdown("**Art Information**")
        col3, col4 = st.columns(2)
        with col3:
            art_class = st.text_input("Art Classification")
            art_symbols = st.text_input("Art Symbols")
        with col4:
            subject = st.text_input("Subject")
            ruler = st.text_input("Ruler")
        if st.form_submit_button("Save"):
            if not code or not name:
                st.error("Code and Name required")
            else:
                with sqlite3.connect(DB_NAME) as conn:
                    if conn.execute("SELECT id FROM antiques WHERE id=?", (code,)).fetchone():
                        st.error("Code already exists")
                        return
                urls = parse_image_urls(img_urls_text) if img_urls_text else []
                urls_str = '||'.join(urls)
                now = datetime.datetime.now().isoformat()
                with sqlite3.connect(DB_NAME) as conn:
                    conn.execute("""INSERT INTO antiques
                        (id, name, serial_number, code, category, note, description, price, country, date_added, sold,
                         dimensions, material, material_main, children, place_of_origin, historical_period,
                         condition, price_source, room, image_urls,
                         art_classification, subject, art_symbols, ruler)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (code, name, serial, code, cat, note, desc, price, origin, now, '0',
                         dim, mat, mat_main, children, origin, period, cond, price_src, room, urls_str,
                         art_class, subject, art_symbols, ruler))
                if images:
                    save_multiple_images(images, code)
                st.success(f"Item {name} added")
                st.rerun()

def show_manage_users():
    if st.session_state.role != "admin":
        st.error("Admin only")
        return
    st.header("👥 User Management")
    with st.form("new_user"):
        uname = st.text_input("Username")
        pwd = st.text_input("Password", type="password")
        role = st.selectbox("Role", ["viewer","editor","admin"])
        if st.form_submit_button("Add"):
            if uname and pwd:
                hashed = bcrypt.hashpw(pwd.encode(), bcrypt.gensalt())
                try:
                    with sqlite3.connect(DB_NAME) as conn:
                        conn.execute("INSERT INTO users (username,password,role) VALUES (?,?,?)", (uname, hashed, role))
                    st.success("Added")
                except:
                    st.error("Username exists")
            else:
                st.error("Fill all")
    with sqlite3.connect(DB_NAME) as conn:
        users_df = pd.read_sql("SELECT id, username, role FROM users", conn)
    st.dataframe(users_df, use_container_width=True)

def show_logs():
    if st.session_state.role != "admin":
        st.error("Admin only")
        return
    st.header("📜 Activity Logs")
    with sqlite3.connect(DB_NAME) as conn:
        logs_df = pd.read_sql("SELECT * FROM logs ORDER BY timestamp DESC LIMIT 200", conn)
    st.dataframe(logs_df, use_container_width=True)

def show_stats():
    st.header("📊 Statistics")
    with sqlite3.connect(DB_NAME) as conn:
        df = pd.read_sql("SELECT * FROM antiques", conn)
        sales = pd.read_sql("SELECT * FROM sales", conn)
    if not df.empty:
        c1,c2,c3 = st.columns(3)
        c1.metric("Total Items", len(df))
        c2.metric("Sold", len(df[df['sold']=='1']))
        c3.metric("Available", len(df[df['sold']=='0']))
        if not sales.empty and st.session_state.role in ['admin','editor']:
            st.metric("Total Revenue", f"${sales['total'].sum():.2f}")
        st.subheader("Category Distribution")
        st.bar_chart(df['category'].value_counts())
    else:
        st.info("No data")

def show_backup():
    if st.session_state.role != "admin":
        st.error("Admin only")
        return
    st.header("💾 Backup")
    if st.button("Create Backup"):
        path = create_backup()
        with open(path, "rb") as f:
            st.download_button("Download", f, file_name=os.path.basename(path))

def show_import_export():
    st.header("📂 Import/Export Excel")
    tab1, tab2 = st.tabs(["Import", "Export"])
    with tab1:
        f = st.file_uploader("Excel file", type=['xlsx','xls'])
        if st.button("Import") and f:
            try:
                df = pd.read_excel(f, dtype=str)
                df.columns = df.columns.str.strip().str.lower()
                if 'images' in df.columns or 'image' in df.columns:
                    img_col = 'images' if 'images' in df.columns else 'image'
                    df['image_urls'] = df[img_col].apply(lambda x: parse_image_urls(x) if isinstance(x, str) else [])
                    df['image_urls_str'] = df['image_urls'].apply(lambda urls: '||'.join(urls))
                else:
                    df['image_urls_str'] = ''
                count = import_from_gsheet_to_db(df)
                st.success(f"Imported {count} items")
            except Exception as e:
                st.error(f"Error: {e}")
    with tab2:
        with sqlite3.connect(DB_NAME) as conn:
            out = pd.read_sql("SELECT id, name, serial_number, code, category, note, description, price, place_of_origin, dimensions, material, material_main, children, historical_period, condition, price_source, room, art_classification, subject, art_symbols, ruler FROM antiques", conn)
        if not out.empty:
            buf = BytesIO()
            with pd.ExcelWriter(buf, engine='openpyxl') as writer:
                out.to_excel(writer, index=False)
            st.download_button("Download Excel", buf.getvalue(), file_name=f"antiques_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx")

def show_gsheet_importer():
    st.header("📊 Import from Google Sheets")
    st.markdown("Requires `credentials.json` in app directory")
    sheet_url = st.text_input("Google Sheets URL")
    sheet_name = st.text_input("Sheet name", value="Sheet1")
    if st.button("Load"):
        df = load_from_google_sheets(sheet_url, sheet_name)
        if df is not None:
            st.success(f"Loaded {len(df)} rows")
            st.dataframe(df.head(20))
            if st.button("Import to DB"):
                count = import_from_gsheet_to_db(df)
                st.success(f"Imported {count} items")

def show_sales_invoice():
    if st.session_state.role not in ['admin','editor']:
        st.error("Unauthorized")
        return
    st.header("🧾 New Sales Invoice")
    with sqlite3.connect(DB_NAME) as conn:
        avail = pd.read_sql("SELECT id, name, serial_number, price FROM antiques WHERE sold='0'", conn)
    if avail.empty:
        st.warning("No items available")
        return
    with st.form("sale_form"):
        opt = {f"{r['name']} (SN: {r['serial_number'] or 'N/A'}) - ${r['price']}": r['id'] for _, r in avail.iterrows()}
        sel = st.selectbox("Select item", list(opt.keys()))
        iid = opt[sel]
        price = avail[avail['id']==iid]['price'].values[0]
        disc = st.number_input("Discount ($)", 0.0, float(price), step=1.0)
        total = price - disc
        st.write(f"Base: ${price:.2f} | Discount: ${disc:.2f} | Total: ${total:.2f}")
        cust_name = st.text_input("Customer name *")
        cust_phone = st.text_input("Phone *")
        cust_addr = st.text_area("Address")
        preview = st.form_submit_button("Preview")
        sell = st.form_submit_button("Issue Invoice")
    if preview:
        if not cust_name or not cust_phone:
            st.error("Enter customer name and phone")
        else:
            inv_preview = {
                'invoice_id': "PREVIEW",
                'sale_date': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                'customer_name': cust_name,
                'customer_phone': cust_phone,
                'customer_address': cust_addr,
                'item_name': avail[avail['id']==iid]['name'].values[0],
                'price': price,
                'discount': disc,
                'total': total
            }
            html_inv = create_html_invoice(inv_preview)
            st.components.v1.html(html_inv, height=500)
    if sell:
        if not cust_name or not cust_phone:
            st.error("Enter customer name and phone")
        else:
            ok, inv_id, tot, it = sell_item(iid, cust_name, cust_phone, cust_addr, disc)
            if ok:
                st.success(f"Sold! Invoice: {inv_id}")
                inv_data = {
                    'invoice_id': inv_id,
                    'sale_date': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    'customer_name': cust_name,
                    'customer_phone': cust_phone,
                    'customer_address': cust_addr,
                    'item_name': it['name'],
                    'price': price,
                    'discount': disc,
                    'total': tot
                }
                html_inv = create_html_invoice(inv_data)
                st.download_button("Download Invoice", html_inv, file_name=f"{inv_id}.html", mime="text/html")
                with st.expander("View Invoice"):
                    st.components.v1.html(html_inv, height=500)
            else:
                st.error(ok)

def show_sales_list():
    if st.session_state.role != "admin":
        st.error("Admin only")
        return
    st.header("📋 Invoices List")
    with sqlite3.connect(DB_NAME) as conn:
        sales = pd.read_sql("SELECT * FROM sales ORDER BY sale_date DESC", conn)
    if sales.empty:
        st.info("No sales")
    else:
        st.dataframe(sales, use_container_width=True)
        if st.button("Export to Excel"):
            buf = BytesIO()
            with pd.ExcelWriter(buf, engine='openpyxl') as writer:
                sales.to_excel(writer, index=False)
            st.download_button("Download", buf.getvalue(), file_name=f"sales_{datetime.datetime.now().strftime('%Y%m%d')}.xlsx")

# ======================== حالة الجلسة ========================
if "auth" not in st.session_state:
    st.session_state.auth = False
    st.session_state.username = ""
    st.session_state.role = ""
    st.session_state.selected_item_id = None
    st.session_state.page = "main"
    st.session_state.show_change_pwd = False
    st.session_state.show_reset_confirm = False
    st.session_state.gallery_page = 0
    st.session_state.img_index = 0
    st.session_state.gemini_api_key = ""
    st.session_state.tesseract_path = ""
    st.session_state.pending_item = None

def go_to_details(iid):
    st.session_state.selected_item_id = iid
    st.session_state.page = "details"
    st.rerun()

def go_back_to_main():
    st.session_state.selected_item_id = None
    st.session_state.page = "main"
    st.rerun()

def change_password():
    with st.sidebar.form("change_pwd"):
        old = st.text_input("Current Password", type="password")
        new = st.text_input("New Password", type="password")
        conf = st.text_input("Confirm Password", type="password")
        if st.form_submit_button("Change"):
            if new != conf:
                st.sidebar.error("Passwords do not match")
            else:
                with sqlite3.connect(DB_NAME) as conn:
                    cur = conn.cursor()
                    cur.execute("SELECT password FROM users WHERE username=?", (st.session_state.username,))
                    row = cur.fetchone()
                    if row and bcrypt.checkpw(old.encode(), row[0]):
                        hashed = bcrypt.hashpw(new.encode(), bcrypt.gensalt())
                        conn.execute("UPDATE users SET password=? WHERE username=?", (hashed, st.session_state.username))
                        log_action(st.session_state.username, "Password changed")
                        st.sidebar.success("Password changed successfully")
                    else:
                        st.sidebar.error("Current password is incorrect")

# ======================== تسجيل الدخول ========================
if not st.session_state.auth:
    st.title("🏛️ Antiq Khana")
    st.subheader("Login")
    un = st.text_input("Username")
    pw = st.text_input("Password", type="password")
    if st.button("Login"):
        init_db()
        with sqlite3.connect(DB_NAME) as conn:
            cur = conn.cursor()
            cur.execute("SELECT password, role FROM users WHERE username=?", (un,))
            row = cur.fetchone()
            if row and bcrypt.checkpw(pw.encode(), row[0]):
                st.session_state.auth = True
                st.session_state.username = un
                st.session_state.role = row[1]
                log_action(un, "Login")
                if st.session_state.get("pending_item"):
                    st.session_state.selected_item_id = st.session_state.pending_item
                    st.session_state.page = "details"
                    st.session_state.pending_item = None
                st.rerun()
            else:
                st.error("Invalid credentials")
    st.stop()

# ======================== القائمة الجانبية ========================
st.sidebar.markdown(f"**Welcome {st.session_state.username}** - Role: {st.session_state.role}")
if st.sidebar.button("🔐 Change Password"):
    st.session_state.show_change_pwd = not st.session_state.get("show_change_pwd", False)
if st.session_state.get("show_change_pwd", False):
    change_password()
    if st.sidebar.button("Hide"):
        st.session_state.show_change_pwd = False
        st.rerun()
if st.session_state.role == "admin":
    st.sidebar.divider()
    st.sidebar.subheader("Admin Tools")
    if st.sidebar.button("🗑️ Reset Database"):
        st.session_state.show_reset_confirm = True
    if st.session_state.get("show_reset_confirm", False):
        confirm = st.sidebar.text_input("Type 'yes' to confirm")
        col1, col2 = st.sidebar.columns(2)
        with col1:
            if st.button("Confirm"):
                if confirm.lower() == "yes":
                    if reset_database_data():
                        st.sidebar.success("Reset successful")
                        st.session_state.show_reset_confirm = False
                        st.rerun()
                    else:
                        st.sidebar.error("Error")
                else:
                    st.sidebar.error("Type 'yes'")
        with col2:
            if st.button("Cancel"):
                st.session_state.show_reset_confirm = False
                st.rerun()

# ======================== القائمة الرئيسية ========================
if st.session_state.page == "details":
    show_details()
else:
    role = st.session_state.role
    menu = ["Gallery 🖼️"]
    if role in ['admin','editor']:
        menu.append("Sales Invoice 🧾")
    if role == "admin":
        menu.append("Invoices List 📋")
    menu.append("Search by Image 🔍")
    menu.append("Import from Google Sheets 📊")
    if role in ['admin','editor']:
        menu.append("Add Item ✨")
    if role == "admin":
        menu.extend(["User Management 👥", "Activity Logs 📜"])
    menu.extend(["Statistics 📊"])
    if role == "admin":
        menu.append("Backup 💾")
    menu.append("Import/Export Excel 📂")
    choice = st.sidebar.radio("Main Menu", menu)
    if choice == "Gallery 🖼️":
        show_gallery()
    elif choice == "Sales Invoice 🧾":
        show_sales_invoice()
    elif choice == "Invoices List 📋":
        show_sales_list()
    elif choice == "Search by Image 🔍":
        show_image_search()
    elif choice == "Add Item ✨":
        show_add_item()
    elif choice == "User Management 👥":
        show_manage_users()
    elif choice == "Activity Logs 📜":
        show_logs()
    elif choice == "Statistics 📊":
        show_stats()
    elif choice == "Backup 💾":
        show_backup()
    elif choice == "Import/Export Excel 📂":
        show_import_export()
    elif choice == "Import from Google Sheets 📊":
        show_gsheet_importer()

st.markdown(f"""
<div class="footer">
    © 2026 Techno logic | Haytham Elsaadany.<br>
    هذا البرنامج مرخص حصرياً  باسم ا.هيثم السعدني: {OWNER_PHONE} - جميع الحقوق محفوظة.
</div>
""", unsafe_allow_html=True)

if __name__ == "__main__":
    init_db()