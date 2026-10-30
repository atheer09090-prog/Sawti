"""Isolated contracts: mocked provider output is never proof of a working AI provider."""
import json
import pytest
from app.routers import evaluation
from app.services.security import create_token


def stub_speech(monkeypatch):
    monkeypatch.setattr(evaluation, 'transcribe_arabic_audio_detailed', lambda *a, **k: {'whisper_text':'ذهب الولد إلى البحر', 'rules_text':'ذهب الولد إلى البحر'})
    monkeypatch.setattr(evaluation, 'correct_stt_errors', lambda text, **k: {'correctedText':text, 'corrections':[], 'status':'skipped_no_api_key'})
    seen={}
    def score(text, reference, lesson):
        seen.update(reference=reference, lesson=lesson)
        return {'transcript':text, 'overall':50}
    monkeypatch.setattr(evaluation, 'evaluate_speaking', score)
    return seen


def test_browser_multipart_preserves_activity_context(client, monkeypatch):
    seen=stub_speech(monkeypatch)
    token=create_token('audit-student')
    response=client.post('/api/eval/speech',headers={'Authorization':f'Bearer {token}'},
        data={'lesson_id':'opinion','reference_text':'القراءة','student_id':'0'},
        files={'audio_file':('recording.webm',b'\x1aE\xdf\xa3'+b'\0'*3000,'audio/webm')})
    assert response.status_code==200
    assert seen=={'reference':'القراءة','lesson':'opinion'}


def test_registration_rejects_passwords_over_bcrypt_byte_limit():
    from app.routers.auth import RegisterPayload
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        RegisterPayload(name='تدقيق',grade='السادس',email='audit@example.com',password='ع'*40)


def test_teacher_ignores_thought_parts_and_joins_answer_parts(monkeypatch):
    from app.services.ask_teacher import answer_student_question
    monkeypatch.setenv('GEMINI_API_KEY','isolated-test-key')
    class Response:
        def __enter__(self): return self
        def __exit__(self,*args): pass
        def read(self): return json.dumps({'candidates':[{'finishReason':'STOP','content':{'parts':[{'thought':True,'text':'private reasoning'},{'text':'هذه إجابة.'},{'text':'وهذا مثال.'}]}}]}).encode()
    monkeypatch.setattr('urllib.request.urlopen',lambda *args,**kwargs:Response())
    answer=answer_student_question('ما الجملة؟')
    assert answer=='هذه إجابة.\nوهذا مثال.'


def test_teacher_empty_success_is_service_failure(monkeypatch):
    from app.services.ask_teacher import answer_student_question, TeacherUnavailable
    monkeypatch.setenv('GEMINI_API_KEY','isolated-test-key')
    class Response:
        def __enter__(self): return self
        def __exit__(self,*args): pass
        def read(self): return b'{"candidates":[{"finishReason":"STOP","content":{"parts":[]}}]}'
    monkeypatch.setattr('urllib.request.urlopen',lambda *a,**k:Response())
    with pytest.raises(TeacherUnavailable): answer_student_question('ما الجملة؟')


def test_teacher_retries_temporary_overload_but_never_retries_bad_credentials(monkeypatch):
    import io, urllib.error
    from app.services import ask_teacher
    monkeypatch.setattr(ask_teacher.time, 'sleep', lambda _: None)
    calls=[]
    sentinel=object()
    def retrying(*args, **kwargs):
        calls.append(1)
        if len(calls)<3: raise urllib.error.HTTPError('https://provider.invalid',503,'busy',{},io.BytesIO(b'busy'))
        return sentinel
    monkeypatch.setattr(ask_teacher.urllib.request,'urlopen',retrying)
    assert ask_teacher._open_with_retry(object()) is sentinel
    assert len(calls)==3
    calls.clear()
    def invalid(*args, **kwargs):
        calls.append(1)
        raise urllib.error.HTTPError('https://provider.invalid',403,'invalid key',{},io.BytesIO(b'invalid'))
    monkeypatch.setattr(ask_teacher.urllib.request,'urlopen',invalid)
    with pytest.raises(urllib.error.HTTPError): ask_teacher._open_with_retry(object())
    assert len(calls)==1


def test_public_registration_cannot_claim_someone_elses_legacy_progress(client):
    r=client.post('/api/auth/register',json={'name':'مستخدم جديد','grade':'السادس','email':'legacy-audit@example.com','password':'secret123','legacy_name':'اسم معروف','legacy_grade':'السادس'})
    assert r.status_code==401
