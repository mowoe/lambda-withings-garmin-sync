terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 4.16"
    }
  }

  required_version = ">= 1.2.0"

  backend "s3" {
    bucket         = "tf-state-bucket-withings-garmin-sync"
    key            = "state/terraform.tfstate"
    region         = "eu-central-1"
    dynamodb_table = "withings-garmin-sync"
  }
}

data "external" "git-tag" {
  program = [
    "git",
    "log",
    "--pretty=format:{ \"sha\": \"%h\" }",
    "-1",
    "HEAD"
  ]
}

data "aws_ecr_repository" "lambda_image_repo" {
  name = "lambda-withings-garmin-sync"
}

data "aws_ecr_image" "lambda_image" {
  repository_name = "lambda-withings-garmin-sync"
  most_recent     = true
}

variable "garmin_connect_email" {
  type      = string
  sensitive = true
}

variable "garmin_connect_password" {
  type      = string
  sensitive = true
}

variable "withings_access_token" {
  type      = string
  sensitive = true
}

variable "withings_refresh_token" {
  type      = string
  sensitive = true
}

variable "withings_token_valid_until" {
  type      = string
  sensitive = true
}

variable "withings_client_id" {
  type      = string
  sensitive = true
}

variable "withings_secret" {
  type      = string
  sensitive = true
}

resource "aws_s3_bucket" "lambda_bucket" {
  bucket = "withings-garmin-sync-config-bucket"
}

resource "aws_iam_role" "lambda_exec_role" {
  name = "lambda_exec_role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17",
    Statement = [{
      Action = "sts:AssumeRole",
      Effect = "Allow",
      Principal = {
        Service = [
            "lambda.amazonaws.com",
            "scheduler.amazonaws.com",
        ],
      },
    }],
  })

  managed_policy_arns = [
    "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole",
    "arn:aws:iam::aws:policy/AmazonS3FullAccess",
    "arn:aws:iam::aws:policy/AmazonEventBridgeSchedulerFullAccess"
  ]
}

resource "aws_lambda_function" "withings_garmin_sync_function" {
  function_name = "withings_garmin_sync_function"
  role          = aws_iam_role.lambda_exec_role.arn
  image_uri     = "${data.aws_ecr_repository.lambda_image_repo.repository_url}:${data.external.git-tag.result.sha}"
  timeout       = 900
  package_type  = "Image"
  environment {
    variables = {
      GARMIN_CONNECT_EMAIL       = var.garmin_connect_email
      GARMIN_CONNECT_PASSWORD    = var.garmin_connect_password
      WITHINGS_ACCESS_TOKEN      = var.withings_access_token
      WITHINGS_REFRESH_TOKEN     = var.withings_refresh_token
      WITHINGS_TOKEN_VALID_UNTIL = var.withings_token_valid_until
      WITHINGS_CLIENT_ID         = var.withings_client_id
      WITHINGS_SECRET            = var.withings_secret
    }
  }
}

resource "aws_lambda_permission" "allow_s3" {
  statement_id  = "AllowExecutionFromS3"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.withings_garmin_sync_function.function_name
  principal     = "s3.amazonaws.com"
}

resource "aws_scheduler_schedule" "lambda_scheduler" {
  name       = "schedule_garmin_withings_sync"
  group_name = "default"

  flexible_time_window {
    mode = "OFF"
  }

  schedule_expression = "rate(10 minutes)"

  target {
    arn      = aws_lambda_function.withings_garmin_sync_function.arn
    role_arn = aws_iam_role.lambda_exec_role.arn
  }
}