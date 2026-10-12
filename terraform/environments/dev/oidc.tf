data "aws_iam_openid_connect_provider" "github" {
  url = "https://token.actions.githubusercontent.com"
}

resource "aws_iam_role" "gh_terraform_main" {
  name = "${var.project}-${var.environment}-${var.ci_branch}-gh-terraform"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Action    = "sts:AssumeRoleWithWebIdentity"
      Principal = { Federated = data.aws_iam_openid_connect_provider.github.arn }
      Condition = {
        StringEquals = {
          "token.actions.githubusercontent.com:aud" = "sts.amazonaws.com"
          "token.actions.githubusercontent.com:sub" = [
            "repo:${var.github_repo}:ref:refs/heads/${var.ci_branch}"
          ]
        }
      }
    }]
  })
}

resource "aws_iam_role" "gh_terraform_pr" {
  name = "${var.project}-${var.environment}-pr-gh-terraform"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Action    = "sts:AssumeRoleWithWebIdentity"
      Principal = { Federated = data.aws_iam_openid_connect_provider.github.arn }
      Condition = {
        StringEquals = {
          "token.actions.githubusercontent.com:aud" = "sts.amazonaws.com"
          "token.actions.githubusercontent.com:sub" = [
            "repo:${var.github_repo}:pull_request"
          ]
        }
      }
    }]
  })
}

resource "aws_iam_role_policy_attachment" "gh_terraform_pr_readonly" {
  role       = aws_iam_role.gh_terraform_pr.name
  policy_arn = "arn:aws:iam::aws:policy/ReadOnlyAccess"
}

resource "aws_iam_role_policy" "gh_terraform_main" {
  name = "terraform-apply"
  role = aws_iam_role.gh_terraform_main.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "TfState"
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:DeleteObject",
          "s3:ListBucket",
        ]
        Resource = [
          "arn:aws:s3:::${var.tfstate_bucket}",
          "arn:aws:s3:::${var.tfstate_bucket}/*",
        ]
      },
      {
        Sid    = "ManagedResources"
        Effect = "Allow"
        Action = [
          "s3:*",
          "dynamodb:*",
          "lambda:*",
          "logs:*",
          "cloudfront:*",
          "scheduler:*",
          "sns:*",
          "budgets:*",
        ]
        Resource = "*"
      },
      {
        Sid    = "ProjectIam"
        Effect = "Allow"
        Action = ["iam:*"]
        Resource = [
          "arn:aws:iam::${var.allowed_account_id}:role/${var.project}-${var.environment}-*",
          "arn:aws:iam::${var.allowed_account_id}:policy/${var.project}-${var.environment}-*",
        ]
      },
      {
        Sid      = "PassRoleToLambda"
        Effect   = "Allow"
        Action   = ["iam:PassRole"]
        Resource = "arn:aws:iam::${var.allowed_account_id}:role/${var.project}-${var.environment}-*"
        Condition = {
          StringEquals = { "iam:PassedToService" = "lambda.amazonaws.com" }
        }
      }
    ]
  })
}

resource "aws_iam_role_policy" "gh_terraform_pr" {
  name = "terraform-plan"
  role = aws_iam_role.gh_terraform_pr.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "TfStateRead"
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:ListBucket",
        ]
        Resource = [
          "arn:aws:s3:::${var.tfstate_bucket}",
          "arn:aws:s3:::${var.tfstate_bucket}/*",
        ]
      },
      {
        Sid    = "TfStateLock"
        Effect = "Allow"
        Action = [
          "s3:PutObject",
          "s3:DeleteObject",
        ]
        Resource = "arn:aws:s3:::${var.tfstate_bucket}/*.tflock"
      },
    ]
  })
}

