resource "aws_eks_cluster" "this" {
  name     = var.cluster_name
  role_arn = var.cluster_role_arn
  version  = var.cluster_version

  vpc_config {
    subnet_ids              = var.subnet_ids
    endpoint_private_access = true
    endpoint_public_access  = true
    public_access_cidrs     = var.public_access_cidrs
  }
}

data "aws_ssm_parameter" "ubuntu_eks_ami" {
  name = "/aws/service/canonical/ubuntu/eks/24.04/${var.cluster_version}/stable/current/amd64/hvm/ebs-gp3/ami-id"
}

data "aws_eks_cluster" "this" {
  name = aws_eks_cluster.this.name
}

resource "aws_launch_template" "ubuntu" {
  name_prefix = "${var.cluster_name}-ubuntu-"

  image_id      = data.aws_ssm_parameter.ubuntu_eks_ami.value
  instance_type = var.instance_types[0]

  user_data = base64encode(<<-EOF
    #!/bin/bash
    set -euo pipefail

    /etc/eks/bootstrap.sh '${aws_eks_cluster.this.name}' \
      --apiserver-endpoint '${aws_eks_cluster.this.endpoint}' \
      --b64-cluster-ca '${aws_eks_cluster.this.certificate_authority[0].data}'
  EOF
  )

  tag_specifications {
    resource_type = "instance"

    tags = {
      Name = "${var.cluster_name}-ubuntu-worker"
    }
  }

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_eks_node_group" "this" {
  cluster_name    = aws_eks_cluster.this.name
  node_group_name = "general-ubuntu"

  node_role_arn = var.node_role_arn
  subnet_ids    = var.private_subnet_ids
  capacity_type = "ON_DEMAND"

  scaling_config {
    min_size     = var.min_size
    desired_size = var.desired_size
    max_size     = var.max_size
  }

  update_config {
    max_unavailable = 1
  }

  launch_template {
    id      = aws_launch_template.ubuntu.id
    version = aws_launch_template.ubuntu.latest_version
  }

  depends_on = [
    aws_eks_cluster.this
  ]
}