"""Yerel kontrol aracı — oyuncu adı yaz, tüm bilgilerini (foto, ülke, kariyer
geçmişi) gör. Ana uygulamaya BAĞLI DEĞİL, sadece localde elle çalıştırılır.

    python tools/inspect_player.py      # http://127.0.0.1:8777

Salt-okunur; DB'ye yazmaz. Bağımlılık yok (stdlib).
"""
from __future__ import annotations

import json
import sqlite3
import webbrowser
from datetime import date, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

DB = Path(__file__).resolve().parent.parent / "data" / "football_quiz_v2.db"
PORT = 8777


def _age(dob: str | None) -> int | None:
    if not dob:
        return None
    try:
        d = datetime.strptime(dob[:10], "%Y-%m-%d").date()
    except ValueError:
        return None
    t = date.today()
    return t.year - d.year - ((t.month, t.day) < (d.month, d.day))


def lookup(q: str) -> list[dict]:
    conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT * FROM players WHERE name LIKE ? OR search_name LIKE ? "
            "ORDER BY highest_market_value DESC LIMIT 25",
            (f"%{q}%", f"%{q}%"),
        ).fetchall()
        out = []
        for p in rows:
            clubs = [
                dict(c) for c in conn.execute(
                    "SELECT c.name, c.domestic_competition_id AS league, c.logo_url, "
                    "pc.date_from, pc.date_to "
                    "FROM player_clubs pc JOIN clubs c ON c.club_id = pc.club_id "
                    "WHERE pc.player_id = ? ORDER BY pc.date_from",
                    (p["player_id"],),
                )
            ]
            d = dict(p)
            d["age"] = _age(p["date_of_birth"])
            d["clubs"] = clubs
            out.append(d)
        return out
    finally:
        conn.close()


PAGE = """<!doctype html><meta charset=utf-8><title>Oyuncu Kontrol</title>
<style>
body{font:15px system-ui;margin:0;background:#0f1115;color:#e6e6e6}
header{padding:16px;background:#161a22;position:sticky;top:0}
input{font:16px system-ui;padding:10px 14px;width:min(420px,80vw);border-radius:8px;
 border:1px solid #333;background:#0f1115;color:#fff}
.wrap{padding:16px;display:grid;gap:16px;max-width:900px;margin:auto}
.card{background:#161a22;border:1px solid #262b36;border-radius:12px;padding:16px;
 display:grid;grid-template-columns:120px 1fr;gap:16px}
.card img.face{width:120px;height:120px;object-fit:cover;border-radius:10px;background:#222}
h2{margin:0 0 6px}
.meta{color:#9aa4b2;font-size:14px;line-height:1.7}
.meta b{color:#e6e6e6}
table{border-collapse:collapse;width:100%;margin-top:10px;font-size:14px}
td,th{border-bottom:1px solid #262b36;padding:6px 8px;text-align:left}
th{color:#9aa4b2;font-weight:600}
.logo{width:20px;height:20px;object-fit:contain;vertical-align:middle;margin-right:6px}
.empty{color:#9aa4b2;padding:24px}
</style>
<header><input id=q placeholder="Oyuncu adı yaz..." autofocus autocomplete=off maxlength=80></header>
<div class=wrap id=out></div>
<script>
const out=document.getElementById('out'),q=document.getElementById('q');
let t;
q.oninput=()=>{clearTimeout(t);t=setTimeout(go,250)};
async function go(){
 const v=q.value.trim();
 if(v.length<2){out.innerHTML='';return}
 const r=await fetch('/api?q='+encodeURIComponent(v));
 const d=await r.json();
 if(!d.length){out.innerHTML='<div class=empty>Eşleşme yok.</div>';return}
 out.innerHTML=d.map(p=>`<div class=card>
  <img class=face src="${safeUrl(p.image_url)}" onerror="this.style.visibility='hidden'">
  <div>
   <h2>${esc(p.name)} ${p.is_legend?'⭐':''}</h2>
   <div class=meta>
    <b>ID</b> ${p.player_id} &nbsp; <b>Ülke</b> ${esc(p.country_of_citizenship||'-')} &nbsp;
    <b>Mevki</b> ${esc(p.position||'-')} &nbsp; <b>Yaş</b> ${p.age??'-'}<br>
    <b>Doğum</b> ${esc(p.date_of_birth||'-')} &nbsp; <b>Caps</b> ${p.international_caps??'-'}<br>
    <b>Değer</b> ${fmt(p.market_value)} &nbsp; <b>Zirve</b> ${fmt(p.highest_market_value)}
   </div>
   ${p.clubs.length?`<table><tr><th>Kulüp</th><th>Lig</th><th>Başlangıç</th><th>Bitiş</th></tr>
    ${p.clubs.map(c=>`<tr><td>${safeUrl(c.logo_url)?`<img class=logo src="${safeUrl(c.logo_url)}">`:''}${esc(c.name)}</td>
     <td>${esc(c.league||'-')}</td><td>${esc(c.date_from||'-')}</td><td>${esc(c.date_to||'-')}</td></tr>`).join('')}
    </table>`:'<div class=meta>Kulüp kaydı yok.</div>'}
  </div></div>`).join('');
}
function esc(s){return String(s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]))}
function safeUrl(value){
 try{const u=new URL(String(value||''));return u.protocol==='https:'?esc(u.href):''}catch(_){return ''}
}
function fmt(n){return n?'€'+n.toLocaleString():'-'}
</script>"""


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):  # sessiz
        pass

    def do_GET(self):
        u = urlparse(self.path)
        if u.path == "/api":
            q = (parse_qs(u.query).get("q") or [""])[0].strip()[:80]
            body = json.dumps(lookup(q)).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
        else:
            body = PAGE.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    assert DB.exists(), f"DB yok: {DB}"
    url = f"http://127.0.0.1:{PORT}"
    print(f"Oyuncu kontrol aracı → {url}  (Ctrl+C ile durdur)")
    webbrowser.open(url)
    ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
