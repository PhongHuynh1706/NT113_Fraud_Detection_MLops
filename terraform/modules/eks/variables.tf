variable "name" {
  type = string
}

variable "cluster_version" {
  type = string
}

variable "role_arn" {
  type = string
}

variable "subnet_ids" {
  type = list(string)
}

variable "security_group_id" {
  type = string
}

variable "admin_principal_arn" {
  type = string
}

variable "public_access_cidrs" {
  type    = list(string)
  default = []
}

variable "tags" {
  type    = map(string)
  default = {}
}
