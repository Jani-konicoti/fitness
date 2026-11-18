from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import sqlite3, os, hashlib, hmac, secrets, datetime, base64, binascii
from fastapi.responses import Response
from contextlib import contextmanager

DB = os.getenv('DATABASE_PATH', os.path.join(os.path.dirname(__file__), 'fitness.db'))
app = FastAPI(title='CP Fitness API')
app.add_middleware(CORSMiddleware, allow_origins=os.getenv('CORS_ORIGINS', 'http://localhost:5173,http://127.0.0.1:5173').split(','), allow_methods=['*'], allow_headers=['*'])

def now(): return datetime.datetime.now(datetime.timezone.utc).isoformat()
def today(): return datetime.date.today().isoformat()
@contextmanager
def db():
    con=sqlite3.connect(DB); con.row_factory=sqlite3.Row; con.execute('PRAGMA foreign_keys=ON')
    try:
        yield con
        con.commit()
    finally: con.close()
def password_hash(p, salt=None):
    salt=salt or secrets.token_hex(16)
    return salt+'$'+hashlib.pbkdf2_hmac('sha256',p.encode(),salt.encode(),260000).hex()
def verify(p, hashed): return hmac.compare_digest(password_hash(p,hashed.split('$')[0]),hashed)
def rows(cur): return [dict(x) for x in cur.fetchall()]

def init():
  with db() as c:
    c.executescript('''
    CREATE TABLE IF NOT EXISTS tenants (id INTEGER PRIMARY KEY, name TEXT NOT NULL, slug TEXT NOT NULL UNIQUE, email TEXT DEFAULT '', active INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, tenant_id INTEGER REFERENCES tenants(id), name TEXT NOT NULL, email TEXT NOT NULL UNIQUE COLLATE NOCASE, password TEXT NOT NULL, role TEXT NOT NULL CHECK(role IN ('superadmin','admin','operator')), active INTEGER NOT NULL DEFAULT 1);
    CREATE TABLE IF NOT EXISTS sessions (token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, expires_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS clients (id INTEGER PRIMARY KEY, tenant_id INTEGER NOT NULL REFERENCES tenants(id), code TEXT NOT NULL, first_name TEXT NOT NULL, last_name TEXT NOT NULL, email TEXT DEFAULT '', phone TEXT DEFAULT '', birth_date TEXT DEFAULT '', gender TEXT DEFAULT '', address TEXT DEFAULT '', city TEXT DEFAULT '', fiscal_code TEXT DEFAULT '', consultant TEXT DEFAULT '', source TEXT DEFAULT '', certificate_expiry TEXT DEFAULT '', insurance_expiry TEXT DEFAULT '', notes TEXT DEFAULT '', blocked INTEGER DEFAULT 0, block_reason TEXT DEFAULT '', created_at TEXT NOT NULL, UNIQUE(tenant_id,code));
    CREATE TABLE IF NOT EXISTS plans (id INTEGER PRIMARY KEY, tenant_id INTEGER NOT NULL REFERENCES tenants(id), name TEXT NOT NULL, category TEXT DEFAULT '', duration_days INTEGER NOT NULL DEFAULT 30, price REAL NOT NULL DEFAULT 0, lessons INTEGER, active INTEGER DEFAULT 1);
    CREATE TABLE IF NOT EXISTS memberships (id INTEGER PRIMARY KEY, tenant_id INTEGER NOT NULL REFERENCES tenants(id), client_id INTEGER NOT NULL REFERENCES clients(id), plan_id INTEGER NOT NULL REFERENCES plans(id), start_date TEXT NOT NULL, end_date TEXT NOT NULL, price REAL NOT NULL DEFAULT 0, discount REAL NOT NULL DEFAULT 0, paid REAL NOT NULL DEFAULT 0, lessons_remaining INTEGER, status TEXT NOT NULL DEFAULT 'active', notes TEXT DEFAULT '');
    CREATE TABLE IF NOT EXISTS visits (id INTEGER PRIMARY KEY, tenant_id INTEGER NOT NULL REFERENCES tenants(id), client_id INTEGER NOT NULL REFERENCES clients(id), membership_id INTEGER REFERENCES memberships(id), check_in TEXT NOT NULL, check_out TEXT, status TEXT NOT NULL, department TEXT DEFAULT '');
    CREATE TABLE IF NOT EXISTS payments (id INTEGER PRIMARY KEY, tenant_id INTEGER NOT NULL REFERENCES tenants(id), membership_id INTEGER NOT NULL REFERENCES memberships(id), amount REAL NOT NULL, method TEXT NOT NULL DEFAULT '', note TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL, user_id INTEGER REFERENCES users(id));
    CREATE TABLE IF NOT EXISTS membership_events (id INTEGER PRIMARY KEY, tenant_id INTEGER NOT NULL REFERENCES tenants(id), membership_id INTEGER NOT NULL REFERENCES memberships(id), action TEXT NOT NULL, created_at TEXT NOT NULL, user_id INTEGER REFERENCES users(id));
    CREATE TABLE IF NOT EXISTS client_documents (id INTEGER PRIMARY KEY, tenant_id INTEGER NOT NULL REFERENCES tenants(id), client_id INTEGER NOT NULL REFERENCES clients(id), name TEXT NOT NULL, category TEXT NOT NULL, mime TEXT NOT NULL, content BLOB NOT NULL, created_at TEXT NOT NULL, user_id INTEGER REFERENCES users(id));
    CREATE INDEX IF NOT EXISTS idx_clients_tenant ON clients(tenant_id); CREATE INDEX IF NOT EXISTS idx_memberships_tenant ON memberships(tenant_id); CREATE INDEX IF NOT EXISTS idx_visits_tenant ON visits(tenant_id);
    ''')
    email=os.getenv('SUPERADMIN_EMAIL'); pwd=os.getenv('SUPERADMIN_PASSWORD')
    if email and pwd and not c.execute("SELECT 1 FROM users WHERE role='superadmin'").fetchone():
      c.execute("INSERT INTO users(name,email,password,role) VALUES(?,?,?,'superadmin')",('Super Admin',email,password_hash(pwd)))
init()

class Login(BaseModel): email:str; password:str
class TenantIn(BaseModel): name:str; slug:str; email:str=''; admin_name:str; admin_email:str; admin_password:str
class UserIn(BaseModel): name:str; email:str; password:str; role:str='operator'
class ClientIn(BaseModel):
    code:str; first_name:str; last_name:str; email:str=''; phone:str=''; birth_date:str=''; gender:str=''; address:str=''; city:str=''; fiscal_code:str=''; consultant:str=''; source:str=''; certificate_expiry:str=''; insurance_expiry:str=''; notes:str=''; blocked:bool=False; block_reason:str=''
class PlanIn(BaseModel): name:str; category:str=''; duration_days:int=30; price:float=0; lessons:int|None=None
class MembershipIn(BaseModel): client_id:int; plan_id:int; start_date:str; end_date:str; price:float=0; discount:float=0; paid:float=0; lessons_remaining:int|None=None; status:str='active'; notes:str=''
class VisitIn(BaseModel): client_id:int; department:str=''
class PaymentIn(BaseModel): amount:float; method:str=''; note:str=''

def current(authorization:str=Header(default='')):
    if not authorization.startswith('Bearer '): raise HTTPException(401,'Accesso richiesto')
    token=hashlib.sha256(authorization[7:].encode()).hexdigest()
    with db() as c:
      u=c.execute('SELECT u.id,u.name,u.email,u.role,u.tenant_id,t.name tenant_name,t.active tenant_active FROM sessions s JOIN users u ON u.id=s.user_id LEFT JOIN tenants t ON t.id=u.tenant_id WHERE s.token_hash=? AND s.expires_at>? AND u.active=1',(token,now())).fetchone()
    if not u or (u['tenant_id'] and not u['tenant_active']): raise HTTPException(401,'Sessione non valida o scaduta')
    return dict(u)
def tenant(u=Depends(current)):
    if not u['tenant_id']: raise HTTPException(403,'Seleziona un account operatore')
    return u
def admin(u=Depends(tenant)):
    if u['role']!='admin': raise HTTPException(403,'Permessi insufficienti')
    return u
def superuser(u=Depends(current)):
    if u['role']!='superadmin': raise HTTPException(403,'Permessi insufficienti')
    return u
@app.post('/api/login')
def login(data:Login):
    with db() as c:
      u=c.execute('SELECT * FROM users WHERE email=? AND active=1',(data.email.strip(),)).fetchone()
      if not u or not verify(data.password,u['password']): raise HTTPException(401,'Email o password non corretti')
      if u['tenant_id'] and not c.execute('SELECT active FROM tenants WHERE id=?',(u['tenant_id'],)).fetchone()['active']: raise HTTPException(403,'Palestra disattivata')
      token=secrets.token_urlsafe(32); expiry=(datetime.datetime.now(datetime.timezone.utc)+datetime.timedelta(hours=12)).isoformat()
      c.execute('INSERT INTO sessions VALUES(?,?,?)',(hashlib.sha256(token.encode()).hexdigest(),u['id'],expiry))
    return {'token':token}
@app.post('/api/logout')
def logout(authorization:str=Header(default=''), u=Depends(current)):
    with db() as c: c.execute('DELETE FROM sessions WHERE token_hash=?',(hashlib.sha256(authorization[7:].encode()).hexdigest(),))
    return {'ok':True}
@app.get('/api/me')
def me(u=Depends(current)): return u
@app.get('/api/tenants')
def tenants(u=Depends(superuser)):
    with db() as c: return rows(c.execute('SELECT t.*, (SELECT count(*) FROM users WHERE tenant_id=t.id) operators, (SELECT count(*) FROM clients WHERE tenant_id=t.id) clients FROM tenants t ORDER BY t.name'))
@app.post('/api/tenants')
def create_tenant(d:TenantIn,u=Depends(superuser)):
    if len(d.admin_password)<8: raise HTTPException(400,'La password deve contenere almeno 8 caratteri')
    try:
      with db() as c:
        cur=c.execute('INSERT INTO tenants(name,slug,email,created_at) VALUES(?,?,?,?)',(d.name,d.slug.lower(),d.email,now())); tid=cur.lastrowid
        c.execute("INSERT INTO users(tenant_id,name,email,password,role) VALUES(?,?,?,?, 'admin')",(tid,d.admin_name,d.admin_email,password_hash(d.admin_password)))
      return {'id':tid}
    except sqlite3.IntegrityError: raise HTTPException(400,'Slug o email già in uso')
@app.patch('/api/tenants/{tid}/toggle')
def toggle_tenant(tid:int,u=Depends(superuser)):
    with db() as c: c.execute('UPDATE tenants SET active=1-active WHERE id=?',(tid,))
    return {'ok':True}
@app.get('/api/users')
def users(u=Depends(admin)):
    with db() as c: return rows(c.execute('SELECT id,name,email,role,active FROM users WHERE tenant_id=?',(u['tenant_id'],)))
@app.post('/api/users')
def create_user(d:UserIn,u=Depends(admin)):
    if d.role not in ('admin','operator') or len(d.password)<8: raise HTTPException(400,'Ruolo o password non validi')
    try:
      with db() as c: c.execute('INSERT INTO users(tenant_id,name,email,password,role) VALUES(?,?,?,?,?)',(u['tenant_id'],d.name,d.email,password_hash(d.password),d.role))
    except sqlite3.IntegrityError: raise HTTPException(400,'Email già in uso')
    return {'ok':True}
@app.get('/api/clients')
def clients(q:str='',u=Depends(tenant)):
    with db() as c: return rows(c.execute('''SELECT c.*, (SELECT p.name FROM memberships m JOIN plans p ON p.id=m.plan_id WHERE m.client_id=c.id AND m.tenant_id=c.tenant_id ORDER BY m.end_date DESC LIMIT 1) plan_name, (SELECT m.end_date FROM memberships m WHERE m.client_id=c.id AND m.tenant_id=c.tenant_id ORDER BY m.end_date DESC LIMIT 1) membership_end FROM clients c WHERE c.tenant_id=? AND (c.first_name LIKE ? OR c.last_name LIKE ? OR c.code LIKE ? OR c.email LIKE ?) ORDER BY c.last_name,c.first_name''',(u['tenant_id'],*[f'%{q}%']*4)))
@app.post('/api/clients')
def create_client(d:ClientIn,u=Depends(tenant)):
    vals=d.model_dump(); keys=list(vals)
    try:
      with db() as c:
        cur=c.execute(f"INSERT INTO clients(tenant_id,created_at,{','.join(keys)}) VALUES ({','.join(['?']*(len(keys)+2))})",[u['tenant_id'],now(),*vals.values()]); return {'id':cur.lastrowid}
    except sqlite3.IntegrityError: raise HTTPException(400,'Codice cliente già in uso')
@app.put('/api/clients/{cid}')
def update_client(cid:int,d:ClientIn,u=Depends(tenant)):
    vals=d.model_dump()
    try:
      with db() as c:
        cur=c.execute('UPDATE clients SET '+','.join(k+'=?' for k in vals)+' WHERE id=? AND tenant_id=?',(*vals.values(),cid,u['tenant_id']))
        if not cur.rowcount: raise HTTPException(404,'Cliente non trovato')
    except sqlite3.IntegrityError: raise HTTPException(400,'Codice cliente già in uso')
    return {'ok':True}
@app.get('/api/plans')
def plans(u=Depends(tenant)):
    with db() as c: return rows(c.execute('SELECT * FROM plans WHERE tenant_id=? ORDER BY name',(u['tenant_id'],)))
@app.post('/api/plans')
def create_plan(d:PlanIn,u=Depends(tenant)):
    if d.duration_days<1 or d.price<0: raise HTTPException(400,'Durata o prezzo non validi')
    with db() as c: c.execute('INSERT INTO plans(tenant_id,name,category,duration_days,price,lessons) VALUES(?,?,?,?,?,?)',(u['tenant_id'],d.name,d.category,d.duration_days,d.price,d.lessons))
    return {'ok':True}
@app.get('/api/memberships')
def memberships(u=Depends(tenant)):
    with db() as c: return rows(c.execute('''SELECT m.*, c.first_name,c.last_name,c.code,p.name plan_name,p.category FROM memberships m JOIN clients c ON c.id=m.client_id AND c.tenant_id=m.tenant_id JOIN plans p ON p.id=m.plan_id AND p.tenant_id=m.tenant_id WHERE m.tenant_id=? ORDER BY m.end_date DESC''',(u['tenant_id'],)))
@app.post('/api/memberships')
def create_membership(d:MembershipIn,u=Depends(tenant)):
    if d.end_date<d.start_date or min(d.price,d.paid,d.discount)<0 or d.discount>100 or d.status not in ('active','suspended'): raise HTTPException(400,'Dati abbonamento non validi')
    with db() as c:
      if not c.execute('SELECT 1 FROM clients WHERE id=? AND tenant_id=?',(d.client_id,u['tenant_id'])).fetchone() or not c.execute('SELECT 1 FROM plans WHERE id=? AND tenant_id=?',(d.plan_id,u['tenant_id'])).fetchone(): raise HTTPException(404,'Cliente o tipologia non trovati')
      v=d.model_dump(); cur=c.execute('INSERT INTO memberships(tenant_id,'+','.join(v)+') VALUES('+','.join(['?']*(len(v)+1))+')',[u['tenant_id'],*v.values()]); mid=cur.lastrowid
      if d.paid: c.execute("INSERT INTO payments(tenant_id,membership_id,amount,method,note,created_at,user_id) VALUES(?,?,?,?,?,?,?)",(u['tenant_id'],mid,d.paid,'','Incasso iniziale',now(),u['id']))
      c.execute('INSERT INTO membership_events(tenant_id,membership_id,action,created_at,user_id) VALUES(?,?,?,?,?)',(u['tenant_id'],mid,'Creazione',now(),u['id']))
    return {'ok':True}
@app.patch('/api/memberships/{mid}/status')
def membership_status(mid:int,u=Depends(tenant)):
    with db() as c:
      cur=c.execute("UPDATE memberships SET status=CASE status WHEN 'active' THEN 'suspended' ELSE 'active' END WHERE id=? AND tenant_id=?",(mid,u['tenant_id']))
      if not cur.rowcount: raise HTTPException(404,'Abbonamento non trovato')
      status=c.execute('SELECT status FROM memberships WHERE id=? AND tenant_id=?',(mid,u['tenant_id'])).fetchone()['status']
      c.execute('INSERT INTO membership_events(tenant_id,membership_id,action,created_at,user_id) VALUES(?,?,?,?,?)',(u['tenant_id'],mid,'Riattivazione' if status=='active' else 'Sospensione',now(),u['id']))
    return {'ok':True}
@app.post('/api/memberships/{mid}/payments')
def payment(mid:int,d:PaymentIn,u=Depends(tenant)):
    if d.amount<=0: raise HTTPException(400,'Importo non valido')
    with db() as c:
      cur=c.execute('UPDATE memberships SET paid=paid+? WHERE id=? AND tenant_id=?',(d.amount,mid,u['tenant_id']))
      if not cur.rowcount: raise HTTPException(404,'Abbonamento non trovato')
      c.execute('INSERT INTO payments(tenant_id,membership_id,amount,method,note,created_at,user_id) VALUES(?,?,?,?,?,?,?)',(u['tenant_id'],mid,d.amount,d.method,d.note,now(),u['id']))
    return {'ok':True}
@app.get('/api/payments')
def payments(u=Depends(tenant)):
    with db() as c: return rows(c.execute('SELECT p.*, u.name operator_name FROM payments p LEFT JOIN users u ON u.id=p.user_id WHERE p.tenant_id=? ORDER BY p.created_at DESC',(u['tenant_id'],)))
@app.get('/api/membership-events')
def membership_events(u=Depends(tenant)):
    with db() as c: return rows(c.execute('SELECT e.*,u.name operator_name FROM membership_events e LEFT JOIN users u ON u.id=e.user_id WHERE e.tenant_id=? ORDER BY e.created_at DESC',(u['tenant_id'],)))
@app.put('/api/memberships/{mid}')
def update_membership(mid:int,d:MembershipIn,u=Depends(tenant)):
    if d.end_date<d.start_date or min(d.price,d.discount)<0 or d.discount>100 or d.status not in ('active','suspended') or (d.lessons_remaining is not None and d.lessons_remaining<0): raise HTTPException(400,'Dati abbonamento non validi')
    with db() as c:
      old=c.execute('SELECT * FROM memberships WHERE id=? AND tenant_id=?',(mid,u['tenant_id'])).fetchone()
      if not old: raise HTTPException(404,'Abbonamento non trovato')
      if d.client_id!=old['client_id'] or d.plan_id!=old['plan_id'] or d.paid!=old['paid']: raise HTTPException(400,'Cliente, tipologia e incassi non sono modificabili da questa schermata')
      c.execute('UPDATE memberships SET start_date=?,end_date=?,price=?,discount=?,lessons_remaining=?,notes=? WHERE id=? AND tenant_id=?',(d.start_date,d.end_date,d.price,d.discount,d.lessons_remaining,d.notes,mid,u['tenant_id']))
      c.execute('INSERT INTO membership_events(tenant_id,membership_id,action,created_at,user_id) VALUES(?,?,?,?,?)',(u['tenant_id'],mid,'Modifica',now(),u['id']))
    return {'ok':True}
@app.get('/api/visits')
def visits(u=Depends(tenant)):
    with db() as c: return rows(c.execute('''SELECT v.*,c.first_name,c.last_name,c.code,p.name plan_name FROM visits v JOIN clients c ON c.id=v.client_id AND c.tenant_id=v.tenant_id LEFT JOIN memberships m ON m.id=v.membership_id AND m.tenant_id=v.tenant_id LEFT JOIN plans p ON p.id=m.plan_id AND p.tenant_id=v.tenant_id WHERE v.tenant_id=? ORDER BY v.check_in DESC''',(u['tenant_id'],)))
@app.post('/api/visits')
def checkin(d:VisitIn,u=Depends(tenant)):
    with db() as c:
      c.execute('BEGIN IMMEDIATE')
      client=c.execute('SELECT * FROM clients WHERE id=? AND tenant_id=?',(d.client_id,u['tenant_id'])).fetchone()
      if not client: raise HTTPException(404,'Cliente non trovato')
      if client['blocked']: raise HTTPException(400,'Cliente bloccato: '+client['block_reason'])
      if c.execute('SELECT 1 FROM visits WHERE client_id=? AND tenant_id=? AND check_out IS NULL',(d.client_id,u['tenant_id'])).fetchone(): raise HTTPException(400,'Cliente già presente nella struttura')
      m=c.execute("SELECT * FROM memberships WHERE client_id=? AND tenant_id=? AND status='active' AND start_date<=? AND end_date>=? AND (lessons_remaining IS NULL OR lessons_remaining>0) ORDER BY end_date DESC LIMIT 1",(d.client_id,u['tenant_id'],today(),today())).fetchone()
      if not m: raise HTTPException(400,'Nessun abbonamento attivo valido')
      status='Certificato scaduto' if client['certificate_expiry'] and client['certificate_expiry']<today() else 'Attivo'
      c.execute('INSERT INTO visits(tenant_id,client_id,membership_id,check_in,status,department) VALUES(?,?,?,?,?,?)',(u['tenant_id'],d.client_id,m['id'],now(),status,d.department))
      if m['lessons_remaining'] is not None: c.execute('UPDATE memberships SET lessons_remaining=lessons_remaining-1 WHERE id=? AND tenant_id=?',(m['id'],u['tenant_id']))
    return {'status':status}
@app.patch('/api/visits/{vid}/checkout')
def checkout(vid:int,u=Depends(tenant)):
    with db() as c:
      cur=c.execute('UPDATE visits SET check_out=? WHERE id=? AND tenant_id=? AND check_out IS NULL',(now(),vid,u['tenant_id']))
      if not cur.rowcount: raise HTTPException(404,'Ingresso non trovato o già chiuso')
    return {'ok':True}

class DocumentIn(BaseModel):
    name:str
    category:str = 'Altro'
    content_base64:str

@app.get('/api/clients/{cid}/documents')
def list_documents(cid:int,u=Depends(tenant)):
    with db() as c:
      if not c.execute('SELECT 1 FROM clients WHERE id=? AND tenant_id=?',(cid,u['tenant_id'])).fetchone(): raise HTTPException(404,'Cliente non trovato')
      return rows(c.execute('SELECT id,name,category,mime,length(content) size,created_at FROM client_documents WHERE client_id=? AND tenant_id=? ORDER BY created_at DESC',(cid,u['tenant_id'])))

@app.post('/api/clients/{cid}/documents')
def add_document(cid:int,d:DocumentIn,u=Depends(tenant)):
    import mimetypes
    name=os.path.basename(d.name.replace('\\','/'))
    ext=os.path.splitext(name)[1].lower()
    types={'.pdf':'application/pdf','.jpg':'image/jpeg','.jpeg':'image/jpeg','.png':'image/png'}
    if ext not in types or not name or d.category not in ('Certificato medico','Documento','Contratto','Altro'): raise HTTPException(400,'Formato o categoria non validi')
    if len(d.content_base64)>14000000: raise HTTPException(400,'File troppo grande: massimo 10 MB')
    try: content=base64.b64decode(d.content_base64,validate=True)
    except (ValueError,binascii.Error): raise HTTPException(400,'File non valido')
    if not content or len(content)>10*1024*1024: raise HTTPException(400,'File vuoto o superiore a 10 MB')
    with db() as c:
      if not c.execute('SELECT 1 FROM clients WHERE id=? AND tenant_id=?',(cid,u['tenant_id'])).fetchone(): raise HTTPException(404,'Cliente non trovato')
      c.execute('INSERT INTO client_documents(tenant_id,client_id,name,category,mime,content,created_at,user_id) VALUES(?,?,?,?,?,?,?,?)',(u['tenant_id'],cid,name,d.category,types[ext],content,now(),u['id']))
    return {'ok':True}

@app.get('/api/clients/{cid}/documents/{did}/file')
def get_document(cid:int,did:int,u=Depends(tenant)):
    with db() as c: doc=c.execute('SELECT content,mime FROM client_documents WHERE id=? AND client_id=? AND tenant_id=?',(did,cid,u['tenant_id'])).fetchone()
    if not doc: raise HTTPException(404,'Allegato non trovato')
    return Response(content=doc['content'],media_type=doc['mime'],headers={'Content-Disposition':'attachment','X-Content-Type-Options':'nosniff','Cache-Control':'no-store'})

@app.delete('/api/clients/{cid}/documents/{did}')
def delete_document(cid:int,did:int,u=Depends(tenant)):
    with db() as c:
      result=c.execute('DELETE FROM client_documents WHERE id=? AND client_id=? AND tenant_id=?',(did,cid,u['tenant_id']))
      if not result.rowcount: raise HTTPException(404,'Allegato non trovato')
    return {'ok':True}
