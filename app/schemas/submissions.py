"""Request/response models for `/exams/{id}/submit` and `/submissions`."""

from datetime import datetime

from pydantic import BaseModel


class AnswerRequest(BaseModel):
    question_id: int
    selected_option_id: int | None = None


class SubmitExamRequest(BaseModel):
    answers: list[AnswerRequest]


class GradedAnswerResponse(BaseModel):
    question_id: int
    selected_option_id: int | None
    is_correct: bool


class SubmitExamResponse(BaseModel):
    submission_id: int
    score: int
    total_questions: int
    breakdown: list[GradedAnswerResponse]


class SubmissionResponse(BaseModel):
    id: int
    exam_assignment_id: int
    score: int
    total_questions: int
    submitted_at: datetime
    answers: list[GradedAnswerResponse]


class ExamSubmissionResponse(SubmissionResponse):
    user_id: int
