# Cognito replaces the local Keycloak realm for the AWS deployment. Demo users are
# created by scripts/aws-up.ps1 with permanent passwords, so no temporary-password step.

resource "aws_cognito_user_pool" "this" {
  name                     = "${var.project}-users"
  username_attributes      = ["email"]
  auto_verified_attributes = ["email"]
  mfa_configuration        = "OFF" # demo; enable OPTIONAL or ON before any real use

  password_policy {
    minimum_length                   = 12
    require_lowercase                = true
    require_uppercase                = true
    require_numbers                  = true
    require_symbols                  = true
    temporary_password_validity_days = 7
  }

  account_recovery_setting {
    recovery_mechanism {
      name     = "verified_email"
      priority = 1
    }
  }

  admin_create_user_config {
    allow_admin_create_user_only = true # no public self-sign-up for a demo app
  }
}

resource "aws_cognito_user_pool_domain" "this" {
  domain       = "${var.project}-${random_id.suffix.hex}"
  user_pool_id = aws_cognito_user_pool.this.id
}

resource "aws_cognito_user_pool_client" "web" {
  name                                 = "${var.project}-web"
  user_pool_id                         = aws_cognito_user_pool.this.id
  generate_secret                      = false # browser app: PKCE, no client secret
  allowed_oauth_flows_user_pool_client = true
  allowed_oauth_flows                  = ["code"]
  allowed_oauth_scopes                 = ["openid", "profile", "email"]
  supported_identity_providers         = ["COGNITO"]
  callback_urls                        = ["https://${aws_cloudfront_distribution.app.domain_name}/"]
  logout_urls                          = ["https://${aws_cloudfront_distribution.app.domain_name}/"]
  prevent_user_existence_errors        = "ENABLED"
  explicit_auth_flows                  = ["ALLOW_REFRESH_TOKEN_AUTH"]
}
