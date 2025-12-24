#!/bin/bash
# Usage: ./scripts/mlp/docker_run.sh <command>
# Example: ./scripts/mlp/docker_run.sh scripts/mlp/train.py --data scripts/mlp/dataset.csv

docker run --rm -it \
    --gpus all \
    -e PYTHONPATH=/app \
    -v $(pwd):/app \
    -v /home/dby/chromium/v8/v8:/home/dby/chromium/v8/v8 \
    mlp-trainer "$@"
