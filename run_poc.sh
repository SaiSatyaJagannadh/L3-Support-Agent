#!/usr/bin/env bash
# One-command POC run with DUMMY stand-ins for everything that needs accounts:
#   GitLab pipeline -> this script (same stages: test, build, "deploy" = render + validate manifests)
#   Azure SQL       -> SQLite
#   AKS deploy      -> helm lint/template + az bicep build (no cluster)
#   Azure OpenAI / Search / Prompt Shields / ServiceNow / Confluence / Entra -> local mocks in poc/dummy_run.py
set -e
cd "$(dirname "$0")/poc"
echo "== test stage =="; python3 -m pytest -q --ignore=test_e2e.py; python3 evals.py; python3 redteam.py
echo "== dummy integrations =="; python3 dummy_run.py
echo "== build stage =="; docker build -q -t l3-poc . >/dev/null && echo "image built"
echo "== deploy stage (dummy: render + validate, no cluster) =="; cd ..
helm lint infra/helm >/dev/null && helm template infra/helm --set env=dev >/dev/null && echo "helm ok"
az bicep build --file infra/main.bicep --stdout >/dev/null && echo "bicep ok"
echo "== ALL POC STAGES PASSED =="
