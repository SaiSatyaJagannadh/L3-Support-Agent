---
id: kb1
source: confluence
app: payflow
acl: staff
url: https://wiki.demo/payflow/504-timeout
title: PayFlow 504 gateway timeout on disbursement submit
---
PayFlow error 504 gateway timeout on disbursement submit: the batch gateway pool is exhausted. Restart the batch-gateway pod and check that queue depth is below 500. If the error returns within ten minutes, raise the pool size in the gateway config and open a ticket for the payments L2 team.
