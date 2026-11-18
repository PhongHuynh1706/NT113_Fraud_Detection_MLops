output "id" {
  value = aws_vpc.this.id
}

output "cidr" {
  value = aws_vpc.this.cidr_block
}
