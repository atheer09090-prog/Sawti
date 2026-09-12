"""
اتصال بقاعدة بيانات Postgres دائمة (مثل Supabase) لتخزين بيانات لا يجوز
أن تُفقَد — بعكس التخزين القديم كملفات JSON على قرص خادم Render، والذي
كان يُصفَّر بالكامل مع كل عملية نشر (deploy) جديدة لأن القرص المحلي هناك
غير دائم (ephemeral)، وهذا كان السبب الحقيقي في اختفاء بيانات الطلاب بعد
كل تحديث للكود.

إن لم يكن متغيّر البيئة DATABASE_URL مضبوطًا بعد، تعمل is_configured()
بإرجاع False حتى تستمر الأجزاء التي تعتمد على هذا الملف بالعمل بطريقتها
الاحتياطية القديمة (ملف JSON) دون أن ينهار السيرفر، مع تسجيل تحذير واضح
في اللوقز يوضّح أن البيانات غير دائمة حتى تُضبَط القاعدة فعليًا.
"""
import os
import logging
import psycopg2

logger = logging.getLogger("sawti.db")

DATABASE_URL = os.getenv("DATABASE_URL", "")
_ready_tables: set[str] = set()


def is_configured() -> bool:
    return bool(DATABASE_URL)


def get_conn():
    """اتصال جديد بقاعدة البيانات. المتصل مسؤول عن إغلاقه (conn.close())."""
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL غير مضبوط")
    # sslmode=require مطلوب لمعظم مزوّدي Postgres السحابيين (مثل Supabase)
    return psycopg2.connect(DATABASE_URL, sslmode="require", connect_timeout=10)


def ensure_table(name: str, create_sql: str):
    """
    ينشئ الجدول إن لم يكن موجودًا، مرة واحدة فقط لكل عملية تشغيل للسيرفر
    (وليس عند كل طلب) لتفادي إبطاء الطلبات بلا داعٍ.
    """
    if name in _ready_tables or not DATABASE_URL:
        return
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(create_sql)
        conn.commit()
        _ready_tables.add(name)
        logger.info("Database: table '%s' ready", name)
    except Exception:
        logger.exception("Database: failed to ensure table '%s'", name)
        raise
    finally:
        conn.close()
