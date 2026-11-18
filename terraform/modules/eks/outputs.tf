output "name" {
  value = aws_eks_cluster.this.name
}

output "endpoint" {
  value = aws_eks_cluster.this.endpoint
}

output "certificate_authority_data" {
  value = aws_eks_cluster.this.certificate_authority[0].data
}

output "primary_security_group_id" {
  value = aws_eks_cluster.this.vpc_config[0].cluster_security_group_id
}

output "version" {
  value = aws_eks_cluster.this.version
}
