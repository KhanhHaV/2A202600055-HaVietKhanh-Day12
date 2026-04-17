# Day 12 Lab - Mission Answers

## Part 1: Localhost vs Production

### Exercise 1.1: Anti-patterns found
1. **Hardcoded Secrets:** API Keys và Database URL được viết trực tiếp trong code (`OPENAI_API_KEY`, `DATABASE_URL`). Nếu đẩy lên GitHub sẽ bị lộ thông tin nhạy cảm.
2. **Thiếu Config Management:** Sử dụng biến global thay vì đọc từ environment variables hoặc file cấu hình tập trung.
3. **Logging không chuyên nghiệp:** Sử dụng `print()` thay vì `logging` library. Nguy hiểm hơn là log cả thông tin nhạy cảm (API Key).
4. **Không có Health Check:** Thiếu endpoint để container platform (như Railway/Docker) kiểm tra trạng thái của Agent.
5. **Cứng Port và Host:** Code gắn chết port `8000` và host `localhost`. Trên cloud, IP và Port thường được cấp phát động qua biến môi trường.
6. **Bật Debug Mode trong Prod:** Sử dụng `reload=True` của uvicorn, điều này làm giảm hiệu năng và tiềm ẩn rủi ro bảo mật ở môi trường thực tế.

### Exercise 1.3: Comparison table

| Feature | Develop | Production | Why Important? |
|---------|---------|------------|----------------|
| **Config** | Hardcode | Environment Variables | Bảo mật secret và linh hoạt cấu hình theo môi trường (dev, staging, prod). |
| **Health check**| None | Endpoint `/health` | Giúp hệ thống tự động phát hiện và khởi động lại agent nếu nó bị treo/crash. |
| **Logging** | `print()` | Structured JSON Logging | Dễ dàng thu thập và phân tích log bằng các công cụ như CloudWatch, Grafana Loki. |
| **Shutdown** | Đột ngột | Graceful Shutdown | Đảm bảo các request đang xử lý được hoàn tất trước khi dừng app, tránh mất dữ liệu. |

---

## Part 2: Docker

### Exercise 2.1: Dockerfile questions
1. **Base image:** `python:3.11`.
2. **Working directory:** `/app`.
3. **Tại sao COPY requirements.txt trước?** Để tận dụng Docker Layer Cache. Nếu chỉ sửa code mà không thêm thư viện, Docker sẽ không phải chạy lại bước `pip install`, giúp build nhanh hơn.
4. **CMD vs ENTRYPOINT:** `CMD` là lệnh mặc định có thể bị ghi đè khi chạy container. `ENTRYPOINT` quy định file thực thi chính và các đối số truyền vào sẽ được cộng dồn vào đó.

### Exercise 2.3: Image size comparison
- **Develop (Single-stage):** ~1 GB.
- **Production (Multi-stage):** ~200-300 MB.
- **Difference:** Giảm khoảng 70% dung lượng nhờ loại bỏ build tools (gcc, git) và các file rác trong stage builder.

---

## Part 3: Cloud Deployment

### Exercise 3.2: Railway vs Render
- `railway.toml` tập trung vào cách chạy ứng dụng (start command, health check).
- `render.yaml` (Blueprints) mở rộng hơn, cho phép định nghĩa cả các dịch vụ đi kèm như Database, Redis, Cron jobs trong cùng một file.

---

## Part 4: API Security

### Exercise 4.3: Rate limiting analysis
- **Algorithm:** Sliding Window Counter (dùng `deque` để lưu timestamps).
- **Limit:** 10 requests/phút cho user thường và 100 requests/phút cho admin.
- **Bypass Admin:** Admin có instance RateLimiter riêng với giới hạn cao hơn nhiều, giúp tránh bị chặn khi đang debug hoặc thực hiện các tác vụ quản trị.

---

## Part 5: Scaling & Reliability

### Exercise 5.1-5.5: Implementation notes
- **Health vs Readiness:** `/health` (Liveness) dùng để check app còn sống không; `/ready` dùng để check app đã load xong model/database và sẵn sàng nhận traffic chưa.
- **Stateless:** Việc chuyển conversation history sang **Redis** giúp chúng ta có thể chạy nhiều instance Agent song song. User có thể request vào bất kỳ instance nào mà vẫn giữ được ngữ cảnh hội thoại.
