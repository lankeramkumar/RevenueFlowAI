output "app_url" {
  description = "The public address of the demo."
  value       = local.app_origin
}

output "cognito_issuer" {
  value = local.issuer
}

output "cognito_client_id" {
  value = aws_cognito_user_pool_client.web.id
}

output "cognito_user_pool_id" {
  value = aws_cognito_user_pool.this.id
}

output "ecr_backend_url" {
  value = aws_ecr_repository.backend.repository_url
}

output "ecr_frontend_url" {
  value = aws_ecr_repository.frontend.repository_url
}

output "ecs_cluster" {
  value = aws_ecs_cluster.this.name
}

output "ecs_services" {
  value = [aws_ecs_service.backend.name, aws_ecs_service.worker.name, aws_ecs_service.frontend.name]
}
