terraform {
  required_version = ">= 1.7, < 2.0"
  required_providers {
    aws        = { source = "hashicorp/aws", version = "~> 6.0" }
    kubernetes = { source = "hashicorp/kubernetes", version = "~> 2.38" }
  }
  # Separate local state per environment; configure remote backend before shared use.
}

