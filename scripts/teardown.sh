#!/usr/bin/env bash
# Remove everything (deletes the kind cluster "obs").
set -euo pipefail
kind delete cluster --name obs
