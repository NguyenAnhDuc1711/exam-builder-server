from sqlalchemy.ext.asyncio import AsyncSession

from app.models.exam import ExamAssignment


class ExamAssignmentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, assignment_id: int) -> ExamAssignment | None:
        return await self._session.get(ExamAssignment, assignment_id)

    def add(self, assignment: ExamAssignment) -> None:
        self._session.add(assignment)
