# Kiểm chứng image runtime local

Ngày kiểm tra: 18/11/2026. Đã kiểm tra local trước khi push thay đổi.

## Thay đổi

- Thay `python:3.11-slim` (Debian) bằng Wolfi base cố định digest trong
  [Dockerfile](../docker/Dockerfile), cài Python 3.11 và libstdc++ qua APK.
- Dùng multi-stage build: pip và công cụ build chỉ cài ở builder; runtime nhận
  virtualenv đã cài ứng dụng. Runtime không dùng package Debian.
- Giữ UID/GID 10001, cổng 8000, lệnh Uvicorn và hợp đồng model như trước.
- Pin Trivy v0.76.2 trong [CI](../.github/workflows/ci.yaml) khớp phiên bản đã thử.
- Thêm [smoke test HTTP](../workflow/smoke_container.py) sau build trong CI.
  Khi chưa cấu hình model, kỳ vọng live = 200 và ready = 503.
- Giữ ngưỡng HIGH/CRITICAL và exit code 1, không bỏ qua CVE chưa có bản vá.

Wolfi có package manager APK và glibc, không phải Alpine/musl. Tài liệu nền:
[Wolfi](https://www.chainguard.dev/docs/open-source/wolfi).

## Kết quả thực tế

- Build thành công image `fraud-api:local-verified` với Python 3.11.18.
- Dependency check và import MLflow/scikit-learn/API trong builder thành công.
- Trivy v0.76.2 nhận diện Wolfi, kiểm tra cả package OS lẫn Python và trả exit 0:
  **0 HIGH, 0 CRITICAL** tại thời điểm kiểm tra.
- Không còn hai CVE Python CVE-2026-23949, CVE-2026-24049 hoặc các cảnh báo
  Debian của image cũ. Đây là kết quả scan tại thời điểm chạy, không đảm bảo các
  lần scan tương lai luôn có cùng kết quả khi cơ sở dữ liệu CVE cập nhật.
- Chạy API với model v1 thật, user không phải root, root filesystem chỉ đọc,
  `/tmp` dùng tmpfs, model và manifest mount chỉ đọc.
- Kiểm tra HTTP health, readiness, metrics và POST predict thành công.
  Payload tổng hợp toàn số 0 trả version `1`, xác suất `0.2362996837948046`,
  threshold `0.8528996455659125`.
- Ruff lint và format check thành công.

MLflow có cảnh báo khác phiên bản giữa môi trường train và image: MLflow 3.17.2
so với 3.18.0 và threadpoolctl 3.7.0 so với 3.8.0. Load và inference đã được kiểm
tra thành công; kết quả này không thay thế việc khóa toàn bộ dependency khi phát hành model.

## Chạy lại

```powershell
docker build --pull -f docker/Dockerfile -t fraud-api:local-verified .
```

Tạo manifest dành cho container; giữ nguyên model và manifest gốc trên host:

```powershell
New-Item -ItemType Directory -Force reports | Out-Null
$modelManifest = Get-Content artifacts/manifest.registry.json -Raw | ConvertFrom-Json
$modelManifest.model_uri = '/model'
$modelManifest | ConvertTo-Json -Depth 10 | Set-Content reports/manifest.container.json -Encoding Ascii
```

Chạy trên loopback, cổng host 18000. Tên container cần chưa tồn tại:

```powershell
docker run --detach --name fraud-api-local-verified --publish 127.0.0.1:18000:8000 --read-only --tmpfs /tmp:rw,nosuid,size=512m --mount type=bind,source=D:/MLops_Fraud_Detection/artifacts/training/8a5980d06a884a08b3afb9922847845c/model,target=/model,readonly --mount type=bind,source=D:/MLops_Fraud_Detection/reports/manifest.container.json,target=/models/manifest.json,readonly --env MODEL_MANIFEST=/models/manifest.json fraud-api:local-verified
python workflow/smoke_container.py --url http://127.0.0.1:18000 --manifest artifacts/manifest.registry.json
```

Mở `http://127.0.0.1:18000/docs` để kiểm tra tay. Dừng container khi không dùng:

```powershell
docker stop fraud-api-local-verified
```

Quét lại với Trivy container và Docker socket:

```powershell
docker run --rm --mount type=bind,source=/var/run/docker.sock,target=/var/run/docker.sock --mount type=volume,source=fraud-trivy-cache,target=/root/.cache/trivy ghcr.io/aquasecurity/trivy:0.76.2 image --scanners vuln --severity HIGH,CRITICAL --exit-code 1 --no-progress fraud-api:local-verified
```

Báo cáo JSON lần kiểm chứng ở `reports/trivy-local-verified.json`, không commit.
Chưa triển khai image này lên Kubernetes hoặc chạy load test.
