# صوتي قلمي — الـBackend (FastAPI)

واجهة برمجية لمنصة «صوتي قلمي» لتعليم اللغة العربية (التحدث والكتابة): حسابات الطلاب، لوحة المعلم، محتوى الدروس، التقييم بالذكاء الاصطناعي (Groq Whisper + Gemini)، استبيان SUS، وتقارير PDF.

## المتطلبات
- Python 3.11+
- PostgreSQL (مثلًا Supabase) — مطلوب للحسابات ومحتوى المعلم في الإنتاج
- مفتاح Groq (تحويل الصوت لنص) ومفتاح Gemini (التصحيح والتشكيل والمعلم الذكي)

## التشغيل محليًا
```bash
cd sawti-backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # ثم عبّئ القيم
uvicorn main:app --reload --port 8000
```
التوثيق التفاعلي: http://localhost:8000/docs — فحص الصحة: `/api/health`.
بدون `DATABASE_URL` يعمل التطوير بملفات محلية (`app/data/local/`)، لكن الحسابات (التسجيل/الدخول) تتطلب قاعدة بيانات.

## متغيرات البيئة
| المتغير | الوصف |
|---|---|
| `ENVIRONMENT` | `production` في الإنتاج (أو `ENV=production`) |
| `JWT_SECRET` | سر توقيع الجلسات. **في الإنتاج يفشل الإقلاع بدونه** |
| `TEACHER_ACCESS_CODE` | رمز دخول المعلم. بدونه يُغلق دخول المعلم (لا رمز افتراضي) |
| `DATABASE_URL` | رابط PostgreSQL. يُضاف `sslmode=require` تلقائيًا ما لم يُذكر في الرابط |
| `GROQ_API_KEY` | Whisper لتحويل الصوت لنص |
| `GEMINI_API_KEY` | التصحيح والتشكيل والتدقيق والمعلم الذكي |
| `ALLOWED_ORIGINS` | نطاقات الواجهة المسموحة (CORS)، مفصولة بفواصل. `*` غير مسموح |

الواجهة تستخدم `VITE_API_URL` (انظر README الواجهة).

## الأمان باختصار
- **المعلم:** `POST /api/auth/teacher-login` يُصدر JWT (`role=teacher`، 8 ساعات). كل مسارات المعلم تتحقق منه (`require_teacher`) عبر `Authorization: Bearer`.
- **الطالب:** JWT (`role=student`) من التسجيل/الدخول/الحساب التجريبي. لا يصل إلا لسجله (`/api/students/me`).
- **للمعلم فقط:** قائمة الطلاب، تعليق المعلم، كل POST/PUT/DELETE في `/api/lessons/*`، `/api/sus/export|report|summary`، `/api/reports/student`، `GET /api/reviews`.
- **خدمات AI (`/api/eval/*`):** تتطلب تسجيل دخول، وبها حدود: النص 5000 حرف، السؤال 500، الصوت 10MB، وتحديد معدّل لكل مستخدم (في الذاكرة، يُصفَّر عند إعادة التشغيل).
- محتوى المعلم يُخزَّن في جدول `content_store` (PostgreSQL)، وتُزرع القيم الافتراضية عند أول قراءة.

## الاختبارات
```bash
pytest test -q                                   # بدون قاعدة: تُتخطّى اختبارات DB
TEST_DATABASE_URL="postgresql://user:pass@localhost:5432/sawti_test?sslmode=disable" pytest test -q
```
**استخدم قاعدة اختبار منفصلة دائمًا.** الاختبارات تتجاهل `DATABASE_URL` عمدًا ولا تعمل إلا على `TEST_DATABASE_URL`.

## النشر (Render)
1. أنشئ Web Service من هذا المجلد (`render.yaml` جاهز): Build `pip install -r requirements.txt`، Start `uvicorn main:app --host 0.0.0.0 --port $PORT`.
2. اضبط المتغيرات: `DATABASE_URL`، `TEACHER_ACCESS_CODE`، `GROQ_API_KEY`، `GEMINI_API_KEY`، و**`ALLOWED_ORIGINS` بنطاق الواجهة الفعلي**. (`JWT_SECRET` يُولَّد تلقائيًا من `render.yaml` ويبقى ثابتًا.)
3. تحقق من `/api/health` ثم جرّب دخول المعلم والتسجيل.

> قرص Render مؤقت: لا تعتمد على أي ملف محلي للبيانات. كل شيء قابل للتعديل في PostgreSQL.
