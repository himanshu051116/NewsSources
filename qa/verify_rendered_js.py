"""QA only: check actual rendered JavaScript syntax for the main user journeys."""
from pathlib import Path
from tempfile import TemporaryDirectory
from html.parser import HTMLParser
import subprocess
import sys
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'qa'))
from replay_server import app, EVENT_B, ART_B, CURRENT_USER, qa_user  # noqa: E402
from newsintel.api.dependencies import get_current_user  # noqa: E402
from newsintel.domain.access import AccessRole, permissions_for_role  # noqa: E402


class InlineScripts(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.scripts = []
        self.current = None

    def handle_starttag(self, tag, attrs):
        if tag == 'script' and 'src' not in dict(attrs):
            self.current = []

    def handle_data(self, data):
        if self.current is not None:
            self.current.append(data)

    def handle_endtag(self, tag):
        if tag == 'script' and self.current is not None:
            content = ''.join(self.current)
            if content.strip():
                self.scripts.append(content)
            self.current = None

async def qa_source_manager():
    return CURRENT_USER.model_copy(update={
        'role': AccessRole.SOURCE_MANAGER,
        'permissions': frozenset(p.value for p in permissions_for_role(AccessRole.SOURCE_MANAGER)),
    })


routes = ['/app','/briefs','/news','/news-sources','/events','/search',f'/events/{EVENT_B}/briefing']
results=[]
with TestClient(app) as client, TemporaryDirectory(prefix='newsintel-js-') as temp:
    for route in routes:
        app.dependency_overrides[get_current_user] = qa_source_manager if route == '/news-sources' else qa_user
        r = client.get(route)
        assert r.status_code == 200,(route,r.status_code,r.text[:160])
        parser = InlineScripts()
        parser.feed(r.text)
        scripts = parser.scripts
        for i, content in enumerate(scripts):
            file=Path(temp) / f'generated_{len(results)}.js'
            file.write_text(content,encoding='utf-8')
            check=subprocess.run(['node','--check',str(file)],capture_output=True,text=True)
            assert check.returncode==0,(route,i,check.stderr)
            results.append((route,i))
print('Rendered pages:',len(routes),'Script blocks:',len(results),'Syntax errors: 0')
