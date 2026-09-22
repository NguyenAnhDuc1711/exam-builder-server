"""Input sanitization: HTML-escape free-text fields to prevent stored XSS."""

from app.core.sanitize import sanitize_text
from app.schemas.exams import CreateExamRequest
from app.schemas.questions import OptionSchema


def test_sanitize_text_escapes_html_special_characters():
    assert sanitize_text("<script>alert(1)</script>") == (
        "&lt;script&gt;alert(1)&lt;/script&gt;"
    )


def test_option_schema_sanitizes_text():
    option = OptionSchema(text="<img src=x onerror=alert(1)>", is_correct=True)

    assert option.text == "&lt;img src=x onerror=alert(1)&gt;"


def test_create_exam_request_sanitizes_title():
    exam = CreateExamRequest(title="<b>Midterm</b>", question_ids=[1, 2])

    assert exam.title == "&lt;b&gt;Midterm&lt;/b&gt;"
