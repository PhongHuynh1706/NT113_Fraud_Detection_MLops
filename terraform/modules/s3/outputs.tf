output "bucket_names" { value = { for k, b in aws_s3_bucket.this : k => b.id } }
output "bucket_arns" { value = { for k, b in aws_s3_bucket.this : k => b.arn } }
output "models_uri" { value = "s3://${aws_s3_bucket.this["models"].id}/" }
output "dataset_uri" { value = "s3://${aws_s3_bucket.this["dataset"].id}/" }
