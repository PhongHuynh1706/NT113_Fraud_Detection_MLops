provider "aws" {
  region              = var.aws_region
  allowed_account_ids = var.allowed_account_ids
  default_tags {
    tags = merge(var.tags, { Project = "fraud-detection", Environment = "production", ManagedBy = "terraform" })
  }
}
provider "kubernetes" {
  host                   = var.manage_namespace ? module.eks.endpoint : null
  cluster_ca_certificate = var.manage_namespace ? base64decode(module.eks.certificate_authority_data) : null
  exec {
    api_version = "client.authentication.k8s.io/v1beta1"
    command     = "aws"
    args        = ["eks", "get-token", "--region", var.aws_region, "--cluster-name", var.name]
  }
}
