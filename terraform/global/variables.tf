variable "region" {
  type    = string
  default = "ap-northeast-1"
}


variable "allowed_account_id" {
  type        = string
  description = "apply を許可する AWS アカウントID。public リポジトリに置かないため tfvars で渡す。"
}

variable "project" {
  type    = string
  default = "raincast"
}
