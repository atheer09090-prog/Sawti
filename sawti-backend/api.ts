// client/src/lib/api.ts
// ربط منصة صوتي قلمي بالـ Backend

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000/api";

// ==============================
// تقييم التحدث
// ==============================
export async function evaluateSpeech(
  audioBlob: Blob,
  referenceText?: string,
  studentId: number = 0,
  lessonId: string = ""
) {
  const formData = new FormData();
  formData.append("audio_file", audioBlob, "recording.wav");
  formData.append("student_id", String(studentId));
  formData.append("lesson_id", lessonId);
  if (referenceText) formData.append("reference_text", referenceText);

  const res = await fetch(`${API_BASE}/eval/speech`, {
    method: "POST",
    body: formData,
  });

  if (!res.ok) throw new Error(`خطأ في تقييم التحدث: ${res.status}`);
  return res.json();
}

// ==============================
// تقييم الكتابة
// ==============================
export async function evaluateWriting(
  text: string,
  minWords: number = 20,
  studentId: number = 0,
  lessonId: string = ""
) {
  const res = await fetch(`${API_BASE}/eval/writing`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      student_id: studentId,
      lesson_id: lessonId,
      text,
      min_words: minWords,
    }),
  });

  if (!res.ok) throw new Error(`خطأ في تقييم الكتابة: ${res.status}`);
  return res.json();
}

// ==============================
// توليد تقرير PDF
// ==============================
export async function generateStudentReport(studentData: {
  name: string;
  grade: string;
  speaking_progress: number;
  writing_progress: number;
  self_learning_progress: number;
  teacher_comment?: string;
  points?: number;
  stars?: number;
}) {
  const res = await fetch(`${API_BASE}/reports/student`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(studentData),
  });

  if (!res.ok) throw new Error(`خطأ في توليد التقرير: ${res.status}`);

  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `تقرير_${studentData.name}.pdf`;
  a.click();
  URL.revokeObjectURL(url);
}

// ==============================
// فحص حالة الخادم
// ==============================
export async function checkHealth(): Promise<boolean> {
  try {
    const res = await fetch(`${API_BASE}/health`);
    return res.ok;
  } catch {
    return false;
  }
}
