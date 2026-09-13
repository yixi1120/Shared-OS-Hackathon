"""Same-origin live Dashboard adapter; Seller implementation is unchanged."""
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'src'))
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from sharedos_commerce_agent.api import app

@app.get('/', include_in_schema=False)
def home():
    return FileResponse(ROOT / 'dashboard/index.html', headers={
        'Link': '</.well-known/agent.json>; rel="describedby"; type="application/json", </openapi.json>; rel="service-desc"; type="application/json"'
    })

app.mount('/dashboard', StaticFiles(directory=ROOT / 'dashboard', html=True), name='dashboard')
app.mount('/product', StaticFiles(directory=ROOT / 'docs' / 'guansheng'), name='product')

if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='127.0.0.1', port=8786)
