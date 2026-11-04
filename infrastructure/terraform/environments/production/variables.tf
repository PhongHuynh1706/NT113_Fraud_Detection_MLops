variable "aws_region" {
  type = string
}

variable "project" {
  type    = string
  default = "fraud-detection"
}

variable "environment" {
  type    = string
  default = "test"
}

variable "vpc_cidr" {
  type = string
}

variable "public_subnets" {
  type = map(string)
}

variable "private_subnets" {
  type = map(string)
}

variable "cluster_version" {
  type = string
}

variable "instance_types" {
  type = list(string)
}

variable "node_min_size" {
  type = number
}

variable "node_desired_size" {
  type = number
}

variable "node_max_size" {
  type = number
}

variable "eks_public_access_cidrs" {
  type = list(string)
}

variable "rds_engine_version" {
  type = string
}

variable "rds_instance_class" {
  type = string
}

variable "rds_multi_az" {
  type = bool
}

variable "rds_deletion_protection" {
  type = bool
}

variable "rds_skip_final_snapshot" {
  type = bool
}

variable "force_delete_storage" {
  type = bool
}

variable "force_delete_ecr" {
  type = bool
}
