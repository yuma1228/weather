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
  type        = string
  description = <<-EOT
    AWS CLI の profile 名。null の場合は環境変数などの既定の認証チェーンを使う。
    CI(GitHub Actions)には ~/.aws が無く profile を解決できないため、既定は null にする。
    ローカルで profile を使いたい場合は AWS_PROFILE 環境変数か terraform.tfvars で指定する
    (terraform.tfvars は .gitignore 済みなので CI には渡らない)。
  EOT
  default     = null
}

variable "allowed_account_id" {
  type        = string
  description = "apply を許可する AWS アカウントID。public リポジトリに置かないため tfvars で渡す。"
}