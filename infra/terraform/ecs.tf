locals {
  issuer     = "https://cognito-idp.${var.region}.amazonaws.com/${aws_cognito_user_pool.this.id}"
  app_origin = "https://${aws_cloudfront_distribution.app.domain_name}"
  backend_env = [
    { name = "APP_ENV", value = "production" },
    { name = "OIDC_ISSUER", value = local.issuer },
    { name = "OIDC_JWKS_URL", value = "${local.issuer}/.well-known/jwks.json" },
    { name = "OIDC_AUDIENCE", value = aws_cognito_user_pool_client.web.id },
    { name = "CORS_ALLOWED_ORIGINS", value = jsonencode([local.app_origin]) },
    { name = "LIVE_PLANNER_PROVIDER", value = "bedrock" },
    { name = "BEDROCK_GUARDRAIL_ID", value = aws_bedrock_guardrail.this.guardrail_id },
    { name = "BEDROCK_GUARDRAIL_VERSION", value = aws_bedrock_guardrail_version.this.version },
    { name = "AWS_REGION", value = var.region },
    { name = "S3_REGION", value = var.region },
    { name = "S3_BUCKET_RAW_IMPORTS", value = aws_s3_bucket.this["raw_imports"].id },
    { name = "S3_BUCKET_DOCUMENTS", value = aws_s3_bucket.this["documents"].id },
    { name = "S3_BUCKET_EXPORTS", value = aws_s3_bucket.this["exports"].id },
  ]
  database_secret = [{ name = "DATABASE_URL", valueFrom = aws_secretsmanager_secret.database_url.arn }]
}

resource "aws_ecs_cluster" "this" {
  name = "${var.project}-cluster"
}

resource "aws_cloudwatch_log_group" "this" {
  for_each          = toset(["backend", "worker", "frontend"])
  name              = "/ecs/${var.project}/${each.key}"
  retention_in_days = 7
}

resource "aws_ecs_task_definition" "backend" {
  family                   = "${var.project}-backend"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.api_cpu
  memory                   = var.api_memory
  execution_role_arn       = aws_iam_role.task_execution.arn
  task_role_arn            = aws_iam_role.task.arn

  container_definitions = jsonencode([{
    name         = "backend"
    image        = "${aws_ecr_repository.backend.repository_url}:${var.image_tag}"
    essential    = true
    portMappings = [{ containerPort = 8000, protocol = "tcp" }]
    environment  = local.backend_env
    secrets      = local.database_secret
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        awslogs-group         = aws_cloudwatch_log_group.this["backend"].name
        awslogs-region        = var.region
        awslogs-stream-prefix = "backend"
      }
    }
  }])
}

resource "aws_ecs_task_definition" "worker" {
  family                   = "${var.project}-worker"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.small_cpu
  memory                   = var.small_memory
  execution_role_arn       = aws_iam_role.task_execution.arn
  task_role_arn            = aws_iam_role.task.arn

  container_definitions = jsonencode([{
    name        = "worker"
    image       = "${aws_ecr_repository.backend.repository_url}:${var.image_tag}"
    essential   = true
    command     = ["python", "-m", "revenueflowai.worker"]
    environment = local.backend_env
    secrets     = local.database_secret
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        awslogs-group         = aws_cloudwatch_log_group.this["worker"].name
        awslogs-region        = var.region
        awslogs-stream-prefix = "worker"
      }
    }
  }])
}

resource "aws_ecs_task_definition" "frontend" {
  family                   = "${var.project}-frontend"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.small_cpu
  memory                   = var.small_memory
  execution_role_arn       = aws_iam_role.task_execution.arn

  container_definitions = jsonencode([{
    name         = "frontend"
    image        = "${aws_ecr_repository.frontend.repository_url}:${var.image_tag}"
    essential    = true
    portMappings = [{ containerPort = 5173, protocol = "tcp" }]
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        awslogs-group         = aws_cloudwatch_log_group.this["frontend"].name
        awslogs-region        = var.region
        awslogs-stream-prefix = "frontend"
      }
    }
  }])
}

resource "aws_ecs_service" "backend" {
  name            = "${var.project}-backend"
  cluster         = aws_ecs_cluster.this.id
  task_definition = aws_ecs_task_definition.backend.arn
  desired_count   = var.running ? 1 : 0
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = data.aws_subnets.default.ids
    security_groups  = [aws_security_group.app.id]
    assign_public_ip = true
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.backend.arn
    container_name   = "backend"
    container_port   = 8000
  }

  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }

  depends_on = [aws_lb_listener_rule.api]
}

resource "aws_ecs_service" "worker" {
  name            = "${var.project}-worker"
  cluster         = aws_ecs_cluster.this.id
  task_definition = aws_ecs_task_definition.worker.arn
  desired_count   = var.running ? 1 : 0
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = data.aws_subnets.default.ids
    security_groups  = [aws_security_group.app.id]
    assign_public_ip = true
  }
}

resource "aws_ecs_service" "frontend" {
  name            = "${var.project}-frontend"
  cluster         = aws_ecs_cluster.this.id
  task_definition = aws_ecs_task_definition.frontend.arn
  desired_count   = var.running ? 1 : 0
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = data.aws_subnets.default.ids
    security_groups  = [aws_security_group.app.id]
    assign_public_ip = true
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.frontend.arn
    container_name   = "frontend"
    container_port   = 5173
  }

  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }
}
