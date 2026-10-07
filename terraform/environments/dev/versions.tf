terraform {
  required_version = "1.16.5"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "6.67.0"
    }
  }

  # backend は provider の設定を読まず、独自に認証情報を解決する。
  # profile は書かない: ローカルは AWS_PROFILE 環境変数、CI は OIDC が環境変数で渡す。
  backend "s3" {
    bucket       = "raincast-tfstate"
    key          = "dev/terraform.tfstate"
    region       = "ap-northeast-1"
    encrypt      = true
    use_lockfile = true
  }
}

provider "aws" {
  region              = var.region
  allowed_account_ids = [var.allowed_account_id]

  default_tags {
    tags = {
      Project     = var.project
      Environment = var.environment
      ManagedBy   = "Terraform"
    }
  }
}
