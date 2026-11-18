# Transaction Lab — web riêng

Web HTML/CSS/JS không phụ thuộc MLflow, pandas hoặc package fraud_detection. Không train/load model ở web. Mọi dự đoán gọi inference API qua HTTP. API trả schema từ `/model-info`, nhận payload ở `/predict`; response chứa model version, threshold, score và cảnh báo. Raw dataset/model không đưa vào web hoặc web image.

## Chạy local

Terminal1, tại root dự án, Conda fraud-mlops:

```powershell
$env:MODEL_MANIFEST = 'D:/MLops_Fraud_Detection/artifacts/manifest.json'
$env:WEB_ORIGINS = 'http://127.0.0.1:8080,http://localhost:8080'
python -m uvicorn fraud_detection.api:app --host 127.0.0.1 --port 18001 --no-access-log
```

Terminal2, tại root:

```powershell
python -m http.server 8080 --bind 127.0.0.1 --directory src/web
```

Mở http://127.0.0.1:8080/. Hai VS Code tasks tương ứng: **MLOps API local**, **Transaction Lab web**. API cổng18001 không còn serve HTML; Swagger tại http://127.0.0.1:18001/docs. Dừng web không dừng model/API; dừng API thì web vẫn mở nhưng không dự đoán được.

Địa chỉ API cấu hình trong [config.js](config.js). Đây là URL trình duyệt truy cập được, không phải hostname nội bộ Docker. Không đặt credentials trong JS. Muốn đổi host/port, sửa config.js và `WEB_ORIGINS` của backend, restart API và reload web. CORS mặc định tắt khi không cấu hình; allowlist là cơ chế browser, không phải authentication. Không public hai service này như production khi chưa có auth/TLS/rate limit.

## Test giao dịch và Locust

Điền form hoặc chọn mẫu tổng hợp. Phần batch mặc định100 dòng (1–256), random PCA[-5,5], Amount[0,5000]. Bấm **Tạo batch ngẫu nhiên** rồi **Gửi batch đang có**. Không dùng nút form đơn nếu muốn giữ batch100, vì form tạo lại một giao dịch. Dữ liệu tổng hợp không có nhãn, không mô phỏng phân bố thật; số cảnh báo không phải precision/recall.

**Tải payload Locust** → lưu thành `artifacts/synthetic-payload.json` ở root, sau đó:

```powershell
$env:LOCUST_PAYLOAD_FILE = 'D:/MLops_Fraud_Detection/artifacts/synthetic-payload.json'
locust -f load_testing/locustfile.py --host http://127.0.0.1:18001 --web-host 127.0.0.1
```

Mở http://127.0.0.1:8089/, bắt đầu2users/spawn-rate1. Locust gọi API trực tiếp, không đi qua web; mỗi request chọn một mẫu trong pool100, có thể lặp. Users là số user đồng thời, không phải tổng request. Không tự chạy load test ở ngoài local. Không cần bật web để chạy Locust.

## Docker tách biệt

[Dockerfile](Dockerfile) chỉ chứa web assets, dùng nginx official image. Build context là `src/web/`; backend image vẫn build từ root bằng Dockerfile API, không COPY web. Cấu hình Compose có profile `web`, không tự khởi động giao diện trong luồng MLflow-only.

```powershell
docker compose -f docker/compose.yaml --profile web up --build -d mlflow api web
```

Compose mount [config.docker.js](config.docker.js) vào config.js: browser gọi API host cổng8000, web host8080. API Compose dùng `artifacts/manifest.registry.json` đã mount vào `/models`, MLflow HTTP trong mạng Docker. Model Registry phải có phiên bản được manifest tham chiếu; compose mới/volume trống chưa có model thì API ready503. Dùng backend host18001 thì chạy web riêng và giữ config.js mặc định, không mount bản docker8000.

Đã build fraud-web:local-check và smoke HTTP trang/app.js/config.js/styles.css200; container thử đã dọn. Chưa scan web image bằng Trivy; Compose đã validate. Không nhầm việc validate file với image đã kiểm chứng. CI kiểm tra cú pháp JS và backend tests; chưa tự build/publish web image riêng. Triển khai K8s/Ingress cho web sau này là workload riêng; hiện chưa deploy.

## Khởi động nhanh và xử lý lỗi kết nối

Để bật cả hai service và đợi model ready, từ root chạy:

```powershell
conda activate fraud-mlops
./workflow/start_local.ps1
```

Có thể truyền `-PythonExe 'C:/Users/ADMIN/miniconda3/envs/fraud-mlops/python.exe'` nếu terminal chưa chọn đúng interpreter. Script chạy process nền local, ghi log/PID vào artifacts/local-app, xác minh model version/threshold và CORS trước khi báo Ready. Không restart/xóa process cũ tự động; nếu đã có API sai config thì dừng API cũ trước. Kiểm tra PID và command line trước khi dùng Stop-Process để dừng đúng process do script mở.

Mở http://127.0.0.1:8080/ và Ctrl+F5 để bỏ JS cũ trong cache. Web chạy một mình không load model được: API18001 cũng phải chạy. Khi API không kết nối/timeout, web báo địa chỉ API cần bật; khi API trả503, web báo model chưa load (xem artifacts/local-app/api.stderr.log, manifest và đường dẫn model). Nếu health200 nhưng browser không gọi được, kiểm tra WEB_ORIGINS và origin thực tế; không mở index.html bằng file://. CI không khởi động model local hoặc thay các service đang chạy trên máy của bạn.
