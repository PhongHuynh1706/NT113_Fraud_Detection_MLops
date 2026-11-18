variable "aws_region" { type = string }
variable "allowed_account_ids" {
  type = list(string)
  validation {
    condition     = length(var.allowed_account_ids) > 0 && alltrue([for id in var.allowed_account_ids : can(regex("^[0-9]{12}$", id))])
    error_message = "Provide explicit 12-digit allowed account IDs."
  }
}
variable "name" {
  type = string
  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{2,35}$", var.name))
    error_message = "Use 3-36 lowercase letters/digits/hyphens, starting with a letter."
  }
}
variable "vpc_cidr" { type = string }
variable "subnets" {
  type = map(object({ az = string, public_cidr = string, private_cidr = string }))
  validation {
    condition     = length(var.subnets) >= 2 && length(distinct([for s in values(var.subnets) : s.az])) == length(var.subnets)
    error_message = "Require at least two distinct AZs with public/private subnet pairs."
  }
}
variable "single_nat_gateway" {
  type    = bool
  default = false
}
variable "cluster_version" {
  type        = string
  description = "Explicit EKS-supported minor version; confirm availability in target region."
  validation {
    condition     = can(regex("^1\\.[0-9]{2}$", var.cluster_version)) && try(tonumber(split(".", var.cluster_version)[1]) >= 31, false)
    error_message = "Choose a supported Kubernetes version in 1.xx form."
  }
}
variable "admin_principal_arn" {
  type = string
  validation {
    condition     = can(regex("^arn:aws[a-z-]*:iam::[0-9]{12}:(role|user)/.+$", var.admin_principal_arn))
    error_message = "Use an existing IAM role/user ARN, not an STS session."
  }
}
variable "public_access_cidrs" {
  type    = list(string)
  default = []
  validation {
    condition     = alltrue([for c in var.public_access_cidrs : can(cidrnetmask(c)) && try(tonumber(split("/", c)[1]) >= 8, false)])
    error_message = "Provide scoped IPv4 admin CIDRs; world-open access is forbidden."
  }
}
variable "node_groups" {
  type = map(object({ capacity_type = string, min_size = number, desired_size = number, max_size = number, disk_size = number }))
  validation {
    condition = length(var.node_groups) > 0 && alltrue([for g in values(var.node_groups) :
      g.min_size >= 1 && g.min_size <= g.desired_size && g.desired_size <= g.max_size &&
      floor(g.min_size) == g.min_size && floor(g.desired_size) == g.desired_size &&
      floor(g.max_size) == g.max_size && floor(g.disk_size) == g.disk_size &&
      g.disk_size >= 20 && contains(["ON_DEMAND", "SPOT"], g.capacity_type)
    ])
    error_message = "Require nonempty groups, integer 1<=min<=desired<=max, disk>=20GiB, ON_DEMAND/SPOT."
  }
}
variable "tags" {
  type    = map(string)
  default = {}
}

variable "manage_namespace" {
  type        = bool
  default     = false
  description = "Enable only after EKS exists and the runner can reach its API as an authorized IAM principal."
}
variable "ubuntu_ami_serial" {
  type        = string
  description = "Canonical Ubuntu24.04 EKS AMI serial YYYYMMDD, or current for test; pin a dated serial for production."
}

