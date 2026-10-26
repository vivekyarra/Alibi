"""Environment variables shared by the API and worker containers (interface set by the lead, 2026-10-26)."""

from __future__ import annotations

from aws_cdk import aws_sqs as sqs

from .auth import AuthStack
from .config import InfraConfig
from .data import DataStack
from .storage import StorageStack

API_COMMAND = ["uvicorn", "api.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
WORKER_COMMAND = ["python", "-m", "api.worker", "--sqs"]


def service_env(cfg: InfraConfig, storage: StorageStack, data: DataStack, queue: sqs.IQueue,
                auth: AuthStack) -> dict[str, str]:
    return {
        "GRIDPRINT_MODE": "aws",
        "JOBS_TABLE": data.jobs.table_name,
        "REVIEWS_TABLE": data.reviews.table_name,
        "TRACE_TABLE": data.trace_index.table_name,
        "GRIDLOG_TABLE": data.gridlog.table_name,
        "RESULTS_BUCKET": storage.results.bucket_name,
        "UPLOADS_BUCKET": storage.uploads.bucket_name,
        "JOBS_QUEUE_URL": queue.queue_url,
        "COGNITO_REGION": cfg.region,
        "COGNITO_USER_POOL_ID": auth.user_pool.user_pool_id,
        "COGNITO_CLIENT_ID": auth.web_client.user_pool_client_id,
    }
