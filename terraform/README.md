# Terraform AWS/EKS theo module

Chỉ có hai root môi trường: [test](environments/test/) và [production](environments/production/). `main.tf` mỗi root chỉ gọi module và nối dependency; variables/providers/outputs/versions nằm ở file riêng. Chưa plan/apply AWS thật hoặc tạo tài nguyên tính phí.

## Các module

| Module | Trách nhiệm |
|---|---|
| [vpc](modules/vpc/) | VPC, DNS support/hostnames |
| [networking](modules/networking/) | Public/private subnets theo AZ, IGW, NAT, routes/associations |
| [security_groups](modules/security_groups/) | SG bổ sung control plane và nodes |
| [iam](modules/iam/) | Roles/policies cho EKS và managed nodes |
| [eks](modules/eks/) | EKS control plane, logs, Access Entry quản trị |
| [nodes](modules/nodes/) | Launch template và managed node groups Ubuntu24.04/t3.large |
| [namespace](modules/namespace/) | Namespace fraud-test hoặc fraud-production trong cùng root |
| [ecr](modules/ecr/) | Repository Docker image private, tag immutable, scan-on-push |
| [s3](modules/s3/) | Hai bucket riêng cho models và dataset |

```text
VPC → networking + security groups
IAM + private subnets + SG → EKS → nodes → namespace
ECR → nơi chứa Docker images
S3 → models bucket + dataset bucket
```

## Namespace không còn là root/folder riêng

Root test gọi namespace `fraud-test`; root production gọi `fraud-production`, khớp manifests ứng dụng hiện tại. Không thêm namespace môi trường khác. Không còn mã cấu hình ở `terraform/kubernetes/`; cache `.terraform` bị ignore có thể vẫn còn trên máy sau lần init cũ.

Kubernetes provider cần cluster đã tồn tại, token hợp lệ và đường mạng tới API. `depends_on` trên namespace không trì hoãn khởi tạo provider. Vì vậy vẫn dùng **hai lần plan/apply trong cùng root**, không dùng hai folder:

1. Giữ `manage_namespace=false` (mặc định) để provision AWS. Bước này không tạo namespace.
2. Sau khi EKS/nodes sẵn sàng, xác nhận runner truy cập private API và AWS CLI hiện dùng đúng IAM principal có quyền EKS. Đổi `manage_namespace=true`, xem plan và apply lần hai để tạo namespace.

Provider dùng AWS CLI `eks get-token` mỗi lần cần token; không lưu token/kubeconfig vào code. Nếu chọn role admin khác role provisioning, phải cấu hình profile/session assume role phù hợp trước lần hai. Khi namespace đã được quản lý, giữ `manage_namespace=true`; tắt lại sẽ đề xuất destroy namespace. Không destroy cluster trước khi đã xử lý namespace/app còn trong state.

Nếu có state cũ quản lý namespace ở địa chỉ `module.namespace`, cần backup và chuyển sang `module.namespace[0]` với state/cluster phù hợp trước apply; không áp state namespace của cluster cũ vào root tạo EKS mới. Nếu từng dùng root namespace riêng, phải review migration/import sang root đích, không để hai state quản lý cùng namespace. Chưa di chuyển state thật trong thay đổi này.

## Nodes cố định Ubuntu24.04 và t3.large

- `instance_type="t3.large"` được cố định ngay trong launch template, không còn biến instance_types ở từng group.
- AMI là **Canonical Ubuntu24.04 EKS amd64**, không phải Ubuntu server thường. Tra SSM path `/aws/service/canonical/ubuntu/eks/24.04/<cluster_version>/stable/<serial>/amd64/hvm/ebs-gp3/ami-id`, rồi xác minh AMI qua EC2 với owner Canonical `099720109477`, tên Noble24.04 đúng Kubernetes version và kiến trúc x86_64.
- `ubuntu_ami_serial` chọn release Canonical cụ thể `YYYYMMDD`; `current` được chấp nhận cho thử nghiệm nhưng có thể đổi AMI ở plan sau. Production nên pin serial đã review và có trong region. OS/type là cố định, AMI ID thay đổi theo region/Kubernetes/serial, không bịa một AMI ID dùng mọi nơi.
- User-data gọi `/etc/eks/bootstrap.sh` với tên cluster, API endpoint và certificate. Root disk lấy đúng `root_device_name` của AMI, dùng EBS gp3 mã hóa; IMDSv2 bắt buộc, không mở SSH/keypair.
- Vì launch template chứa custom AMI, managed node group không đặt `ami_type`, `version` hay `instance_types` gây xung đột. Nâng Kubernetes cần chọn AMI tương thích và review node replacement, không chỉ thay nhãn version.
- Min/desired/max, dung lượng disk và ON_DEMAND/SPOT vẫn cấu hình theo node group. Chưa cài autoscaler EC2; HPA ứng dụng chỉ scale Pod.

Tài liệu Canonical: [AMI lookup](https://ubuntu.com/aws/docs/aws-how-to/instances/build-cloudformation-templates/) và [managed Ubuntu nodes/bootstrap](https://ubuntu.com/aws/docs/aws-how-to/kubernetes/deploy-managed-node-group/). Terraform validate/mock tests không xác minh AMI thực sự có trong region hoặc node join thành công; cần plan AWS thật và kiểm chứng triển khai khi được cho phép.

## ECR và S3 lưu gì

**ECR:** một private repository `<name>/fraud-api` cho mỗi môi trường; tags immutable, mã hóa AES256, scan-on-push. Lifecycle chỉ xóa image untagged sau30 ngày để giữ version tags rollback. `force_delete=false` tránh xóa repository còn images ngoài ý muốn. Output `ecr_repository_url` dùng cho login/tag/push sau này; chưa cấp CI role push hoặc tự chuyển workflow GHCR sang ECR. Node role hiện có ECR PullOnly để pull image khi có cấu hình runtime phù hợp.

**S3:** hai bucket có prefix môi trường và suffix duy nhất: models/dataset. Bật versioning, SSE-S3 AES256, Block Public Access, BucketOwnerEnforced và deny HTTP; abort multipart chưa hoàn tất sau7 ngày. Không tự expire model/dataset hoặc noncurrent versions; theo dõi chi phí versioning và xây retention theo nhu cầu. `force_destroy=false` ngăn destroy bucket còn dữ liệu.

Outputs `models_s3_uri`, `dataset_s3_uri`, `s3_bucket_names` cho biết bucket được tạo. Chưa upload bất kỳ raw/model nào, không commit dữ liệu và không tự thay MLflow backend/artifact destination. Cần cấu hình MLflow artifact store tới models bucket và quyền S3 theo role workload/uploader riêng khi triển khai; không cấp toàn bộ worker quyền đọc/ghi dataset. Chưa có Pod Identity/IRSA hoặc IAM policy S3 dành cho workloads, không khẳng định chỉ tạo bucket là ứng dụng đã truy cập được. Bucket chứa artifacts/dataset **không phải backend Terraform state**.

## Networking và quyền truy cập

- Ít nhất hai AZ khác nhau, nodes ở private subnet; public subnet không tự gán public IP. IGW/NAT cấp outbound. Mặc định NAT mỗi AZ; test example dùng một NAT giảm số gateway nhưng giảm HA và có thể tăng traffic liên AZ.
- Kiểm tra CIDR thuộc VPC, không overlap nhau hoặc VPN/peering/service network trước plan.
- EKS API luôn private-access; `public_access_cidrs=[]` tắt public endpoint. Nếu mở public cần allowlist CIDR tin cậy, không cho0.0.0.0/0. Private endpoint đòi runner/VPN có đường tới VPC.
- Nodes gắn cả primary cluster SG do EKS quản lý và SG bổ sung. SG cộng gộp quyền; SG bổ sung không thu hẹp quyền primary SG. Chưa phải hardening/NetworkPolicy đầy đủ.
- EKS bootstrap creator admin tắt, dùng Access Entry cho IAM user/role hiện có. Node role có WorkerNode/ECRPullOnly/CNI policy; chưa chuyển CNI sang role riêng.
- Logs EKS retention30 ngày, bootstrap self-managed CNI/CoreDNS/kube-proxy. Chưa cài Metrics Server, Ingress/LB controller, CSI, monitoring hoặc nodeautoscaler.

## Cấu hình và kiểm tra local

Điền [test tfvars example](environments/test/terraform.tfvars.example) hoặc [production example](environments/production/terraform.tfvars.example), copy thành `terraform.tfvars` trong đúng môi trường khi chuẩn bị dùng. Account/region/AZ/CIDR/admin role trong example chỉ minh họa; `cluster_version` là placeholder buộc chọn version hỗ trợ Ubuntu24.04/EKS trong region. Dùng IAM profile/SSO, không ghi credentials vào code.

Terraform>=1.7,<2; đã dùng1.14.9, AWS provider6.73.0, Kubernetes provider2.38.0. Giữ lock files trong Git, không commit `.terraform`, state/plan/tfvars/token. Hai root có local state riêng; remote backend/locking chưa được chọn/tạo. Cần backend và key riêng test/production trước làm việc chung.

```powershell
Set-Location D:/MLops_Fraud_Detection
$env:TEMP = 'D:/MLops_Fraud_Detection/artifacts/test-tmp'
$env:TMP = $env:TEMP
$env:TF_PLUGIN_CACHE_DIR = 'D:/MLops_Fraud_Detection/artifacts/terraform-provider-cache'
New-Item -ItemType Directory -Force $env:TEMP, $env:TF_PLUGIN_CACHE_DIR | Out-Null
terraform fmt -check -recursive terraform
terraform -chdir=terraform/environments/test init -backend=false -lockfile=readonly
terraform -chdir=terraform/environments/test validate
terraform -chdir=terraform/environments/test test
terraform -chdir=terraform/environments/production init -backend=false -lockfile=readonly
terraform -chdir=terraform/environments/production validate
```

Terraform không nằm trong CI theo yêu cầu; chạy validate và mock tests thủ công bằng các lệnh trên. Tests dùng mock AWS/Kubernetes, `command=plan`, không credentials/apply AWS thật: kiểm tra topology/NAT, chặn world-open API/scaling sai/AZ trùng, OS/type cố định, hai bucket và namespace bật/tắt. Init chỉ tải provider; validate không chứng minh quota/account/AMI/EKS version khả dụng.

Chưa chạy plan/apply thật. Khi đã xác nhận account, IAM, budget và state thì mới chạy plan cho đúng môi trường, xem toàn bộ create/update/destroy và chỉ apply khi được phép. EKS, EC2 t3.large, EBS, NAT/EIP, S3, ECR, logs và data transfer sẽ tính phí khi sử dụng; không tự tạo backend hoặc triển khai production trong thay đổi này.
