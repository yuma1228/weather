variable "project" {
  type    = string
  default = "weather"
}

variable "environment" {
  type    = string
  default = "dev"
}

variable "region" {
  type    = string
  default = "ap-northeast-1"
}

variable "aws_profile" {
  type    = string
  default = "yuma"
}

variable "allowed_account_id" {
  type        = string
  description = "apply を許可する AWS アカウントID。public リポジトリに置かないため tfvars で渡す。"
}

// S3 
variable "bucket_name" {
  type    = string
  default = "weather-data"
}

variable "versioning_enabled" {
  type    = bool
  default = true
}

