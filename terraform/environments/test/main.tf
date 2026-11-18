module "vpc" {
  source = "../../modules/vpc"
  name   = var.name
  cidr   = var.vpc_cidr
  tags   = var.tags
}
module "networking" {
  source             = "../../modules/networking"
  name               = var.name
  vpc_id             = module.vpc.id
  subnets            = var.subnets
  single_nat_gateway = var.single_nat_gateway
  tags               = var.tags
}
module "security_groups" {
  source   = "../../modules/security_groups"
  name     = var.name
  vpc_id   = module.vpc.id
  vpc_cidr = module.vpc.cidr
  tags     = var.tags
}
module "iam" {
  source = "../../modules/iam"
  name   = var.name
  tags   = var.tags
}
module "eks" {
  source              = "../../modules/eks"
  name                = var.name
  cluster_version     = var.cluster_version
  role_arn            = module.iam.cluster_role_arn
  subnet_ids          = module.networking.private_subnet_ids
  security_group_id   = module.security_groups.control_plane_id
  admin_principal_arn = var.admin_principal_arn
  public_access_cidrs = var.public_access_cidrs
  tags                = var.tags
  depends_on          = [module.iam]
}
module "nodes" {
  source             = "../../modules/nodes"
  cluster_name       = module.eks.name
  cluster_version    = module.eks.version
  node_role_arn      = module.iam.node_role_arn
  subnet_ids         = module.networking.private_subnet_ids
  security_group_ids = [module.eks.primary_security_group_id, module.security_groups.nodes_id]
  node_groups        = var.node_groups
  cluster_endpoint   = module.eks.endpoint
  cluster_ca_data    = module.eks.certificate_authority_data
  ubuntu_ami_serial  = var.ubuntu_ami_serial
  tags               = var.tags
  depends_on         = [module.iam, module.networking]
}

module "ecr" {
  source = "../../modules/ecr"
  name   = var.name
  tags   = var.tags
}
module "s3" {
  source = "../../modules/s3"
  name   = var.name
  tags   = var.tags
}
module "namespace" {
  count      = var.manage_namespace ? 1 : 0
  source     = "../../modules/namespace"
  name       = "fraud-test"
  depends_on = [module.nodes]
}
