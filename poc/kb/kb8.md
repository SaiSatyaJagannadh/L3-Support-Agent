---
id: kb8
source: google-docs
app: payflow
acl: staff
url: https://docs.google.com/document/d/demo-payflow-stuck
title: PayFlow disbursement stuck in pending
---
PayFlow disbursement stuck in pending: check the batch certificate expiry first. An expired batch certificate blocks submission silently. Renew the certificate from the secrets vault and re-run the job. Confirm the disbursement moves to completed within five minutes.
