variable "cluster_name" {
  type = string
}

variable "cluster_version" {
  type = string
}

variable "node_role_arn" {
  type = string
}

variable "subnet_ids" {
  type = list(string)
}

variable "security_group_ids" {
  type = list(string)
}

variable "node_groups" {
  type = map(object({ capacity_type = string, min_size = number, desired_size = number, max_size = number, disk_size = number }))
}

variable "cluster_endpoint" { type = string }
variable "cluster_ca_data" { type = string }
variable "ubuntu_ami_serial" {
  type        = string
  description = "Canonical release serial (YYYYMMDD); current is allowed for test but changes on future plans."
  validation {
    condition     = can(regex("^(current|[0-9]{8})$", var.ubuntu_ami_serial))
    error_message = "Use current or a Canonical YYYYMMDD release serial."
  }
}

variable "tags" {
  type    = map(string)
  default = {}
}
