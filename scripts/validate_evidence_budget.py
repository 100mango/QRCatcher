#!/usr/bin/env python3
"""Fail closed before any artifact upload, including after exporter failures."""
import argparse,hashlib,json,os,stat
from pathlib import Path
FOLDER_LIMIT=6*1024*1024
FILE_LIMIT=800*1024
COMBINED_LIMIT=20_000_000
ALLOWED={'.jpg','.png','.json','.log','.txt','.plist'}
def inspect(folder: Path,required=True):
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
  if total>FOLDER_LIMIT:raise ValueError('Evidence folder exceeds 6 MiB')
  rows.append({'path':str(file.relative_to(folder)),'bytes':size,'sha256':hashlib.sha256(file.read_bytes()).hexdigest()})
  if len(rows)>128:raise ValueError('Evidence file-count cap exceeded')
 if required and not rows:raise ValueError('Evidence folder is empty')
 return {'bytes':total,'files':rows}
def main():
 parser=argparse.ArgumentParser();parser.add_argument('folder',type=Path);parser.add_argument('--previous',type=Path);parser.add_argument('--report',required=True,type=Path);args=parser.parse_args()
 current=inspect(args.folder);prior=inspect(args.previous,False) if args.previous else {'bytes':0,'files':[]}
 combined=current['bytes']+prior['bytes']
 if combined>COMBINED_LIMIT:raise ValueError('Combined outbound evidence exceeds 20,000,000 bytes')
 report={'validated':True,'current':current,'previous_bytes':prior['bytes'],'combined_bytes':combined,'combined_limit_bytes':COMBINED_LIMIT}
 args.report.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report),flush=True)
if __name__=='__main__':main()
