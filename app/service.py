import os, re, json, hashlib, uuid, difflib
from datetime import datetime, timezone
from pathlib import Path
import fitz
from sqlalchemy import create_engine, String, Integer, Text, ForeignKey, select
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

DB_URL=os.getenv('DATABASE_URL','sqlite:///./ct200.db')
engine=create_engine(DB_URL, connect_args={'check_same_thread':False} if DB_URL.startswith('sqlite') else {})
Session=sessionmaker(engine,expire_on_commit=False)
class Base(DeclarativeBase): pass
class Version(Base):
 __tablename__='versions'; id:Mapped[str]=mapped_column(String,primary_key=True); doc_id:Mapped[str]=mapped_column(String,index=True); number:Mapped[int]=mapped_column(Integer); source:Mapped[str]=mapped_column(String); created:Mapped[str]=mapped_column(String)
class Node(Base):
 __tablename__='nodes'; id:Mapped[str]=mapped_column(String,primary_key=True); logical_id:Mapped[str]=mapped_column(String,index=True); version_id:Mapped[str]=mapped_column(ForeignKey('versions.id'),index=True); parent_id:Mapped[str|None]=mapped_column(String,nullable=True,index=True); heading:Mapped[str]=mapped_column(Text); level:Mapped[int]=mapped_column(Integer); body:Mapped[str]=mapped_column(Text); content_hash:Mapped[str]=mapped_column(String); ordinal:Mapped[int]=mapped_column(Integer)
class Selection(Base):
 __tablename__='selections'; id:Mapped[str]=mapped_column(String,primary_key=True); name:Mapped[str]=mapped_column(String); created:Mapped[str]=mapped_column(String); refs:Mapped[str]=mapped_column(Text)
class Generation(Base):
 __tablename__='generations'; id:Mapped[str]=mapped_column(String,primary_key=True); selection_id:Mapped[str]=mapped_column(String,index=True); created:Mapped[str]=mapped_column(String); payload:Mapped[str]=mapped_column(Text); snapshots:Mapped[str]=mapped_column(Text)
def db_init(): Base.metadata.create_all(engine)
def sha(s): return hashlib.sha256(s.encode()).hexdigest()
def pdf_text(path):
 doc=fitz.open(path); out=[]
 for page in doc:
  blocks=page.get_text('blocks',sort=True)
  out.extend(b[4] for b in blocks if len(b)>4 and b[4].strip())
 return '\n'.join(out)
HEAD=re.compile(r'^\s*(\d+(?:\.\d+)*)\.?\s+(.+?)\s*$')
def parse_document(text):
 # Numbered headings define explicit structural levels. Missing levels attach to the nearest existing prefix.
 nodes=[]; stack=[]; current=None; body=[]
 def flush():
  if current is not None:
   current['body']='\n'.join(body).strip(); current['hash']=sha(current['heading']+'\n'+current['body']); nodes.append(current.copy())
 for line in text.splitlines():
  line=line.strip()
  m=HEAD.match(line)
  if m and len(m.group(1))<=22:
   num,title=m.groups(); parts=num.split('.'); candidate={'num':num,'heading':title.strip(),'level':len(parts),'body':'','hash':''}
   # `2.1.1.1` is retained at level 4 and parented to 2.1 when levels 2 and 3 are absent.
   flush(); body=[]
   while stack and len(stack[-1]['num'].split('.'))>=len(parts): stack.pop()
   candidate['parent_num']=stack[-1]['num'] if stack else None
   stack.append(candidate); current=candidate
  else:
   if line: body.append(line)
 flush()
 return nodes

def _version(s,doc_id=None,number=None):
 q=select(Version).where(Version.id==s)
 return None

def ingest(path,version=None):
 path=str(Path(path).resolve()); text=pdf_text(path); parsed=parse_document(text)
 if not parsed: raise ValueError('No numbered headings found in PDF')
 doc_id='ct200-manual';
 with Session() as s:
  previous=s.scalars(select(Version).where(Version.doc_id==doc_id).order_by(Version.number.desc())).first()
  number=version or (previous.number+1 if previous else 1)
  if s.scalars(select(Version).where(Version.doc_id==doc_id,Version.number==number)).first(): raise ValueError(f'version {number} already exists')
  vid=str(uuid.uuid4()); v=Version(id=vid,doc_id=doc_id,number=number,source=path,created=datetime.now(timezone.utc).isoformat()); s.add(v)
  old={}
  if previous:
   old={n.heading+'|'+(n.parent_id or ''):n for n in s.scalars(select(Node).where(Node.version_id==previous.id))}
  ids={}; rows=[]
  for i,p in enumerate(parsed):
   parent=ids.get(p['parent_num']); key=p['heading']+'|'+str(parent or '')
   prior=next((n for n in s.scalars(select(Node).where(Node.version_id==previous.id)) if n.heading==p['heading']),None) if previous else None
   logical=prior.logical_id if prior else str(uuid.uuid4()); nid=str(uuid.uuid4()); ids[p['num']]=nid
   rows.append(Node(id=nid,logical_id=logical,version_id=vid,parent_id=parent,heading=p['heading'],level=p['level'],body=p['body'],content_hash=p['hash'],ordinal=i))
  s.add_all(rows); s.commit()
  return {'document_id':doc_id,'version':number,'version_id':vid,'node_count':len(rows),'source':path}

def _resolve(s,doc_id,version):
 v=s.scalars(select(Version).where(Version.doc_id==doc_id).order_by(Version.number.desc())).first() if version is None else s.scalars(select(Version).where(Version.doc_id==doc_id,Version.number==version)).first()
 return v

def _node_json(n,children=None): return {'id':n.id,'logical_id':n.logical_id,'heading':n.heading,'level':n.level,'body':n.body,'content_hash':n.content_hash,'parent_id':n.parent_id,'children':children or []}
def list_nodes(doc_id,version=None,roots_only=False):
 with Session() as s:
  v=_resolve(s,doc_id,version)
  if not v:return []
  ns=list(s.scalars(select(Node).where(Node.version_id==v.id).order_by(Node.ordinal)))
  return [_node_json(n) for n in ns if not roots_only or not n.parent_id]
def get_node(node_id,version=None):
 with Session() as s:
  n=s.get(Node,node_id)
  if not n:return None
  if version is not None:
   v=s.get(Version,n.version_id)
   if not v or v.number!=version:return None
  alln=list(s.scalars(select(Node).where(Node.version_id==n.version_id).order_by(Node.ordinal))); byparent={}
  for x in alln: byparent.setdefault(x.parent_id,[]).append(x)
  def build(x): return _node_json(x,[build(c) for c in byparent.get(x.id,[])])
  return build(n)
def search_nodes(doc_id,q,version=None):
 with Session() as s:
  v=_resolve(s,doc_id,version)
  if not v:return []
  term=q.lower(); return [_node_json(n) for n in s.scalars(select(Node).where(Node.version_id==v.id).order_by(Node.ordinal)) if term in (n.heading+' '+n.body).lower()]
def node_changes(logical_id):
 with Session() as s:
  ns=list(s.scalars(select(Node).where(Node.logical_id==logical_id)))
  ns.sort(key=lambda n:s.get(Version,n.version_id).number)
  return {'logical_id':logical_id,'versions':[{'version':s.get(Version,n.version_id).number,'node_id':n.id,'heading':n.heading,'content_hash':n.content_hash,'changed':bool(ns and n.content_hash!=ns[0].content_hash),'diff':difflib.unified_diff(ns[0].body.splitlines(),n.body.splitlines(),lineterm='')} for n in ns]}
def create_selection(name,node_ids,version=None):
 with Session() as s:
  refs=[]
  for nid in node_ids:
   n=s.get(Node,nid)
   if not n: raise ValueError(f'unknown node {nid}')
   v=s.get(Version,n.version_id)
   if version is not None and v.number!=version: raise ValueError('all nodes must belong to requested version')
   refs.append({'node_id':n.id,'version_id':n.version_id,'content_hash':n.content_hash,'text':n.heading+'\n'+n.body})
  obj=Selection(id=str(uuid.uuid4()),name=name,created=datetime.now(timezone.utc).isoformat(),refs=json.dumps(refs));s.add(obj);s.commit();return {'selection_id':obj.id,'name':name,'node_count':len(refs),'version_pinned':True}
def _llm(text,provider):
 import urllib.request
 if not provider or provider=='openai-compatible':
  key=os.getenv('OPENAI_API_KEY'); url=os.getenv('OPENAI_BASE_URL','https://api.openai.com/v1/chat/completions'); model=os.getenv('OPENAI_MODEL','gpt-4o-mini')
 else: key=os.getenv('GROQ_API_KEY');url='https://api.groq.com/openai/v1/chat/completions';model=os.getenv('GROQ_MODEL','llama-3.3-70b-versatile')
 if not key: raise RuntimeError('Set OPENAI_API_KEY (or GROQ_API_KEY with provider=groq)')
 schema={'type':'object','properties':{'test_cases':{'type':'array','minItems':3,'maxItems':5,'items':{'type':'object','properties':{'title':{'type':'string'},'steps':{'type':'array','items':{'type':'string'}},'expected_result':{'type':'string'},'source_node_id':{'type':'string'}},'required':['title','steps','expected_result','source_node_id'],'additionalProperties':False}}},'required':['test_cases'],'additionalProperties':False}
 prompt='Create 3-5 concrete, repeatable medical-device QA test ideas solely grounded in the supplied source. Include observable expected results and source_node_id. Return JSON matching schema. Source:\n'+text
 payload={'model':model,'messages':[{'role':'user','content':prompt}],'response_format':{'type':'json_object'}}
 req=urllib.request.Request(url,data=json.dumps(payload).encode(),headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'})
 with urllib.request.urlopen(req,timeout=60) as r: raw=json.loads(r.read())['choices'][0]['message']['content']
 result=json.loads(raw); cases=result['test_cases']
 if not 3<=len(cases)<=5 or any(not all(k in c for k in ('title','steps','expected_result','source_node_id')) for c in cases): raise RuntimeError('LLM response failed structured-output validation')
 return result

def generate_cases(selection_id,provider=None):
 with Session() as s:
  sel=s.get(Selection,selection_id)
  if not sel: raise ValueError('selection not found')
  refs=json.loads(sel.refs); result=_llm('\n\n'.join(r['text']+' [source_node_id='+r['node_id']+']' for r in refs),provider)
  g=Generation(id=str(uuid.uuid4()),selection_id=sel.id,created=datetime.now(timezone.utc).isoformat(),payload=json.dumps(result),snapshots=sel.refs);s.add(g);s.commit();return {'generation_id':g.id,'selection_id':sel.id,'test_cases':result['test_cases'],'staleness':_staleness(s,g)}
def _staleness(s,g):
 refs=json.loads(g.snapshots); latest={}
 for r in refs:
  old=s.get(Node,r['node_id']); oldv=s.get(Version,old.version_id); current=_resolve(s,oldv.doc_id,None)
  nn=s.scalars(select(Node).where(Node.version_id==current.id,Node.logical_id==old.logical_id)).first() if current else None
  latest[r['node_id']]={'stale':nn is None or nn.content_hash!=r['content_hash'],'current_node_id':nn.id if nn else None,'old_hash':r['content_hash'],'current_hash':nn.content_hash if nn else None}
 return {'stale':any(x['stale'] for x in latest.values()),'sources':latest}
def get_generations(selection_id=None,node_id=None):
 with Session() as s:
  gs=list(s.scalars(select(Generation).order_by(Generation.created.desc())))
  out=[]
  for g in gs:
   refs=json.loads(g.snapshots)
   if selection_id and g.selection_id!=selection_id:continue
   if node_id and not any(r['node_id']==node_id for r in refs):continue
   out.append({'generation_id':g.id,'selection_id':g.selection_id,'created':g.created,'test_cases':json.loads(g.payload)['test_cases'],'staleness':_staleness(s,g)})
  return out
