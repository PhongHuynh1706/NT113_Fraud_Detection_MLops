output "control_plane_id" {
  value = aws_security_group.control_plane.id
}

output "nodes_id" {
  value = aws_security_group.nodes.id
}
