output "public_subnet_ids" {
  value = [for k in sort(keys(var.subnets)) : aws_subnet.public[k].id]
}

output "private_subnet_ids" {
  value = [for k in sort(keys(var.subnets)) : aws_subnet.private[k].id]
}

output "nat_gateway_ids" {
  value = { for k, nat in aws_nat_gateway.this : k => nat.id }
}
