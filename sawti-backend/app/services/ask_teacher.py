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

    # تعليمات صارمة ومباشرة — التجربة أظهرت أن النموذج قد يفتح بمقدمات
    # حماسية طويلة، أو يقطع الجملة الأخيرة، أو يُسرّب كلمات إنجليزية/
    # ملاحظات جانبية عن طريقة تفكيره داخل الإجابة نفسها. هذه القواعد
    # مكتوبة صراحة لمنع كل واحدة من هذه المشاكل تحديدًا.
    prompt = (
        "أنت \"المعلم الذكي\" في منصة تعليمية للغة العربية لطلاب الصف السادس "
        "(حوالي 11-12 سنة). مهمتك الإجابة المباشرة عن سؤال الطالب المتعلق "
        "باللغة العربية (نحو، إملاء، معنى كلمة، أو أي موضوع دراسي مشابه).\n\n"
        "قواعد صارمة يجب الالتزام بها دائمًا:\n"
        "1. ابدأ إجابتك مباشرة بالمعلومة المطلوبة — بلا أي تحية أو مقدمة أو "
        "عبارات ترحيبية مثل \"أهلاً بك يا بطل\" أو ما شابه.\n"
        "2. اكتب بالعربية الفصحى المبسّطة فقط، ولا تكتب ولا كلمة واحدة "
        "بالإنجليزية أو بأي لغة أخرى مهما كان السبب.\n"
        "3. لا تكتب أي ملاحظات عن نفسك أو عن طريقة تفكيرك (مثل \"دعني "
        "أفكر\" أو \"Wait\" أو أي تعليق جانبي) — فقط الإجابة النهائية "
        "المباشرة، بلا غيرها.\n"
        "4. اجعل إجابتك كاملة ومكتملة الجمل دائمًا مهما كانت قصيرة. لا تنهِ "
        "الإجابة في منتصف جملة أبدًا — إن لم تتّسع المساحة فاختصر الفكرة "
        "كاملة بدل قطعها.\n"
        "5. اذكر مثالاً واحدًا قصيرًا فقط إن كان يساعد على الفهم.\n"
        "6. لا تتجاوز إجابتك 3 إلى 4 جمل قصيرة إجمالًا.\n"
        "7. إذا كان السؤال غير مفهوم أو خارج نطاق اللغة العربية تمامًا، "
        "اطلب من الطالب إعادة صياغته بجملة واحدة فقط.\n\n"
        f"سؤال الطالب: {question}\n\n"
        "اكتب الآن الإجابة النهائية مباشرة (بلا أي مقدمات):"
    )

    try:
        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"gemini-3.6-flash:generateContent?key={api_key}"
        )
        payload = json.dumps({
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.2, "maxOutputTokens": 1024,
            },
        }).encode("utf-8")

        req = urllib.request.Request(
            url, data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read())
            candidate = data["candidates"][0]
            finish_reason = candidate.get("finishReason", "")
            if finish_reason and finish_reason not in ("STOP",):
                # يساعد هذا السطر على تشخيص أي قطع مستقبلي في الإجابة
                # (مثلاً MAX_TOKENS يعني أن الإجابة قُطعت لضيق المساحة)
                logger.warning("Gemini finishReason=%s for question: %s", finish_reason, question[:80])
            text = candidate["content"]["parts"][0]["text"].strip()
            return text
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
