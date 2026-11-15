output "oidc_provider_arn" {
  description = "GitHub Actions OIDC Provider ARN。apply 後の確認用。各環境は ARN を文字列で組み立てるため参照しない"
  value       = aws_iam_openid_connect_provider.github.arn
}
