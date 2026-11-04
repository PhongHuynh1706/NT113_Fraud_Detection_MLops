# Fraud Detection MLOps — AWS personal Terraform

## Contents

Seven modules: networking, iam, eks, ecr, s3, rds, monitoring-storage. Two independent environments: test and production.

## Important

- This is for a **personal AWS account**, not AWS Academy Learner Lab. Terraform uses the AWS credentials you supply and creates EKS cluster/node IAM roles.
- EKS, EC2 nodes, NAT Gateway, RDS and other resources incur charges. `terraform destroy` removes resources subject to IAM and service constraints.
- Local state stores sensitive information; keep it private and do not commit it.
- The EKS public API CIDR defaults to `0.0.0.0/0` for initial access. **Restrict to your public IP /32** before deployment.
- Verify EKS and PostgreSQL engine versions in your selected region. Check EC2 instance quotas and AZ support.
- Production defaults include RDS deletion protection and a final snapshot. Disable protection deliberately before destroy.
- S3 versioning is enabled. For nonempty buckets, `force_delete_storage = true` may be necessary for destroy, after reviewing data loss.
- IAM policies for workload access to S3 and GitHub Actions OIDC are **not included**; add those before MLflow and CI/CD production use.
- The monitoring bucket is storage only; Prometheus/Grafana/KEDA are deployed separately to Kubernetes.

## PowerShell commands

```powershell
aws sts get-caller-identity
cd infrastructure/terraform/environments/test
terraform init
terraform fmt -recursive ../../
terraform validate
terraform plan -out=tfplan
terraform show tfplan
terraform apply tfplan
aws eks update-kubeconfig --region ap-southeast-1 --name fraud-detection-test-eks
kubectl get nodes
```

To destroy test:

```powershell
terraform plan -destroy
terraform destroy
```

Do not mix the old Learner Lab Terraform state with this new configuration. Never apply test and production without reviewing estimated costs.
