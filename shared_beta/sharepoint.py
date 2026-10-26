"""Upload a user-selected report to a configured SharePoint document folder."""
import json
import uuid
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, build_opener, HTTPRedirectHandler


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None


def upload_report(profile,path,token):
    path=Path(path)
    if path.suffix.lower() not in ('.csv','.xlsx','.pdf') or path.stat().st_size>20*1024*1024:
        raise ValueError('Choose a CSV, Excel, or PDF report smaller than 20 MB.')
    destination=profile.get('sharepoint',{})
    drive=destination.get('drive_id','');folder=destination.get('folder_id','')
    if not drive or not folder:
        raise ValueError('Configure the approved SharePoint drive_id and folder_id first.')
    # Unique filenames avoid accidentally replacing an existing report.
    name=f'{path.stem}-{uuid.uuid4().hex[:12]}{path.suffix}'
    url=f'https://graph.microsoft.com/v1.0/drives/{quote(drive,safe="")}/items/{quote(folder,safe="")}:/'+quote(name,safe='')+':/content'
    request=Request(url,data=path.read_bytes(),method='PUT',headers={
        'Authorization':'Bearer '+token,'Content-Type':'application/octet-stream'})
    with build_opener(NoRedirect).open(request,timeout=30) as response:
        result=json.load(response)
    if result.get('size')!=path.stat().st_size:
        raise ValueError('SharePoint did not confirm the expected file size. Check the destination before retrying.')
    return result
