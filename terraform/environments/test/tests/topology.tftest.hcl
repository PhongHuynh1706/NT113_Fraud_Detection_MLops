mock_provider "kubernetes" {}
mock_provider "aws" {
  mock_data "aws_ssm_parameter" {
    defaults = { value = "ami-0123456789abcdef0" }
  }
  mock_data "aws_ami" {
    defaults = { id = "ami-0123456789abcdef0", root_device_name = "/dev/sda1" }
  }
  mock_data "aws_partition" {
    defaults = {
      partition = "aws"
    }
  }
}

variables {
  aws_region          = "ap-southeast-1"
  allowed_account_ids = ["123456789012"]
  name                = "fraud-test"
  vpc_cidr            = "10.20.0.0/16"
  ubuntu_ami_serial   = "current"
  cluster_version     = "1.35" # Test fixture only, not a selected deployment version.
  admin_principal_arn = "arn:aws:iam::123456789012:role/test-admin"
  subnets = {
    a = { az = "ap-southeast-1a", public_cidr = "10.20.0.0/24", private_cidr = "10.20.10.0/24" }
    b = { az = "ap-southeast-1b", public_cidr = "10.20.1.0/24", private_cidr = "10.20.11.0/24" }
  }
  node_groups = {
    general = { capacity_type = "ON_DEMAND", min_size = 1, desired_size = 2, max_size = 3, disk_size = 30 }
  }
}

run "compose_modules" {
  command = plan
  assert {
    condition     = length(module.networking.private_subnet_ids) == 2 && length(module.networking.public_subnet_ids) == 2
    error_message = "EKS requires subnet pairs in two AZs."
  }
  assert {
    condition     = length(module.networking.nat_gateway_ids) == 2
    error_message = "Default NAT topology must be per AZ."
  }
}

run "single_nat_for_test" {
  command = plan
  variables {
    single_nat_gateway = true
  }
  assert {
    condition     = length(module.networking.nat_gateway_ids) == 1
    error_message = "Single NAT option must create exactly one NAT gateway."
  }
}

run "reject_open_api" {
  command = plan
  variables {
    public_access_cidrs = ["0.0.0.0/0"]
  }
  expect_failures = [var.public_access_cidrs]
}

run "reject_invalid_scaling" {
  command = plan
  variables {
    node_groups = {
      general = { capacity_type = "ON_DEMAND", min_size = 3, desired_size = 2, max_size = 1, disk_size = 30 }
    }
  }
  expect_failures = [var.node_groups]
}

run "reject_same_az" {
  command = plan
  variables {
    subnets = {
      a = { az = "ap-southeast-1a", public_cidr = "10.20.0.0/24", private_cidr = "10.20.10.0/24" }
      b = { az = "ap-southeast-1a", public_cidr = "10.20.1.0/24", private_cidr = "10.20.11.0/24" }
    }
  }
  expect_failures = [var.subnets]
}

run "fixed_nodes_and_storage" {
  command = plan
  assert {
    condition     = output.node_instance_type == "t3.large" && output.node_os == "Ubuntu 24.04 LTS (Canonical EKS amd64)"
    error_message = "Node OS and instance type must match the fixed contract."
  }
  assert {
    condition     = toset(keys(output.s3_bucket_names)) == toset(["models", "dataset"])
    error_message = "Models and datasets require separate buckets."
  }
  assert {
    condition     = output.namespace == null
    error_message = "Namespace must be opt-in after cluster readiness."
  }
}
run "namespace_second_stage" {
  command = plan
  variables { manage_namespace = true }
  assert {
    condition     = output.namespace == "fraud-test"
    error_message = "Test environment must create only fraud-test namespace."
  }
}
