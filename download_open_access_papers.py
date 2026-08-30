#!/usr/bin/env python3
import csv,re,time,argparse,requests,xml.etree.ElementTree as ET
from pathlib import Path
from difflib import SequenceMatcher
from urllib.parse import quote
UA='Robotics300OA/2.0'; TIMEOUT=30

def norm(s): return ' '.join(re.sub(r'[^a-z0-9]+',' ',(s or '').lower()).split())
def sim(a,b): return SequenceMatcher(None,norm(a),norm(b)).ratio()
def safe(s): return re.sub(r'[\\/:*?"<>|]','_',s or '')[:120].strip()
def js(url,params=None):
    for i in range(3):
        try:
            r=requests.get(url,params=params,timeout=TIMEOUT,headers={'User-Agent':UA});
            if r.status_code==429: time.sleep(2+i*2); continue
            r.raise_for_status(); return r.json()
        except Exception: time.sleep(1+i)
    return {}
def openalex(t,y):
    out=[]
    for w in js('https://api.openalex.org/works',{'search':t,'per-page':8}).get('results',[]):
        s=sim(t,w.get('title','')); wy=w.get('publication_year');
        if y and wy and abs(int(y)-int(wy))>2:s-=.1
        urls=[]
        for l in [w.get('best_oa_location'),w.get('primary_location')]+(w.get('locations') or []):
            if l and l.get('pdf_url'): urls.append(('OpenAlex',l['pdf_url']))
        out.append((s,w.get('title',''),wy,urls))
    return out
def sem(t,y):
    d=js('https://api.semanticscholar.org/graph/v1/paper/search',{'query':t,'limit':5,'fields':'title,year,externalIds,openAccessPdf'}); out=[]
    for w in d.get('data',[]):
        s=sim(t,w.get('title','')); wy=w.get('year');
        if y and wy and abs(int(y)-int(wy))>2:s-=.1
        u=[]; oa=w.get('openAccessPdf') or {}; ext=w.get('externalIds') or {}
        if oa.get('url'):u.append(('SemanticScholar',oa['url']))
        if ext.get('ArXiv'):u.append(('arXiv','https://arxiv.org/pdf/'+ext['ArXiv']+'.pdf'))
        out.append((s,w.get('title',''),wy,u))
    return out
def arxiv(t):
    out=[]
    queries=['ti:"'+t.replace('"','')+'"','all:'+ ' '.join(norm(t).split()[:10])]
    for q0 in queries:
        try:
            r=requests.get('https://export.arxiv.org/api/query?search_query='+quote(q0)+'&start=0&max_results=8',timeout=TIMEOUT,headers={'User-Agent':UA})
            if r.status_code!=200:continue
            root=ET.fromstring(r.text); ns={'a':'http://www.w3.org/2005/Atom'}
            for e in root.findall('a:entry',ns):
                tt=(e.findtext('a:title','',ns) or '').replace('\n',' ').strip(); aid=e.findtext('a:id','',ns).rstrip('/').split('/')[-1]
                out.append((sim(t,tt),tt,None,[('arXiv','https://arxiv.org/pdf/'+aid+'.pdf')]))
        except Exception: pass
        time.sleep(.4)
    return out
def dl(url,dest):
    try:
        r=requests.get(url,timeout=45,headers={'User-Agent':UA},allow_redirects=True)
        if r.status_code==200 and (r.content[:5]==b'%PDF-' or 'application/pdf' in r.headers.get('content-type','').lower()) and len(r.content)>20000:
            dest.write_bytes(r.content); return True
    except Exception: pass
    return False

def main():
    a=argparse.ArgumentParser(); a.add_argument('--domain',default='all'); a.add_argument('--min-score',type=float,default=.72); args=a.parse_args()
    root=Path(__file__).parent; rows=list(csv.DictReader(open(root/'paper_manifest.csv',encoding='utf-8-sig'))); fails=[]; done=0
    wanted={'Contact_Rich':'Contact_Rich','DOM':'DOM','Assistive':'Assistive'}
    for i,row in enumerate(rows,1):
        if args.domain!='all' and row['domain']!=wanted.get(args.domain,args.domain): continue
        t=row['title']; y=int(row['year']) if row.get('year','').isdigit() else None; folder=root/'downloads'/safe(row['domain'])/safe(row['category']); folder.mkdir(parents=True,exist_ok=True); dest=folder/f"{row.get('year','NA')}_{safe(t)}.pdf"
        print(f'[{i:03}/300] {t}',flush=True); c=openalex(t,y); time.sleep(.4); c+=sem(t,y); time.sleep(.4); c+=arxiv(t); c.sort(key=lambda x:x[0],reverse=True)
        urls=[]; seen=set()
        for score,rt,ry,us in c:
            if score<args.min_score:continue
            for src,u in us:
                if u not in seen:seen.add(u);urls.append((src,u,score))
        ok=False
        for src,u,score in urls:
            if dl(u,dest): row['status']='DOWNLOADED'; row['source']=src; row['oa_pdf_url']=u; done+=1; ok=True; break
        if not ok: row['status']='FAILED'; row['error']='No downloadable OA PDF found'; fails.append(row.copy())
    fields=list(rows[0]);
    with open(root/'download_failures.csv','w',encoding='utf-8-sig',newline='') as f:w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(fails)
    print(f'Downloaded {done}; failed {len(fails)}')
if __name__=='__main__':main()
