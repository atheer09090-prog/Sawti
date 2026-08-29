"""
تقييم سياق الجمل العربية باستخدام Gemini API
"""
import os
import json
import urllib.request


def evaluate_context(text: str) -> list:
    api_key = os.getenv("GEMINI_API_KEY", "")
    if not api_key or not text or len(text.strip()) < 10:
        return []

    prompt = """أنت مدرس لغة عربية. حلّل النص التالي وابحث عن أي من هذه المشاكل:

١. تأخير الفعل: مثل "كل غرفة تحتوي" → الأصح "تحتوي كل غرفة" (الفعل يتقدم على الفاعل في العربية الفصحى)
٢. تكرار غير مبرر للكلمات
٣. جمل طويلة يمكن تقسيمها
٤. استخدام "و" بشكل مفرط بدل أدوات ربط أوضح

مهم: يجب أن تجد اقتراحاً واحداً على الأقل إذا كان النص يحتوي على فعل مؤخر عن فاعله.

أعد JSON فقط بدون أي نص آخر:
[
  {
    "original": "العبارة كما في النص",
    "suggested": "العبارة المحسّنة",
    "rule": "سبب التحسين"
  }
]

النص: """ + text

    try:
        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"gemini-3.6-flash:generateContent?key={api_key}"
        )
        payload = json.dumps({
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.1, "maxOutputTokens": 800,
                "thinkingConfig": {"thinkingBudget": 0},
            },
        }).encode("utf-8")

        req = urllib.request.Request(
            url, data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            raw = data["candidates"][0]["content"]["parts"][0]["text"].strip()
            raw = raw.replace("```json", "").replace("```", "").strip()
            result = json.loads(raw)
            return result if isinstance(result, list) else []
    except Exception:
        return []
