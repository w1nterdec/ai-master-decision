from artifact_tool import Blob,SpreadsheetFile
import os,subprocess,tempfile,zipfile,xml.etree.ElementTree as ET,json,itertools
SRC='/mnt/data/Phase3_7C_情景覆盖率门槛修复版.xlsx'
OUT='/mnt/data/Phase3_7C_实际回归测试结果.json'
base=SpreadsheetFile.import_xlsx(Blob.load(SRC))
w0=[float(r[0] or 0) for r in base.worksheets.get_item('三级指标树').get_range('G2:G19').values]
mult=base.worksheets.get_item('3_2情景权重').get_range('E2:G19').values
ws=[]
for k in range(3):
 a=[w0[i]*float(mult[i][k] or 0) for i in range(18)];ws.append([x/sum(a) for x in a])
subset=None
for mask in itertools.combinations(range(18),11):
 b=sum(w0[i] for i in mask); c=sum(ws[0][i] for i in mask)
 if b>=.8 and c<.8:subset=mask;break
if subset is None:
 for count in range(8,17):
  for mask in itertools.combinations(range(18),count):
   b=sum(w0[i] for i in mask);c=sum(ws[0][i] for i in mask)
   if b>=.8 and c<.8:subset=mask;break
  if subset:break
print('subset',subset, 'base',sum(w0[i] for i in subset),'career',sum(ws[0][i] for i in subset))

def make(name,inds,gate='yes',value=4):
 w=SpreadsheetFile.import_xlsx(Blob.load(SRC))
 s=w.worksheets.get_item('三级证据评分')
 for i in inds:
  s.get_range(f'E{i+2}:F{i+2}').values=[[value,'TEST_SOURCE']]
 if gate=='yes':w.worksheets.get_item('路径').get_range('K2:M2').values=[['是','是','是']]
 if gate=='no':w.worksheets.get_item('路径').get_range('K2:M2').values=[['是','是','否']]
 path=f'/mnt/data/_phase37c_{name}.xlsx';SpreadsheetFile.export_xlsx(w).save(path);return path
cases={'full':make('full',range(18)),'divergence':make('divergence',subset),'excluded':make('excluded',range(18),'no'),'invalid':make('invalid',range(18),'yes',99)}
NS={'m':'http://schemas.openxmlformats.org/spreadsheetml/2006/main','r':'http://schemas.openxmlformats.org/officeDocument/2006/relationships'}
def read_cells(path,sheetname,addresses):
 with zipfile.ZipFile(path) as z:
  book=ET.fromstring(z.read('xl/workbook.xml'))
  rel=ET.fromstring(z.read('xl/_rels/workbook.xml.rels'))
  rels={e.attrib['Id']:e.attrib['Target'] for e in rel}
  ss=[]
  if 'xl/sharedStrings.xml' in z.namelist():
   st=ET.fromstring(z.read('xl/sharedStrings.xml'))
   ss=[''.join(t.text or '' for t in si.iter('{%s}t'%NS['m'])) for si in st]
  target=None
  for e in book.find('m:sheets',NS):
   if e.attrib['name']==sheetname:target=rels[e.attrib['{%s}id'%NS['r']]]
  if target.startswith('/'): target=target.lstrip('/')
  elif not target.startswith('xl/'):target='xl/'+target
  root=ET.fromstring(z.read(target))
  d={}
  for c in root.iter('{%s}c'%NS['m']):
   addr=c.attrib.get('r')
   if addr not in addresses:continue
   v=c.find('m:v',NS); inline=c.find('m:is',NS)
   val=v.text if v is not None else None
   if c.attrib.get('t')=='s' and val is not None:val=ss[int(val)]
   elif c.attrib.get('t')=='inlineStr' and inline is not None:val=''.join(x.text or '' for x in inline.iter('{%s}t'%NS['m']))
   elif c.attrib.get('t') not in ('str','e') and val is not None:
    try:val=float(val)
    except:pass
   d[addr]=val
  return d
results={}
for name,path in cases.items():
 dest=f'/mnt/data/_phase37c_calc_{name}';os.makedirs(dest,exist_ok=True)
 cmd=['libreoffice','-env:UserInstallation=file:///tmp/lo_p37c_'+name,'--headless','--convert-to','xlsx','--outdir',dest,path]
 p=subprocess.run(cmd,capture_output=True,text=True,timeout=90)
 new=os.path.join(dest,os.path.basename(path))
 if not os.path.isfile(new):results[name]={'error':p.stderr+p.stdout};continue
 results[name]=read_cells(new,'3_2情景比较',['D2','E2','F2','G2','H2','I2','K2','L2','M2','P2','Q2','R2'])
 print(name,results[name])
full=results['full'];div=results['divergence'];exc=results['excluded'];inv=results['invalid']
checks={
 'full_all_scores_4':all(abs(full.get(c,0)-4)<1e-7 for c in ['E2','F2','G2','H2']),
 'divergence_base_ge_80':div.get('D2',0)>=.8,
 'divergence_career_lt_80':div.get('K2',1)<.8,
 'divergence_career_blank':div.get('F2') in (None,''),
 'divergence_career_insufficient':div.get('P2')=='证据不足',
 'excluded_all_blank':all(exc.get(c) in (None,'') for c in ['E2','F2','G2','H2']),
 'invalid_coverage_zero':abs(inv.get('D2',-1))<1e-9,
}
json.dump({'source':SRC,'subset':subset,'weights':{'base':sum(w0[i] for i in subset),'career':sum(ws[0][i] for i in subset)},'cases':results,'checks':checks,'engine':'LibreOffice headless on isolated artifact_tool-exported test copies'},open(OUT,'w'),ensure_ascii=False,indent=2)
print('CHECKS',checks)
