import os, tempfile
p=tempfile.mktemp(suffix='.db'); os.environ['DATABASE_PATH']=p; os.environ['SUPERADMIN_EMAIL']='root@test.it'; os.environ['SUPERADMIN_PASSWORD']='password123'
from fastapi.testclient import TestClient
from backend.main import app
c=TestClient(app)
def login(email):
 r=c.post('/api/login',json={'email':email,'password':'password123'}); assert r.status_code==200,r.text; return {'Authorization':'Bearer '+r.json()['token']}
a=login('root@test.it')
for i in (1,2):
 r=c.post('/api/tenants',headers=a,json={'name':f'Club {i}','slug':f'club{i}','admin_name':'Admin','admin_email':f'admin{i}@test.it','admin_password':'password123'}); assert r.status_code==200,r.text
h=login('admin1@test.it'); h2=login('admin2@test.it')
r=c.post('/api/clients',headers=h,json={'code':'001','first_name':'Mario','last_name':'Rossi'}); assert r.status_code==200,r.text; cid=r.json()['id']
assert c.get('/api/clients',headers=h2).json()==[]
r=c.post(f'/api/clients/{cid}/documents',headers=h,json={'name':'certificato.pdf','category':'Certificato medico','content_base64':'JVBERi0xLjQ='}); assert r.status_code==200,r.text
doc=c.get(f'/api/clients/{cid}/documents',headers=h).json()[0]
assert c.get(f"/api/clients/{cid}/documents/{doc['id']}/file",headers=h2).status_code==404
assert c.get(f"/api/clients/{cid}/documents/{doc['id']}/file",headers=h).content==b'%PDF-1.4'
assert c.delete(f"/api/clients/{cid}/documents/{doc['id']}",headers=h).status_code==200
r=c.post('/api/plans',headers=h,json={'name':'Mensile','duration_days':30,'price':50}); assert r.status_code==200,r.text
pid=c.get('/api/plans',headers=h).json()[0]['id']
r=c.post('/api/memberships',headers=h2,json={'client_id':cid,'plan_id':pid,'start_date':'2020-01-01','end_date':'2099-01-01'}); assert r.status_code==404,r.text
r=c.post('/api/memberships',headers=h,json={'client_id':cid,'plan_id':pid,'start_date':'2020-01-01','end_date':'2099-01-01','price':50}); assert r.status_code==200,r.text
m=c.get('/api/memberships',headers=h).json()[0]; mid=m['id']
assert c.post(f'/api/memberships/{mid}/payments',headers=h,json={'amount':12.50,'method':'Carta','note':'Acconto'}).status_code==200
assert c.get('/api/payments',headers=h).json()[0]['amount']==12.5
assert c.get('/api/payments',headers=h2).json()==[]
assert c.patch(f'/api/memberships/{mid}/status',headers=h).status_code==200
assert c.patch(f'/api/memberships/{mid}/status',headers=h).status_code==200
assert len(c.get('/api/membership-events',headers=h).json())==3
m=c.get('/api/memberships',headers=h).json()[0]; m['notes']='Prova modifica'
assert c.put(f'/api/memberships/{mid}',headers=h,json=m).status_code==200
assert c.put(f'/api/memberships/{mid}',headers=h2,json=m).status_code==404
r=c.post('/api/visits',headers=h,json={'client_id':cid}); assert r.status_code==200,r.text
assert c.post('/api/visits',headers=h,json={'client_id':cid}).status_code==400
v=c.get('/api/visits',headers=h).json()[0]; assert c.patch(f"/api/visits/{v['id']}/checkout",headers=h2).status_code==404
assert c.patch(f"/api/visits/{v['id']}/checkout",headers=h).status_code==200
assert c.get('/api/tenants',headers=h).status_code==403
print('Flussi API e isolamento tenant: OK')
os.unlink(p)
