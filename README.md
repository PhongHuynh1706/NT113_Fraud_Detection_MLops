# MLOps Fraud Detection

Dự án phát hiện gian lận với scikit-learn, MLflow, FastAPI, Docker và GitHub Actions; có cấu hình Kubernetes HPA, Prometheus/Grafana, Terraform và Locust cho giai đoạn triển khai sau.

## 1. Trạng thái và cách dùng hướng dẫn

Hướng dẫn này mô tả **kiểm tra thủ công trên máy local**. Các lệnh bên dưới là quy trình để người dùng chạy, không phải tuyên bố mọi lệnh đã được thực thi lại khi viết README. Không cần train lại chỉ để xem model.

- Model đang chọn: **FraudDetection v2**, Extra Trees 200 cây, threshold `0.27963616586275475`.
- Test ULB đã đo: precision **84,7826%**, recall **75%**, F1 **0,79592**, AP **0,78188**, accuracy **99,9516%**; confusion matrix `[[41291,7],[13,39]]`.
- Đã thử thêm 4 cấu hình rồi 3 cấu hình: không vượt điều kiện cải thiện nên không đăng ký version mới hoặc build Docker mới cho các candidate đó.
- V1/v2 đã có trong MLflow server local cổng5000. Model v2 đã kiểm tra HTTP API trên host; container từng được kiểm chứng với v1. **Chưa xác minh container v2 bằng các bước dưới đây.**
- CI tự build/scan image API theo sự kiện GitHub; **đã nối train cải thiện → đăng ký → build image local chứa model** trong script thử nghiệm. CI thông thường vẫn build image API riêng theo commit.
- Chưa triển khai cluster/production trong phạm vi hiện tại. Không chạy deploy workflow, Terraform apply hay kubectl apply khi làm theo bài kiểm tra local này.

Luồng cần hiểu:

```text
Raw data → kiểm tra/làm sạch → train/validation/test theo thời gian
         → train và chọn model/threshold trên validation
         → đánh giá model đã khóa trên test → gate → MLflow Registry
         → chọn manifest/version cụ thể → API → Docker → smoke test/scan
         → [giai đoạn sau: triển khai, giám sát, load test autoscaling]
```

Mỗi mũi tên là một bước kiểm soát riêng. Đăng ký model không tự đổi model API đang chạy; build image không chứng minh chất lượng model; readiness200 không chứng minh precision tốt.

## 2. Chuẩn bị môi trường và kiểm thử mã

Mở PowerShell tại thư mục gốc:

```powershell
Set-Location D:/MLops_Fraud_Detection
conda activate fraud-mlops
Get-Command python
python --version
python -m pip show scikit-learn mlflow
```

**Quan sát:** interpreter thuộc môi trường `fraud-mlops`, không phải Conda base. Môi trường đã dùng huấn luyện là Python3.11.18, scikit-learn1.9.1, MLflow3.17.2; server Docker dùng MLflow3.18.0. Xem dependency thực tế trong artifact từng run khi so sánh môi trường. Dự án khai báo Python>=3.11,<3.14; CI hiện kiểm tra3.11, chưa xác nhận mọi runtime trong khoảng này.

Chỉ cài nếu môi trường thiếu package/project chưa được cài editable:

```powershell
python -m pip install -e '.[dev,load]'
```

**Tại sao:** editable giúp import mã trong [src/](src/) khi chạy module. Không tự cài lại môi trường đã hoạt động vì có thể đổi dependency. Khai báo tại [pyproject.toml](pyproject.toml); dependency runtime chưa được khóa toàn bộ.

Đặt file tạm ở ổD, rồi kiểm tra mã trước khi train:

```powershell
New-Item -ItemType Directory -Force artifacts/test-tmp | Out-Null
$env:TEMP = 'D:/MLops_Fraud_Detection/artifacts/test-tmp'
$env:TMP = $env:TEMP
$env:PYTHONIOENCODING = 'utf-8'
python -m ruff check .
python -m ruff format --check .
python -m pytest --cov=fraud_detection --cov-report=xml --cov-report=term-missing --cov-fail-under=80
```

**Quan sát:** tests/lint phải đạt; coverage là tỷ lệ mã được kiểm tra, **không phải accuracy model**. Bộ test đầy đủ gần nhất đã ghi nhận39 passed/coverage93,45%; sau thêm CLI chọn cấu hình, test selection riêng1 passed và Ruff đạt. Chạy lệnh trên để biết kết quả hiện tại của checkout của bạn.

## 3. Kiểm tra dữ liệu và mở đúng MLflow backend

```powershell
Test-Path dataset/creditcard.csv
Get-FileHash dataset/creditcard.csv -Algorithm SHA256
Get-Content configs/training.json -Raw
```

**Quan sát:** file tồn tại; SHA256 bản đã dùng:

```text
76274b691b16a6c49d3f159c883398e03ccd6d1ee12d9d8ee38f4b4b98551a89
```

Dataset ULB/Worldline:284807 dòng/492 fraud trước làm sạch. Pipeline kiểm tra schema/nhãn/số hữu hạn, giữ Time sớm nhất cho mỗi vector29 feature trùng, còn275663 dòng/473 fraud. Input `V1`–`V28`,`Amount`; `Class` là nhãn; `Time` chỉ chia tập, không đưa vào model.

| Tập | Dòng | Fraud | Time |
|---|---:|---:|---|
| Train | 192963 | 365 | 0–132628 |
| Validation | 41350 | 56 | 132629–151045 |
| Test | 41350 | 52 | 151046–172792 |

**Tại sao:** chia thời gian mô phỏng dự đoán tương lai, không tách cùng timestamp. Loại vector lặp giảm nguy cơ cùng đầu vào xuất hiện ở nhiều tập. Không resample validation/test. Dataset chỉ hai ngày năm2013, không có customerID hoặc raw-to-PCA transform; chưa chứng minh dùng được với giao dịch thật hiện tại.

Mở Docker Desktop, chỉ bật dịch vụ MLflow:

```powershell
docker compose -f docker/compose.yaml up -d mlflow
Invoke-RestMethod http://127.0.0.1:5000/health
```

**Quan sát:** health thành công, mở [MLflow UI](http://localhost:5000). Lệnh này không build API hoặc triển khai hạ tầng ngoài máy. Compose tại [docker/compose.yaml](docker/compose.yaml) lưu DB/artifacts trong named volume `mlflow-data`.

Có hai backend khác nhau:

| Backend | URI | Ý nghĩa |
|---|---|---|
| Server Docker/UI5000 | `http://127.0.0.1:5000` | Backend CLI train mặc định; dùng để xem các run mới |
| SQLite host cũ | `sqlite:///D:/MLops_Fraud_Detection/artifacts/mlflow.db` | Lưu lịch sử ban đầu; không tự xuất hiện trong UI Docker |

V1/v2 đã được copy sang server bằng [sync_mlflow.py](workflow/sync_mlflow.py), không train lại. Không chạy sync mỗi lần train HTTP. Nếu UI trống, kiểm tra backend/volume/experiment trước, không train lại để chữa lỗi hiển thị. Không dùng `docker compose down -v`: tùy chọn đó xóa volume dữ liệu.

## 4. Train một run mới — chỉ khi thực sự cần

Đọc [training.json](configs/training.json) và [train.py](src/fraud_detection/train.py) trước khi đổi cấu hình. Để kiểm tra model hiện có, bỏ qua mục này và sang mục5.

```powershell
python -m fraud_detection.train --config configs/training.json --output artifacts/manual-training --tracking-uri http://127.0.0.1:5000
```

**Lệnh làm gì:** đọc raw data, làm sạch/chia tập, train candidate, chọn threshold trên validation, đánh giá test, log params/metrics/schema/dependency/source/fingerprint, kiểm tra serialize/load và đăng ký Registry nếu đạt gate. Thư mục output riêng giúp không thay manifest mặc định đang dùng. **Registry vẫn tạo version tiếp theo nếu đạt gate**, dù cấu hình giống v2.

**Vì sao cần validation:** threshold quyết định đánh đổi FP/FN; chọn nó theo test sẽ làm kết quả cuối lạc quan. Cấu hình hiện chọn threshold tối ưu F1 với validation recall>=80%, precision>60%, ít nhất20 cảnh báo. Không sửa ngưỡng sau khi xem test.

**Gate train mặc định:** accuracy>60%, precision>60%, vượt baseline về F1/AP. Gate này kiểm tra mức tối thiểu, **không có nghĩa tốt hơn v2**. Khi không đạt, script báo lỗi, lưu report nhưng không đăng ký; đọc report trước khi kết luận pipeline hỏng.

**Đầu ra:** `artifacts/manual-training/training/<run_id>/report.json`, cấu hình, dependency, model và manifests; manifest tổng tại `artifacts/manual-training/manifest.json` và `manifest.registry.json` nếu thành công. Dùng runID console/UI, không đoán version mới.

## 5. Xem run và đánh giá thủ công

Trong [MLflow UI](http://localhost:5000):

1. Chọn experiment `fraud-ulb-chronological`; mở run v2 trên server `02cd901aab2c499bb0c67612aeec54c4`. Run SQLite gốc là `e69e67d42b464b51b351b91f9399e409`; tag `origin_run_id` giúp truy vết việc copy.
2. Xem Params: dữ liệu/fingerprint, seed, thuật toán, threshold. Xem Artifacts: cấu hình, dependency, report, signature/model. Run được copy có thể có bố cục artifact khác run train trực tiếp.
3. Xem Metrics có tiền tố validation/test/baseline; so sánh cùng dataset và protocol. Với thử nghiệm bổ sung, mở experiment `fraud-ulb-improvements`, parent run chứa test/report; child run chứa validation từng trial.
4. Chọn run và Compare để xem chênh lệch; chỉ so sánh test của candidate đã khóa, không thử test mọi model rồi chọn model đẹp nhất.
5. Vào Registered Models → FraudDetection → version2, kiểm tra source run, trạng tháiREADY và schema. Một training run không đạt gate vẫn có thể tồn tại mà không có Registry version.

Đọc report v2 trực tiếp, không cần train:

```powershell
$reportPath = 'artifacts/training/e69e67d42b464b51b351b91f9399e409/report.json'
Get-Content $reportPath -Raw -Encoding UTF8 | ConvertFrom-Json | Format-List
Get-Content artifacts/manifest.registry.json -Raw -Encoding UTF8
```

Với run mới, thay reportPath bằng đường dẫn console đã in. Đối chiếu:

| Chỉ số | V2 test | Ý nghĩa đánh giá |
|---|---:|---|
| Accuracy | 99,9516% | Baseline luôn hợp lệ cũng99,8742%; không kết luận bằng accuracy |
| Precision | 84,7826% | 39 đúng trên46 cảnh báo |
| Recall | 75% | Bắt39/52 fraud, bỏ sót13 |
| F1 | 0,79592 | Cân bằng precision/recall tại threshold đã khóa |
| AP (`pr_auc`) | 0,78188 | Average Precision; đánh giá xếp hạng lớp fraud |
| ROC-AUC | 0,91844 | Chỉ số phụ, không thay F1/AP/FP/FN |
| Confusion matrix | `[[41291,7],[13,39]]` | Thứ tự `[[TN,FP],[FN,TP]]`;7 cảnh báo sai |

**Giới hạn:** test đã được xem nhiều đợt, không còn là holdout mới độc lập. Chỉ52 fraud nên một trường hợp làm recall đổi khoảng1,92 điểm phần trăm. Không tuyên bố sẵn sàng production từ các con số này.

## 6. Thử cải thiện và quyết định có đóng Docker hay không

Không chạy lại chỉ để xem lịch sử. Khi muốn thực hiện một đợt mới:

```powershell
python -m workflow.improve_model --config configs/improvement-round2.json
```

Script [improve_model.py](workflow/improve_model.py) dùng cấu hình trial riêng, đối chiếu fingerprint với Registry v2, train trên train, chọn một winner theo F1 validation/AP, chỉ đánh giá winner trên test. **Chạy lại lệnh vẫn tạo run mới**, không chỉ mở report cũ.

Docker Desktop cần chạy nếu candidate vượt gate. Gate cải thiện: F1 test phải tăng so với v2, recall>=75%, precision>60%, accuracy>60%. Nếu đạt, script đăng ký version và xuất manifest riêng dưới `artifacts/improvements/<parent_run_id>/`; không tự thay manifest mặc định hoặc gán production alias. Nếu không đạt: giữ v2, dừng trước bước đóng Docker cho candidate. Script **tự build Docker sau khi đăng ký và kiểm chứng reload thành công**. Không vượt gate thì Docker không được gọi.

| Kết quả đợt đã chạy | V2 | Winner đợt4 trial | Winner đợt3 trial |
|---|---:|---:|---:|
| Precision test | 84,78% | 84,78% | 78% |
| Recall test | 75% | 75% | 75% |
| F1 test | 0,79592 | 0,79592 | 0,76471 |
| AP test | 0,78188 | 0,77550 | 0,77523 |
| Đăng ký version mới | Đã có v2 | Không | Không |

Parent run tương ứng `812c66df14944e20b88b74cab91fdccb` và `0b7f43023b444091b50dcf3292ae2c92`. Nhật ký chi tiết local tại [training-log.md](docs/training-log.md); docs và artifacts bị Git ignore, nên link có thể không tồn tại ở clone mới.

## 7. Chọn model cụ thể và chạy API trên host

Dùng local manifest hiện có để kiểm tra offline với artifact đã xuất:

```powershell
Get-Content artifacts/manifest.json -Raw
$env:MODEL_MANIFEST = 'D:/MLops_Fraud_Detection/artifacts/manifest.json'
python -m uvicorn fraud_detection.api:app --host 127.0.0.1 --port 18001 --no-access-log
```

Hoặc kiểm tra tải đúng model từ Registry: dừng API bằng Ctrl+C rồi chạy lại với:

```powershell
$env:MLFLOW_TRACKING_URI = 'http://127.0.0.1:5000'
$env:MODEL_MANIFEST = 'D:/MLops_Fraud_Detection/artifacts/manifest.registry.json'
python -m uvicorn fraud_detection.api:app --host 127.0.0.1 --port 18001 --no-access-log
```

**Tại sao hai cách:** local kiểm tra artifact có thể load trực tiếp; Registry kiểm tra thêm kết nối backend/artifact store và version cụ thể. Manifest phải ghép đúng URI/version/threshold/features; không đổi riêng nhãn version. Model load một lần khi startup, thay manifest phải restart. Ứng dụng không tự đọc `.env`.

Giữ terminal server mở. Trong **PowerShell thứ hai**, kiểm tra:

```powershell
Invoke-RestMethod http://127.0.0.1:18001/health/live
Invoke-RestMethod http://127.0.0.1:18001/health/ready
$row = @{}
1..28 | ForEach-Object { $row["V$_"] = 0.0 }
$row['Amount'] = 0.0
$body = @{ instances = @($row) } | ConvertTo-Json -Depth 4
$result = Invoke-RestMethod -Method Post -Uri http://127.0.0.1:18001/predict -ContentType 'application/json' -Body $body
$result | ConvertTo-Json -Depth 5
(Invoke-WebRequest http://127.0.0.1:18001/metrics -UseBasicParsing).Content
```

**Quan sát:** live/ready200; `model_version` phải là version đã chọn (hiện2), threshold đúng manifest; một prediction có `fraud_probability` trong[0,1], `is_fraud` bằng `score>=threshold`. `/metrics` có `fraud_model_ready 1`, số request và latency. Mở Swagger tại `http://127.0.0.1:18001/docs` nếu muốn gửi tay.

Payload trên là29 số tổng hợp để kiểm tra hợp đồng, không dùng giao dịch thật và **không đo precision/recall**. API nhận1–256 dòng/batch; thiếu/thừa feature, chuỗi/bool, NaN/Infinity hoặc batch rỗng phải bị từ chối.

Thử schema sai (PowerShell sẽ hiện lỗi HTTP422, đây là kết quả mong đợi):

```powershell
Invoke-WebRequest -Method Post -Uri http://127.0.0.1:18001/predict -ContentType 'application/json' -Body '{"instances":[{"Amount":0}]}' -UseBasicParsing
```

Để thử trạng thái chưa có model: Ctrl+C, `Remove-Item Env:MODEL_MANIFEST -ErrorAction SilentlyContinue`, khởi động lại server. Live vẫn200, ready503; predict với payload hợp lệ trả503. Cần phân biệt process còn sống với model đã sẵn sàng phục vụ.

## 8. Build Docker và kiểm tra local — bước thủ công tùy chọn

Chỉ làm mục này khi chủ động muốn kiểm chứng một model đã chọn. Hai đợt cải tiến gần nhất không đạt nên không cần build candidate. Không dùng lệnh Compose khởi động toàn bộ API với manifest Windows: đường dẫn `D:/...` không có nghĩa trong container Linux.

Ví dụ dưới đây kiểm tra **v2 đã có**, mount Registry manifest readonly; model không được COPY vào image. Nếu chọn version khác, tạo manifest riêng từ artifact của version đó và sửa tag/đường dẫn tương ứng.

```powershell
docker build -f docker/Dockerfile -t fraud-api:manual-v2 .
docker run --detach --name fraud-api-manual-v2 --publish 127.0.0.1:18002:8000 --env MODEL_MANIFEST=/models/manifest.registry.json --env MLFLOW_TRACKING_URI=http://host.docker.internal:5000 --mount "type=bind,source=D:/MLops_Fraud_Detection/artifacts/manifest.registry.json,target=/models/manifest.registry.json,readonly" fraud-api:manual-v2
python workflow/smoke_container.py --url http://127.0.0.1:18002 --manifest artifacts/manifest.registry.json
docker logs fraud-api-manual-v2
```

**Tại sao:** build kiểm tra dependency/API chạy trên Linux; mount manifest tránh nhúng đường dẫn host và tách model khỏi image. `host.docker.internal` là địa chỉ host từ Docker Desktop, còn localhost trong container là chính container. MLflow local phải đang chạy và truy cập được từ container. Nếu tên container đã tồn tại, kiểm tra container cũ trước hoặc chọn tên khác, không xóa nhầm service đang dùng.

**Quan sát:** smoke kiểm tra live/ready200, predict200 đúng version, score hợp lệ và metrics200. Smoke không đo chất lượng fraud detection. Nếu kết nối MLflow qua Docker Desktop bị từ chối do binding/network, xem health/logs và xác minh đường kết nối; không sửa allowed-hosts thành wildcard hoặc public server chỉ để vượt test. Một lựa chọn khác là local model mount dưới `/models` cùng manifest có URI Linux tương ứng; không sửa manifest gốc đang dùng.

Nếu đã có Trivy CLI local:

```powershell
trivy image --severity HIGH,CRITICAL --scanners vuln --exit-code 1 fraud-api:manual-v2
```

**Quan sát:** exit0 là không có phát hiện HIGH/CRITICAL theo database scan lúc chạy; exit1 cần xem chi tiết và cập nhật dependency/OS phù hợp, không mặc định bỏ qua. Chưa có Trivy local có thể kiểm tra bước scan CI; không ghi nhận local scan đạt nếu chưa chạy.

Dọn đúng container thử nghiệm sau khi xem kết quả:

```powershell
docker stop fraud-api-manual-v2
docker rm fraud-api-manual-v2
```

Giữ image nếu cần lặp lại. Không chạy prune toàn bộ hoặc xóa volume MLflow. Rollback local bằng chọn lại manifest/version cũ phù hợp schema rồi restart API/container, không ghi đè Registry version cũ. Image và manifest cần được ghi cùng run/version/threshold trong biên bản kiểm tra.

## 9. CI/CD hiện làm gì và kiểm tra tay ở đâu

Đọc [ci.yaml](.github/workflows/ci.yaml) để đối chiếu checkout hiện tại:

1. PR, push main hoặc Run workflow kích hoạt lint/tests/coverage. Push/manual chạy SonarQube Cloud và đợi Quality Gate; PR hiện bỏ qua Sonar. Cần secret `SONAR_TOKEN`; `SONAR_HOST_URL` mặc định `https://sonarcloud.io`. Không có công tắc `SONAR_ENABLED` trong workflow hiện tại.
2. Sonar dùng [sonar-project.properties](sonar-project.properties): projectKey `PhongHuynh1706_NT113_Fraud_Detection_MLops`, organization `phonghuynh1706`, coverage từ `coverage.xml`. Kiểm tra log upload rồi Quality Gate và trang Issues/Coverage; upload thành công chưa có nghĩa gate đạt.
3. CI render Kustomize để kiểm tra manifests; Terraform không chạy trong CI, kiểm tra thủ công theo Terraform README. Khi job test đạt, job image build một image, smoke không có model (ready503 là mong đợi), scan Trivy HIGH/CRITICAL.
4. Chỉ sự kiện push publish image đã scan lên GHCR theo commitSHA; PR/manual không publish. Xem digest trong log publish để truy vết image chính xác.
5. CI hiện không gọi deploy-test sau push để giữ phạm vi chưa thay đổi hạ tầng thực tế. [deploy.yaml](.github/workflows/deploy.yaml) vẫn là workflow riêng có thao tác apply thật khi được chạy với đủ cấu hình; chưa chạy workflow đó.

CI không train raw dataset local và không kiểm tra candidate có tốt hơn v2. Vì vậy CI xanh không tự đồng nghĩa một model mới đã được đánh giá/đóng gói/triển khai. Không push chỉ để xem model; push main có thể publish image; CI hiện không tự deploy.

## 10. Metrics và load test local tùy chọn

Mở `/metrics` của API đã ready. Code hiện xuất request/status, histogram latency, phân bố score, decision counts và readiness. Các metric này trả lời service có chạy/nhanh/lỗi không; precision/recall cần nhãn thật đủ độ trễ, hiện chưa có pipeline online đó.

Để load test local khi máy đủ tài nguyên, tạo payload tổng hợp UTF8 không BOM rồi bắt đầu mức thấp:

```powershell
$row = @{}
1..28 | ForEach-Object { $row["V$_"] = 0.0 }
$row['Amount'] = 0.0
$payloadJson = @{ instances = @($row) } | ConvertTo-Json -Depth 4
[System.IO.File]::WriteAllText('D:/MLops_Fraud_Detection/artifacts/synthetic-payload.json', $payloadJson, [System.Text.UTF8Encoding]::new($false))
$env:LOCUST_PAYLOAD_FILE = 'D:/MLops_Fraud_Detection/artifacts/synthetic-payload.json'
New-Item -ItemType Directory -Force artifacts/load-reports | Out-Null
locust -f load_testing/locustfile.py --host http://127.0.0.1:18001 --headless --users 2 --spawn-rate 1 --run-time 30s --csv artifacts/load-reports/local --html artifacts/load-reports/local.html
```

**Quan sát:** throughput, failure rate, p50/p95/p99 trong console/CSV/HTML. Ghi model/image version, số user, thời lượng và cấu hình máy cùng kết quả. Mức tải trên chỉ minh họa, không phải benchmark đã đo. Local một process/container không chứng minh HPA scale được; không chạy vào production hoặc endpoint ngoài phạm vi được phép.

## 11. Hạ tầng giai đoạn sau — chỉ xem cấu hình

- [K8s/](K8s/) có Deployment/Service/Ingress và HPA CPU/memory. [Terraform AWS/EKS](terraform/README.md) đã tách module VPC, networking, security groups, IAM, EKS và managed nodes; main của test/production chỉ gọi module. Namespace fraud-test/fraud-production được gọi trong cùng root môi trường qua manage_namespace sau khi cluster sẵn sàng; thêm module ECR cho image, S3 cho models/dataset, nodes cố định Ubuntu24.04 EKS/t3.large. Chưa plan/apply AWS thật; xem cảnh báo state migration trong hướng dẫn trước khi dùng root AWS mới.
- [Monitoring](K8s/monitoring/) có ServiceMonitor, alerts/dashboard; cần Prometheus Operator, Grafana và cấu hình phù hợp cluster trước khi dùng. Metrics Server cấp metric HPA; không dùng KEDA đồng thời để điều khiển cùng workload.
- Renderer [render.py](workflow/render.py) yêu cầu GHCR image digest, manifest Registry version số khớp nhau, địa chỉ MLflow từ Pod, Ingress host/class, TLS secret cho production và imagePullSecret khi cần. Base còn placeholder, không apply trực tiếp.
- Cần chọn cluster, registry access, backend/artifact store, backup/secrets, tài nguyên và mục tiêu latency trước triển khai. Khi có cluster test được cho phép mới đo replica, CPU/memory và scale out/in bằng Locust; con số autoscaling trong YAML chỉ là cấu hình ban đầu.
- Rollback sau này cần ghép image digest, model version, threshold và runtime config; giữ revision/ConfigMap cũ. Chưa kiểm chứng rollback cluster trong hướng dẫn local này.

## 12. Biên bản đánh giá mỗi lần chạy

Ghi lại runID/experiment/backend, datasetSHA, commit và trạng thái working tree, cấu hình/seed/dependency; validation threshold và quy tắc chọn; test metrics/confusion matrix; Registry version hoặc lý do không đăng ký; image tag/digest nếu build; health/predict/schema/metrics/scan; phần chưa kiểm chứng và quyết định giữ/đổi model. Không ghi payload giao dịch/PII/secrets vào biên bản.

[Nhật ký local](docs/training-log.md) là ví dụ đã tổng hợp các lần train. Raw [dataset/](dataset/), [artifacts/](artifacts/), [docs/](docs/) và AGENTS.md đang được Git ignore theo yêu cầu; clone mới cần dataset/artifact được cung cấp riêng. README này được quản lý trong Git, không phụ thuộc việc phải train lại mới hiểu quy trình.


### Image tự động sau cải thiện

Lệnh `python -m workflow.improve_model --config configs/improvement-round2.json` nay thực hiện nối tiếp: chọn winner → đánh giá gate → đăng ký Registry → xuất/load lại model → build image local. Không cần chạy lệnh build riêng khi run thành công. Không có candidate đủ điều kiện thì `report.image.status=skipped` và không gọi Docker.

[build_model_image.py](workflow/build_model_image.py) build runtime từ Dockerfile hiện có, sau đó tạo image chứa riêng model đã xuất và manifest Linux `/opt/fraud/manifest.json`. Context đóng gói chỉ chứa model/manifest/Dockerfile, không nới `.dockerignore` để đưa raw dataset vào image. Tag là `fraud-api:v<version>-<parent_run_id>`; labels ghi version/run. `image.json` và report lưu imageID/tag/version, log tại `docker-build.log`; run MLflow thành công có các artifact này. Không push image, không tự start container/deploy, không sửa manifest mặc định hoặc production alias.

Nếu build lỗi, tiến trình exit khác0, report ghi `image.status=failed`; model đã đăng ký vẫn được giữ, không rollback/xóa version. Sau khi sửa Docker/dependency, chỉ retry build từ report của chính run đó, không retrain:

```powershell
# Thay RUN_ID bằng parent run đã đạt gate và đăng ký/load lại thành công.
python -m workflow.build_model_image --report artifacts/improvements/RUN_ID/report.json
```

Lệnh retry cập nhật report/image/log cục bộ; không tự đồng bộ lại artifact MLflow. Report run không đạt gate vẫn bị bỏ qua. Image cần được smoke test và Trivy scan trước khi cân nhắc sử dụng; build thành công chưa có nghĩa scan hoặc chất lượng vận hành đạt.

Để kiểm tra image vừa build mà không cần kết nối MLflow (thay tag bằng giá trị `image.tag` trong report):

```powershell
docker run --detach --name fraud-api-improved-check --publish 127.0.0.1:18003:8000 fraud-api:vVERSION-RUN_ID
python workflow/smoke_container.py --url http://127.0.0.1:18003 --manifest artifacts/improvements/RUN_ID/manifest.local.json
trivy image --severity HIGH,CRITICAL --scanners vuln --exit-code 1 fraud-api:vVERSION-RUN_ID
docker stop fraud-api-improved-check
docker rm fraud-api-improved-check
```

Các tag/RUN_ID trên là placeholder cần thay, không phải version mới đã tạo. Hiện các candidate đã train vẫn không vượt v2 nên chưa có image từ nhánh thắng thực tế; tests dùng giả lập subprocess Docker để kiểm tra gate/đóng gói/lỗi, không giả lập metrics thành kết quả model mới.
