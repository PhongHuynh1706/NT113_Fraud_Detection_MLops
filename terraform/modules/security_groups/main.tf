resource "aws_security_group" "control_plane" {
  name_prefix = "${var.name}-control-"
  description = "Additional private EKS API access"
  vpc_id      = var.vpc_id
  tags        = merge(var.tags, { Name = "${var.name}-control" })
}
resource "aws_vpc_security_group_ingress_rule" "private_api" {
  security_group_id = aws_security_group.control_plane.id
  description       = "HTTPS from VPC clients; IAM authentication still required"
  cidr_ipv4         = var.vpc_cidr
  ip_protocol       = "tcp"
  from_port         = 443
  to_port           = 443
}
resource "aws_vpc_security_group_egress_rule" "control_plane" {
  security_group_id = aws_security_group.control_plane.id
  cidr_ipv4         = var.vpc_cidr
  ip_protocol       = "-1"
}
resource "aws_security_group" "nodes" {
  name_prefix = "${var.name}-nodes-"
  description = "Worker egress; EKS managed primary SG supplies cluster communication"
  vpc_id      = var.vpc_id
  tags        = merge(var.tags, { Name = "${var.name}-nodes" })
}
resource "aws_vpc_security_group_egress_rule" "nodes" {
  security_group_id = aws_security_group.nodes.id
  description       = "Outbound package, registry and AWS API access via NAT"
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "-1"
}
