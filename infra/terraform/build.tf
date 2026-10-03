# Builds the container images inside AWS, so no large upload goes through a
# workstation. Source is uploaded to S3 (scripts/aws-build.ps1), CodeBuild builds
# both images and pushes them to ECR.

resource "aws_s3_bucket" "build_source" {
  bucket        = "${var.project}-build-source-${random_id.suffix.hex}"
  force_destroy = true
}

resource "aws_s3_bucket_public_access_block" "build_source" {
  bucket                  = aws_s3_bucket.build_source.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

data "aws_iam_policy_document" "codebuild_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["codebuild.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "codebuild" {
  name               = "${var.project}-codebuild"
  assume_role_policy = data.aws_iam_policy_document.codebuild_assume.json
}

resource "aws_iam_role_policy" "codebuild" {
  name = "build-images"
  role = aws_iam_role.codebuild.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "EcrLogin"
        Effect   = "Allow"
        Action   = ["ecr:GetAuthorizationToken"]
        Resource = "*"
      },
      {
        Sid    = "EcrPush"
        Effect = "Allow"
        Action = [
          "ecr:BatchCheckLayerAvailability", "ecr:CompleteLayerUpload", "ecr:InitiateLayerUpload",
          "ecr:PutImage", "ecr:UploadLayerPart", "ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer",
        ]
        Resource = [aws_ecr_repository.backend.arn, aws_ecr_repository.frontend.arn]
      },
      {
        Sid      = "ReadSource"
        Effect   = "Allow"
        Action   = ["s3:GetObject", "s3:GetObjectVersion", "s3:GetBucketAcl", "s3:GetBucketLocation"]
        Resource = [aws_s3_bucket.build_source.arn, "${aws_s3_bucket.build_source.arn}/*"]
      },
      {
        Sid      = "Logs"
        Effect   = "Allow"
        Action   = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"]
        Resource = ["arn:aws:logs:${var.region}:*:log-group:/aws/codebuild/${var.project}-images*"]
      },
    ]
  })
}

resource "aws_codebuild_project" "images" {
  name          = "${var.project}-images"
  service_role  = aws_iam_role.codebuild.arn
  build_timeout = 30

  artifacts {
    type = "NO_ARTIFACTS"
  }

  environment {
    compute_type                = "BUILD_GENERAL1_SMALL"
    image                       = "aws/codebuild/standard:7.0"
    type                        = "LINUX_CONTAINER"
    privileged_mode             = true # required to run Docker builds
    image_pull_credentials_type = "CODEBUILD"

    environment_variable {
      name  = "ECR_REGISTRY"
      value = split("/", aws_ecr_repository.backend.repository_url)[0]
    }
    environment_variable {
      name  = "ECR_BACKEND"
      value = aws_ecr_repository.backend.repository_url
    }
    environment_variable {
      name  = "ECR_FRONTEND"
      value = aws_ecr_repository.frontend.repository_url
    }
    environment_variable {
      name  = "VITE_OIDC_AUTHORITY"
      value = "https://cognito-idp.${var.region}.amazonaws.com/${aws_cognito_user_pool.this.id}"
    }
    environment_variable {
      name  = "VITE_OIDC_CLIENT_ID"
      value = aws_cognito_user_pool_client.web.id
    }
  }

  source {
    type      = "S3"
    location  = "${aws_s3_bucket.build_source.bucket}/source.zip"
    buildspec = <<-BUILDSPEC
      version: 0.2
      phases:
        pre_build:
          commands:
            - aws ecr get-login-password --region $AWS_DEFAULT_REGION | docker login --username AWS --password-stdin $ECR_REGISTRY
        build:
          commands:
            - docker build -f infra/Dockerfile.backend -t $ECR_BACKEND:latest backend
            - docker build -f infra/Dockerfile.frontend --build-arg VITE_API_BASE_URL= --build-arg VITE_OIDC_AUTHORITY=$VITE_OIDC_AUTHORITY --build-arg VITE_OIDC_CLIENT_ID=$VITE_OIDC_CLIENT_ID --build-arg VITE_API_TOKEN_KIND=id -t $ECR_FRONTEND:latest frontend
        post_build:
          commands:
            - docker push $ECR_BACKEND:latest
            - docker push $ECR_FRONTEND:latest
    BUILDSPEC
  }

  logs_config {
    cloudwatch_logs {
      group_name = "/aws/codebuild/${var.project}-images"
    }
  }
}
