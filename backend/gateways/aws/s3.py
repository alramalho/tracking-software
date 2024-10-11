from botocore.exceptions import ClientError
from shared.logger import logger
from constants import AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, S3_BUCKET_NAME
import boto3


class S3Gateway:
    def __init__(self):
        self.bucket = boto3.resource(
            "s3",
            aws_access_key_id=AWS_ACCESS_KEY_ID,
            aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
            region_name="eu-central-1",
        ).Bucket(S3_BUCKET_NAME)

    def upload(self, bytes: bytes, key: str):
        try:
            self.bucket.put_object(Key=key, Body=bytes)
        except ClientError as e:
            logger.error(f"Error putting file onto {S3_BUCKET_NAME}")
            raise e

    def get_bytes(self, key: str):
        return self.bucket.Object(key).get()["Body"].read()

    def get_text(self, key: str) -> str:
        return self.get_bytes(key).decode("utf-8")

    def file_exists(self, key: str) -> bool:
        try:
            self.bucket.Object(key).load()
            return True
        except ClientError as e:
            if e.response["Error"]["Code"] == "404":
                return False
            else:
                raise e