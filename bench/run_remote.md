# Run the COOL benchmark on EC2 (human task, needs H1)

These steps run configurations A, B and C of `bench/configs.yaml` on EC2 in `us-east-1`.
Run them in order. Stop each instance when its runs finish. Do not edit any result file by hand.

## 0. Before you start

1. Finish H1: the `gridprint` AWS profile works (`aws sts get-caller-identity --profile gridprint`).
2. Subscribe to "Cloud Optimized OpenCV For AWS Graviton4" in AWS Marketplace
   (https://aws.amazon.com/marketplace/pp/prodview-fdvbfiewzuehs). Read the EULA first.
   Write down the software fee per instance-hour for `c8g.2xlarge` from the listing, the URL and the
   date in `results/bench/<date>/cool_software_fee.json`:
   `{"instance_type": "c8g.2xlarge", "usd_per_hour": <value from listing>, "source_url": "...", "date": "YYYY-MM-DD"}`
3. On your workstation, get the EC2 prices (V12):
   `python -m bench.prices c7i.2xlarge c8g.2xlarge`
   This writes `results/bench/<date>/prices.json`.
4. Note the git commit you benchmark: `git rev-parse HEAD`. Use the same commit on every instance.
5. Make sure `bench/inputs.txt` lists every input file with its SHA-256 hash.

## 1. Launch the instances

Use one key pair and a security group that allows SSH only from your IP. Use a 60 GiB gp3 root volume.

| Config | Instance type | AMI |
|---|---|---|
| A | `c7i.2xlarge` | Amazon Linux 2023 x86_64: `aws ssm get-parameter --name /aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64 --query Parameter.Value --output text --profile gridprint --region us-east-1` |
| B | `c8g.2xlarge` | Amazon Linux 2023 arm64: same command with `al2023-ami-kernel-default-arm64` |
| C | `c8g.2xlarge` | The COOL Graviton4 AMI from your Marketplace subscription (Ubuntu 24.04, user `ubuntu`) |

Run one configuration at a time on an otherwise idle instance.

## 2. Prepare each instance

On A and B (Amazon Linux 2023, user `ec2-user`):

```
sudo dnf install -y docker git perf
sudo systemctl enable --now docker
sudo usermod -aG docker ec2-user && newgrp docker
```

On C (Ubuntu 24.04, user `ubuntu`):

```
sudo apt-get update
sudo apt-get install -y docker.io git linux-tools-common linux-tools-aws "linux-tools-$(uname -r)"
sudo usermod -aG docker ubuntu && newgrp docker
```

On every instance:

```
git clone <repo-url> gridprint && cd gridprint && git checkout <commit>
# copy the pinned inputs listed in bench/inputs.txt into data/bench/ (scp or aws s3 cp)
sha256sum -c <(awk '{print $2"  "$1}' bench/inputs.txt)     # adapt to the inputs.txt column order
```

Build the engine image on the instance (native architecture, no emulation):

```
docker build -f infra/docker/engine.Dockerfile -t gridprint-engine:bench .
```

## 3. Configuration C only: check the COOL install

C1. Find the COOL Python bindings for Python 3.11:

```
ls /opt/cool /opt/cool/venvs
/opt/cool/venvs/python_3.11/bin/python -c "import cv2; print(cv2.__version__); print(cv2.__file__)"
```

C2. Set `COOL_SITE` to the directory that contains the `cv2` package printed above
(for example the folder that holds `cv2/`). The value `/opt/cool/python_3.11/site-packages` in
`configs.yaml` is an assumption from the listing; use what the instance shows.

C3. Check that the container loads the COOL build:

```
docker run --rm -v /opt/cool:/opt/cool:ro -v /opt/ffmpeg:/opt/ffmpeg:ro \
  -e PYTHONPATH="$COOL_SITE:/app:/app/engine" -e LD_LIBRARY_PATH=/opt/cool/cpp_sdk/lib \
  gridprint-engine:bench python -c "import cv2; print(cv2.__file__); print(cv2.getBuildInformation())"
```

The printed `cv2.__file__` must be under `/opt/cool`. If it is not, or the import fails (for
example a GLIBC version error, because the image is Debian-based and COOL is built on Ubuntu 24.04),
stop and record the error text in `results/bench/<date>/evidence/C/container_error.txt`. Then use the
native fallback below and record that choice in `docs/DECISIONS.md`.

Native fallback for C (and then also run B natively, so A/B/C compare like with like where possible):

```
uv export --frozen --no-dev --group agent --no-hashes | grep -v '^opencv' > /tmp/req.txt
uv pip install --python /opt/cool/venvs/python_3.11/bin/python -r /tmp/req.txt
PYTHONPATH=.:engine /opt/cool/venvs/python_3.11/bin/python -m bench.run_bench --config C
```

## 4. Run the benchmark

Define the run command for the configuration (`CFG` is A, B or C):

A and B:

```
RUN="docker run --rm --user $(id -u):$(id -g) -v $PWD:/app -w /app gridprint-engine:bench python -m bench.run_bench --config $CFG"
```

C (container path):

```
RUN="docker run --rm --user $(id -u):$(id -g) -v $PWD:/app -w /app -v /opt/cool:/opt/cool:ro -v /opt/ffmpeg:/opt/ffmpeg:ro \
  -e PYTHONPATH=$COOL_SITE:/app:/app/engine -e LD_LIBRARY_PATH=/opt/cool/cpp_sdk/lib \
  gridprint-engine:bench python -m bench.run_bench --config C"
```

`--user` makes the container write results as your user (the image user is uid 10001).

Then:

```
for i in 1 2 3 4 5; do $RUN; done        # at least 5 runs (SPEC Part 12 step 4)
```

`run_bench.py` writes its metrics under `results/bench/<date>/`.

## 5. Collect evidence

Inside the container (build information, `cv2.__file__`, loaded libraries of the container process):

```
docker run --rm --user $(id -u):$(id -g) -v $PWD:/app -w /app <same -v/-e flags as RUN> gridprint-engine:bench \
  python -m bench.cool_evidence --label $CFG
```

Profiler capture on the host, around one benchmark run (needs root; COOL libraries resolve because
`/opt/cool` has the same path on the host and in the container):

```
sudo perf record -a -g -o results/bench/$(date -u +%F)/evidence/$CFG/perf.data -- $RUN
sudo perf report --stdio --sort dso,symbol -i results/bench/$(date -u +%F)/evidence/$CFG/perf.data \
  > results/bench/$(date -u +%F)/evidence/$CFG/perf_report.txt
```

For the native fallback, run `cool_evidence.py` directly with `--cmd` instead; it calls
`perf record` and `perf report` itself.

## 6. Bring results back and stop instances

```
tar czf bench-$CFG.tgz results/bench
scp ...:gridprint/bench-$CFG.tgz .       # then unpack into results/ on your workstation
```

Stop or terminate the instance. Cancel the Marketplace subscription when you no longer need it.

## 7. Report

Report mean and standard deviation per configuration, the parity differences, the evidence files,
and cost per video-hour with the formula in `bench/README.md`. Claim a COOL speedup only for stages
where the `perf` report shows COOL or KleidiCV symbols.
