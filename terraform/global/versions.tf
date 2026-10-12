terraform {
  required_version = "1.16.5"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "6.67.0"
    }
  }

  # environments/* とは別の state にする。
  backend "s3" {
    bucket       = "raincast-tfstate"
    key          = "global/terraform.tfstate"
    region       = "ap-northeast-1"
    encrypt      = true
    use_lockfile = true
  }
}

# region: IAM はグローバルサービスなので何を指定しても結果が変わらない。変数にしない。
# Project / Scope: global 層では固定値。変数にすると environments 側と重複する。
provider "aws" {
  region              = "ap-northeast-1"
  allowed_account_ids = [var.allowed_account_id]

  default_tags {
    tags = {
      Project   = "raincast"
      Scope     = "global"
      ManagedBy = "Terraform"
    }
  }
}
