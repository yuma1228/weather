variable "project" {
  type = string
}

variable "environment" {
  type = string
}

variable "function_name" {
  type    = string
  default = "poll-weather-data"
}

variable "handler" {
  type    = string
  default = "poll_weather_data.handler"
}

variable "runtime" {
  type    = string
  default = "python3.12"
}

variable "timeout" {
  type    = number
  default = 120
  description = "bosai API 取得 + 推論 + S3/DynamoDB 書き込みの余裕を持たせる"
}

variable "memory_size" {
  type    = number
  default = 1024
  description = "scipy + lightgbm のロードと推論に必要"
}

variable "architectures" {
  type    = list(string)
  default = ["x86_64"]
  description = "lightgbm の互換性のため x86_64 を使用"
}

variable "reserved_concurrent_executions" {
  type    = number
  default = -1
  description = "-1 で制限なし。0 で停止"
}

variable "log_retention_days" {
  type    = number
  default = 14
}
