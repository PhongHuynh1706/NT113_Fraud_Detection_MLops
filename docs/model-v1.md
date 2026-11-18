# Model v1 — kết quả huấn luyện

Đã huấn luyện ngày 18/11/2026 bằng Conda `fraud-mlops`, Python 3.11.18,
scikit-learn 1.9.1 và MLflow 3.17.2. Bản v1 đạt yêu cầu accuracy > 60% trên test
độc lập theo thời gian; chất lượng phát hiện gian lận còn hạn chế.

## Dữ liệu và phương pháp

- Dataset: `dataset/creditcard_2026.csv`, 100.000 dòng, 43 cột, 2.055 nhãn fraud.
- Nhãn: `is_fraud`, lớp dương là 1; không phát hiện transaction ID trùng.
- Loại `fraud_type`, `fraud_amount_lost`, ID và thông tin nhân khẩu học khỏi đầu vào.
- Chưa dùng biến lịch sử giao dịch/chargeback vì chưa xác minh cách tính point-in-time.
- Dùng 9 đặc trưng số trong [training.json](../configs/training.json). Cờ rủi ro và khoảng
  cách có sẵn trong dataset vẫn cần xác minh nguồn trước khi production.
- Chia train/validation/test theo `transaction_datetime`, không để cùng timestamp
  rơi vào hai tập. Không resampling. StandardScaler chỉ fit trên train.

| Tập | Số dòng | Fraud | Khoảng thời gian năm 2026 |
| --- | ---: | ---: | --- |
| Train | 70.000 | 1.413 | 01/01 02:28:51 → 14/09 11:11:52 |
| Validation | 15.000 | 333 | 14/09 11:16:30 → 06/11 23:31:10 |
| Test | 15.000 | 309 | 06/11 23:41:52 → 31/12 23:45:47 |

So sánh Logistic Regression + StandardScaler với HistGradientBoosting, đều dùng
class weight balanced. Chọn model theo F1 validation, PR-AUC làm tiêu chí phụ;
chọn threshold tối đa F1 validation. Không chọn cấu hình theo test.

| Model | F1 validation | Average precision validation |
| --- | ---: | ---: |
| Logistic Regression | 0,20120 | 0,10014 |
| HistGradientBoosting | 0,20024 | 0,09801 |

Model được chọn: **Logistic Regression**, threshold **0,8528996455659125**.
Chưa có chi phí sai sót hoặc ngân sách cảnh báo, nên threshold này là lựa chọn
thực nghiệm theo F1, không phải ngưỡng nghiệp vụ đã được duyệt.

## Kết quả test

| Metric | Model v1 | Baseline luôn dự đoán hợp lệ |
| --- | ---: | ---: |
| Accuracy | 95,84% | 97,94% |
| Precision | 13,79% | 0% |
| Recall | 19,42% | 0% |
| F1 | 0,16129 | 0 |
| Average precision (báo cáo dưới tên PR-AUC) | 0,09737 | 0,02060 |
| ROC-AUC | 0,80112 | 0,5 |

Confusion matrix, hàng là nhãn thực tế và cột là dự đoán, thứ tự [hợp lệ, fraud]:

```text
                 Dự đoán hợp lệ   Dự đoán fraud
Thực tế hợp lệ        14316             375
Thực tế fraud           249              60
```

Model phát hiện 60/309 fraud, tạo tổng cộng 435 cảnh báo. Accuracy thấp hơn
baseline vì model có cảnh báo fraud, trong khi baseline bỏ sót toàn bộ fraud.
Model đạt điều kiện khởi tạo accuracy > 60%, F1 và average precision tốt hơn baseline;
không suy ra đã đủ tốt cho production từ các điều kiện này.

## Artifact đã xuất

- Registry: `models:/FraudDetection/1`.
- Run ID: `8a5980d06a884a08b3afb9922847845c`.
- Registry backend: SQLite cục bộ `artifacts/mlflow.db`.
- Model độc lập: `artifacts/training/8a5980d06a884a08b3afb9922847845c/model/`.
- Báo cáo máy đọc, config, dependencies và manifest: cùng thư mục run.
- Manifest dùng trực tiếp trên máy này: `artifacts/manifest.json`.
- Manifest tham chiếu Registry: `artifacts/manifest.registry.json`.

Đã kiểm chứng xác suất trước/sau MLflow load nhất quán trên 128 dòng, load được
bằng Registry version 1, và API trả 200 bằng payload tổng hợp chứa số nguyên.
Model chứa preprocessing và adapter trả cột `fraud_probability` đúng hợp đồng API.
Lần xuất đầu bị lỗi kiểu int64/double ở bước kiểm tra reload; sau khi chuẩn hóa
đầu vào số thực đã chạy lại cùng cấu hình, không thay đổi cách chọn model/threshold.

## Chạy lại và kiểm tra tay

```powershell
conda activate fraud-mlops
cd D:\MLops_Fraud_Detection
pip install -e '.[dev]'
python -m fraud_detection.train --config configs/training.json --tracking-uri sqlite:///D:/MLops_Fraud_Detection/artifacts/mlflow.db
```

Lệnh trên huấn luyện một run mới và tạo version tiếp theo nếu tên model đã tồn tại,
không ghi đè version 1. Cấu hình, seed, fingerprint dữ liệu, source hash, phiên bản
dependency và metrics được lưu cùng run. Repo chưa có commit nên nguồn cũng được
lưu trong artifact MLflow, với commit ghi là `uncommitted`.

Để xem đúng Registry đã tạo trong lần chạy này:

```powershell
mlflow server --host 127.0.0.1 --port 5000 --backend-store-uri sqlite:///D:/MLops_Fraud_Detection/artifacts/mlflow.db --no-serve-artifacts
```

Mở `http://127.0.0.1:5000`, experiment `fraud-detection`, model `FraudDetection`,
version 1. SQLite này và Registry trong Docker Compose là hai backend riêng;
không kỳ vọng version này tự xuất hiện trong volume MLflow của Compose.

Chạy inference trên máy hiện tại, không cần MLflow server vì manifest trỏ model local:

```powershell
$env:MODEL_MANIFEST = 'D:/MLops_Fraud_Detection/artifacts/manifest.json'
uvicorn fraud_detection.api:app --host 127.0.0.1 --port 8000 --no-access-log
```

Trong terminal khác:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health/ready
$body = @{
  instances = @(@{
    transaction_amount = 100.0
    transaction_hour = 12
    card_present = 1
    used_chip = 1
    used_pin = 1
    international_transaction = 0
    high_risk_country = 0
    distance_from_home_km = 5.0
    is_weekend = 0
  })
} | ConvertTo-Json -Depth 5
Invoke-RestMethod http://127.0.0.1:8000/predict -Method Post -ContentType 'application/json' -Body $body
```

Payload trên là tổng hợp; phản hồi phải có version `1`, threshold đã nêu và xác suất
trong [0, 1]. Không yêu cầu giao dịch minh họa phải thuộc một nhãn cụ thể.

Manifest local chứa đường dẫn tuyệt đối của máy này. Khi chuyển máy hoặc container,
copy model và sửa URI theo nơi mount model, đồng thời giữ đúng dependency đã ghi.
Không dùng trực tiếp đường dẫn Windows bên trong Linux container.

## Giới hạn cần giải quyết

- Chưa xác minh nguồn dữ liệu, cách tạo nhãn và độ trễ nhãn; timestamp kéo dài tới
  31/12/2026, sau ngày huấn luyện 18/11/2026. Đây là đánh giá offline trên file được
  cung cấp, không phải kết quả kiểm chứng trên giao dịch thực đã xảy ra.
- Có 6.817 khách hàng xuất hiện ở cả train và test: đánh giá giao dịch tương lai
  theo thời gian với khách hàng có thể lặp lại, chưa đánh giá khách hàng hoàn toàn mới.
- Recall và precision còn thấp; cần xác minh feature provenance, bổ sung xử lý
  categorical, đánh giá đặc trưng lịch sử hợp lệ và chốt mục tiêu nghiệp vụ ở vòng sau.
- Test hiện tại đã được sử dụng để báo cáo. Vòng cải tiến tiếp theo phải giữ quy
  tắc tuning trên validation; cần test mới trước kết luận production nếu lặp nhiều vòng.
- Chưa deploy, promote alias production, benchmark latency hoặc load test model này.
