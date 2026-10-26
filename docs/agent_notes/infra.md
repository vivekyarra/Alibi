# Agent notes — infra/ and bench/ scaffolding (2026-10-26)

Scope: `infra/` (AWS CDK v2, Python), `bench/prices.py`, `bench/cool_evidence.py`, `bench/configs.yaml`,
`bench/README.md`, `bench/run_remote.md`, tests in `infra/tests/` and `bench/tests/`.
Nothing was deployed. There is no `gridprint` AWS profile on this machine (H1 is BLOCKED-HUMAN).

## Versions (checked 2026-10-26)

- `npm view aws-cdk-lib version` -> `2.274.0`; `npm view constructs version` -> `10.8.1`;
  `npm view aws-cdk version` -> `2.1146.1` (CLI, run through `npx aws-cdk@2`).
- Installed into the venv: `uv pip install --python D:/Open-cv/.venv aws-cdk-lib constructs` ->
  `aws-cdk-lib==2.274.0`, `constructs==10.8.1`, `jsii==1.142.0`. Pinned in `infra/requirements.txt`.
  These packages are not in `pyproject.toml`/`uv.lock` (outside this scope); `uv sync` will remove them.
  Suggested: add an `infra` dependency group with these pins.
- Importing `aws_cdk` on this Windows host takes about 4 minutes (jsii start-up). Infra tests are slow.

## Decisions

| ID | Decision | Reason | Alternatives |
|---|---|---|---|
| I-1 | Stacks: Network, Storage, Data, Ai, Auth, Compute, Api, Iot, Web, Observability (+ optional BenchImages with `-c bench=true`). All in `aws.region` from config. | SPEC 10.6 table. | One stack (harder to read). |
| I-2 | API = Fargate arm64 service behind an **internal** ALB; CloudFront reaches it through a CloudFront **VPC origin**; `/v1/*` routed by CloudFront. | Simplest way to put the API behind the same CloudFront + WAF as the web app with no public ALB and no custom domain. | API Gateway HTTP API + VPC link (more parts); public ALB (bypasses WAF). |
| I-3 | CloudFront -> ALB hop is HTTP inside the VPC. Viewer -> CloudFront is HTTPS only (redirect or HTTPS-only behaviors; see I-21 for the TLS version). | HTTPS to the ALB needs a domain and ACM certificate, which the project does not have. | Add a domain + ACM cert later (human). |
| I-4 | Upload retention: S3 lifecycle counts whole days, so `limits.upload_retention_hours` is rounded up: `ceil(hours/24)`, minimum 1 day. 24 h -> 1 day. S3 runs lifecycle once a day, so deletion can be later than the exact limit. If an exact-hour deletion is needed, the API/worker must delete the upload after analysis. | S3 lifecycle has no hour unit. | Scheduled Lambda that deletes by hour (more code). |
| I-5 | (Superseded) Uploads CORS is `PUT` from the CloudFront origin only, set by a custom resource in the Web stack. | Lead interface; avoids a stack cycle. | `*` origin. |
| I-6 | Buckets and tables use `RemovalPolicy.DESTROY` and bucket auto-delete. | SPEC 10.6: `make destroy` removes everything. | RETAIN (would break `make destroy`). |
| I-7 | Worker: `Ec2TaskDefinition`, bridge network mode, placement constraint `attribute:ecs.cpu-architecture == arm64`. | CDK rejects `runtimePlatform` on EC2 tasks ("Cannot specify runtimePlatform in non-Fargate and non-Managed Instances compatible tasks", seen at synth). Bridge mode avoids task-ENI support on the Ubuntu COOL host. | awsvpc mode. |
| I-8 | COOL host: when `aws.cool_ami_id` is set, the ASG uses that AMI; user data installs `docker.io` and `amazon-ecs-init-latest.arm64.deb` from `https://s3.<region>.amazonaws.com/amazon-ecs-agent-<region>/` and starts `ecs.service` with `--no-block` (ECS developer guide, "Installing the Amazon ECS container agent"). The worker container mounts `/opt/cool` and `/opt/ffmpeg` read-only and sets `PYTHONPATH=<cool site-packages>:/app:/app/engine`, `LD_LIBRARY_PATH=/opt/cool/cpp_sdk/lib`. Without `cool_ami_id`: ECS-optimized AL2023 arm64 AMI and stock OpenCV (no COOL claim). | Keeps one arm64 image for B and C. | Bake the engine natively on the AMI (no containers); COOL Docker Marketplace product (see "Found" below). |
| I-9 | Scaling: step scaling on `visible + in-flight` SQS messages (1-minute max); 0 -> scale to 0, >=1 -> +1, >=5 -> +2; max tasks = `worker_max_instances` (default 4). ASG capacity provider uses managed scaling, min 0. One worker task per c8g.2xlarge (7168 CPU units, 13312 MiB). | In-flight jobs keep their task alive; idle cost is zero. | Target tracking on backlog-per-task. |
| I-10 | SQS: visibility timeout 1800 s, DLQ after 3 receives. | Longer than `decode_timeout_s` (300) plus analysis. | — |
| I-11 | Bedrock IAM: one statement, actions `bedrock:InvokeModel` and `bedrock:InvokeModelWithResponseStream`, resources = inference profile `arn:aws:bedrock:<region>:<account>:inference-profile/<model_id>` and the foundation model `anthropic.claude-sonnet-4-6` with Region `*` and the empty-Region form. | The Converse API reference states "This operation requires permission for the `bedrock:InvokeModel` action" (checked 2026-10-26, https://docs.aws.amazon.com/bedrock/latest/APIReference/API_runtime_Converse.html). There is no separate Converse IAM action. A global profile can route to any Region. | Add a `bedrock:InferenceProfileArn` condition (not verified; left out). |
| I-12 | IoT policy uses thing policy variables: connect only as `${iot:Connection.Thing.ThingName}` with `iot:Connection.Thing.IsAttached`; publish only to `gridprint/${iot:Connection.Thing.Attributes[zone]}/${iot:Connection.Thing.ThingName}`. Each Node thing needs attribute `zone`. Certificates are created by a person (H2). Topic rule `SELECT *, topic(2) AS topic_zone, topic(3) AS topic_node FROM 'gridprint/+/+'` -> Lambda `handler.handler` in `node/ingest/` (python3.11, arm64). | SPEC 10.4. | — |
| I-13 | WAF (scope CLOUDFRONT, in us-east-1): rate rule all requests per IP (default 300 / 5 min) and rate rule `POST /v1/jobs*` per IP (default 20 / 5 min). No managed rule groups. | "Anonymous uploads are rate-limited (WAF)". Managed rule groups can block valid requests; not required. | AWSManagedRulesCommonRuleSet. |
| I-14 | Cognito: no self sign-up, email sign-in, TOTP MFA required, group `reviewer`, public SPA client with SRP auth. | Reviewers approve CONTRADICTED (R3). | Hosted UI (needs a domain). |
| I-15 | Observability: app metrics as EMF in namespace `GRIDPRINT` (contract table in `observability.py`); alarms -> SNS topic (no subscriber; human adds one): app errors, ingest Lambda errors, ALB target 5xx, DLQ depth > 0, NodeFreshnessSeconds > `grid.freshness_limit_s` per Node zone (missing data = breaching). | SPEC 10.6. | — |
| I-21 | CloudFront uses its default certificate, so `minimumProtocolVersion` has no effect (CDK synth warning: the default certificate policy is fixed at TLSv1). Viewer TLS 1.2+ needs a custom domain + ACM certificate. | No domain yet. | Add a domain (human). |
| I-22 | Docker build contexts are allow-lists (`*` then `!path`, `IgnoreMode.DOCKER`): engine = Dockerfile, pyproject.toml, uv.lock, config, engine, agent, mcp_server, api, models; API = Dockerfile, pyproject.toml, uv.lock, config, engine, api. | A deny-list staged the whole repo and failed when another agent's transient log file vanished during copy. Checked by listing the staged asset folders after synth. | Deny-list. |
| I-16 | No Secrets Manager secret is created. | The current design has no application secret: AWS access is by IAM roles, Bedrock by IAM, Cognito JWTs are checked with public keys, Node keys stay on the device. Creating an unused secret would be fake. Any future secret goes to Secrets Manager. | — |
| I-17 | Site bucket uses SSE-S3 (not KMS). | Static public web assets only; keeps OAC simple. Video and reports stay in KMS buckets. | SSE-KMS + key policy for CloudFront. |
| I-18 | No CloudFront error-response rewrite to `index.html`. | It would also rewrite API 403/404 answers. The web app should use hash routing or only root URLs. | CloudFront Function for SPA paths. |
| I-19 | `bench/configs.yaml`: A `c7i.2xlarge`, B/C `c8g.2xlarge`. Both 8 vCPU / 16.00 GiB (AWS docs table, checked 2026-10-26, https://docs.aws.amazon.com/ec2/latest/instancetypes/co.html). c7i has 4 cores x 2 threads; c8g has 8 cores x 1 thread. | SPEC Part 12 equal vCPU and memory. | — |
| I-20 | Cost of C = EC2 on-demand + COOL Marketplace software fee per hour, recorded by a person with URL and date. `prices.py` reads only the Price List API. | The Marketplace fee is not in the EC2 price list. | — |

## Optional config keys read by infra (defaults in `infra/gridprint_infra/config.py`)

Not yet in `config/default.yaml` (outside this scope). The lead may add them:
`aws.cool_ami_id` (unset), `aws.worker_instance_type` (`c8g.2xlarge`), `aws.worker_max_instances` (4),
`aws.waf_rate_limit_5min` (300), `aws.waf_job_create_limit_5min` (20),
`aws.cool_pythonpath` (`/opt/cool/python_3.11/site-packages`, NOT verified),
`aws.cool_ld_library_path` (`/opt/cool/cpp_sdk/lib`), `grid.node_zones` (`[IN]`, assumption).

## Contracts other components must match (interface set by the lead, 2026-10-26)

- Env vars on API and worker: `GRIDPRINT_MODE=aws`, `JOBS_TABLE`, `REVIEWS_TABLE`, `TRACE_TABLE`, `GRIDLOG_TABLE`,
  `RESULTS_BUCKET`, `UPLOADS_BUCKET`, `JOBS_QUEUE_URL`, `COGNITO_REGION`, `COGNITO_USER_POOL_ID`, `COGNITO_CLIENT_ID`
  (`infra/gridprint_infra/runtime_env.py`). Extra: `GRIDPRINT_METRIC_NAMESPACE` (both), `GRIDPRINT_COOL_HOST` (worker);
  on COOL hosts the worker also gets `PYTHONPATH` (COOL site-packages first) and `LD_LIBRARY_PATH`.
- Ingest Lambda env: `GRIDPRINT_GRIDLOG_TABLE`, `GRIDPRINT_METRIC_NAMESPACE`; handler `node/ingest/handler.py: handler`.
- Table keys: Jobs, Reviews, TraceIndex: `pk` (S) only, PAY_PER_REQUEST, PITR on, no TTL, no GSI.
  GridLog: `pk` (S, "zone#YYYYMMDD") + `t` (N, epoch second).
- Commands: API `uvicorn api.app:create_app --factory --host 0.0.0.0 --port 8000` (health `GET /v1/health`);
  worker `python -m api.worker --sqs`. Set both in the Dockerfile CMD and in the ECS task definition.
- Engine image copies `config engine agent mcp_server api models`; API image copies `config engine api`.
  Both use repo-root build context and `PYTHONPATH=/app:/app/engine`.
- Uploads CORS: `PUT` only from `https://<cloudfront domain>`, header `Content-Type`, set by a custom resource
  (`AwsCustomResource` -> `S3 putBucketCors`) in the Web stack, because the domain exists only after the distribution
  is created (a Storage-stack rule would create a stack cycle). This replaces decision I-5.
- Worker IAM: S3 read/write on uploads and results, DynamoDB read/write on all 4 tables, SQS consume
  (receive, delete, change visibility), Bedrock InvokeModel on the pinned profile (covers Converse).
- API IAM: uploads put/read, results read, Jobs/Reviews read/write, TraceIndex/GridLog read, SQS send.
- `pyproject.toml` `testpaths` does not include `infra/tests` or `bench/tests`; run `pytest infra bench`.
- `cdk.json` runs `python app.py`; the venv must be first on PATH when `make deploy` calls `npx aws-cdk@2`.

## Found during verification (for docs/VERIFICATION.md V5; not written there, outside scope)

- COOL Graviton4 listing (https://aws.amazon.com/marketplace/pp/prodview-fdvbfiewzuehs, fetched 2026-10-26):
  AMI, Ubuntu 24.04 LTS, "Built on OpenCV 5.0", Arm KleidiCV, compatible families c8g/m8g/r8g, Python
  venvs `python_3.10`, `python_3.11`, `python_3.12` under `/opt/cool/venvs/`, C++ SDK `/opt/cool/cpp_sdk/lib`,
  usage-based hourly software fee, 7-day trial. The listing mentions a separate Docker product.
- A COOL "Graviton4 [Docker]" listing exists per search results (targets ECS/EKS, Python 3.10-3.12); not opened.
  It may be a simpler path than mounting host libraries.
- COOL Graviton5 listing (prodview-igdweaoo6prb6) is for c9g/m9g, OpenCV 5.1.0, KleidiCV 0.7.0; not used.

## Not verified

- COOL Python site-packages path for 3.11 inside the AMI, and whether COOL libraries (Ubuntu 24.04 glibc)
  load inside the Debian-based `python:3.11-slim` container. `run_remote.md` step C3 checks this; native fallback given.
- The COOL AMI root device name and whether ECS awsvpc/cgroup settings need changes on Ubuntu 24.04.
- `opencv-python-headless==5.0.0.93` arm64 wheel availability (D-003; affects the arm64 image build).
- `ghcr.io/astral-sh/uv:0.11.8` image tag (matches local `uv 0.11.8`).
- CloudFront VPC origin with an internal ALB has not been deployed; synth only.
- Deployer policy (`infra/iam/deployer-policy.json`) is a scoped starting point; not tested against a real
  `cdk bootstrap`. Default bootstrap gives the CloudFormation execution role AdministratorAccess unless
  `--cloudformation-execution-policies` is passed.
