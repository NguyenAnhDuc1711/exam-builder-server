"""Request/response models for `/exams`."""

from pydantic import BaseModel, Field


class CreateExamRequest(BaseModel):
    title: str = Field(max_length=255)
    question_ids: list[int]


class ExamQuestionResponse(BaseModel):
    question_id: int
    order: int

    model_config = {"from_attributes": True}


class ExamResponse(BaseModel):
    id: int
    title: str
    exam_questions: list[ExamQuestionResponse]

    model_config = {"from_attributes": True}


class AssignExamRequest(BaseModel):
    user_id: int


class ExamAssignmentResponse(BaseModel):
    id: int
    exam_id: int
    user_id: int

    model_config = {"from_attributes": True}
