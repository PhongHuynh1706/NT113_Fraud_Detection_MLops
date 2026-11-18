terraform {
  required_providers {
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "~> 2.38"
    }
  }
}

variable "name" {
  type = string
}

resource "kubernetes_namespace_v1" "this" {
  metadata {
    name = var.name
    labels = {
      "app.kubernetes.io/part-of"          = "fraud-detection"
      "pod-security.kubernetes.io/enforce" = "restricted"
    }
  }
}

output "name" {
  value = kubernetes_namespace_v1.this.metadata[0].name
}
