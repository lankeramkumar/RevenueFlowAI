resource "random_id" "suffix" {
  byte_length = 3
}

locals {
  buckets = {
    raw_imports = "${var.project}-raw-imports-${random_id.suffix.hex}"
    documents   = "${var.project}-documents-${random_id.suffix.hex}"
    exports     = "${var.project}-exports-${random_id.suffix.hex}"
  }
}

resource "aws_s3_bucket" "this" {
  for_each = local.buckets

  bucket        = each.value
  force_destroy = true # demo data is regenerated on each `aws-up`; teardown must not block
}

resource "aws_s3_bucket_public_access_block" "this" {
  for_each = aws_s3_bucket.this

  bucket                  = each.value.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "this" {
  for_each = aws_s3_bucket.this

  bucket = each.value.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_ecr_repository" "backend" {
  name         = "${var.project}-backend"
  force_delete = true
}

resource "aws_ecr_repository" "frontend" {
  name         = "${var.project}-frontend"
  force_delete = true
}
