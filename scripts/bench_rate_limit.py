"""Local latency benchmark script (T080, NFR-1 / SC-4).

Measures p95 latency before/after enabling rate limiting across 4 representative
endpoints:
1. POST /auth/login (auth group)
2. POST /questions (write group)
3. POST /exams/{assignment_id}/submit (submit group)
4. GET /questions (read group)

Also measures the Redis-down (circuit breaker + in-memory fallback) degraded path.
"""

import asyncio
import json
import time
from typing import Any
from unittest.mock import patch

from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.core import rate_limit as rate_limit_module
from app.core.security import hash_password
from app.main import app
from app.models.base import Base
from app.models.exam import Exam, ExamAssignment, ExamQuestion
from app.models.question import Option, Question
from app.models.user import User


def _percentile(values: list[float], p: float) -> float:
    """Calculate the p-th percentile (0-100) from a list of values."""
    if not values:
        return 0.0
    sorted_values = sorted(values)
    k = (len(sorted_values) - 1) * (p / 100.0)
    f = int(k)
    c = f + 1
    if c < len(sorted_values):
        return sorted_values[f] + (k - f) * (sorted_values[c] - sorted_values[f])
    return sorted_values[f]


async def _setup_benchmark_data(session: AsyncSession) -> dict[str, Any]:
    """Seed test users, questions, and assignments for benchmarking."""
    # 1. Users
    admin = await session.scalar(select(User).where(User.email == "bench_admin@example.com"))
    if not admin:
        admin = User(
            email="bench_admin@example.com",
            password_hash=hash_password("adminpass123"),
            role="admin",
        )
        session.add(admin)

    student = await session.scalar(select(User).where(User.email == "bench_student@example.com"))
    if not student:
        student = User(
            email="bench_student@example.com",
            password_hash=hash_password("studentpass123"),
            role="user",
        )
        session.add(student)

    await session.commit()
    await session.refresh(admin)
    await session.refresh(student)

    # 2. Questions
    q = Question(text="Benchmark Question Sample?", image_url=None)
    session.add(q)
    await session.flush()
    opt1 = Option(question_id=q.id, text="Option A", is_correct=True)
    opt2 = Option(question_id=q.id, text="Option B", is_correct=False)
    session.add_all([opt1, opt2])

    # 3. Create exams and assignments for submit benchmarking
    assignments = []
    for i in range(160):
        exam = Exam(title=f"Benchmark Exam {i}")
        session.add(exam)
        await session.flush()
        eq = ExamQuestion(exam_id=exam.id, question_id=q.id, order=0)
        session.add(eq)
        assignment = ExamAssignment(exam_id=exam.id, user_id=student.id)
        session.add(assignment)
        assignments.append(assignment)

    await session.commit()
    for a in assignments:
        await session.refresh(a)
    await session.refresh(q)
    await session.refresh(opt1)

    return {
        "admin": admin,
        "student": student,
        "question_id": q.id,
        "option_id": opt1.id,
        "assignment_ids": [a.id for a in assignments],
    }


async def run_benchmark(iterations: int = 50) -> None:
    print("=" * 70)
    print(f"Starting Rate Limiting Latency Benchmark ({iterations} iterations per run)...")
    print("=" * 70)

    # Set up engine & tables
    engine = create_async_engine(settings.DATABASE_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_maker() as session:
        data = await _setup_benchmark_data(session)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Obtain tokens
        res = await client.post(
            "/auth/login",
            json={"email": "bench_admin@example.com", "password": "adminpass123"},
        )
        admin_token = res.json()["access_token"]

        res = await client.post(
            "/auth/login",
            json={"email": "bench_student@example.com", "password": "studentpass123"},
        )
        student_token = res.json()["access_token"]

        admin_headers = {"Authorization": f"Bearer {admin_token}"}
        student_headers = {"Authorization": f"Bearer {student_token}"}

        # Benchmark targets
        benchmarks = [
            {
                "group": "auth",
                "name": "POST /auth/login",
                "method": "POST",
                "url": "/auth/login",
                "kwargs": {
                    "json": {
                        "email": "bench_student@example.com",
                        "password": "studentpass123",
                    }
                },
            },
            {
                "group": "write",
                "name": "POST /questions",
                "method": "POST",
                "url": "/questions",
                "kwargs": {
                    "data": {
                        "text": "Bench Question",
                        "options": json.dumps(
                            [{"text": "A", "is_correct": True}, {"text": "B", "is_correct": False}]
                        ),
                    },
                    "headers": admin_headers,
                },
            },
            {
                "group": "read",
                "name": "GET /questions",
                "method": "GET",
                "url": "/questions",
                "kwargs": {"headers": admin_headers},
            },
            {
                "group": "submit",
                "name": "POST /exams/{id}/submit",
                "method": "POST",
                "url_template": "/exams/{assignment_id}/submit",
                "kwargs": {
                    "json": {
                        "answers": [
                            {
                                "question_id": data["question_id"],
                                "selected_option_id": data["option_id"],
                            }
                        ]
                    },
                    "headers": student_headers,
                },
            },
        ]

        results = []
        assignment_idx = 0

        for bench in benchmarks:
            group = bench["group"]
            name = bench["name"]
            print(f"Benchmarking [{group.upper()}] {name}...")

            # 1. Baseline: RATE_LIMIT_ENABLED = False
            baseline_latencies = []
            with patch.object(settings, "RATE_LIMIT_ENABLED", False):
                for _ in range(iterations):
                    kwargs = dict(bench["kwargs"])
                    url = bench.get("url")
                    if "url_template" in bench:
                        url = bench["url_template"].format(
                            assignment_id=data["assignment_ids"][assignment_idx]
                        )
                        assignment_idx += 1

                    start = time.perf_counter()
                    if bench["method"] == "POST":
                        res = await client.post(url, **kwargs)
                    else:
                        res = await client.get(url, **kwargs)
                    dur_ms = (time.perf_counter() - start) * 1000.0
                    assert res.status_code in (200, 201), f"Unexpected status: {res.status_code}"
                    baseline_latencies.append(dur_ms)

            # 2. Limited (Redis Up): RATE_LIMIT_ENABLED = True, high limits
            limited_latencies = []
            with patch.object(settings, "RATE_LIMIT_ENABLED", True):
                with patch.object(settings, f"RATE_LIMIT_{group.upper()}_MAX", 100000):
                    rate_limit_module.reset_for_tests()
                    for _ in range(iterations):
                        kwargs = dict(bench["kwargs"])
                        url = bench.get("url")
                        if "url_template" in bench:
                            url = bench["url_template"].format(
                                assignment_id=data["assignment_ids"][assignment_idx]
                            )
                            assignment_idx += 1

                        start = time.perf_counter()
                        if bench["method"] == "POST":
                            res = await client.post(url, **kwargs)
                        else:
                            res = await client.get(url, **kwargs)
                        dur_ms = (time.perf_counter() - start) * 1000.0
                        assert res.status_code in (200, 201), f"Unexpected status: {res.status_code}"
                        limited_latencies.append(dur_ms)

            # 3. Degraded (Circuit Breaker open): trip breaker to test in-memory fallback
            degraded_latencies = []
            with patch.object(settings, "RATE_LIMIT_ENABLED", True):
                with patch.object(settings, f"RATE_LIMIT_{group.upper()}_MAX", 100000):
                    rate_limit_module.reset_for_tests()
                    rate_limit_module._redis_unavailable_until = time.monotonic() + 3600.0
                    for _ in range(iterations):
                        kwargs = dict(bench["kwargs"])
                        url = bench.get("url")
                        if "url_template" in bench:
                            url = bench["url_template"].format(
                                assignment_id=data["assignment_ids"][assignment_idx]
                            )
                            assignment_idx += 1

                        start = time.perf_counter()
                        if bench["method"] == "POST":
                            res = await client.post(url, **kwargs)
                        else:
                            res = await client.get(url, **kwargs)
                        dur_ms = (time.perf_counter() - start) * 1000.0
                        assert res.status_code in (200, 201), f"Unexpected status: {res.status_code}"
                        degraded_latencies.append(dur_ms)

            rate_limit_module.reset_for_tests()

            b_p95 = _percentile(baseline_latencies, 95)
            l_p95 = _percentile(limited_latencies, 95)
            d_p95 = _percentile(degraded_latencies, 95)
            delta_p95 = l_p95 - b_p95

            results.append(
                {
                    "group": group,
                    "endpoint": name,
                    "baseline_p95": b_p95,
                    "limited_p95": l_p95,
                    "delta_p95": delta_p95,
                    "degraded_p95": d_p95,
                    "pass": delta_p95 < 5.0,
                }
            )

    await engine.dispose()

    # Print summary table
    print("\n" + "=" * 80)
    print("BENCHMARK RESULTS SUMMARY (NFR-1 / SC-4: Delta p95 Target < 5.0 ms)")
    print("=" * 80)
    print(
        f"| {'Group':<8} | {'Endpoint':<30} | {'Baseline p95':<12} | {'Limited p95':<12} | {'Delta p95':<10} | {'Degraded p95':<12} | {'Status':<6} |"
    )
    print(
        f"|{'-'*10}|{'-'*32}|{'-'*14}|{'-'*14}|{'-'*12}|{'-'*14}|{'-'*8}|"
    )
    for r in results:
        status_str = "PASS" if r["pass"] else "WARN"
        print(
            f"| {r['group']:<8} | {r['endpoint']:<30} | {r['baseline_p95']:>10.2f}ms | {r['limited_p95']:>10.2f}ms | {r['delta_p95']:>8.2f}ms | {r['degraded_p95']:>10.2f}ms | {status_str:<6} |"
        )
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(run_benchmark())
