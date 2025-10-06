# GTI Control Add-ons

Repo chứa 2 add-on:

- **gti-control**: Ingress UI (v0.1.0), không mở port, dùng ingress trong HA.
- **gti-control-debug**: Bản debug (v0.1.0) mở cổng **8099** để truy cập trực tiếp (tránh lỗi 502, dễ chẩn đoán).

> Không thể mở port & ingress cùng lúc, nên tách 2 bản.

## Cách dùng (GitHub)
1) Upload toàn bộ repo này lên GitHub (public).
2) Vào **Settings → Add-ons → Add-on Store → 3 chấm → Repositories** và dán URL repo của bạn.
3) Reload và cài đặt add-on.

## Cách dùng (Local)
- Chép cả thư mục `gti-control/` hoặc `gti-control-debug/` vào `/addons/` trên host → Add-on Store → Local add-ons → Install.

## Ghi chú
- Ứng dụng chạy **FastAPI + Uvicorn** trên port 8099 trong container.
- Tránh lỗi PEP 668: dùng **virtualenv** trong Dockerfile.
- Endpoint kiểm tra: `/health`.
- MQTT:
  - Nếu để trống `mqtt_host`, add-on sẽ cố dùng `core-mosquitto`.
