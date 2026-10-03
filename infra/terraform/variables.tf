variable "region" {
  description = "AWS region."
  type        = string
  default     = "us-east-1"
}

variable "project" {
  description = "Name prefix for every resource."
  type        = string
  default     = "revenueflow"
}

variable "image_tag" {
  description = "Container image tag pushed to ECR (see scripts/aws-up.ps1)."
  type        = string
  default     = "latest"
}

variable "running" {
  description = "false scales every service to zero tasks without destroying anything."
  type        = bool
  default     = true
}

variable "db_instance_class" {
  description = "RDS instance class. db.t4g.micro is the smallest current PostgreSQL option."
  type        = string
  default     = "db.t4g.micro"
}

variable "api_cpu" {
  type    = number
  default = 512
}

variable "api_memory" {
  type    = number
  default = 1024
}

variable "small_cpu" {
  description = "CPU units for the worker and frontend tasks."
  type        = number
  default     = 256
}

variable "small_memory" {
  type    = number
  default = 512
}

