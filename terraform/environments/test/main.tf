terraform {
  required_version = ">= 1.6, < 2.0"
  required_providers {
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "~> 2.38"
    }
  }
}

variable "kubeconfig_path" {
  type        = string
  description = "Path to an existing kubeconfig; never commit its contents."
}

variable "kube_context" {
  type = string
}

provider "kubernetes" {
  config_path    = pathexpand(var.kubeconfig_path)
  config_context = var.kube_context
}

module "namespace" {
  source = "../../modules/namespace"
  name   = "fraud-test"
}

output "namespace" {
  value = module.namespace.name
}
