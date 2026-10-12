output "oidc_provider_arn" {
  description = "GitHub Actions OIDC Provider ARN（各環境の oidc.tf で data source 参照）"
  value       = aws_iam_openid_connect_provider.github.arn
}