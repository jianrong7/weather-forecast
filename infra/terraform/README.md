# Terraform Module (Single Module)

This module provisions the full AWS infrastructure for the rain alert worker:

- DynamoDB table (`PK`, `SK`)
- Lambda function
- Lambda IAM role and inline policy
- CloudWatch log group
- EventBridge schedule (default: every 5 minutes from 07:00-22:55 Singapore time; quiet hours 23:00-07:00 are not scheduled)
- Lambda invoke permission for EventBridge

## Prerequisites

1. AWS credentials configured (`aws configure` or environment variables).
2. Lambda package zip built at `../../lambda.zip` (default expected path from this folder).

Build package from repo root:

```bash
./scripts/build_lambda_zip.sh
```

## Deploy

```bash
cd infra/terraform
cp terraform.tfvars.example terraform.tfvars
# edit terraform.tfvars
terraform init
terraform apply
```

## Required variables

- `telegram_bot_token`

## Common overrides

- `telegram_chat_id`
- `aws_region`
- `lambda_zip_path`
- `lambda_function_name`
- `table_name`
- `schedule_expression`

## Outputs

- `lambda_function_name`
- `lambda_function_arn`
- `dynamodb_table_name`
- `event_rule_arn`
- `iam_role_arn`
