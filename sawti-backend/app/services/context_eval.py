"""
تقييم سياق الجمل العربية باستخدام Gemini API
يكتشف مشاكل الترتيب والأسلوب ويقترح تحسينات
"""
import os
import json
import urllib.request


def evaluate_context(text: str) -> list:
    """
    يحلل النص ويعيد قائمة اقتراحات سياقية
    كل اقتراح: { original, suggested, rule }
    """
    api_key = os.getenv("GEMINI_API_KEY", "")
    if not api_key or not text or len(text.strip()) < 10:
        return []

    prompt = """أنت مدرس لغة عربية متخصص في تقييم كتابة طلاب الصف السادس.

حلّل النص التالي وابحث عن مشاكل أسلوبية ونحوية مثل:
- تقديم الخبر على المبتدأ (مثل: "كل غرفة تحتوي" → الأفضل "تحتوي كل غرفة")
- تكرار الكلمات غير المبرر
- جمل ناقصة أو غير مكتملة
- ترتيب الكلمات الخاطئ

أعد النتيجة بصيغة JSON فقط، بدون أي نص خارجه، كالتالي:
[
  {
    "original": "الجملة أو العبارة الأصلية كما وردت في النص",
    "suggested": "الصياغة الأفضل",
    "rule": "القاعدة النحوية أو الأسلوبية باختصار"
  }
]

إذا لم توجد مشاكل أسلوبية، أعد: []
لا تذكر أخطاء إملائية (همزة، تاء مربوطة...) فقط الأسلوب والترتيب.
اقتصر على أهم 3 ملاحظات فقط.

النص:
""" + text

    try:
        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"gemini-2.0-flash:generateContent?key={api_key}"
        )
        payload = json.dumps({
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.1, "maxOutputTokens": 512},
        }).encode("utf-8")

        req = urllib.request.Request(
            url, data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            raw = data["candidates"][0]["content"]["parts"][0]["text"].strip()
            # نظّف الـ JSON
            raw = raw.replace("```json", "").replace("```", "").strip()
            result = json.loads(raw)
            return result if isinstance(result, list) else []
    except Exception:
        return []
