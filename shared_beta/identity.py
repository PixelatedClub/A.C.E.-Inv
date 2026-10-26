"""Single-tenant Entra authentication. Desktop secrets are never required."""
from uuid import UUID
from urllib.parse import urlsplit

from .store import Problem


def guid(value):
    return str(UUID(value))


def validate_profile(profile):
    url = urlsplit(profile['url'])
    if url.username or url.password or url.query or url.fragment or url.path not in ('','/'):
        raise ValueError('API URL must be an origin without credentials, path, query, or fragment.')
    if profile.get('auth','local') == 'local':
        if profile['url'] != 'http://127.0.0.1:8765':
            raise ValueError('Test credentials are restricted to the local beta server.')
    else:
        if profile['auth'] != 'entra' or url.scheme != 'https' or not url.hostname:
            raise ValueError('Entra profiles require an HTTPS API URL.')
        guid(profile['tenant_id']);guid(profile['client_id']);guid(profile['api_client_id'])
        if profile.get('token'):
            raise ValueError('Do not store access tokens in Entra profiles.')


class DesktopIdentity:
    def __init__(self,profile):
        validate_profile(profile)
        self.profile=profile
        self.app=None
        if profile.get('auth')=='entra':
            import msal
            self.app=msal.PublicClientApplication(guid(profile['client_id']),
                authority=f"https://login.microsoftonline.com/{guid(profile['tenant_id'])}")

    def token(self,interactive=False,graph=False):
        if self.app is None:
            if graph:raise ValueError('SharePoint requires Auburn sign-in.')
            return self.profile['token']
        scopes=['https://graph.microsoft.com/Sites.Selected'] if graph else [f"api://{guid(self.profile['api_client_id'])}/access_as_user"]
        accounts=self.app.get_accounts()
        result=self.app.acquire_token_silent(scopes,account=accounts[0]) if accounts else None
        if not result and interactive:
            result=self.app.acquire_token_interactive(scopes=scopes,prompt='select_account')
        if not result or 'access_token' not in result:
            raise ValueError('Sign in with Auburn to connect. Campus IT must assign the application and consent to its scopes.')
        return result['access_token']


class EntraValidator:
    def __init__(self,tenant_id,audience,desktop_client_id):
        import jwt
        self.tenant=guid(tenant_id);self.audience=guid(audience)
        self.client=guid(desktop_client_id)
        self.issuer=f'https://login.microsoftonline.com/{self.tenant}/v2.0'
        self.keys=jwt.PyJWKClient(f'https://login.microsoftonline.com/{self.tenant}/discovery/v2.0/keys',timeout=5)

    def authenticate(self,token):
        import jwt
        try:
            key=self.keys.get_signing_key_from_jwt(token).key
            claims=jwt.decode(token,key,algorithms=['RS256'],audience=self.audience,issuer=self.issuer,
                options={'require':['exp','iat','nbf','aud','iss','tid','oid','azp']},leeway=30)
            if claims['tid']!=self.tenant or claims['azp']!=self.client or claims.get('ver')!='2.0':
                raise ValueError('Unexpected tenant, client, or token version')
            guid(claims['oid'])
            if 'access_as_user' not in claims.get('scp','').split():
                raise Problem(403,'Required delegated API scope is missing.')
            roles=claims.get('roles',[])
            if 'ACE.Operator' in roles:role='operator'
            elif 'ACE.Viewer' in roles:role='viewer'
            else:raise Problem(403,'No A.C.E. application role assigned.')
            return {'name':f"{self.tenant}/{claims['oid']}",'role':role}
        except Problem:raise
        except Exception:
            raise Problem(401,'Invalid or expired Auburn API access token.')
