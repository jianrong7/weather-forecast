output "lambda_function_name" {
  value       = aws_lambda_function.rain_worker.function_name
  description = "Name of the scheduled Lambda function"
}

output "lambda_function_arn" {
  value       = aws_lambda_function.rain_worker.arn
  description = "ARN of the scheduled Lambda function"
}

output "dynamodb_table_name" {
  value       = aws_dynamodb_table.rain_alert_state.name
  description = "DynamoDB table for profile and alert state"
}

output "event_rule_arn" {
  value       = aws_cloudwatch_event_rule.schedule.arn
  description = "EventBridge schedule ARN"
}

output "iam_role_arn" {
  value       = aws_iam_role.lambda_exec.arn
  description = "IAM role used by Lambda"
}
