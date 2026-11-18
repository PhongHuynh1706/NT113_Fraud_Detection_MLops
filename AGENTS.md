# Hướng dẫn cho agent — MLOps Fraud Detection

## Mục tiêu

Xây dựng nền tảng MLOps trên Kubernetes hỗ trợ tự động triển khai và mở rộng model phát hiện gian lận:

- Xây dựng model với accuracy > 60% trên tập test độc lập; đóng gói model và inference API bằng Docker, quản lý source code bằng GitHub.
- Xây dựng CI/CD bằng GitHub Actions để tự động kiểm thử, build Docker image và triển khai model.
- Sử dụng MLflow để quản lý experiment, phiên bản model và Model Registry.
- Triển khai Model Serving bằng Kubernetes Deployment, Service và Ingress.
- Sử dụng HPA hoặc KEDA để scale Pod theo CPU, memory hoặc lưu lượng request, tùy nguồn metric được cấu hình.
- Tích hợp Prometheus và Grafana để giám sát tài nguyên Kubernetes, request, latency và hiệu năng model khi có nhãn.
- Dùng Locust để load test và đánh giá khả năng mở rộng khi lưu lượng tăng.
- Sử dụng SonarQube để phân tích chất lượng mã, Trivy để quét image và Terraform để quản lý hạ tầng.

## Cấu trúc dự kiến

```text
.github/workflows/          # Workflow CI/CD được GitHub Actions thực thi
workflow/                  # Script hỗ trợ và tài liệu CI/CD nếu cần
configs/                   # Cấu hình huấn luyện
docs/                      # Báo cáo model và hướng dẫn kiểm tra tay
dataset/                   # Raw dataset cục bộ, không commit
artifacts/                 # Model, manifest và MLflow cục bộ, không commit
src/                       # Training, preprocessing và inference API
tests/                     # Kiểm thử dữ liệu, model và API
docker/                    # Dockerfile và cấu hình build image
terraform/
  modules/                 # Module cho từng thành phần hạ tầng
  environments/
    test/                  # Cấu hình môi trường test
    production/            # Cấu hình môi trường production
load_testing/              # Kịch bản Locust
K8s/                       # Deployment, Service, Ingress, HPA/KEDA,
                           # cấu hình Prometheus và Grafana
```

Chỉ tạo thư mục và dependency khi công việc thực tế cần đến. Cấu trúc trên là định hướng, không khẳng định các thành phần đã có.
MLflow, Docker, Kubernetes và các công cụ nêu trên đã được chọn cho dự án. Không tự chọn thêm DVC hoặc nhà cung cấp cloud.
SonarQube không thay thế kiểm thử model. Trivy được chạy trong CI/CD để quét image; đặt cấu hình công cụ theo yêu cầu thực tế.

## Môi trường phát triển

- Dùng môi trường Anaconda tên `fraud-mlops` theo lựa chọn của người dùng.
- Đã xác minh môi trường dùng Python 3.11.18.
- Xác minh interpreter và dependency thực tế trước khi chạy mã hoặc cài package.
- Dependency được khai báo trong [pyproject.toml](./pyproject.toml); đã huấn luyện với scikit-learn 1.9.1 và MLflow 3.17.2. Phiên bản dependency của run được lưu trong artifact.
- Không thay đổi môi trường Conda base khi làm việc cho dự án.

## Khi thay đổi hoặc bổ sung mã huấn luyện

1. Đọc mã train và tài liệu hiện có trước khi sửa cấu trúc hoặc hành vi.
2. Xác định entry point, dependency, đầu vào, nhãn, đặc trưng, cách chia tập, seed và đầu ra model từ mã thực tế; hỏi nếu thông tin quan trọng còn thiếu.
3. Ghi lại lệnh chạy và cấu hình đã kiểm chứng. Không ghi lệnh phỏng đoán như thể đã chạy thành công.
4. Giữ hành vi hiện tại khi tách mã thành pipeline; tránh viết lại toàn bộ nếu chỉ cần bổ sung tracking, kiểm thử hoặc đóng gói.
5. Tích hợp MLflow để ghi params, metrics, artifact, schema đầu vào và phiên bản model.
6. Cập nhật tài liệu này để phản ánh đường dẫn và công cụ thực tế.

Người dùng đã yêu cầu huấn luyện từ raw dataset. Pipeline hiện có tại
[train.py](./src/fraud_detection/train.py), cấu hình tại
[training.json](./configs/training.json), adapter xác suất tại
[probability_model.py](./src/fraud_detection/probability_model.py).
Không bịa metrics, không tự promote model sang production và không ghi đè version cũ.

Lệnh đã chạy thành công từ thư mục gốc dự án, trong Conda `fraud-mlops`:

```powershell
python -m fraud_detection.train --config configs/training.json
```

Nếu muốn dùng đúng backend đã tạo, chỉ định rõ:

```powershell
python -m fraud_detection.train --config configs/training.json --tracking-uri sqlite:///D:/MLops_Fraud_Detection/artifacts/mlflow.db
```

Lệnh chỉ định backend là cách chạy lại; không khẳng định đã chạy riêng lệnh đó.
Mỗi lần chạy huấn luyện tạo run mới và đăng ký version tiếp theo nếu đạt điều kiện.
Không chạy lại chỉ để xem model; dùng artifact đã xuất hoặc Registry.

## Dữ liệu và phòng tránh leakage

- Không commit dữ liệu giao dịch, PII, thông tin thẻ, token hoặc secrets. Dùng dữ liệu tổng hợp hoặc đã khử định danh cho ví dụ và kiểm thử.
- Kiểm tra schema, kiểu dữ liệu, giá trị thiếu, bản ghi trùng, tỷ lệ nhãn và các trường không hợp lệ; không tự đặt ngưỡng nghiệp vụ chưa được xác nhận.
- Chỉ sử dụng đặc trưng có sẵn tại thời điểm ra quyết định. Loại thông tin phát sinh sau giao dịch hoặc sau khi điều tra gian lận khỏi đầu vào model.
- Với dữ liệu giao dịch theo thời gian, ưu tiên chia train/validation/test theo thời gian; xem xét ranh giới khách hàng, tài khoản và giao dịch trùng.
- Fit preprocessing, chọn đặc trưng và resampling chỉ trên tập train. Không resample validation/test; giữ phân bố phục vụ đánh giá thực tế.
- Ghi nhận độ trễ và mức độ hoàn thiện của nhãn khi đánh giá.

## Huấn luyện và đánh giá

- Tách cấu hình khỏi logic; đặt seed khi thư viện hỗ trợ và ghi nhận các nguồn không xác định còn lại.
- So sánh với baseline phù hợp trước khi thêm độ phức tạp.
- Kiểm chứng yêu cầu accuracy > 60% bằng kết quả thực tế; không bịa metrics.
- Với nhãn mất cân bằng, báo cáo PR-AUC, precision, recall, F1 và confusion matrix; có thể bổ sung ROC-AUC, nhưng không dùng accuracy làm kết luận duy nhất.
- Chọn threshold trên validation theo chi phí false positive/false negative hoặc năng lực xử lý cảnh báo. Không mặc định threshold 0.5 là tối ưu.
- Giữ test làm tập đánh giá cuối; không dùng test để tuning hoặc chọn threshold.
- Accuracy > 60% là yêu cầu ban đầu, chưa đủ để kết luận model phù hợp production.

## Tái lập và quản lý artifact

- Ghi nhận phiên bản dữ liệu hoặc fingerprint, commit mã, cấu hình, dependency, seed, metrics và threshold cho mỗi lần chạy bằng MLflow.
- Lưu preprocessing và model tương thích cùng nhau; kèm schema đặc trưng, phiên bản và metadata cần thiết cho inference.
- Không tải artifact model từ nguồn không tin cậy; một số định dạng có thể thực thi mã khi deserialize.
- Quản lý phiên bản model bằng MLflow Model Registry; cấu hình nơi lưu artifact theo hạ tầng được chọn.
- Không ghi đè model đang dùng hoặc chuyển model sang production ngoài phạm vi yêu cầu.

## CI/CD và hạ tầng

- Đặt workflow thực thi của GitHub Actions trong `.github/workflows/`.
- Pipeline kiểm thử, chạy phân tích SonarQube, build và quét image bằng Trivy trước khi triển khai; định nghĩa quality gate khi có cấu hình thực tế.
- Gắn image với phiên bản truy vết được về commit; ưu tiên triển khai bằng digest.
- Quản lý secrets qua cơ chế phù hợp; không đưa credentials vào Git hoặc image.
- Tách Terraform module và cấu hình test/production; tách state giữa hai môi trường.
- Kiểm tra Terraform plan trước khi apply; không tự chọn cloud, tạo tài nguyên tính phí hoặc triển khai production khi chưa được cho phép trong phạm vi công việc.
- Ghi lại cách rollback image, model và cấu hình triển khai tương ứng.

## Inference, triển khai và giám sát

- Dùng cùng phép biến đổi đặc trưng giữa train và inference.
- Kiểm tra schema đầu vào, thứ tự đặc trưng và hành vi với dữ liệu lỗi.
- Cấu hình Deployment, Service, Ingress, readiness/liveness probe và resource requests/limits phù hợp với kết quả đo.
- Khi triển khai, ghi rõ phiên bản model, threshold, health check và cách rollback.
- Chọn HPA hoặc KEDA theo nhu cầu; tránh nhiều bộ điều khiển cùng điều chỉnh replica của một workload. Khai báo nguồn metric và dependency cần thiết.
- Theo dõi chất lượng dữ liệu, drift, latency, lỗi inference, phân bố score và tỷ lệ cảnh báo; đánh giá precision/recall khi có nhãn đủ độ trễ.
- Drift là tín hiệu điều tra; không tự retrain hoặc tự promote model chỉ vì drift.
- Logs và metric labels không chứa payload giao dịch đầy đủ hoặc dữ liệu nhận dạng cá nhân.

## Load testing

- Dùng Locust với dữ liệu tổng hợp hoặc đã khử định danh.
- Cấu hình số user, tốc độ tăng tải, thời lượng và endpoint qua tham số.
- Đo throughput, tỷ lệ lỗi, latency p50/p95/p99, replica và tài nguyên sử dụng.
- Đánh giá cả scale out và scale in; ghi nhận thời gian đáp ứng của autoscaler.
- Chỉ chạy vào môi trường và mức tải được cho phép; không mặc định load test production.
- Báo cáo kết quả đo thực tế, cấu hình chạy và giới hạn của phép thử.

## Quy tắc làm việc và kiểm thử

- Thực hiện thay đổi nhỏ, đúng phạm vi; đọc mã liên quan trước khi chỉnh sửa.
- Không chạy huấn luyện dài, tải dữ liệu lớn hoặc dùng dịch vụ tính phí khi chưa rõ phạm vi và tài nguyên người dùng cho phép.
- Khi có mã thực tế, kiểm thử các hành vi quan trọng: ranh giới chia tập, preprocessing chỉ fit trên train, schema đặc trưng, serialize/load model và tính nhất quán của inference.
- Kiểm thử API với đầu vào hợp lệ, không hợp lệ và trường hợp model chưa sẵn sàng.
- Chạy kiểm thử phù hợp với thay đổi. Báo rõ lệnh đã chạy, kết quả và phần chưa thể xác minh; không bịa metrics hoặc tuyên bố đã kiểm thử.
- Trao đổi và viết tài liệu bằng tiếng Việt, trừ khi người dùng yêu cầu khác.

## Trạng thái đã kiểm chứng

Khung nền tảng đã có: API đọc MLflow artifact, kiểm thử, Docker/Compose, GitHub Actions,
Kubernetes HPA, cấu hình giám sát, Terraform namespace và Locust.
Model thật đã được huấn luyện và đăng ký Registry cục bộ. Xem
[báo cáo v1](./docs/model-v1.md) để biết kết quả và hướng dẫn kiểm tra tay.
[README.md](./README.md) còn một số nội dung từ giai đoạn trước huấn luyện;
đối chiếu báo cáo v1 khi đọc thông tin về model. Chưa triển khai lên cluster hoặc GitHub.

- Dataset cục bộ: `dataset/creditcard_2026.csv`, 100.000 dòng, 43 cột, 2.055 nhãn fraud; chưa xác minh nguồn gốc và độ trễ nhãn.
- Nhãn: `is_fraud` (fraud = 1); chia theo `transaction_datetime`: 70.000 train, 15.000 validation, 15.000 test, không để cùng timestamp rơi vào hai tập.
- Loại `fraud_type`, `fraud_amount_lost`, các ID và biến lịch sử chưa xác minh khỏi đầu vào. Model v1 dùng 9 đặc trưng số trong cấu hình.
- Model v1: **Logistic Regression + StandardScaler**, class weight balanced; so sánh với HistGradientBoosting và baseline. Scaler chỉ fit trên train.
- Chọn model theo F1 validation, PR-AUC làm tiêu chí phụ; threshold **0,8528996455659125**, tối ưu F1 validation. Không chọn threshold theo test.
- Test v1: accuracy **95,84%**, precision **13,79%**, recall **19,42%**, F1 **0,16129**, average precision (metric `pr_auc`) **0,09737**, ROC-AUC **0,80112**.
- Confusion matrix theo thứ tự [hợp lệ, fraud]: `[[14316, 375], [249, 60]]`. Phát hiện 60/309 fraud, bỏ sót 249, có 375 cảnh báo sai.
- Baseline luôn dự đoán hợp lệ đạt accuracy **97,94%**, recall/F1 bằng 0. V1 đạt yêu cầu accuracy > 60% và cải thiện F1/average precision, nhưng recall và precision còn thấp, **chưa đủ cơ sở production**.
- Registry: `models:/FraudDetection/1`; run ID `8a5980d06a884a08b3afb9922847845c`.
- Model local: `artifacts/training/8a5980d06a884a08b3afb9922847845c/model/`; báo cáo JSON và dependency nằm cùng thư mục run.
- Manifest dùng local: `artifacts/manifest.json`; manifest Registry: `artifacts/manifest.registry.json`. Manifest local chứa đường dẫn tuyệt đối, phải điều chỉnh khi chuyển máy/container.
- Tracking/Registry: SQLite cục bộ `artifacts/mlflow.db`; artifact trong `artifacts/`. Đây là backend riêng với MLflow trong Docker Compose, dữ liệu không tự đồng bộ giữa hai backend.
- Đã kiểm chứng load lại model nhất quán trên 128 dòng, load Registry v1, API trả 200 với payload tổng hợp và scaler chỉ fit trên train.
- Lỗi MLflow int64/double ở lần xuất đầu đã sửa bằng chuẩn hóa đầu vào `float64`; chạy lại cùng cấu hình thành công. Có test hồi quy cho đầu vào JSON số nguyên.
- Sau thay đổi training: **31 tests vượt qua**, Ruff lint/format đạt. Sau sửa container đã build image Wolfi/Python 3.11.18, scan Trivy HIGH/CRITICAL exit 0 và chạy API local với model v1 thành công; xem [kiểm chứng container](./docs/container-validation.md). Chưa deploy Kubernetes hoặc load test với model v1.
- Dataset chứa timestamp tới 31/12/2026, sau ngày huấn luyện 18/11/2026; chỉ xem đây là đánh giá offline trên file được cung cấp. Có 6.817 khách hàng xuất hiện cả train và test, chưa phải benchmark khách hàng hoàn toàn mới.
- Test v1 đã được dùng để báo cáo; các vòng cải tiến tiếp theo vẫn phải tuning trên validation. Cần test mới trước kết luận production nếu lặp nhiều vòng đánh giá.
- Môi trường: **Anaconda `fraud-mlops`, Python 3.11.18**.

## Thông tin còn cần bổ sung

- Chi phí sai sót, mục tiêu recall/precision và giới hạn cảnh báo: **chưa xác định**.
- Nguồn gốc dữ liệu, cách tạo nhãn, độ trễ nhãn và tính sẵn có tại thời điểm dự đoán của các feature: **cần xác minh**.
- MLflow backend/artifact store cho production: **chưa chọn**.
- Nơi triển khai Kubernetes, image registry, domain/Ingress và cấu hình secrets: **chưa chọn**.
- Mục tiêu latency, throughput, tỷ lệ lỗi và giới hạn autoscaling: **chưa xác định**.
