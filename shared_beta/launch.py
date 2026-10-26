"""Start the local API when needed and open the isolated beta desktop client."""
import json
import subprocess
import sys
import time
from urllib.request import Request, urlopen
from pathlib import Path

from .server import DEFAULT_DATA, initialize


def main():
    if not (DEFAULT_DATA/'accounts.json').exists():
        initialize(DEFAULT_DATA)
    profile=json.loads((DEFAULT_DATA/'test_williams.json').read_text())
    def ready():
        try:
            req=Request(profile['url']+'/v1/state',headers={'Authorization':'Bearer '+profile['token']})
            with urlopen(req,timeout=0.5) as response:
                return 'revision' in json.load(response)
        except (OSError,ValueError):return False
    if not ready():
        log=open(DEFAULT_DATA/'server.log','a',encoding='utf-8')
        subprocess.Popen([sys.executable,'-m','shared_beta.server'],cwd=Path(__file__).resolve().parent.parent,
                         stdout=log,stderr=log,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        log.close()
        for _ in range(20):
            if ready():break
            time.sleep(0.15)
    from .client import Client
    Client(DEFAULT_DATA/'test_williams.json').mainloop()


if __name__=='__main__':main()
