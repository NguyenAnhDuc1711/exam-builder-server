---
name: exam-builder-base
status: backlog
progress: 0%
created: 2026-09-21T09:15:38Z
updated: 2026-09-21T09:22:14Z
prd: exam-builder-base
github: ""
---

# Epic: exam-builder-base

## Overview

Base backend cho hệ thống giao đề trắc nghiệm + chấm điểm tự động, xây theo Modular/Clean Architecture (domain/application/infrastructure/api) trên FastAPI + PostgreSQL/SQLAlchemy/Alembic + JWT + Docker Compose. Kiến trúc tách domain khỏi persistence qua repository pattern để tenant-scoping hoặc mở rộng sau này (multi-select, chấm AI) chỉ động vào infrastructure layer, không viết lại business logic — đúng cam kết trong Product Brief. Toàn bộ 7 FR bắt buộc được nhóm theo 3 phase: nền tảng (auth+schema) → tính năng lõi song song (question bank, exam assembly, quản lý user) → tích hợp (giao đề, nộp bài, xem kết quả), giữ mỗi task độc lập test được và ≤2 ngày.

## Architecture Decisions

### AD-1: Cấu trúc thư mục Clean Architecture
Context: PRD deferred quyết định cấu trúc thư mục cụ thể sang giai đoạn epic (open question #1 từ Product Brief).
Decision:
```
app/
  domain/
    entities/        # User, Question, Option, Exam, ExamAssignment, Submission, Answer — dataclass thuần, không phụ thuộc ORM
    repositories/     # abstract repository interfaces (Protocol)
  application/
    use_cases/         # CreateQuestion, AssembleExam, AssignExam, SubmitExam, GetResults, CreateUser, Login, RefreshToken
    ports/               # ImageStoragePort, TokenServicePort (interface cho infrastructure implement)
  infrastructure/
    db/
      models/            # SQLAlchemy ORM models
      repositories/      # implement domain repository interfaces bằng SQLAlchemy
      session.py
    auth/jwt_service.py    # implement TokenServicePort
    storage/cloudinary_service.py  # implement ImageStoragePort
  api/
    v1/routers/            # auth, users, questions, exams, submissions
    v1/schemas/             # Pydantic request/response
    dependencies.py          # get_current_user, require_role
  core/config.py, security.py
alembic/                      # migrations ở top-level theo chuẩn Alembic
docker-compose.yml
tests/unit/, tests/integration/
```
Alternatives rejected: Flat layered (routers→services→models trực tiếp) — đã cân nhắc ở office-hours nhưng bị loại vì không tách được domain khỏi SQLAlchemy, khó test business logic độc lập.
Trade-off: Nhiều boilerplate hơn (interface + implementation riêng biệt) đổi lấy khả năng thay đổi persistence/storage provider mà không đụng use_cases.
Reversibility: Hard — đổi cấu trúc thư mục giữa chừng epic sẽ tốn công refactor toàn bộ import paths.

### AD-2: JWT với refresh token rotation
Context: FR-1 yêu cầu access (1 ngày) + refresh (1 tuần) với rotation và reuse detection.
Decision: Bảng `refresh_tokens` (user_id, token_hash, family_id, revoked, expires_at). Refresh token KHÔNG lưu plaintext — chỉ lưu hash (SHA-256). Khi refresh: verify hash → nếu revoked=true (đã dùng rồi) → revoke toàn bộ family_id đó (reuse detection) → 401. Nếu hợp lệ → revoke token cũ, issue cặp mới cùng family_id.
Alternatives rejected: Stateless refresh (không lưu DB, chỉ dựa vào JWT exp) — bị loại vì không thể revoke hay detect reuse, vi phạm thẳng NFR-1.
Trade-off: Thêm 1 bảng + write mỗi lần refresh, đổi lấy khả năng phát hiện token bị đánh cắp (R-2 trong PRD).
Reversibility: Easy — đổi thuật toán hash hoặc thời hạn không ảnh hưởng schema logic khác.

### AD-3: Cloudinary sau ImageStoragePort interface
Context: FR-3 cần upload ảnh qua Cloudinary nhưng NFR-2 yêu cầu lỗi upload không chặn tạo câu hỏi.
Decision: Định nghĩa `ImageStoragePort.upload(file) -> url | UploadError` ở application layer; `CloudinaryImageStorage` implement ở infrastructure. Use case `CreateQuestion` catch `UploadError`, vẫn lưu câu hỏi với `image_url=None`, trả warning trong response.
Alternatives rejected: Gọi Cloudinary SDK trực tiếp trong route handler — bị loại vì khó mock trong test (NFR-2/SC-4 yêu cầu test lỗi Cloudinary).
Trade-off: Thêm 1 abstraction layer cho 1 provider duy nhất — chấp nhận được vì đổi lấy testability.
Reversibility: Easy — đổi provider ảnh sau này chỉ cần implement lại port.

### AD-4: Chấm điểm đồng bộ, không dùng task queue
Context: Tier-2 skepticism từ prd-rethink đã loại async task queue (Celery/RQ) cho việc chấm điểm.
Decision: `SubmitExam` use case tính điểm ngay trong request-response cycle — so sánh `selected_option_id` với `correct_option_id` của từng câu.
Alternatives rejected: Background job chấm điểm — bị loại vì so sánh option_id là phép tính O(N) tức thời, không cần async.
Trade-off: Không có, đây là lựa chọn thuần giảm complexity.
Reversibility: Easy — nếu sau này có chấm tự luận nặng hơn, có thể thêm queue riêng cho luồng đó mà không đổi luồng trắc nghiệm.

## Technical Approach

- **Auth (FR-1):** `app/api/v1/routers/auth.py` — `/login`, `/refresh`. `app/infrastructure/auth/jwt_service.py` dùng `python-jose` hoặc `PyJWT`. Password hash bằng `passlib[bcrypt]`.
- **Admin User Management (FR-2):** `app/api/v1/routers/users.py` — `POST /users` giới hạn `require_role("admin")` qua dependency ở `app/api/dependencies.py`.
- **Question Bank (FR-3):** `app/api/v1/routers/questions.py`, model `Question`/`Option` ở `app/infrastructure/db/models/question.py`.
- **Exam Assembly (FR-4):** `app/api/v1/routers/exams.py`, bảng liên kết `exam_question(exam_id, question_id, order)`.
- **Exam Assignment (FR-5):** bảng `exam_assignment(exam_id, user_id, assigned_at)`, endpoint `POST /exams/{id}/assign`.
- **Submission + Grading (FR-6):** `app/application/use_cases/submit_exam.py`, bảng `submission`/`answer`, unique constraint `(exam_assignment_id)` để enforce single-attempt.
- **Results (FR-7):** `GET /submissions/{id}` (user, chỉ bài của mình), `GET /exams/{id}/submissions` (admin, toàn bộ).
- **Docker Compose (NFR-4):** service `api`, `postgres`, `pgadmin`; `api` depends_on postgres healthcheck; volume cho postgres data.

## Traceability Matrix

| PRD Requirement | Epic Coverage | Task(s) | Verification |
|---|---|---|---|
| FR-1: Auth + refresh rotation | AD-2, Technical Approach §Auth | T003 | Security test (SC-3) |
| FR-2: Admin user management | Technical Approach §Admin | T010 | Integration test (SC-6) |
| FR-3: Question bank + image | AD-3, Technical Approach §Question Bank | T011 | Integration test (SC-4) + upload validation test (WARN-3) |
| FR-4: Exam assembly | Technical Approach §Exam Assembly | T012 | Integration test (SC-1) + invalid-question-id test (WARN-1) |
| FR-5: Exam assignment | Technical Approach §Assignment | T012 | Integration test (SC-1) |
| FR-6: Submission + auto-grading | AD-4, Technical Approach §Submission | T020 | Unit test (SC-2) + transaction-rollback test (CRIT-1) + double-submit 409 test (WARN-2) |
| FR-7: Results viewing | Technical Approach §Results | T020 | Integration test (SC-7) + cross-user access-denied test (CRIT-2) + N+1 query-count test (WARN-4) |
| NFR-1: Token rotation security | AD-2 | T003 | Security test (SC-3) |
| NFR-2: Cloudinary failure tolerance | AD-3 | T011 | Integration test (SC-4) |
| NFR-3: Single-tenant | AD-1 (schema review) | T002 | Schema review (no org_id) |
| NFR-4: Docker Compose deploy | Technical Approach §Docker | T001 | Smoke test (SC-5) |
| NTH-1..NTH-5 | Deferred | — | — |

*Task numbering updated post plan-review (see `plan-review.md` RED-1): T012 now covers assembly+assignment (was T012+T020); T020 now covers submission+grading+results (was T021+T022). Old T021/T022 IDs retired.*

## Implementation Strategy

**Phase 1 — Foundation (critical path):** Scaffolding, schema, auth. Không thể song song vì mọi thứ khác phụ thuộc DB models + JWT middleware. Exit: `docker-compose up` chạy được, login/refresh hoạt động, migration áp dụng thành công.

**Phase 2 — Core features:** T010 (admin user mgmt) và T011 (question bank) chạy song song, chỉ phụ thuộc T003. T012 (exam assembly + assignment, đã gộp theo plan-review RED-1) phụ thuộc thêm T010 vì assignment cần user đã tồn tại — không còn full-parallel với T010 nhưng vẫn tách biệt T011. Exit: CRUD đầy đủ cho question/exam/user, ảnh upload qua Cloudinary hoạt động kèm fallback lỗi, giao đề tường minh hoạt động.

**Phase 3 — Integration:** T020 (submission + grading + results, đã gộp theo plan-review RED-1), tuần tự vì phụ thuộc T012. Exit: luồng end-to-end (tạo câu hỏi → ghép đề → giao đề → nộp bài → xem kết quả) chạy được qua API, kèm transaction-safety (CRIT-1) và access-control boundary (CRIT-2) đã đóng.

## Task Breakdown (enriched preview)

##### T001: Project scaffolding + Docker Compose + Alembic init
- Phase: 1 | Parallel: no | Est: 1d | Depends: — | Complexity: simple
- What: Tạo cấu trúc thư mục theo AD-1, `docker-compose.yml` (api+postgres+pgadmin), `Dockerfile`, `alembic init`, `core/config.py` (Pydantic Settings đọc env: DB_URL, JWT secrets, CLOUDINARY credentials).
- Key files: `docker-compose.yml`, `Dockerfile`, `alembic.ini`, `app/core/config.py`
- PRD requirements: NFR-4
- Key risk: Sai network/env config giữa các service khiến `api` không kết nối được `postgres`.
- Interface produces: skeleton project mà mọi task sau import vào.

##### T002: Domain entities + SQLAlchemy models + initial migration
- Phase: 1 | Parallel: no | Est: 2d | Depends: T001 | Complexity: complex
- What: Định nghĩa domain entities (dataclass) + SQLAlchemy models cho User, Question, Option, Exam, ExamQuestion, ExamAssignment, Submission, Answer, RefreshToken. Viết migration Alembic đầu tiên.
- Key files: `app/domain/entities/*.py`, `app/infrastructure/db/models/*.py`, `alembic/versions/0001_initial.py`
- PRD requirements: NFR-3 (schema review — không có org_id)
- Key risk: Thiếu constraint (vd unique `exam_assignment_id` trên submission) dẫn đến vi phạm single-attempt ở FR-6 sau này.
- Interface produces: ORM models + migration mà T003/T010/T011/T012 đều import.

##### T003: Auth — JWT access/refresh + rotation + reuse detection
- Phase: 1 | Parallel: no | Est: 2d | Depends: T002 | Complexity: complex
- What: `jwt_service.py` implement TokenServicePort, endpoint `/login` `/refresh`, `require_role` dependency, bảng `refresh_tokens` lưu hash theo AD-2.
- Key files: `app/infrastructure/auth/jwt_service.py`, `app/api/v1/routers/auth.py`, `app/api/dependencies.py`
- PRD requirements: FR-1, NFR-1
- Key risk: Lưu nhầm plaintext token thay vì hash — lỗ hổng bảo mật nghiêm trọng (R-6).
- Interface produces: `get_current_user`, `require_role(role)` dependencies dùng bởi mọi router Phase 2/3.

##### T010: Admin user management
- Phase: 2 | Parallel: yes | Est: 1d | Depends: T003 | Complexity: simple
- What: `POST /users` (admin-only, tạo tài khoản role=user), không có route đăng ký công khai.
- Key files: `app/api/v1/routers/users.py`, `app/application/use_cases/create_user.py`
- PRD requirements: FR-2
- Key risk: Quên áp `require_role("admin")` khiến user thường tạo được tài khoản khác.
- Interface receives from T003: `require_role` dependency.

##### T011: Question bank CRUD + Cloudinary image upload
- Phase: 2 | Parallel: yes | Est: 2d | Depends: T003 | Complexity: moderate
- What: `POST/GET /questions` (text + đúng 1 đáp án đúng), `ImageStoragePort`/`CloudinaryImageStorage` theo AD-3, catch `UploadError` không chặn tạo câu hỏi. **(WARN-3 fix)** Validate MIME-type (chỉ image/png, image/jpeg, image/webp) và giới hạn kích thước file (ví dụ ≤5MB) TRƯỚC khi gọi Cloudinary — reject 400 nếu sai định dạng/quá lớn.
- Key files: `app/api/v1/routers/questions.py`, `app/application/ports/image_storage.py`, `app/infrastructure/storage/cloudinary_service.py`
- PRD requirements: FR-3, NFR-2
- Key risk: Không mock được Cloudinary trong test nếu gọi SDK trực tiếp thay vì qua port.
- Interface receives from T003: `require_role` dependency.
- Tests to write: happy path text-only; happy path + ảnh hợp lệ; Cloudinary lỗi → fallback không ảnh (SC-4); file sai MIME-type → 400 (WARN-3); file quá kích thước → 400 (WARN-3).

##### T012: Exam assembly + assignment
- Phase: 2 | Parallel: no | Est: 2d | Depends: T003, T010 | Complexity: moderate
- What: `POST /exams` nhận danh sách question_id có thứ tự, lưu vào `exam_question`. `POST /exams/{id}/assign` gán exam cho user cụ thể, tạo bản ghi `exam_assignment`. **(WARN-1 fix)** Validate mọi question_id tồn tại trong ngân hàng trước khi ghép — reject 404 với danh sách question_id không tìm thấy nếu có. Validate user_id tồn tại và chưa được gán đề đó trước khi assign — reject 404/409 tương ứng.
- Key files: `app/api/v1/routers/exams.py`, `app/application/use_cases/assemble_exam.py`, `app/application/use_cases/assign_exam.py`
- PRD requirements: FR-4, FR-5
- Key risk: Gán trùng (cùng exam+user) — chặn bằng unique constraint DB (T002) + check tường minh ở use case.
- Interface receives from T003: `require_role` dependency. Interface receives from T010: user đã tồn tại trong DB để assign.
- Interface produces: `exam_assignment_id` dùng làm khóa cho T020.
- Tests to write: ghép đề thành công; ghép đề với question_id không tồn tại → 404 (WARN-1); assign thành công; assign trùng → 409.

##### T020: Submission + auto-grading + results
- Phase: 3 | Parallel: no | Est: 3d | Depends: T012 | Complexity: complex
- What: `POST /exams/{assignment_id}/submit` nhận đáp án, so khớp `correct_option_id`, tính điểm, lưu `submission`+`answer`. **(CRIT-1 fix)** Toàn bộ insert Submission + Answer(s) bọc trong MỘT DB transaction (`session.begin()` / `async with session.begin()`) — rollback toàn bộ nếu bất kỳ insert nào lỗi, không để lại state một phần. **(WARN-2 fix)** Catch `IntegrityError` từ unique constraint (single-attempt) và trả 409 "already submitted" thay vì để lộ 500 thô. `GET /submissions/{id}` (user xem bài của mình), `GET /exams/{id}/submissions` (admin xem toàn bộ), trả điểm + breakdown đúng/sai từng câu. **(CRIT-2 fix)** Bắt buộc kiểm tra `submission.user_id == current_user.id` cho role `user` trước khi trả dữ liệu — 403 nếu không khớp và role không phải admin. **(WARN-4 fix)** Dùng SQLAlchemy `selectinload`/`joinedload` cho endpoint list-submissions, kèm test khẳng định số lượng query không tăng theo O(N).
- Key files: `app/application/use_cases/submit_exam.py`, `app/application/use_cases/get_results.py`, `app/api/v1/routers/submissions.py`
- PRD requirements: FR-6, FR-7
- Key risk: Race condition khi 2 request submit cùng lúc — DB unique constraint là nguồn sự thật cuối cùng, application-layer check chỉ là UX nhanh.
- Interface receives from T012: `exam_assignment_id` hợp lệ và thuộc về user hiện tại.
- Tests to write: chấm điểm đúng theo fixture (SC-2); rollback khi insert Answer lỗi giữa chừng (CRIT-1); double-submit → 409 sạch (WARN-2); user A gọi `GET /submissions/{id}` của user B → 403 (CRIT-2); admin gọi cùng endpoint → 200 (không bị chặn bởi check của CRIT-2); query-count không tăng tuyến tính khi list N submissions (WARN-4).

##### T090: Verification (mandatory, final)
- Phase: final | Parallel: no | Est: 1d | Depends: T001, T002, T003, T010, T011, T012, T020 | Complexity: moderate
- What: Chạy toàn bộ test suite, `docker-compose up` smoke test, kiểm tra từng AC trong Traceability Matrix, xác nhận không còn TODO/FIXME trong code.
- Key files: `tests/integration/test_e2e_flow.py`
- PRD requirements: Tất cả FR/NFR (verification tổng)
- Key risk: Bỏ sót 1 AC không có test tương ứng.
- Interface receives from tất cả: toàn bộ API đã implement.

## Risks

| # | Risk | Severity | Likelihood | Mitigation |
|---|------|----------|------------|------------|
| R-1 | Cloudinary outage/lỗi cấu hình chặn luồng tạo câu hỏi có ảnh | Medium | Low | AD-3 — ImageStoragePort cô lập lỗi, question creation vẫn thành công không ảnh |
| R-2 | Refresh token rotation cài sai gây khóa nhầm user hoặc không phát hiện token bị đánh cắp | High | Medium | T003 có test riêng cho reuse-detection; dùng thư viện JWT đã kiểm chứng |
| R-3 | Giả định single-tenant sai nếu tổ chức thứ 2 xuất hiện sớm | Medium | Low | AD-1 repository pattern cho phép thêm tenant-scoping ở infrastructure layer sau |
| R-4 | Thuật ngữ generic (admin/user) lệch với quy trình thật của khách hàng | Low | Medium | Field/enum trung tính ở API layer, alias được mà không cần migration |
| R-5 | N+1 query khi admin xem danh sách submission của 1 đề | Medium | Medium | T022 dùng SQLAlchemy eager loading (`selectinload`) cho endpoint list |
| R-6 | Lưu nhầm plaintext refresh token thay vì hash — lỗ hổng bảo mật | High | Low | AD-2 chỉ lưu hash, T003 có test xác nhận không lưu plaintext |

## Success Criteria (Technical)

| PRD Success Criterion | Technical Metric | Target | Measurement |
|---|---|---|---|
| SC-1 | E2E integration test suite (create→assemble→assign→submit→grade) | 100% pass | `pytest tests/integration/test_e2e_flow.py` |
| SC-2 | Grading unit test trên fixture đáp án đã biết | 100% khớp kỳ vọng | `pytest tests/unit/test_grading.py` |
| SC-3 | Security test reuse-detection cho refresh token | Token cũ trả 401, session bị revoke | `pytest tests/integration/test_auth_rotation.py` |
| SC-4 | Integration test mock Cloudinary lỗi | Question tạo thành công không ảnh, HTTP 201 | `pytest tests/integration/test_question_upload_failure.py` |
| SC-5 | Smoke test môi trường sạch | `docker-compose up -d` + health check 200 trong 60s | CI job `smoke-test` |
| SC-6 | Integration test admin/non-admin tạo user | Admin 201, non-admin 403 | `pytest tests/integration/test_admin_users.py` |
| SC-7 | Integration test breakdown kết quả | Breakdown khớp fixture answer key cho cả user và admin view | `pytest tests/integration/test_results.py` |
| CRIT-1 (plan-review) | Transaction rollback test cho submit flow | Insert Answer lỗi giữa chừng → không có Submission mồ côi trong DB | `pytest tests/integration/test_submit_transaction.py` |
| CRIT-2 (plan-review) | Cross-user access-control test | User A gọi `GET /submissions/{id}` của User B → 403; admin → 200 | `pytest tests/integration/test_results_authz.py` |
| WARN-4 (plan-review) | Query-count assertion cho list-submissions | Số query không tăng tuyến tính theo N submission (eager loading) | `pytest tests/integration/test_results_n_plus_1.py` |

## Tasks Created

| Task | Name | Phase | Complexity | Model | Depends On | Parallel |
|---|---|---|---|---|---|---|
| T001 | Project scaffolding + Docker Compose + Alembic init | 1 | simple | sonnet | — | no |
| T002 | Domain entities + SQLAlchemy models + initial migration | 1 | complex | opus | T001 | no |
| T003 | Auth — JWT access/refresh + rotation + reuse detection | 1 | complex | opus | T002 | no |
| T010 | Admin user management | 2 | simple | sonnet | T003 | yes |
| T011 | Question bank CRUD + Cloudinary image upload | 2 | moderate | sonnet | T003 | yes |
| T012 | Exam assembly + assignment | 2 | moderate | sonnet | T003, T010 | no |
| T020 | Submission + auto-grading + results | 3 | complex | opus | T012 | no |
| T090 | Verification — full epic | final | moderate | sonnet | T001,T002,T003,T010,T011,T012,T020 | no |

**Dependency graph:**
```
T001 → T002 → T003 ─┬─→ T010 ─┬─→ T012 → T020 → T090
                     └─→ T011 ─┴──────────↑
```
(T011 phụ thuộc T003 nhưng độc lập với T010/T012 — chạy song song. T012 chờ cả T003 và T010.)

**Parallel ratio:** 2/8 task đánh dấu `parallel: true` (T010, T011) — có thể chạy đồng thời trong Phase 2 sau khi T003 xong.

## PRD Coverage

| Requirement | Covered | Task |
|---|---|---|
| FR-1 | ✅ | T003 |
| FR-2 | ✅ | T010 |
| FR-3 | ✅ | T011 |
| FR-4 | ✅ | T012 |
| FR-5 | ✅ | T012 |
| FR-6 | ✅ | T020 |
| FR-7 | ✅ | T020 |
| NFR-1 | ✅ | T003 |
| NFR-2 | ✅ | T011 |
| NFR-3 | ✅ | T002 |
| NFR-4 | ✅ | T001 |
| NTH-1..5 | Deferred (out of scope v1) | — |

**Coverage: 11/11 MUST FR+NFR mapped (100%). 0 unmapped.**
