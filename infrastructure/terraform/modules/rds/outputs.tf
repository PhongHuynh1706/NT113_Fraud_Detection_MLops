output "endpoint" {
  value = aws_db_instance.mlflow.endpoint
}

output "identifier" {
  value = aws_db_instance.mlflow.identifier
}

output "master_user_secret_arn" {
  value = try(aws_db_instance.mlflow.master_user_secret[0].secret_arn, null)
}
