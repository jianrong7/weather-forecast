variable "aws_region" {
  description = "AWS region for all resources"
  type        = string
  default     = "ap-southeast-1"
}

variable "name_prefix" {
  description = "Prefix used for IAM role and scheduler names"
  type        = string
  default     = "rain-radar"
}

variable "table_name" {
  description = "DynamoDB table name"
  type        = string
  default     = "rain_alert_state"
}

variable "user_id" {
  description = "Logical user id stored in DynamoDB PK"
  type        = string
  default     = "me"
}

variable "lambda_function_name" {
  description = "Lambda function name"
  type        = string
  default     = "rain-radar-worker"
}

variable "lambda_zip_path" {
  description = "Path to deployment zip generated from this repo"
  type        = string
  default     = "../../lambda.zip"
}

variable "lambda_handler" {
  description = "Python Lambda handler"
  type        = string
  default     = "weather_bot.handler.lambda_handler"
}

variable "lambda_runtime" {
  description = "Lambda runtime"
  type        = string
  default     = "python3.12"
}

variable "lambda_timeout" {
  description = "Lambda timeout in seconds"
  type        = number
  default     = 30
}

variable "lambda_memory_mb" {
  description = "Lambda memory in MB"
  type        = number
  default     = 128
}

variable "schedule_expression" {
  description = "EventBridge schedule expression in UTC. Default runs every 5 minutes from 07:00-22:55 Singapore time (quiet hours 23:00-07:00 SGT are skipped)."
  type        = string
  default     = "cron(0/5 0-14,23 ? * * *)"
}

variable "log_retention_days" {
  description = "CloudWatch log retention"
  type        = number
  default     = 7
}

variable "telegram_bot_token" {
  description = "Telegram bot token"
  type        = string
  sensitive   = true
}

variable "telegram_chat_id" {
  description = "Optional default Telegram chat id"
  type        = string
  default     = null
}

variable "extra_env_vars" {
  description = "Additional Lambda environment variables"
  type        = map(string)
  default     = {}
}

variable "tags" {
  description = "Tags applied to all resources"
  type        = map(string)
  default     = {}
}
