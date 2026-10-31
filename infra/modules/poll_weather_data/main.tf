# Lambda 関数

# Lambda 実行用 IAM ロール
resource "aws_iam_role" "lambda" {
  name = "${var.project}-${var.environment}-${var.function_name}-lambda"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Action    = "sts:AssumeRole"
      Principal = { Service = "lambda.amazonaws.com" }
    }]
  })
}

# CloudWatch Logs への書き込み権限（Lambda の基本権限）
resource "aws_iam_role_policy_attachment" "basic" {
  role       = aws_iam_role.lambda.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# Lambda 関数
resource "aws_lambda_function" "lambda" {
  function_name = "${var.project}-${var.environment}-${var.function_name}-lambda"
  role          = aws_iam_role.lambda.arn
  filename      = "${path.module}/functions/poll_weather_data.zip"
  source_code_hash = filebase64sha256("${path.module}/functions/poll_weather_data.zip")
  handler       = var.handler
  runtime       = var.runtime
  timeout       = var.timeout
  memory_size   = var.memory_size
  architectures = var.architectures

  reserved_concurrent_executions = var.reserved_concurrent_executions

}

# CloudWatch Logs のロググループ（保持期間を設定）
resource "aws_cloudwatch_log_group" "this" {
  name              = "/aws/lambda/${aws_lambda_function.lambda.function_name}"
  retention_in_days = var.log_retention_days
}

# event scheduler
resource "aws_iam_role" "event_scheduler" {
  name = "${var.project}-${var.environment}-${var.function_name}-event-scheduler"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Action    = "sts:AssumeRole"
      Principal = { Service = "events.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy" "event_scheduler" {
  role = aws_iam_role.event_scheduler.name

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Action    = "lambda:InvokeFunction"
      Resource  = aws_lambda_function.lambda.arn
    }]
  })
}

resource "aws_scheduler_schedule" "event_scheduler" {
  name = "${var.project}-${var.environment}-${var.function_name}-event-scheduler"
  schedule_expression = var.schedule_expression
  target {
      arn = aws_lambda_function.lambda.arn
      role_arn = aws_iam_role.event_scheduler.arn
  }
  flexible_time_window {
    mode = "OFF"
  }
}
