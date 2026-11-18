locals {
  nat_keys = var.single_nat_gateway ? [sort(keys(var.subnets))[0]] : sort(keys(var.subnets))
}
resource "aws_internet_gateway" "this" {
  vpc_id = var.vpc_id
  tags   = merge(var.tags, { Name = var.name })
}
resource "aws_subnet" "public" {
  for_each                = var.subnets
  vpc_id                  = var.vpc_id
  availability_zone       = each.value.az
  cidr_block              = each.value.public_cidr
  map_public_ip_on_launch = false
  tags                    = merge(var.tags, { Name = "${var.name}-public-${each.key}", "kubernetes.io/role/elb" = "1" })
}
resource "aws_subnet" "private" {
  for_each                = var.subnets
  vpc_id                  = var.vpc_id
  availability_zone       = each.value.az
  cidr_block              = each.value.private_cidr
  map_public_ip_on_launch = false
  tags                    = merge(var.tags, { Name = "${var.name}-private-${each.key}", "kubernetes.io/role/internal-elb" = "1" })
}
resource "aws_route_table" "public" {
  vpc_id = var.vpc_id
  tags   = merge(var.tags, { Name = "${var.name}-public" })
}
resource "aws_route" "internet" {
  route_table_id         = aws_route_table.public.id
  destination_cidr_block = "0.0.0.0/0"
  gateway_id             = aws_internet_gateway.this.id
}
resource "aws_route_table_association" "public" {
  for_each       = var.subnets
  subnet_id      = aws_subnet.public[each.key].id
  route_table_id = aws_route_table.public.id
}
resource "aws_eip" "nat" {
  for_each = toset(local.nat_keys)
  domain   = "vpc"
  tags     = merge(var.tags, { Name = "${var.name}-nat-${each.key}" })
}
resource "aws_nat_gateway" "this" {
  for_each      = toset(local.nat_keys)
  allocation_id = aws_eip.nat[each.key].id
  subnet_id     = aws_subnet.public[each.key].id
  depends_on    = [aws_internet_gateway.this]
  tags          = merge(var.tags, { Name = "${var.name}-nat-${each.key}" })
}
resource "aws_route_table" "private" {
  for_each = var.subnets
  vpc_id   = var.vpc_id
  tags     = merge(var.tags, { Name = "${var.name}-private-${each.key}" })
}
resource "aws_route" "nat" {
  for_each               = var.subnets
  route_table_id         = aws_route_table.private[each.key].id
  destination_cidr_block = "0.0.0.0/0"
  nat_gateway_id         = aws_nat_gateway.this[var.single_nat_gateway ? local.nat_keys[0] : each.key].id
}
resource "aws_route_table_association" "private" {
  for_each       = var.subnets
  subnet_id      = aws_subnet.private[each.key].id
  route_table_id = aws_route_table.private[each.key].id
}
