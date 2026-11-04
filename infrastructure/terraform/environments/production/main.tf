data "aws_caller_identity" "current" {}

data "aws_partition" "current" {}

locals {
  name_prefix = "${var.project}-${var.environment}"
  account_id  = data.aws_caller_identity.current.account_id

  mlflow_bucket_name     = "${local.name_prefix}-mlflow-${local.account_id}-${var.aws_region}"
  monitoring_bucket_name = "${local.name_prefix}-monitor-${local.account_id}-${var.aws_region}"
}

module "networking" {
  source = "../../modules/networking"

  name_prefix    = local.name_prefix
  cluster_name   = "${local.name_prefix}-eks"
  vpc_cidr       = var.vpc_cidr
  public_subnets = var.public_subnets
  private_subnets = var.private_subnets
}

module "iam" {
  source = "../../modules/iam"

  name_prefix = local.name_prefix
}

module "ecr" {
  source = "../../modules/ecr"

  name_prefix  = local.name_prefix
  force_delete = var.force_delete_ecr
}

module "s3" {
  source = "../../modules/s3"

  bucket_name   = local.mlflow_bucket_name
  force_destroy = var.force_delete_storage
}

module "monitoring_storage" {
  source = "../../modules/monitoring-storage"

  bucket_name   = local.monitoring_bucket_name
  force_destroy = var.force_delete_storage
}

module "rds" {
  source = "../../modules/rds"

  name_prefix             = local.name_prefix
  vpc_id                  = module.networking.vpc_id
  vpc_cidr                = module.networking.vpc_cidr
  private_subnet_ids      = module.networking.private_subnet_ids
  engine_version          = var.rds_engine_version
  instance_class          = var.rds_instance_class
  multi_az                = var.rds_multi_az
  deletion_protection     = var.rds_deletion_protection
  skip_final_snapshot     = var.rds_skip_final_snapshot
}

module "eks" {
  source = "../../modules/eks"

  cluster_name        = "${local.name_prefix}-eks"
  cluster_role_arn    = module.iam.cluster_role_arn
  node_role_arn       = module.iam.node_role_arn
  cluster_version     = var.cluster_version
  subnet_ids          = concat(module.networking.public_subnet_ids, module.networking.private_subnet_ids)
  private_subnet_ids  = module.networking.private_subnet_ids
  public_access_cidrs = var.eks_public_access_cidrs
  instance_types      = var.instance_types
  min_size            = var.node_min_size
  desired_size        = var.node_desired_size
  max_size            = var.node_max_size

  depends_on = [module.iam]
}
