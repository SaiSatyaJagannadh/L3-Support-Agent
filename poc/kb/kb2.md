---
id: kb2
source: sharepoint
app: wealthplan
acl: staff
url: https://sharepoint.demo/wealthplan/sso-login-loop
title: WealthPlan login loop after SSO
---
WealthPlan login loop after SSO: clear the session cookie and verify the Entra app redirect URI matches the environment URL. A redirect URI mismatch is the most common cause in UAT. If the loop continues, collect the browser network trace and escalate.
