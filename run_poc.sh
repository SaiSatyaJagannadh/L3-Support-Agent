#!/usr/bin/env bash
# One-command POC check. Everything that needs accounts is replaced by local stand-ins:
#   GitLab pipeline -> this script   Azure SQL -> SQLite   AKS deploy -> helm lint/template + az bicep build   Azure/ServiceNow/... -> mocks in poc/dummy_run.py
set -e
cd "$(dirname "$0")/poc"
echo "== tests (agent, API, DB, Streamlit UI) =="; python3 -m pytest -q
echo "== eval gate =="; python3 evals.py
echo "== red team =="; python3 redteam.py
echo "== dummy integrations =="; python3 dummy_run.py
cd ..
echo "== build =="; docker build -q -t l3-assist . >/dev/null; echo "image built"
echo "== manifests =="; helm lint infra/helm >/dev/null; helm template infra/helm --set env=dev >/dev/null; echo "helm ok"
az bicep build --file infra/main.bicep --stdout >/dev/null; echo "bicep ok"
echo "== ALL POC STAGES PASSED =="
echo "Run the app: streamlit run streamlit_app.py"
