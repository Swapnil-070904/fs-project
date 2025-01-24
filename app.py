import boto3
import json
import time
from flask import Flask, request, jsonify, render_template

app = Flask(__name__, static_folder='static', template_folder='templates')

# AWS region and account details
AWS_REGION = 'ap-south-1'  # Specify your AWS region
AWS_ACCOUNT_ID = '533267092098'  # Replace with your AWS Account ID

# Create an S3 client and resource using the default session (it will use the credentials from AWS CLI)
s3_client = boto3.client('s3', region_name=AWS_REGION)
s3_resource = boto3.resource('s3', region_name=AWS_REGION)

@app.route('/')
def home():
    # Serve the homepage.
    return render_template('index.html')

@app.route('/create_bucket', methods=['POST'])
def create_bucket():
    # Endpoint to create an S3 bucket, enable static website hosting, versioning, and public read access.
    try:
        bucket_name = request.json.get('bucket_name')
        if not bucket_name:
            return jsonify({'error': 'Bucket name is required'}), 400

        # Prepend the AWS account ID to the bucket name to ensure it's unique
        bucket_name = f"{AWS_ACCOUNT_ID}-{bucket_name}"

        # Step 1: Create the S3 bucket in the specified region
        s3_client.create_bucket(
            Bucket=bucket_name,
            CreateBucketConfiguration={'LocationConstraint': AWS_REGION},
        )

        # Wait until the bucket exists
        s3_client.get_waiter('bucket_exists').wait(Bucket=bucket_name)

        # Step 2: Disable public access block to allow public read access
        s3_client.put_public_access_block(
            Bucket=bucket_name,
            PublicAccessBlockConfiguration={
                'BlockPublicAcls': False,
                'IgnorePublicAcls': False,
                'BlockPublicPolicy': False,
                'RestrictPublicBuckets': False
            }
        )

        # Step 3: Enable static website hosting
        s3_client.put_bucket_website(
            Bucket=bucket_name,
            WebsiteConfiguration={
                'IndexDocument': {'Suffix': 'index.html'},
                'ErrorDocument': {'Key': 'error.html'},
            },
        )

        # Step 4: Enable versioning on the bucket
        s3_client.put_bucket_versioning(
            Bucket=bucket_name,
            VersioningConfiguration={'Status': 'Enabled'},
        )

        # Step 5: Set public read access policy for the bucket (removes ACL usage)
        public_read_policy = {
            'Version': '2012-10-17',
            'Statement': [
                {
                    'Effect': 'Allow',
                    'Principal': '*',
                    'Action': 's3:GetObject',
                    'Resource': f'arn:aws:s3:::{bucket_name}/*',
                }
            ]
        }

        # Apply the public read policy to the bucket
        s3_client.put_bucket_policy(
            Bucket=bucket_name,
            Policy=json.dumps(public_read_policy)
        )

        return jsonify({'message': f'Bucket {bucket_name} created successfully with public read access!'}), 200

    except Exception as e:
        print(f"Error creating bucket: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/list_buckets', methods=['GET'])
def list_buckets():
    # Endpoint to list all S3 buckets.
    try:
        # List all buckets using the S3 resource
        bucket_names = [bucket.name for bucket in s3_resource.buckets.all()]
        return jsonify({'buckets': bucket_names}), 200
    except Exception as e:
        print(f"Error listing buckets: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/upload', methods=['POST'])
def upload_files():
    # Endpoint to upload files to an existing S3 bucket.
    try:
        # Get files and bucket name from the request
        files = request.files.getlist('files')
        bucket_name = request.form.get('bucket_name')
        if not files or not bucket_name:
            return jsonify({'error': 'Files and bucket name are required'}), 400

        # Access the S3 bucket using the resource
        s3_bucket = s3_resource.Bucket(bucket_name)

        # Retry mechanism to wait until the bucket exists
        max_retries = 10
        for attempt in range(max_retries):
            try:
                print(f"Attempting to access bucket: {bucket_name}")
                s3_client.head_bucket(Bucket=bucket_name)
                print(f"Bucket {bucket_name} is accessible.")
                break
            except s3_client.exceptions.NoSuchBucket:
                print(f"Bucket {bucket_name} does not exist, attempt {attempt + 1}")
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)  # Exponential backoff
                else:
                    print(f"Final attempt: Bucket {bucket_name} not accessible.")
                    return jsonify({'error': 'Bucket does not exist or is not accessible'}), 500
            except Exception as e:
                print(f"Error accessing bucket {bucket_name}: {str(e)}")
                return jsonify({'error': f"Error accessing bucket {bucket_name}: {str(e)}"}), 500

        # Upload files to the specified bucket with proper Content-Type
        for file in files:
            content_type = file.content_type  # Get the file's MIME type
            print(f"Uploading file: {file.filename} with Content-Type: {content_type}")

            # Upload the file with Content-Type metadata
            s3_bucket.put_object(
                Key=file.filename,
                Body=file,
                ContentType=content_type,
                CacheControl="no-cache, no-store, must-revalidate"
            )
            print(f"File {file.filename} uploaded successfully.")

        # Return the S3 static website URL
        url = f"http://{bucket_name}.s3-website.{AWS_REGION}.amazonaws.com"
        print(f"Website URL: {url}")
        return jsonify({'url': url}), 200

    except Exception as e:
        print(f"Error uploading files: {str(e)}")
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    app.run(debug=True)
