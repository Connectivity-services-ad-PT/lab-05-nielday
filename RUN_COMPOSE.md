# RUN_COMPOSE.md – Hướng dẫn chạy Lab 05

Tài liệu này hướng dẫn người khác clone repo sạch và chạy lại stack Compose của Lab 05.

---

## 1. Clone repo

```bash
git clone <repo-url>
cd FIT4110_lab05_docker_compose_readiness
```

---

## 2. Cài dependencies cho Newman/Prism/Spectral (tuỳ chọn)

```bash
npm install
```

---

## 3. Build & chạy stack Docker Compose

Đảm bảo bạn đã khởi động Docker Desktop.

```bash
# Bắt buộc tạo network bên ngoài trước khi chạy (quan trọng cho điểm 10)
docker network create class-net || true

# Khởi chạy các dịch vụ (API, DB, AI)
docker compose up -d --build
```

> **Lưu ý:** Flag `--build` đảm bảo Docker luôn đóng gói code mới nhất.

---

## 4. Kiểm tra Container và Logs

```bash
# Xem trạng thái các dịch vụ
docker compose ps
```

Bạn sẽ thấy 3 dịch vụ ở trạng thái `Up`:
- `fit4110-api-lab05` (cổng 8000)
- `fit4110-db-lab05` (cổng 5432)
- `fit4110-ai-lab05` (cổng 9000)

Bạn có thể kiểm tra health của mỗi service:

```bash
# API & DB & AI
curl http://localhost:8000/health

# AI service độc lập
curl http://localhost:9000/health

# DB readiness
docker exec -it fit4110-db-lab05 pg_isready -U lab05
```

---

## 5. Build và Push Image theo chuẩn tag

Bạn cần push image API lên GitHub Container Registry theo yêu cầu của Lab 05. Vì image API đã được Compose build sẵn, bạn chỉ cần tag lại rồi push:

```bash
docker login ghcr.io -u <your-username>
docker tag lab-05-nielday-api:latest ghcr.io/nielday/team-iot:v0.1.0-team-iot
docker push ghcr.io/nielday/team-iot:v0.1.0-team-iot
```

*(Lưu ý thay `nielday` bằng username thực tế của bạn)*

---

## 6. Chạy Newman test trên stack Compose (tuỳ chọn)

```bash
npm run test:compose
```

Report sinh tại:

```text
reports/newman-lab05-compose.xml
reports/newman-lab05-compose.html
```

---

## 7. Dừng stack và dọn dẹp

Khi không cần nữa, dừng và xoá các container bằng:

```bash
docker compose down
```

Nếu muốn xoá volume dữ liệu của DB, thêm tuỳ chọn `-v`:

```bash
docker compose down -v
```

---

## 8. Mẹo gỡ lỗi

- Sử dụng `docker compose ps` để xem trạng thái container.
- Sử dụng `docker compose logs api` để kiểm tra lỗi bên trong API.
- Nếu API trả lỗi kết nối DB, hãy kiểm tra biến môi trường `POSTGRES_*` trong `.env` và đảm bảo DB đã sẵn sàng (`pg_isready`).
- Nếu AI service chưa ready, kiểm tra log qua lệnh `docker compose logs ai-service`.