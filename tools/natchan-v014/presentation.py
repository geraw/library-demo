"""Canonical report projection: retain all raw rule matches, merge overlapping labels."""
from copy import deepcopy
ALIASES={'GIT-PG-NUL-ERROR':'GIT-C9','GIT-PG-LENGTH-ERROR':'GIT-C10'}

def project_findings(records):
 index={(x['catalog_id'],x['observation_id']):deepcopy(x) for x in records}
 if len(index)!=len(records):raise ValueError('Duplicate raw finding pair')
 for (rule,oid),item in list(index.items()):
  primary=ALIASES.get(rule)
  if primary and (primary,oid) in index:
   index[primary,oid].setdefault('supporting_labels',[]).append(rule)
   del index[rule,oid]
 for item in index.values():
  if 'supporting_labels' in item:item['supporting_labels'].sort()
 return sorted(index.values(),key=lambda x:(x['catalog_id'],x['observation_id']))
