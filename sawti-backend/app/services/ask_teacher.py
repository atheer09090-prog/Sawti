"""
مُعَلِّمٌ ذَكِيٌّ مُسَاعِدٌ يُجِيبُ عَنْ أَسْئِلَةِ الطَّالِبِ الْمُتَعَلِّقَةِ بِاللُّغَةِ الْعَرَبِيَّةِ
(إملاء، قواعد، معنى كلمة...)، ضمن نشاط "🤖 اسأل بذكاء" في قسم التعلم
الذاتي. الهدف ليس فقط الإجابة، بل تشجيع الطالب على صياغة سؤال واضح
ومحدد، فالإجابة تبقى موجزة ومبسّطة بدل إعطاء شرح أكاديمي طويل.
"""
import os
import json
import logging
import urllib.request
import urllib.error

logger = logging.getLogger("ask_teacher")

MAX_QUESTION_LEN = 300


def answer_student_question(question: str) -> str:
    question = (question or "").strip()
    if not question:
        return "اكْتُبْ سُؤَالَكَ أَوَّلًا حَتَّى أَسْتَطِيعَ مُسَاعَدَتَكَ 🌱"
    if len(question) > MAX_QUESTION_LEN:
        question = question[:MAX_QUESTION_LEN]

    api_key = os.getenv("GEMINI_API_KEY", "")
    if not api_key:
        return "عُذْرًا، الْمُعَلِّمُ الذَّكِيُّ غَيْرُ مُتَاحٍ حَالِيًّا. حَاوِلْ مَرَّةً أُخْرَى لَاحِقًا."

    prompt = (
        "أنت معلم لغة عربية مساعد لطلاب المرحلة الابتدائية (حوالي 11-12 سنة). "
        "سيسألك الطالب سؤالاً عن اللغة العربية (إملاء، قواعد، معنى كلمة، أو أي شيء "
        "متعلق بالمادة). أجب بإيجاز ووضوح بلغة عربية فصيحة مبسّطة تناسب عمره، "
        "بأسلوب مشجّع ودافئ كأنك تكلّم طالبك مباشرة، واذكر مثالاً واحدًا قصيراً "
        "يوضّح الفكرة. لا تتجاوز إجابتك 4 جمل قصيرة، ولا تستخدم رموزاً أو تنسيقاً "
        "معقّداً. إذا كان السؤال خارج نطاق اللغة العربية تمامًا أو غير مفهوم، "
        "وجّهه بلطف لإعادة صياغة سؤاله أو سؤال معلمه.\n\n"
        f"سؤال الطالب: {question}"
    )

    try:
        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"gemini-3.6-flash:generateContent?key={api_key}"
        )
        payload = json.dumps({
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.4, "maxOutputTokens": 800,
            },
        }).encode("utf-8")

        req = urllib.request.Request(
            url, data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read())
            return data["candidates"][0]["content"]["parts"][0]["text"].strip()
    except urllib.error.HTTPError as e:
        # هذا يكشف السبب الحقيقي غالبًا: مفتاح API غير صالح (403)،
        # أو تجاوز الحصة (429)، أو اسم نموذج غير موجود (404)، إلخ.
        # راجع سجلّات Render لرؤية النص الكامل القادم من Google.
        body = e.read().decode("utf-8", errors="replace") if hasattr(e, "read") else ""
        logger.error("Gemini HTTPError %s: %s", e.code, body[:500])
        return "تَعَذَّرَ الِاتِّصَالُ بِالْمُعَلِّمِ الذَّكِيِّ الْآنَ. حَاوِلْ مَرَّةً أُخْرَى بَعْدَ قَلِيلٍ 🌱"
    except Exception as e:
        logger.error("Gemini request failed: %s: %s", type(e).__name__, e)
        return "تَعَذَّرَ الِاتِّصَالُ بِالْمُعَلِّمِ الذَّكِيِّ الْآنَ. حَاوِلْ مَرَّةً أُخْرَى بَعْدَ قَلِيلٍ 🌱"
