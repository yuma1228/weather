variable "project" {
  type = string
}

variable "environment" {
  type = string
}

variable "table_name" {
  type = string
}

variable "billing_mode" {
  type    = string
  default = "PROVISIONED"

  validation {
    condition     = contains(["PROVISIONED", "PAY_PER_REQUEST"], var.billing_mode)
    error_message = "Invalid billing mode. Valid values are PROVISIONED or PAY_PER_REQUEST."
  }
}

variable "hash_key" {
  type = string
}

variable "range_key" {
  type = string
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
