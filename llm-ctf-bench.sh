#!/bin/bash

set -euo pipefail

PYTHONPATH=src:. .venv/bin/python ctf/phase2_run.py "$@"
