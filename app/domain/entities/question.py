"""Question / Option domain entities.

Pure Python — no SQLAlchemy imports (AD-1).

Invariant: a Question must have exactly one Option with `is_correct=True`.
It is not expressible as a simple DB constraint, so it is enforced in the
application layer (see T011's CreateQuestion use case) — `has_single_answer`
is provided here so the rule lives with the entity that owns it.
"""

from dataclasses import dataclass, field


@dataclass
class Option:
    id: int | None
    text: str
    is_correct: bool


@dataclass
class Question:
    id: int | None
    text: str
    image_url: str | None = None
    options: list[Option] = field(default_factory=list)

    def has_single_answer(self) -> bool:
        return sum(1 for o in self.options if o.is_correct) == 1

    def correct_option_id(self) -> int | None:
        for option in self.options:
            if option.is_correct:
                return option.id
        return None
