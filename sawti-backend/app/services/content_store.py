"""
مخزن محتوى المعلم (الدروس، المواضيع، الألعاب...) في PostgreSQL.

كان هذا المحتوى يُحفَظ في ملفات JSON على قرص الخادم، وقرص Render مؤقت
(ephemeral) يُمحى مع كل نشر — فتضيع تعديلات المعلم. الآن مصدر الحقيقة
الوحيد هو جدول واحد عام:

    content_store(key TEXT PRIMARY KEY, data JSONB, updated_at TIMESTAMPTZ)

المفاتيح: speaking, writing, self_learning, games, dictation,
hamza_games, hamza_journeys. شكل JSON المخزَّن هو نفسه الذي تعيده واجهات
/api/lessons منذ البداية، فلا تتغير الواجهة الأمامية.

البذر (seed): عند أول قراءة لمفتاح لا صف له في القاعدة، تُخزَّن القيمة
الافتراضية (أو محتوى ملف مرفق مع المشروع إن وُجد، مثل hamza_games.json)
فلا تضيع البيانات الافتراضية.

بدون DATABASE_URL:
  • في الإنتاج: القراءة تعيد الافتراضي من الذاكرة، وأي تعديل يُرفَض
    برسالة 503 واضحة (لا نكتب ملفات على قرص مؤقت ونوهم المعلم بأنها حُفظت).
  • في التطوير المحلي فقط: ملفات JSON داخل app/data/local/ (خارج git).
"""
import os
import json
import copy
import logging
from typing import Any, Callable

from fastapi import HTTPException

from app.services import db
from app.services.security import is_production

logger = logging.getLogger("sawti.content")

_CREATE_SQL = """
    CREATE TABLE IF NOT EXISTS content_store (
        key TEXT PRIMARY KEY,
        data JSONB NOT NULL,
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )
"""

_LOCAL_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "local")
_warned_no_db = False


def _warn_no_db():
    global _warned_no_db
    if not _warned_no_db:
        _warned_no_db = True
        logger.error(
            "ContentStore: DATABASE_URL غير مضبوط — محتوى المعلم لا يُحفَظ بشكل دائم. "
            "%s", "التعديلات مرفوضة حتى تضبط القاعدة." if is_production()
            else "يُستخدم ملف محلي للتطوير فقط."
        )


def _seed_value(default_factory: Callable[[], Any], seed_file: str | None) -> Any:
    """القيمة الابتدائية: ملف مرفق مع المشروع إن وُجد وصحّ، وإلا الافتراضي من الكود."""
    if seed_file and os.path.exists(seed_file):
        try:
            with open(seed_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError):
            logger.exception("ContentStore: تعذّرت قراءة ملف البذر %s — يُستخدم الافتراضي", seed_file)
    return copy.deepcopy(default_factory())


def _local_path(key: str) -> str:
    return os.path.join(_LOCAL_DIR, f"{key}.json")


def get(key: str, default_factory: Callable[[], Any], seed_file: str | None = None) -> Any:
    """يقرأ قيمة المفتاح؛ إن لم توجد يبذرها بالافتراضي ثم يعيدها. دائمًا نسخة مستقلة."""
    if db.is_configured():
        db.ensure_table("content_store", _CREATE_SQL)
        conn = db.get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT data FROM content_store WHERE key = %s", (key,))
                row = cur.fetchone()
                if row is not None:
                    return row[0]
                value = _seed_value(default_factory, seed_file)
                cur.execute(
                    "INSERT INTO content_store (key, data) VALUES (%s, %s) ON CONFLICT (key) DO NOTHING",
                    (key, json.dumps(value, ensure_ascii=False)),
                )
                # قد يكون طلب آخر سبقنا بالبذر — نقرأ ما استقر فعلًا في القاعدة
                cur.execute("SELECT data FROM content_store WHERE key = %s", (key,))
                stored = cur.fetchone()
            conn.commit()
            return stored[0] if stored else value
        finally:
            conn.close()

    _warn_no_db()
    if not is_production():
        path = _local_path(key)
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (OSError, json.JSONDecodeError):
                logger.exception("ContentStore: ملف محلي تالف %s", path)
    return _seed_value(default_factory, seed_file)


def put(key: str, data: Any) -> None:
    """يحفظ قيمة المفتاح (استبدال كامل)."""
    if db.is_configured():
        db.ensure_table("content_store", _CREATE_SQL)
        conn = db.get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO content_store (key, data, updated_at) VALUES (%s, %s, now())
                    ON CONFLICT (key) DO UPDATE SET data = EXCLUDED.data, updated_at = now()
                    """,
                    (key, json.dumps(data, ensure_ascii=False)),
                )
            conn.commit()
        finally:
            conn.close()
        return

    _warn_no_db()
    if is_production():
        raise HTTPException(503, "التخزين الدائم غير مُفعَّل على الخادم، لذلك لا يمكن حفظ التعديلات الآن")
    os.makedirs(_LOCAL_DIR, exist_ok=True)
    with open(_local_path(key), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
