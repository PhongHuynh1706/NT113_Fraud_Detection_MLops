data "aws_ssm_parameter" "ubuntu_ami" {
  name = "/aws/service/canonical/ubuntu/eks/24.04/${var.cluster_version}/stable/${var.ubuntu_ami_serial}/amd64/hvm/ebs-gp3/ami-id"
}
data "aws_ami" "ubuntu" {
  owners = ["099720109477"]
  filter {
    name   = "image-id"
    values = [nonsensitive(data.aws_ssm_parameter.ubuntu_ami.value)]
  }
  filter {
    name   = "name"
    values = ["ubuntu-eks/k8s_${var.cluster_version}/images/hvm-ssd-gp3/ubuntu-noble-24.04-amd64-server-*"]
  }
  filter {
    name   = "architecture"
    values = ["x86_64"]
  }
}
resource "aws_launch_template" "this" {
  for_each               = var.node_groups
  name_prefix            = "${var.cluster_name}-${each.key}-"
  vpc_security_group_ids = var.security_group_ids
  image_id               = data.aws_ami.ubuntu.id
  instance_type          = "t3.large"
  user_data = base64encode(<<-SCRIPT
    #!/bin/bash
    set -euo pipefail
    /etc/eks/bootstrap.sh '${var.cluster_name}' --apiserver-endpoint '${var.cluster_endpoint}' --b64-cluster-ca '${var.cluster_ca_data}'
  SCRIPT
  )
  metadata_options {
    http_endpoint               = "enabled"
    http_tokens                 = "required"
    http_put_response_hop_limit = 2
  }
  block_device_mappings {
    device_name = data.aws_ami.ubuntu.root_device_name
    ebs {
      volume_size           = each.value.disk_size
      volume_type           = "gp3"
      encrypted             = true
      delete_on_termination = true
    }
  }
  tag_specifications {
    resource_type = "instance"
    tags          = merge(var.tags, { Name = "${var.cluster_name}-${each.key}" })
  }
  tags = var.tags
}
resource "aws_eks_node_group" "this" {
  for_each        = var.node_groups
  cluster_name    = var.cluster_name
  node_group_name = each.key
  node_role_arn   = var.node_role_arn
  subnet_ids      = var.subnet_ids
  capacity_type   = each.value.capacity_type
  launch_template {
    id      = aws_launch_template.this[each.key].id
    version = tostring(aws_launch_template.this[each.key].latest_version)
  }
  scaling_config {
    min_size     = each.value.min_size
    desired_size = each.value.desired_size
    max_size     = each.value.max_size
  }
  update_config {
    max_unavailable = 1
  }
  tags = var.tags
}
