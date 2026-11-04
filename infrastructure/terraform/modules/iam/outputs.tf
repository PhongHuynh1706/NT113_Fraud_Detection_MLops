output "cluster_role_arn" {
  value = aws_iam_role.cluster.arn
}

output "node_role_arn" {
  value = aws_iam_role.node.arn
}

output "cluster_policy_attachment_id" {
  value = aws_iam_role_policy_attachment.cluster.id
}

output "node_policy_attachment_ids" {
  value = [for attachment in aws_iam_role_policy_attachment.node : attachment.id]
}
