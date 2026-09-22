"""SC-2 — auto-grading is 100% correct against a known answer-key fixture.

`grade` is a pure function (no session, no I/O), so this is a true unit
test: the fixture below *is* the answer key.

Unexecuted (no Python available in the authoring environment).
"""

from app.services.submit_exam import AnswerInput, grade

# The answer key: question_id -> id of that question's correct Option.
# Insertion order is the exam's question order, which `grade` preserves.
ANSWER_KEY: dict[int, int | None] = {
    11: 101,  # correct option 101, distractor 102
    22: 201,  # correct option 201, distractor 202
    33: 301,  # correct option 301, distractor 302
}


def test_all_correct_scores_every_question():
    graded = grade(
        ANSWER_KEY,
        [
            AnswerInput(question_id=11, selected_option_id=101),
            AnswerInput(question_id=22, selected_option_id=201),
            AnswerInput(question_id=33, selected_option_id=301),
        ],
    )

    assert [g.is_correct for g in graded] == [True, True, True]
    assert sum(g.is_correct for g in graded) == 3


def test_all_wrong_scores_nothing():
    graded = grade(
        ANSWER_KEY,
        [
            AnswerInput(question_id=11, selected_option_id=102),
            AnswerInput(question_id=22, selected_option_id=202),
            AnswerInput(question_id=33, selected_option_id=302),
        ],
    )

    assert [g.is_correct for g in graded] == [False, False, False]


def test_mixed_payload_matches_the_key_exactly():
    graded = grade(
        ANSWER_KEY,
        [
            AnswerInput(question_id=11, selected_option_id=101),  # right
            AnswerInput(question_id=22, selected_option_id=202),  # wrong
            AnswerInput(question_id=33, selected_option_id=301),  # right
        ],
    )

    assert [(g.question_id, g.is_correct) for g in graded] == [
        (11, True),
        (22, False),
        (33, True),
    ]
    assert sum(g.is_correct for g in graded) == 2


def test_grading_matches_by_question_id_not_by_position():
    """The payload is deliberately shuffled relative to the exam order."""
    graded = grade(
        ANSWER_KEY,
        [
            AnswerInput(question_id=33, selected_option_id=301),  # right
            AnswerInput(question_id=11, selected_option_id=101),  # right
            AnswerInput(question_id=22, selected_option_id=201),  # right
        ],
    )

    # Breakdown still comes back in exam order...
    assert [g.question_id for g in graded] == [11, 22, 33]
    # ...and every answer is credited to its own question, not to the one
    # sitting at the same index in the payload.
    assert all(g.is_correct for g in graded)


def test_unanswered_question_is_never_correct():
    graded = grade(
        ANSWER_KEY,
        [
            AnswerInput(question_id=11, selected_option_id=101),
            AnswerInput(question_id=22, selected_option_id=None),  # explicit skip
            # question 33 omitted from the payload entirely
        ],
    )

    by_id = {g.question_id: g for g in graded}
    assert by_id[11].is_correct is True
    assert by_id[22].is_correct is False and by_id[22].selected_option_id is None
    assert by_id[33].is_correct is False and by_id[33].selected_option_id is None
    # A missing question still produces a breakdown row: one Answer row per
    # exam question, always.
    assert len(graded) == 3
    assert sum(g.is_correct for g in graded) == 1


def test_answers_outside_the_exam_are_ignored():
    """Extra ids cannot inflate the score or add breakdown rows."""
    graded = grade(
        ANSWER_KEY,
        [
            AnswerInput(question_id=11, selected_option_id=101),
            AnswerInput(question_id=999, selected_option_id=9001),
        ],
    )

    assert [g.question_id for g in graded] == [11, 22, 33]
    assert sum(g.is_correct for g in graded) == 1


def test_question_with_no_correct_option_is_never_correct():
    graded = grade(
        {11: None},
        [AnswerInput(question_id=11, selected_option_id=101)],
    )

    assert graded[0].is_correct is False
    # A `None` selection against a `None` key must not compare equal either.
    assert grade({11: None}, [AnswerInput(11, None)])[0].is_correct is False


def test_empty_exam_produces_empty_breakdown():
    assert grade({}, [AnswerInput(question_id=11, selected_option_id=101)]) == []
