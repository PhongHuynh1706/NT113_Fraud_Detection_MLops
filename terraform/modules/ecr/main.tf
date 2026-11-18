resource "aws_ecr_repository" "this" {
  name                 = "${var.name}/fraud-api"
  image_tag_mutability = "IMMUTABLE"
  force_delete         = false
  image_scanning_configuration { scan_on_push = true }
  encryption_configuration { encryption_type = "AES256" }
  tags = var.tags
}
resource "aws_ecr_lifecycle_policy" "this" {
  repository = aws_ecr_repository.this.name
  policy = jsonencode({ rules = [{
    rulePriority = 1
    description  = "Remove only untagged images after 30 days; retain version tags for rollback"
    selection    = { tagStatus = "untagged", countType = "sinceImagePushed", countUnit = "days", countNumber = 30 }
    action       = { type = "expire" }
  }] })
}
