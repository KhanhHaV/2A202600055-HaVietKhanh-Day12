# Deployment Guide - Day 12 Agent

Hệ thống của bạn đã sẵn sàng để triển khai lên Cloud. Dưới đây là hướng dẫn chi tiết để đưa Agent lên **Railway** (hoặc các nền tảng tương tự).

## 1. Chuẩn bị (Pre-requisites)
- Đã cài đặt [Railway CLI](https://docs.railway.app/guides/cli).
- Tài khoản Railway (Free $5 credit cho người dùng mới).
- Code đã được đẩy lên GitHub (khuyến nghị).

## 2. Các bước triển khai lên Railway

```bash
# 1. Đăng nhập
railway login

# 2. Khởi tạo dự án (chọn 'Empty Project' hoặc connect repo GitHub)
railway init

# 3. Thêm dịch vụ Redis (Bắt buộc cho Stateless Agent)
# Bạn vào Dashboard Railway -> New -> Database -> Redis

# 4. Cấu hình Biến môi trường
# Railway sẽ tự động cung cấp REDIS_URL nếu bạn thêm dịch vụ Redis.
# Bạn cần set thêm các biến sau:
railway variables set PORT=8000
railway variables set AGENT_API_KEY=your-secure-api-key-here
railway variables set ENVIRONMENT=production
railway variables set OPENAI_API_KEY=sk-your-openai-key (Nếu dùng LLM thật)

# 5. Triển khai
railway up
```

## 3. Kiểm tra sau khi Deploy

Giả sử URL của bạn là `https://your-agent.railway.app`:

### Kiểm tra Health Check
```bash
curl https://your-agent.railway.app/health
# Mong đợi: {"status": "ok", "storage": "redis", ...}
```

### Kiểm tra Authentication (Phải lỗi 401 nếu không có key)
```bash
curl -X POST https://your-agent.railway.app/ask \
     -H "Content-Type: application/json" \
     -d '{"question": "Hello"}'
# Mong đợi: {"detail": "Invalid or missing API key."}
```

### Kiểm tra Agent (Dùng API Key)
```bash
curl -X POST https://your-agent.railway.app/ask \
     -H "X-API-Key: your-secure-api-key-here" \
     -H "Content-Type: application/json" \
     -d '{"question": "What is Cloud Deployment?"}'
```

### Kiểm tra Rate Limiting
Chạy lệnh sau 15-20 lần liên tục:
```bash
for i in {1..15}; do curl -H "X-API-Key: your-key" -X POST -d '{"question":"test"}' https://your-agent.railway.app/ask; done
# Mong đợi: Xuất hiện lỗi 429 "Too Many Requests"
```

## 4. Troubleshooting
- **Lỗi Redis connection:** Kiểm tra xem biến `REDIS_URL` đã được Railway inject vào chưa.
- **Lỗi 402:** Bạn đã vượt quá `DAILY_BUDGET_USD` (Mặc định là $5.0). Có thể tăng thêm qua biến môi trường.
- **Log:** Dùng `railway logs` để xem trực tiếp lỗi từ server.
