#!/usr/bin/env python3
"""Fail closed before any artifact upload, including after exporter failures."""
import argparse,hashlib,json,os,stat
from pathlib import Path
FOLDER_LIMIT=6*1024*1024
FILE_LIMIT=800*1024
COMBINED_LIMIT=20_000_000
ALLOWED={'.jpg','.png','.json','.log','.txt','.plist'}
def inspect(folder: Path,required=True,limit=FOLDER_LIMIT):
 if not folder.exists():
  if required:raise ValueError('Required evidence folder was not produced')
  return {'bytes':0,'files':[]}
 if folder.is_symlink() or not folder.is_dir():raise ValueError('Evidence root must be a real directory')
 root=folder.resolve();rows=[];total=0
 for file in sorted(folder.rglob('*')):
  mode=file.lstat().st_mode
  if stat.S_ISLNK(mode) or not file.resolve().is_relative_to(root):raise ValueError('Evidence symlink/path escape rejected')
  if stat.S_ISDIR(mode):continue
  if not stat.S_ISREG(mode) or file.suffix not in ALLOWED:raise ValueError('Unexpected evidence file type: '+file.name)
  size=file.stat().st_size
  if size>FILE_LIMIT:raise ValueError('Evidence per-file cap exceeded: '+file.name)
  if file.suffix=='.json':
   if size>512*1024:raise ValueError('Structured evidence cap exceeded')
   json.loads(file.read_text())
  total+=size
  if total>limit:raise ValueError('Evidence folder exceeds its reserved whole-run allocation')
  rows.append({'path':str(file.relative_to(folder)),'bytes':size,'sha256':hashlib.sha256(file.read_bytes()).hexdigest()})
  if len(rows)>128:raise ValueError('Evidence file-count cap exceeded')
 if required and not rows:raise ValueError('Evidence folder is empty')
 return {'bytes':total,'files':rows}
def allocation():
 value=json.loads(Path(__file__).with_name('evidence-allocation.json').read_text())
 limits=value['scope_limits_bytes']
 assert set(limits)=={'macos','visionos','tvos','watchos','iphone_pro','iphone_se3','ipad_pro','ipad_mini'}
 assert value['whole_run_limit_bytes']==COMBINED_LIMIT
 assert all(isinstance(n,int) and 0<n<=FOLDER_LIMIT for n in limits.values())
 assert sum(limits.values())<=COMBINED_LIMIT
 return value
def main():
 parser=argparse.ArgumentParser();parser.add_argument('folder',type=Path,nargs='?');parser.add_argument('--previous',type=Path);parser.add_argument('--report',type=Path);parser.add_argument('--scope');parser.add_argument('--validate-allocation',action='store_true');args=parser.parse_args()
 reserved=allocation()
 if args.validate_allocation:
  print(json.dumps(reserved),flush=True);return
 assert args.folder and args.report and args.scope in reserved['scope_limits_bytes']
 limit=reserved['scope_limits_bytes'][args.scope]
 current=inspect(args.folder,limit=limit);prior=inspect(args.previous,False) if args.previous else {'bytes':0,'files':[]}
 combined=current['bytes']+prior['bytes']
 if combined>COMBINED_LIMIT:raise ValueError('Combined outbound evidence exceeds 20,000,000 bytes')
 report={'validated':True,'scope':args.scope,'current':current,'previous_bytes':prior['bytes'],'combined_bytes':combined,'scope_limit_bytes':limit,'whole_run_reserved_bytes':sum(reserved['scope_limits_bytes'].values()),'combined_limit_bytes':COMBINED_LIMIT}
 args.report.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report),flush=True)
if __name__=='__main__':main()
