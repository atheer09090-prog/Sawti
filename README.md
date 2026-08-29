# 🎙️ صوتي قلمي — Backend

خادم FastAPI لتقييم التحدث والكتابة في منصة صوتي قلمي.

---

## 📁 هيكل المشروع

```
sawti-backend/
├── main.py                    ← نقطة الدخول
├── requirements.txt           ← المكتبات
├── render.yaml                ← إعدادات Render
├── .env.example               ← متغيرات البيئة
├── api.ts                     ← انسخه لـ client/src/lib/
└── app/
    ├── routers/
    │   ├── evaluation.py      ← /api/eval/speech  و  /api/eval/writing
    │   └── reports.py         ← /api/reports/student
    └── services/
        ├── speech_eval.py     ← Whisper + تقييم النطق
        ├── writing_eval.py    ← تقييم الإملاء والتركيب
        └── pdf_gen.py         ← توليد PDF
```

---

## 🚀 النشر على Render (مجاناً)

### الخطوة 1 — رفع الكود على GitHub
```bash
git init
git add .
git commit -m "أول نسخة من Backend صوتي قلمي"
git remote add origin https://github.com/اسمك/sawti-backend
git push -u origin main
```

### الخطوة 2 — إنشاء خدمة على Render
1. افتح [render.com](https://render.com) وسجّل دخول
2. اضغط **New → Web Service**
3. اربط مستودع GitHub
4. الإعدادات:
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `uvicorn main:app --host 0.0.0.0 --port $PORT`
   - **Environment:** Python 3

### الخطوة 3 — إضافة متغيرات البيئة في Render
```
WHISPER_MODEL = base
ENVIRONMENT = production
ALLOWED_ORIGINS = https://sawtiqalam-pytdgr9g.manus.space
```

### الخطوة 4 — ربط المنصة بالـ Backend
في مشروع React أضف ملف `.env`:
```
VITE_API_URL=https://اسم-مشروعك.onrender.com/api
```
ثم انسخ ملف `api.ts` إلى `client/src/lib/api.ts`

---

## 🔌 نقاط الـ API

| الطريقة | المسار | الوصف |
|---------|--------|-------|
| POST | `/api/eval/speech` | تقييم التحدث (ملف صوتي) |
| POST | `/api/eval/writing` | تقييم الكتابة (نص) |
| POST | `/api/reports/student` | توليد تقرير PDF |
| GET | `/api/health` | فحص حالة الخادم |
| GET | `/api/docs` | توثيق API التفاعلي |

---

## 💻 التشغيل المحلي

```bash
# تثبيت المكتبات
pip install -r requirements.txt

# تشغيل الخادم
uvicorn main:app --reload --port 8000

# افتح التوثيق
# http://localhost:8000/api/docs
```

---

## 📝 ملاحظة مهمة
نموذج Whisper `base` سريع لكن دقته متوسطة للعربية.
لدقة أعلى غيّر `WHISPER_MODEL=medium` (لكن سيكون أبطأ).
