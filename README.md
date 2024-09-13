# Withings -> GarminConnect Sync via AWS Lambda

This repository contains an automated way to synchronize withings health data from a scale with Garmin Connect automatically.
It does this by deploying an AWS Lambda function which is triggered by a cron schedule every 10 minutes. The lambda function is deployed automatically using [OpenTofu](https://opentofu.org/).

## How to use

First, fork this repository and clone it to your machine.

### Prepare OpenTofu S3 backend

We will use the S3 backend to store the OpenTofu state. This will include a DynamoDB table for state locking. 
To do that, we need to create a bucket called `tf-state-bucket-withings-garmin-sync` and a DynamoDB table called `withings-garmin-sync` (partition key `LockID`) manually. Of course you can name them something else and replace the names in `tofu/main.tf`.

### Create a Withings developer account

Visit [https://developer.withings.com/dashboard/](https://developer.withings.com/dashboard/) and sign up for a developer account with withings (it's free). Create an application and select "Public API Integration" as the type of integration.
The application name as well as its description don't matter. Be sure to select "Development" as the target environment and set `http://127.0.0.1` as the primary registered OAuth callback url. 
Copy the ClientID and Secret to a secure place, you are going to need them later.

Before deploying the automated sync, you need to retrieve an initial access token for your personal withings account. After that, the token will be renewed automatically by the lambda function.  
To retrieve the initial token, execute the `retrieve_initial_withings_token.py` script locally. It will guide you through the process and display the token, as well as a refresh token and a validity duration, at the end. The script will display a link which when visited prompts you to authorize an application to read your withings data. Login with your withings account, _not_ your withings developer account. After that, withings will redirect you to a URL like `http://127.0.0.1/?code=value&code=blargh-foo&state=dummy-state`. Copy the value of the `code` parameter and enter it in the script when prompted.

### Configure GitHub Actions ENV Secrets

The script, packaged as an image, is deployed using OpenTofu. To do this, it needs to have multiple github actions secrets, which you need to configure manually.

| Key  | Value  |
|---|---|
| AWS_ACCESS_KEY_ID  | Key ID of an AWS role  |
| AWS_SECRET_ACCESS_KEY  | Secret of an AWS role  |
| AWS_ACCOUNT_ID  | AWS account id (e.g. 123456789)  |
| TF_VAR_garmin_connect_email  | email address of your garmin connect account  |
| TF_VAR_garmin_connect_password | password of your garmin connect account |
| TF_VAR_withings_access_token | access token given by script |
| TF_VAR_withings_refresh_token | refresh token given by script |
| TF_VAR_withings_token_valid_until | valid_until value given by script |
| TF_VAR_withings_client_id | withings client ID of API application |
| TF_VAR_withings_secret | withings secret of API application |

> [!IMPORTANT]  
> The AWS role needs to have permissions to create ECR repositories, push to ECR repositories, create Lambda functions and create S3 buckets

> [!IMPORTANT]  
> This script does not support MFA enabled Garmin Connect accounts

After you have set all the environment variables, you can trigger the github action by hand which should build the image, push it and create all tofu resources.

## How it works

## Cost to operate

## Troubleshooting

