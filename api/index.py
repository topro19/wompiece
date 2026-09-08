from http.server import BaseHTTPRequestHandler
import json
import os

HTML_CONTENT = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>PIRATE WARS - World Simulation Engine</title>
    <style>
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: #0a0e17; color: #e2e8f0; margin: 0; padding: 2rem; }
        .container { max-width: 800px; margin: 0 auto; background: #131b2e; border: 1px solid #1e293b; border-radius: 12px; padding: 2rem; box-shadow: 0 10px 25px rgba(0,0,0,0.5); }
        h1 { color: #f59e0b; margin-top: 0; display: flex; align-items: center; gap: 0.5rem; }
        .badge { background: #10b981; color: #022c22; font-size: 0.8rem; font-weight: bold; padding: 0.25rem 0.6rem; border-radius: 9999px; }
        .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 1rem; margin: 1.5rem 0; }
        .card { background: #1e293b; border-radius: 8px; padding: 1rem; border: 1px solid #334155; }
        .card h3 { margin: 0 0 0.5rem 0; font-size: 0.9rem; color: #94a3b8; }
        .card p { margin: 0; font-size: 1.2rem; font-weight: bold; color: #f1f5f9; }
        .cmd-list { background: #0f172a; border-radius: 8px; padding: 1rem; border: 1px solid #1e293b; font-family: monospace; font-size: 0.9rem; line-height: 1.6; }
        .footer { margin-top: 1.5rem; text-align: center; font-size: 0.8rem; color: #64748b; }
    </style>
</head>
<body>
    <div class="container">
        <h1>☠️ PIRATE WARS <span class="badge">ONLINE</span></h1>
        <p>Persistent AI-Driven Multiplayer Simulation Engine deployed on Vercel Serverless.</p>
        
        <div class="grid">
            <div class="card">
                <h3>SIMULATION ENGINE</h3>
                <p>Gemini 3.5 Flash Lite</p>
            </div>
            <div class="card">
                <h3>REGISTERED COMMANDS</h3>
                <p>22 Slash Commands</p>
            </div>
            <div class="card">
                <h3>ACTIVE PLATFORM</h3>
                <p>Vercel Cloud</p>
            </div>
            <div class="card">
                <h3>DATABASE</h3>
                <p>Double-Entry Ledger</p>
            </div>
        </div>

        <h3>Active Command Roster</h3>
        <div class="cmd-list">
            /act &bull; /start &bull; /profile &bull; /status &bull; /inventory &bull; /location<br>
            /trade market &bull; /trade buy &bull; /trade sell &bull; /contract board &bull; /protect hire<br>
            /intel gather &bull; /salvage explore &bull; /combat &bull; /ship buy &bull; /bribe offer<br>
            /crew create &bull; /business buy &bull; /gamble &bull; /ginto (Guidebook)
        </div>

        <div class="footer">
            Authoritative Deterministic Engine &bull; Google Gemini AI &bull; Vercel Cloud
        </div>
    </div>
</body>
</html>"""

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in ["/api", "/api/status", "/status", "/healthz"]:
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            data = {
                "status": "online",
                "service": "Pirate Wars Simulation Engine",
                "platform": "Vercel Serverless",
                "ai_model": "gemini-3.6-flash",
                "commands_registered": 22
            }
            self.wfile.write(json.dumps(data).encode('utf-8'))
        else:
            self.send_response(200)
            self.send_header('Content-type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(HTML_CONTENT.encode('utf-8'))
