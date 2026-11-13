"""Entra ID token validation. Set AAD_TENANT_ID + AAD_CLIENT_ID to enforce; otherwise dev stub reads X-User-Groups / X-User-Roles."""
import os, jwt
from fastapi import Header, HTTPException

AUTH = os.getenv('AAD_AUTHORITY', 'https://login.microsoftonline.com')   # override only for the dummy run
_jwks = None
def user(authorization: str = Header(""), x_user_groups: str = Header("staff"), x_user_roles: str = Header("")):
    global _jwks
    tenant = os.getenv("AAD_TENANT_ID")
    if not tenant: return {"groups": x_user_groups.split(","), "roles": x_user_roles.split(",")}
    if not authorization.startswith("Bearer "): raise HTTPException(401, "missing bearer token")
    _jwks = _jwks or jwt.PyJWKClient(f"{AUTH}/{tenant}/discovery/v2.0/keys")
    tok = authorization[7:]
    try:
        c = jwt.decode(tok, _jwks.get_signing_key_from_jwt(tok).key, algorithms=["RS256"], audience=os.environ["AAD_CLIENT_ID"],
                       issuer=f"{AUTH}/{tenant}/v2.0")
    except jwt.PyJWTError as e: raise HTTPException(401, str(e))
    return {"groups": c.get("groups", []), "roles": c.get("roles", [])}   # Entra group ids -> must match KB acl values (map in prod)
