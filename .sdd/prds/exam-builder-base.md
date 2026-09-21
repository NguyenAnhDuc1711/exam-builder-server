---
name: exam-builder-base
description: Base backend cho hệ thống giao đề trắc nghiệm và chấm điểm tự động, dành cho một tổ chức đơn lẻ
status: validated
priority: high
scale: medium
created: 2026-09-21T09:12:26Z
updated: 2026-09-21T09:14:32Z
---

# PRD: exam-builder-base

## Executive Summary

Tổ chức khách hàng hiện soạn đề trắc nghiệm thủ công bằng Word/Excel và chấm tay, gây tốn thời gian cho người quản lý (admin) và độ trễ phản hồi cho người làm bài (user). `exam-builder-base` là base backend (FastAPI + PostgreSQL/SQLAlchemy/Alembic/pgAdmin + JWT + Docker Compose) cho phép admin xây ngân hàng câu hỏi trắc nghiệm (có hỗ trợ ảnh), ghép đề thủ công, giao đề tường minh cho từng user, và tự động chấm điểm + trả breakdown ngay khi user nộp bài. Xây ngay bây giờ vì đây là nền tảng bắt buộc trước khi có thể mở rộng sang các tính năng nâng cao (tự luận, chấm AI, sinh đề tự động) đã được xác định trong quá trình brainstorm nhưng chủ động đẩy ra ngoài phạm vi v1.

## Problem Statement

**Ai gặp vấn đề:** Admin (quản lý/giáo viên nội bộ của tổ chức khách hàng) chịu trách nhiệm soạn đề và chấm bài.

**Tần suất & mức độ nghiêm trọng:** Mỗi lần cần đánh giá kiến thức của user (nhân viên/học viên/ứng viên), admin phải soạn đề trong Word/Excel rồi chấm tay từng bài — lặp lại mỗi kỳ đánh giá, gây tốn thời gian trực tiếp tỷ lệ thuận với số user cần đánh giá.

**Hiện tại không có gì thay thế:** Không có ngân hàng câu hỏi tái sử dụng được, không có cơ chế giao đề có kiểm soát (ai được làm đề nào), không có chấm điểm tự động — mọi thứ thủ công 100%.

## Target Users

**Persona 1 — Admin**
- Vai trò: Quản lý/giáo viên nội bộ của tổ chức khách hàng
- Bối cảnh: Cần đánh giá kiến thức của nhiều user định kỳ, hiện đang làm thủ công trong Word/Excel
- Nhu cầu chính: Tạo câu hỏi (kèm ảnh nếu cần) một lần, tái sử dụng nhiều lần; giao đề đúng người; xem kết quả ngay không cần chấm tay
- Mức độ đau: Cao — tốn thời gian trực tiếp mỗi kỳ đánh giá

**Persona 2 — User**
- Vai trò: Nhân viên/học viên/ứng viên của tổ chức khách hàng (đối tượng cụ thể chưa xác định — hệ thống giữ thuật ngữ trung tính theo quyết định generic ở giai đoạn brainstorm)
- Bối cảnh: Được admin giao một đề trắc nghiệm cần hoàn thành
- Nhu cầu chính: Làm bài, nộp, và biết kết quả ngay lập tức thay vì chờ đợi
- Mức độ đau: Trung bình — chủ yếu là chờ đợi kết quả, không trực tiếp tốn công sức tạo/chấm

## User Stories

**US-1** (Admin): Tôi muốn tạo câu hỏi trắc nghiệm với text và ảnh tùy chọn, để xây ngân hàng câu hỏi tái sử dụng được.
- AC: Given nội dung câu hỏi + ít nhất 2 lựa chọn với đúng 1 đáp án đúng, when admin submit, then câu hỏi được lưu vào ngân hàng.
- AC: Given admin đính kèm 1 file ảnh, when upload, then ảnh được lưu qua Cloudinary và URL được gắn vào câu hỏi.
- AC: Given Cloudinary upload thất bại, when admin vẫn submit câu hỏi, then câu hỏi được lưu thành công không kèm ảnh, kèm thông báo lỗi upload rõ ràng (không chặn toàn bộ luồng).

**US-2** (Admin): Tôi muốn ghép đề bằng cách chọn tay câu hỏi từ ngân hàng, để kiểm soát chính xác nội dung đề.
- AC: Given admin chọn N câu hỏi có sẵn trong ngân hàng theo thứ tự mong muốn, when tạo đề, then đề được lưu với danh sách câu hỏi đúng thứ tự đã chọn.

**US-3** (Admin): Tôi muốn giao một đề cho user cụ thể, để chỉ đúng người được chỉ định mới truy cập được.
- AC: Given đề đã tồn tại và user đã có tài khoản, when admin gán đề cho user đó, then đề xuất hiện trong danh sách đề của user đó, và không xuất hiện với user khác không được gán.

**US-4** (Admin): Tôi muốn tạo tài khoản cho user, để kiểm soát ai được phép truy cập hệ thống.
- AC: Given admin đã đăng nhập, when admin tạo tài khoản với role `user`, then tài khoản được tạo thành công.
- AC: Given không có endpoint đăng ký công khai, when một request đăng ký ẩn danh được gửi, then request bị từ chối (không tồn tại route đó).

**US-5** (User): Tôi muốn xem danh sách đề được giao cho mình, để biết mình cần hoàn thành gì.
- AC: Given user đã đăng nhập, when user xem danh sách đề, then chỉ thấy các đề đã được admin gán cho chính user đó.

**US-6** (User): Tôi muốn nộp bài và được chấm điểm ngay, để không phải chờ đợi.
- AC: Given user có đề được giao chưa nộp, when user nộp đáp án cho tất cả câu hỏi, then hệ thống chấm điểm và trả kết quả ngay trong response.
- AC: Given user đã nộp đề đó rồi, when user cố nộp lại, then request bị từ chối.

**US-7** (User): Tôi muốn xem câu nào đúng/sai sau khi nộp, để hiểu rõ kết quả của mình.
- AC: Given user vừa nộp bài, when xem kết quả, then thấy điểm tổng + breakdown đúng/sai từng câu.

**US-8** (Admin): Tôi muốn xem toàn bộ bài nộp của một đề, để theo dõi kết quả của các user.
- AC: Given đề đã có user nộp bài, when admin xem kết quả đề đó, then thấy danh sách user kèm điểm + breakdown từng người.

## Requirements

### Functional (MUST)

**FR-1: Authentication & Session Management**
- Given thông tin đăng nhập hợp lệ, when login, then nhận access token (hạn 24h) + refresh token (hạn 7 ngày).
- Given refresh token hợp lệ, when gọi endpoint refresh, then nhận cặp access+refresh token mới, refresh token cũ bị vô hiệu hóa ngay (rotation).
- Given refresh token đã bị rotate (dùng lại token cũ), when gọi refresh với token đó, then request bị từ chối và toàn bộ token của user đó bị vô hiệu hóa (reuse detection).

**FR-2: Admin User Management**
- Given admin đã đăng nhập, when tạo tài khoản với role `user`, then tài khoản được tạo, không có endpoint tự đăng ký công khai.
- Given role không phải `admin`, when gọi endpoint tạo tài khoản, then bị từ chối (403).

**FR-3: Question Bank Management**
- Given admin đã đăng nhập, when tạo câu hỏi trắc nghiệm với text + đúng 1 đáp án đúng trong ≥2 lựa chọn, then câu hỏi lưu vào ngân hàng.
- Given câu hỏi có đính kèm ảnh, when admin upload, then ảnh lưu qua Cloudinary và URL gắn vào câu hỏi.
- Given Cloudinary upload thất bại, when tạo câu hỏi, then câu hỏi vẫn lưu thành công không kèm ảnh, kèm lỗi upload trả về riêng.

**FR-4: Exam Assembly**
- Given admin đã đăng nhập, when chọn N câu hỏi từ ngân hàng và tạo đề, then đề được lưu với danh sách câu hỏi có thứ tự.

**FR-5: Exam Assignment**
- Given đề và user đã tồn tại, when admin gán đề cho user, then bản ghi assignment được tạo, đề chỉ hiển thị với user được gán.

**FR-6: Exam Submission & Auto-Grading**
- Given user có đề được giao chưa nộp, when nộp đáp án đầy đủ, then hệ thống so khớp đáp án đúng, tính điểm, lưu submission, trả điểm + breakdown ngay trong response.
- Given user đã nộp đề đó, when cố nộp lại, then bị từ chối (single-attempt).

**FR-7: Results Viewing**
- Given user đã nộp bài, when user xem kết quả, then trả điểm + breakdown đúng/sai từng câu.
- Given admin đã đăng nhập, when xem kết quả của một đề, then trả danh sách toàn bộ user đã nộp kèm điểm + breakdown.

### Nice to Have (NTH — deferred)

- **NTH-1:** Câu hỏi multi-select (nhiều đáp án đúng, luật chấm phần trăm chưa xác định)
  - Given câu hỏi được cấu hình multi-select với >1 đáp án đúng, when user chọn đáp án, then hệ thống chấm theo luật phần trăm (số đáp án đúng đã chọn / tổng đáp án đúng) — luật cụ thể chưa quyết, deferred.
- **NTH-2:** Sinh đề tự động (random theo chủ đề/độ khó)
  - Given ngân hàng câu hỏi có gắn tag chủ đề/độ khó, when admin yêu cầu sinh đề tự động với tiêu chí (N câu, chủ đề, độ khó), then hệ thống rút ngẫu nhiên câu hỏi thỏa tiêu chí để tạo đề.
- **NTH-3:** Câu hỏi tự luận + chấm bằng AI
  - Given câu hỏi dạng tự luận, when user nộp câu trả lời dạng văn bản tự do, then hệ thống hỗ trợ chấm bằng AI hoặc chuyển cho admin chấm tay.
- **NTH-4:** Giới hạn thời gian làm bài (timer)
  - Given đề có cấu hình giới hạn thời gian, when user vượt quá thời gian cho phép, then hệ thống tự động khóa bài và chấm những gì đã nộp tới thời điểm đó.
- **NTH-5:** Cho phép làm lại đề (retake/nhiều lần nộp)
  - Given user đã nộp đề và được phép làm lại, when user bắt đầu lượt làm mới, then hệ thống tạo submission mới độc lập, giữ lịch sử các lần nộp trước.

### Non-Functional

**NFR-1 (Security — token rotation):** Refresh token rotation phải phát hiện reuse. Given một refresh token đã bị rotate được dùng lại, then toàn bộ session của user đó bị vô hiệu hóa ngay lập tức. Đo lường: test bảo mật xác nhận refresh token cũ trả về 401 và vô hiệu hóa session.

**NFR-2 (Reliability — external dependency):** Lỗi Cloudinary không được chặn luồng tạo câu hỏi text-only. Đo lường: integration test mock Cloudinary lỗi, xác nhận tạo câu hỏi vẫn thành công (không ảnh).

**NFR-3 (Architecture — single-tenant):** Hệ thống không có field `organization_id`, không xử lý cách ly đa tổ chức ở v1. Đo lường: schema review xác nhận không có tenant-scoping trong models.

**NFR-4 (Deployment):** Toàn bộ stack (api + postgres + pgadmin) phải chạy được bằng một lệnh `docker-compose up` trên máy sạch. Đo lường: smoke test khởi động từ môi trường sạch, API health check trả 200.

## Success Criteria

- **SC-1:** Admin tạo được 1 câu hỏi + ghép đề 10 câu + giao đề cho 1 user qua API, toàn bộ luồng thành công không lỗi — đo bằng test tích hợp end-to-end.
- **SC-2:** Chấm điểm tự động trả kết quả đúng 100% so với đáp án cấu hình sẵn (test với payload đúng/sai đã biết trước) — đo bằng unit test.
- **SC-3:** Refresh token bị reuse sau khi rotate trả về 401 và vô hiệu hóa session — đo bằng test bảo mật (NFR-1).
- **SC-4:** Tạo câu hỏi text-only vẫn thành công khi Cloudinary lỗi/timeout — đo bằng integration test mock lỗi (NFR-2).
- **SC-5:** `docker-compose up` khởi động thành công cả 3 service và API health check pass — đo bằng smoke test tự động.
- **SC-6:** Admin tạo tài khoản user thành công qua API; request tạo tài khoản từ role không phải admin bị từ chối (403) — đo bằng test tích hợp cho FR-2.
- **SC-7:** Sau khi nộp bài, cả user và admin đều lấy được breakdown đúng/sai chính xác từng câu qua API tương ứng — đo bằng test tích hợp cho FR-7.

## Risks & Mitigations

| # | Risk | Severity | Likelihood | Mitigation |
|---|------|----------|------------|------------|
| R-1 | Cloudinary outage/lỗi cấu hình chặn luồng tạo câu hỏi có ảnh | Medium | Low | Graceful degradation — tạo câu hỏi vẫn thành công không ảnh, upload là bước tách biệt (NFR-2) |
| R-2 | Refresh token rotation cài sai gây khóa nhầm user hoặc không phát hiện được token bị đánh cắp | High | Medium | Test riêng cho reuse-detection (NFR-1/SC-3), dùng thư viện JWT đã kiểm chứng, review kỹ logic rotation |
| R-3 | Giả định single-tenant sai nếu tổ chức thứ 2 xuất hiện sớm hơn dự kiến | Medium | Low | Ranh giới Clean Architecture (repository pattern) cho phép thêm tenant-scoping ở infrastructure layer sau, không cần viết lại business logic |
| R-4 | Thuật ngữ generic (admin/user, exam/question) chọn khi chưa xác nhận vertical có thể lệch với quy trình thật của tổ chức khách hàng | Low | Medium | Giữ tên field/enum trung tính ở tầng API, có thể alias/đổi tên hiển thị sau mà không cần migration DB |

## Constraints & Assumptions

- **Constraint:** Stack cố định — FastAPI, PostgreSQL, SQLAlchemy, Alembic, pgAdmin, JWT, Docker Compose (đã chốt từ đầu, không đổi).
- **Constraint:** Single-tenant, không có `organization_id`. Nếu sai (tổ chức thứ 2 xuất hiện), then cần thêm tenant-scoping vào infrastructure layer trước khi onboard tổ chức đó.
- **Assumption:** Admin tạo toàn bộ tài khoản user, không có self-service signup. Nếu sai (khách hàng muốn tự đăng ký), then cần thêm FR mới cho luồng invite/đăng ký.
- **Assumption:** Toàn bộ câu hỏi là trắc nghiệm 1-đáp-án-đúng. Nếu sai (cần multi-select), then cần FR mới + quyết định luật chấm điểm phần trăm (hiện NTH-1).
- **Assumption:** Đề không giới hạn thời gian làm bài. Nếu sai (cần tính toàn vẹn thi cử), then cần FR mới cho timer + enforcement phía server (hiện NTH-4).

## Out of Scope

- Câu hỏi tự luận / chấm bằng AI — luật chấm chưa xác định, để phase sau (NTH-3)
- Sinh đề tự động (random) — chưa cần cho wedge đầu tiên (NTH-2)
- Câu hỏi multi-select — luật chấm phần trăm chưa rõ (NTH-1)
- Multi-tenancy / `organization_id` — chưa có tổ chức thứ 2 xác nhận (NFR-3)
- Self-registration công khai — phá vỡ mô hình giao đề tường minh, rủi ro truy cập trái phép
- Timer làm bài — business concern thêm sau không phá schema (NTH-4)
- Retake / nhiều lần nộp — mặc định 1 lần/đề (NTH-5)

## Dependencies

- Tài khoản & API credentials Cloudinary — Owner: chủ dự án — Status: chưa provisioned (blocker cho FR-3 phần ảnh trước khi implement)
- PostgreSQL instance qua Docker Compose — Owner: dev team — Status: sẽ setup ở giai đoạn epic-run

## _Metadata

- requirement_ids: FR-1, FR-2, FR-3, FR-4, FR-5, FR-6, FR-7, NTH-1, NTH-2, NTH-3, NTH-4, NTH-5, NFR-1, NFR-2, NFR-3, NFR-4
- scale: medium
- discovery_mode: express
- validation_status: passed
- last_validated: 2026-09-21T09:14:32Z
