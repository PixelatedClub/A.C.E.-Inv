"""Optional GitHub program updates; private access uses existing sign-in only."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import urllib.error
import urllib.parse
import urllib.request

from .installation import RELEASE, CHANNEL, MAX_PROGRAM, release, version_key
from .usb_portable import atomic_json

REPO='https://api.github.com/repos/PixelatedClub/A.C.E.-Inv'


class UpdateUnavailable(Exception):pass


def existing_token():
    """Never opens a sign-in prompt or writes a token to the USB/settings."""
    env=dict(os.environ,GIT_TERMINAL_PROMPT='0',GCM_INTERACTIVE='never',GCM_GUI_PROMPT='false',GH_PROMPT_DISABLED='1')
    try:
        gh=shutil.which('gh')
        if gh:
            answer=subprocess.run([gh,'auth','token','--hostname','github.com'],capture_output=True,text=True,env=env,timeout=5,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            if answer.returncode==0 and answer.stdout.strip():return answer.stdout.strip()
        git=shutil.which('git')
        if git:
            answer=subprocess.run([git,'credential','fill'],input='protocol=https\nhost=github.com\n\n',capture_output=True,text=True,env=env,timeout=5,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            if answer.returncode==0:
                values=dict(line.split('=',1) for line in answer.stdout.splitlines() if '=' in line)
                return values.get('password')
    except (OSError,subprocess.TimeoutExpired):pass
    return None


class SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        parsed=urllib.parse.urlparse(newurl)
        host=parsed.hostname or ''
        if parsed.scheme!='https' or not (host in ('api.github.com','github.com') or host.endswith('.githubusercontent.com')):
            raise UpdateUnavailable('GitHub returned an unexpected download location.')
        request=super().redirect_request(req,fp,code,msg,headers,newurl)
        if request and host!='api.github.com':request.remove_header('Authorization')
        return request


class GitHubUpdates:
    def __init__(self,token=None):
        self.token=token;self.opener=urllib.request.build_opener(SafeRedirect())
    def get(self,url,limit,*,binary=False):
        if not url.startswith(REPO+'/'):raise UpdateUnavailable('Unexpected update API URL.')
        headers={'User-Agent':'Team-Shapes-ACE-Updater','Accept':'application/octet-stream' if binary else 'application/vnd.github+json','X-GitHub-Api-Version':'2022-11-28'}
        if self.token:headers['Authorization']='Bearer '+self.token
        try:
            with self.opener.open(urllib.request.Request(url,headers=headers),timeout=8) as response:
                raw=response.read(limit+1)
        except (OSError,urllib.error.URLError) as error:
            raise UpdateUnavailable('GitHub updates are unavailable or this computer is not signed in to the private repository.') from None
        if len(raw)>limit:raise UpdateUnavailable('The update download exceeds its size limit.')
        return raw
    def fetch_newer(self,current,cache):
        try:releases=json.loads(self.get(REPO+'/releases?per_page=100',1024*1024))
        except (ValueError,TypeError):raise UpdateUnavailable('GitHub returned invalid release metadata.') from None
        if not isinstance(releases,list):raise UpdateUnavailable('GitHub release access is unavailable.')
        candidates=[]
        for entry in releases:
            if entry.get('draft'):continue
            tag=str(entry.get('tag_name',''))
            if not tag.startswith('v') or '-cic.' not in tag:continue
            try:key=version_key(tag[1:])
            except ValueError:continue
            if key>version_key(current):candidates.append((key,entry))
        if not candidates:return None
        entry=max(candidates,key=lambda pair:pair[0])[1]
        assets={a.get('name'):a for a in entry.get('assets',[]) if isinstance(a,dict)}
        if RELEASE not in assets or 'A.C.E.exe' not in assets:raise UpdateUnavailable('The newer release is missing its verified program assets.')
        def asset(name,limit):
            value=assets[name]
            if type(value.get('id')) is not int or type(value.get('size')) is not int or not 0<value['size']<=limit:
                raise UpdateUnavailable('The release asset metadata is invalid.')
            raw=self.get(REPO+'/releases/assets/'+str(value['id']),limit,binary=True)
            if len(raw)!=value['size']:raise UpdateUnavailable('The update download is incomplete.')
            expected=value.get('digest')
            if expected and expected!='sha256:'+hashlib.sha256(raw).hexdigest():raise UpdateUnavailable('The GitHub asset checksum did not match.')
            return raw
        try:manifest=json.loads(asset(RELEASE,64*1024))
        except ValueError:raise UpdateUnavailable('The release manifest is invalid.') from None
        if not isinstance(manifest,dict) or manifest.get('version')!=str(entry['tag_name'])[1:] or manifest.get('channel')!=CHANNEL:
            raise UpdateUnavailable('The release does not match this update channel.')
        version_key(manifest['version'])
        folder=Path(cache)/manifest['version'];folder.mkdir(parents=True,exist_ok=True)
        binary=asset('A.C.E.exe',MAX_PROGRAM)
        if hashlib.sha256(binary).hexdigest()!=manifest.get('sha256') or len(binary)!=manifest.get('size') or binary[:2]!=b'MZ':
            raise UpdateUnavailable('The downloaded program failed checksum verification.')
        staged=folder/'A.C.E.download';staged.write_bytes(binary);staged.replace(folder/'A.C.E.exe')
        atomic_json(folder/RELEASE,manifest);release(folder)
        return folder


def discard_download(folder):
    folder=Path(folder)
    for name in ('A.C.E.exe',RELEASE,'A.C.E.download'):
        path=folder/name
        if path.is_file() and not path.is_symlink():path.unlink()
    try:folder.rmdir()
    except OSError:pass
