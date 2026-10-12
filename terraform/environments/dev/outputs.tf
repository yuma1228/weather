output "gh_terraform_main_arn" {
  value = aws_iam_role.gh_terraform_main.arn
}

output "gh_terraform_pr_arn" {
  value = aws_iam_role.gh_terraform_pr.arn
}
