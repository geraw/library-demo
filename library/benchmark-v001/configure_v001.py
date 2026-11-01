"""Resolve local binaries without replacing an existing installation."""
import argparse,json,os,shutil,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent

def choose(explicit,env,names,roots):
 if explicit or os.environ.get(env):
  p=Path(explicit or os.environ[env]).expanduser().resolve()
  if not p.is_file():raise RuntimeError('Explicit binary not found: '+str(p))
  return str(p)
 for root in roots:
  if not root.is_dir():continue
  for name in names:
   direct=root/name
   if direct.is_file():return str(direct.resolve())
 # Bounded discovery in conventional tool folders; ambiguity is surfaced.
 hits=[]
 for root in roots:
  if not root.is_dir():continue
  for directory,dirs,files in os.walk(root):
   here=Path(directory)
   dirs[:]=[d for d in dirs if d.lower() not in {'.git','.venv','node_modules','state','runs','products','__pycache__'}]
   if len(here.relative_to(root).parts)>=6:dirs[:]=[]
   for name in files:
    if name.lower() in {n.lower() for n in names}:hits.append((here/name).resolve())
 hits=sorted(set(hits))
 hits=[p for p in hits if p.suffix.lower()!='.dll' or not p.with_suffix('.exe').is_file()]
 if len(hits)==1:return str(hits[0])
 if len(hits)>1:raise RuntimeError('Multiple '+env+' candidates; supply its explicit setup parameter: '+', '.join(map(str,hits)))
 return ''

def main():
 p=argparse.ArgumentParser();p.add_argument('--provengo-jar');p.add_argument('--evomaster-jar');p.add_argument('--restler');p.add_argument('--java',default='java');p.add_argument('--analyzer-home');p.add_argument('--install-native',action='store_true');p.add_argument('--output',type=Path,default=HERE/'tools.local.json');a=p.parse_args()
 home=Path(os.environ.get('LOCALAPPDATA',str(Path.home())))/'ISSTA-tools-v006';manifest=home/'manifest.json';managed=json.loads(manifest.read_text()) if manifest.is_file() else {}
 roots=[HERE.parents[1],Path.home()/'Downloads',Path.home()/'tools',home,Path('C:/tools'),Path('D:/tools'),Path('C:/Program Files/Provengo/Provengo Cli')]
 cfg={'java':a.java,'dotnet':'dotnet','analyzer_home':str(Path(a.analyzer_home).resolve()) if a.analyzer_home else '','restler_python_bin':managed.get('python_bin','')}
 cfg['provengo_jar']=choose(a.provengo_jar,'PROVENGO_JAR',['Provengo.uber.jar','Provengo-2026-01-10.uber.jar'],roots)
 cfg['evomaster_jar']=choose(a.evomaster_jar or (managed.get('evo') if Path(managed.get('evo','_missing_')).is_file() else None),'EVOMASTER_JAR',['evomaster.jar'],roots)
 cfg['restler']=choose(a.restler or (managed.get('restler') if Path(managed.get('restler','_missing_')).is_file() else None),'RESTLER_EXE',['Restler.exe','Restler.dll'],roots)
 if a.install_native:
  sys.path.insert(0,str(HERE/'vendor'));import bootstrap_native_v001 as install
  missing={key for key,field in [('evo','evomaster_jar'),('restler','restler')] if not cfg[field]}
  data=install.install(home,missing)
  cfg['evomaster_jar']=cfg['evomaster_jar'] or data.get('evo','');cfg['restler']=cfg['restler'] or data.get('restler','');cfg['restler_python_bin']=data.get('python_bin','')
  if data.get('java_bin'):cfg['java']=str(Path(data['java_bin'])/'java.exe')
  if data.get('dotnet_bin'):cfg['dotnet']=str(Path(data['dotnet_bin'])/'dotnet.exe')
 a.output.write_text(json.dumps(cfg,indent=2)+'\n',encoding='utf-8')
 print('CONFIG_WRITTEN '+str(a.output))
 missing=[k for k in ['provengo_jar','evomaster_jar','restler'] if not cfg[k]]
 if missing:
  print('TOOLS_NOT_READY '+','.join(missing));print('Use setup binary parameters or -InstallNativeTools. Provengo must already be installed.');return 2
 print('ALL_FOUR_CONFIGURATIONS_HAVE_BINARY_PATHS');return 0
def logged_main():
 import contextlib,datetime,traceback,uuid
 folder=HERE/'setup-logs';folder.mkdir(parents=True,exist_ok=True)
 log=folder/('configure-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:8]+'.log')
 class Tee:
  def __init__(self,terminal,file):self.terminal,self.file=terminal,file
  def write(self,text):self.terminal.write(text);self.file.write(text);self.flush();return len(text)
  def flush(self):self.terminal.flush();self.file.flush()
 print('SETUP_LOG '+str(log),flush=True)
 with log.open('w',encoding='utf-8') as stream:
  with contextlib.redirect_stdout(Tee(sys.stdout,stream)),contextlib.redirect_stderr(Tee(sys.stderr,stream)):
   print('PYTHON '+sys.executable,flush=True)
   print('LOCALAPPDATA '+os.environ.get('LOCALAPPDATA','<unset>'),flush=True)
   try:return main()
   except Exception:
    traceback.print_exc()
    print('SETUP_FAILED: full diagnostic log: '+str(log),flush=True)
    return 1
if __name__=='__main__':raise SystemExit(logged_main())
