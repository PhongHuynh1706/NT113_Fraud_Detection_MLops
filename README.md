# MLOps Fraud Detection

Khung nền tảng phục vụ model phát hiện gian lận: FastAPI, MLflow, Docker,
GitHub Actions, Kubernetes HPA, Prometheus/Grafana, Terraform và Locust.

Hiện chưa có file train hoặc model đã huấn luyện. API chỉ sẵn sàng dự đoán khi
được cấu hình artifact thật; không có model giả thay thế trong ứng dụng.
Các model tổng hợp trong tests chỉ kiểm tra hợp đồng tích hợp, không đo chất lượng fraud detection.
Dữ liệu `creditcard_2026.csv` được giữ cục bộ, không dùng làm payload ví dụ và
được loại khỏi Git cũng như Docker build context.

## Chạy cục bộ

Mã nguồn khai báo Python 3.11–3.13; CI kiểm tra Python 3.11. Phạm vi này là cấu hình
dự án, không phải xác nhận đã kiểm thử mọi phiên bản. Dùng môi trường Conda được
thống nhất cho dự án: `fraud-mlops`, đã xác minh Python 3.11.18 trên máy phát triển.

```powershell
conda activate fraud-mlops
pip install -e '.[dev,load]'
ruff check .
pytest --cov=fraud_detection --cov-report=term-missing
uvicorn fraud_detection.api:app --host 127.0.0.1 --port 8000 --no-access-log
```

Đây là hướng dẫn chạy, không phải biên bản các lệnh đã kiểm chứng trên máy bạn.
Kiểm tra `/health/live`, `/health/ready`, `/docs` và `/metrics` trên cổng 8000.
Khi chưa có model: live trả 200; ready và predict trả 503.
Ứng dụng không tự đọc `.env`; xuất biến môi trường bằng shell.

## Hợp đồng tích hợp file train sau

Model MLflow phải chứa preprocessing cùng logic dự đoán, nhận pandas DataFrame
và trả DataFrame có cột `fraud_probability`: xác suất gian lận trong [0, 1],
một dòng đầu ra ứng với một dòng đầu vào. Không dùng nhãn dự đoán thay cho xác suất.
Nếu model sklearn hiện chỉ trả nhãn qua `predict`, cần adapter `mlflow.pyfunc.PythonModel`
gọi xác suất đúng lớp gian lận; triển khai adapter sau khi đọc mã train thực tế.
API hiện hỗ trợ đặc trưng số hữu hạn, không ép chuỗi/bool thành số và không nhận missing values.
Nếu dữ liệu thực tế cần categorical hoặc missing values, mở rộng hợp đồng và tests trước khi tích hợp.

Sau khi có model, tạo `artifacts/manifest.json` theo mẫu dưới đây. Các tên đặc trưng,
version và threshold chỉ minh họa cấu trúc, không mô tả dữ liệu đã có:

```json
{
  "model_uri": "models:/FraudDetection/1",
  "model_version": "1",
  "features": ["synthetic_a", "synthetic_b"],
  "threshold": 0.7,
  "probability_column": "fraud_probability"
}
```

```powershell
$env:MLFLOW_TRACKING_URI = 'http://127.0.0.1:5000'
$env:MODEL_MANIFEST = 'artifacts/manifest.json'
uvicorn fraud_detection.api:app --host 127.0.0.1 --port 8000 --no-access-log
```

POST `/predict` nhận `{"instances":[{"synthetic_a":1.0,"synthetic_b":2.0}]}`.
Tên cột phải khớp manifest, thứ tự trong JSON không quan trọng. Mỗi batch tối đa
256 dòng; phản hồi chứa version, threshold, score và quyết định `score >= threshold`.
Chỉ load artifact tin cậy. Cài thêm dependency của model thật khi tích hợp;
MLflow load model không tự cài toàn bộ môi trường huấn luyện vào API.
Model được load một lần khi khởi động; sau khi sửa manifest, khởi động lại API.

File train sẽ cần ghi MLflow params, dataset fingerprint, seed, commit, dependency,
threshold chọn trên validation, signature và metrics. Đánh giá accuracy > 60% trên
test độc lập cùng PR-AUC, precision, recall, F1 và confusion matrix; hiện chưa có kết quả.

## Docker và MLflow cho phát triển

```powershell
docker compose -f docker/compose.yaml up --build -d
docker compose -f docker/compose.yaml logs api
docker compose -f docker/compose.yaml down
```

MLflow ở `http://127.0.0.1:5000`, API ở `http://127.0.0.1:8000`.
Volume giữ SQLite backend và artifact qua lần restart; `down` không xóa volume.
MLflow chỉ bind cổng host vào loopback và cấu hình host allowlist.
Compose là cấu hình phát triển một máy, chưa có backup, HA hoặc xác thực production.
Trong container, model local cần nằm dưới `/models`; đường dẫn Windows không dùng được ở đó.
Với registry URI, API cần kết nối tới MLflow và kho artifact tương ứng.

## Kubernetes và Terraform

Terraform hiện chỉ tạo namespace trên cluster có sẵn, không tạo cloud hoặc cluster.
Test và production có thư mục và local state riêng. Trước khi dùng cộng tác,
cấu hình remote backend có locking và phân quyền, không commit state hoặc kubeconfig.

```powershell
terraform -chdir=terraform/environments/test init
terraform -chdir=terraform/environments/test plan -var-file=terraform.tfvars -out=test.tfplan
# Chỉ apply sau khi đã xem plan và cho phép thay đổi cluster:
terraform -chdir=terraform/environments/test apply test.tfplan
kubectl kustomize K8s/overlays/test
```

Tạo file biến cục bộ từ `terraform.tfvars.example` và chọn đúng context trước khi plan.
Production làm tương tự ở thư mục riêng. Chưa thực thi apply trong bước khởi tạo.

Điều kiện triển khai: cluster/namespace đã có, Metrics Server, Ingress Controller,
MLflow backend/artifact store kết nối được, model đã đăng ký và image đã được scan.
Quyền GitHub runner chỉ cần cho namespace triển khai. Registry private cần Secret
pull image tạo trước trong namespace. Credentials MLflow tùy chọn qua Secret
`fraud-mlflow-credentials` với các biến môi trường MLflow phù hợp.

Base manifest còn image và domain placeholder, không apply trực tiếp.
Renderer `workflow/render.py` yêu cầu các biến:

| Biến | Ý nghĩa |
| --- | --- |
| `DEPLOY_IMAGE` | Image GHCR gồm digest `@sha256:...` |
| `MODEL_MANIFEST_JSON` | JSON manifest thật, registry URI chứa version số khớp `model_version` |
| `MLFLOW_TRACKING_URI` | Địa chỉ MLflow truy cập được từ Pod |
| `INGRESS_HOST` | Domain thật |
| `INGRESS_CLASS` | IngressClass của cluster |
| `INGRESS_TLS_SECRET` | Secret TLS đã có, bắt buộc với production |
| `IMAGE_PULL_SECRET` | Secret registry đã có nếu image private |

Renderer tạo ConfigMap manifest bất biến theo hash, thay image và cấu hình runtime.
Thay model/config tạo Pod template mới. Giữ ConfigMap cũ để phục vụ rollback;
không xóa chúng khi còn revision tham chiếu. Rollback Deployment bằng
`kubectl -n fraud-test rollout undo deployment/fraud-api`, rồi kiểm tra rollout.
GitHub Actions là nguồn cấu hình chuẩn: một lần deploy mới sẽ áp lại cấu hình đã chọn.

HPA bản đầu dùng CPU và memory, không dùng KEDA đồng thời. Giới hạn 1–5 Pod cho
test, 2–10 cho production; requests/limits và tỷ lệ utilization là giá trị khởi đầu,
chưa được hiệu chỉnh bằng load test. Memory model thường không giảm theo tải;
theo dõi để tránh HPA tăng replica liên tục do dung lượng model nền.
Chỉ `/predict` được expose qua Ingress; API chưa có xác thực người dùng hoặc rate limit.
Trước khi public production, cấu hình auth/rate limit tại gateway theo yêu cầu thực tế.

## Giám sát

Cài Helm chart `prometheus-community/kube-prometheus-stack` với release `monitoring`
trong namespace `monitoring`, dùng `K8s/monitoring/values.yaml`. Chọn và pin phiên bản
chart tương thích cluster trước khi cài. Tạo Secret `grafana-admin` trước, chứa
`admin-user` và `admin-password`. Sau khi CRD của Operator đã có:

```powershell
kubectl apply -f K8s/monitoring/servicemonitor.yaml
kubectl apply -f K8s/monitoring/alerts.yaml
kubectl apply -f K8s/monitoring/dashboard.yaml
```

Dashboard bao gồm RPS, p95 latency, tỷ lệ lỗi, tỷ lệ cảnh báo, replica, CPU và memory.
ServiceMonitor scrape qua Service; xác minh label selector của Prometheus nếu đổi
tên release. Chưa có metrics precision/recall hay drift thực vì chưa có pipeline
nhãn và dữ liệu tham chiếu. Score/decision là tín hiệu vận hành, không thay thế chất lượng model.

## GitHub Actions, SonarQube và Trivy

CI chạy lint/tests/coverage, render Kubernetes và validate Terraform. Build một image,
scan HIGH/CRITICAL bằng Trivy, rồi push chính image đã scan lên GHCR khi push vào `main`.
PR chỉ build/scan, không push/deploy. Scan lỗi sẽ chặn publish.
Dependency hiện khai báo khoảng phiên bản; cần khóa dependency sau khi tích hợp mã train
và chốt môi trường để tái lập image/model đầy đủ.

Repository variable `SONAR_ENABLED=true` bật SonarQube quality gate cho push `main`;
cần `SONAR_HOST_URL` và secret `SONAR_TOKEN`. Khi chưa có server, bước này được bỏ qua
rõ ràng qua điều kiện workflow. Tạo project Sonar có key khớp cấu hình.

Tạo GitHub Environments `test` và `production`; đặt required reviewers cho production.
Mỗi environment cấu hình secret `KUBECONFIG`, `MODEL_MANIFEST_JSON` cùng variables
MLflow/Ingress/pull secret theo bảng trên. Kubeconfig là nội dung YAML, không phải base64.
Bật repository variable `ENABLE_TEST_DEPLOY=true` sau khi test infrastructure và model đã sẵn sàng
để tự deploy test sau CI. Production chạy bằng workflow dispatch với digest đã scan;
cấu hình bảo vệ environment là trách nhiệm của repository admin.
Workflow đợi readiness, thất bại nếu rollout không thành công; không tự rollback
để tránh che khuất lỗi triển khai. Chưa chạy workflow trên GitHub.

## Load testing

Tạo JSON payload tổng hợp khớp model thật rồi chạy vào môi trường test được cho phép:

```powershell
$env:LOCUST_PAYLOAD_FILE = 'artifacts/synthetic-payload.json'
New-Item -ItemType Directory -Force reports
locust -f load_testing/locustfile.py --host http://127.0.0.1:8000 --headless --users 20 --spawn-rate 2 --run-time 2m --csv reports/load --html reports/load.html
```

Đây là mức tải minh họa, chưa phải benchmark đã chạy. Thu thập throughput, tỷ lệ lỗi,
p50/p95/p99 cùng replica và tài nguyên từ Grafana. Chạy tăng tải theo từng mức và
quan sát scale in sau tải ít nhất bằng cửa sổ stabilization 300 giây. Lưu cấu hình,
thời điểm, image/model version và giới hạn tài nguyên cùng báo cáo.

## Kiểm chứng bước khởi tạo

Đã chạy trong Conda `fraud-mlops`, Python 3.11.18, MLflow 3.17.2:

- 28 tests vượt qua; coverage phần `fraud_detection` đạt 98%, gồm MLflow save/load
  bằng model tổng hợp và API TestClient. Đây không phải accuracy của model fraud.
- Ruff lint và kiểm tra định dạng vượt qua; editor không báo lỗi trong mã nguồn,
  tests hoặc renderer.
- Terraform test và production đều `init -backend=false` và `validate` thành công;
  kiểm tra định dạng cũng vượt qua. Chưa plan/apply lên cluster.
- Parse thành công 14 file YAML cùng JSON dashboard; render thực bằng kubectl cho
  cả test/production thành công, gồm image digest, manifest theo hash và TLS production.
- `docker compose config --quiet` thành công. Docker daemon chưa chạy nên chưa
  build image, chạy Compose hoặc quét image cục bộ.
- Dataset cục bộ được `git check-ignore` xác nhận loại khỏi Git. Đã khởi tạo Git;
  chưa commit, tạo GitHub repository hoặc push.

Tests còn cảnh báo từ thư viện về TestClient/httpx và type hints của model tổng hợp;
không có test thất bại. Chưa chạy CI trên GitHub, deploy Kubernetes, load test hay
đánh giá model thật. Cấu hình hạ tầng cần được kiểm chứng trên cluster đã chọn.

## Thứ tự tiếp theo

1. Thêm file train; xác minh schema dữ liệu và cách chia tập trước khi tích hợp MLflow.
2. Chốt threshold, dependency và tiêu chí chấp nhận model bằng kết quả thật.
3. Chọn cluster, registry, MLflow backend/artifact store, domain và secrets.
4. Build/scan image, deploy test, kiểm tra metrics và load test để hiệu chỉnh HPA.
5. Xem xét bảo mật, rollback và kết quả kiểm chứng trước khi triển khai production.

Tài liệu tham chiếu: [MLflow pyfunc](https://mlflow.org/docs/latest/api_reference/python_api/mlflow.pyfunc.html),
[FastAPI lifespan](https://fastapi.tiangolo.com/advanced/events/),
[Kubernetes HPA](https://kubernetes.io/docs/tasks/run-application/horizontal-pod-autoscale-walkthrough/),
[Prometheus Operator](https://github.com/prometheus-operator/prometheus-operator/blob/main/Documentation/developer/getting-started.md),
[GitHub image publishing](https://docs.github.com/en/actions/tutorials/publish-packages/publish-docker-images).
