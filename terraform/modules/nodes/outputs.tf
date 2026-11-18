output "node_group_names" {
  value = { for k, group in aws_eks_node_group.this : k => group.node_group_name }
}

output "ami_id" { value = data.aws_ami.ubuntu.id }
output "instance_type" { value = "t3.large" }
output "os" { value = "Ubuntu 24.04 LTS (Canonical EKS amd64)" }
