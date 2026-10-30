variable "project" {
  type    = string
  default = "raincast"
}

variable "environment" {
  type    = string
  default = "dev"
}

variable "region" {
  type    = string
  default = "ap-northeast-1"
}

variable "allowed_account_id" {
  type        = string
  description = "apply を許可する AWS アカウントID。public リポジトリに置かないため tfvars で渡す。"
}

// GitHub Actions
variable "github_repo" {
  type        = string
  description = "OIDC で assume を許可するリポジトリ (owner/repo)"
  default     = "yuma1228/weather"
}

variable "ci_branch" {
  type        = string
  description = "apply を許可するブランチ。main に統合したら main に変える"
  default     = "main"
}

variable "tfstate_bucket" {
  type        = string
  description = "versions.tf の backend と同じバケット名"
  default     = "raincast-tfstate"
}
// S3 
variable "bucket_name" {
  type    = string
  default = "data"
}

variable "versioning_enabled" {
  type    = bool
  default = true
}

// DynamoDB
variable "table_name" {
  type    = string
  default = "weather-data"
}

variable "billing_mode" {
  type    = string
  default = "PROVISIONED"
}

variable "hash_key" {
  type    = string
  default = "station_id"
}

variable "range_key" {
  type    = string
  default = "datetime"
}

variable "read_capacity" {
  type    = number
  default = 25
}

variable "write_capacity" {
  type    = number
  default = 25
}

variable "deletion_protection" {
  type    = bool
  default = true
}

variable "ttl_attribute_name" {
  type    = string
  default = "ttl"
}

variable "ttl_enabled" {
  type    = bool
  default = true
}

variable "point_in_time_recovery_enabled" {
  type    = bool
  default = false
}

variable "server_side_encryption_enabled" {
  type    = bool
  default = false
}

// Lambda
// デフォルト値は modules/poll_weather_data_lambda/variables.tf に定義
// 上書きが必要な場合のみここで定義して main.tf で渡す
