"""Render only findings produced by engine JSON; no study notes or analyst narrative."""
from collections import Counter,defaultdict
import hashlib
import html
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parent

def escape(x):return html.escape(str(x))
def code(x):return '<span dir="ltr" class="code">'+escape(x)+'</span>'
def paragraph(text):return '<p>'+text+'</p>'
def table(headers,rows):return '<table><thead><tr>'+''.join('<th>'+escape(x)+'</th>' for x in headers)+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+str(v)+'</td>' for v in row)+'</tr>' for row in rows)+'</tbody></table>'
def section(title,body):return '<section><div class="eyebrow">דוח אוטומטי של הנתחן | גרסה v012</div><h1>'+title+'</h1>'+body+'</section>'
def compact(value,limit=220):
 s=json.dumps(value,ensure_ascii=False,sort_keys=True)
 return s if len(s)<=limit else s[:limit]+'… ['+str(len(s))+' chars]'
def get(d,path):
 for k in path.split('.'):
  if not isinstance(d,dict) or k not in d:return '<missing>'
  d=d[k]
 return d

def view(document):
 if document.get('schema_version')!='natchan-unified-analysis/1' or document.get('analyst_narrative_used') is not False:raise ValueError('Only a common-engine result is accepted')
 entries={}
 for p in sorted((ROOT/'catalogs').glob('*.json')):
  for e in json.loads(p.read_text())['entries']:entries[e['id']]=e
 declared={x['name']:x['sha256'] for x in document['catalogs']}
 for p in sorted((ROOT/'catalogs').glob('*.json')):
  if declared.get(p.name)!=hashlib.sha256(p.read_bytes()).hexdigest():raise ValueError('Catalog changed since analysis')
 groups=defaultdict(list)
 for finding in document['finding_records']:groups[finding['catalog_id']].append(finding)
 if {k:len(v) for k,v in groups.items()}!=document['rule_occurrences']:raise ValueError('Finding/count parity failed')
 rows=[dict(id=k,title=entries[k].get('title_he',entries[k]['title']),kind=entries[k]['kind'],occurrences=len(v),observations=[x['observation_id'] for x in v]) for k,v in sorted(groups.items())]
 return entries,groups,rows

def write_report(json_path,output,create_pdf=False):
 raw=json_path.read_bytes();d=json.loads(raw);entries,groups,rows=view(d);pages=[];metrics=d['evidence_summary'];reporthash=hashlib.sha256(raw).hexdigest()
 pages.append(section('ממצאים שהנתחן הפיק אוטומטית',
  paragraph('מערכות Gitea ו־Vikunja | ראיות שמורות, כולל g012 ודוחות כלים מקוריים. המסמך הופק מקובץ JSON של המנוע המשותף. אין במסמך פרשנות ממצאים שנוספה לאחר הסיווג.')+
  table(['מדד בפלט','ערך'],[[escape(k),str(v)] for k,v in metrics.items()])+
  paragraph('אופן הספירה: מופע הוא זוג ייחודי של כלל ותצפית. אותה תצפית יכולה להתאים למספר כללים; אין לסכום את השורות כמספר באגים ייחודיים. התאמה לחתימה אינה קביעה לבאג חדש או לסיבת שורש חדשה.')+
  paragraph('מקור הדוח: '+code(reporthash))+
  paragraph('כללי מדיניות: וריאנט שאינו ברשימת גרסאות של חתימה מוכרת אינו מקבל את השיוך הזה. מדידה חלקית נשארת ברמת הראיות שלה. ללא מדידה אין קביעה של אפס באגים.')))
 detailed=[r for r in rows if r['kind']=='known_bug' or entries[r['id']].get('report_detail')]
 pages.append(section('סיכום חתימות ותצפיות מזוהות',table(['כלל','תיאור מתוך הקטלוג','מופעים'],[[code(r['id']),escape(r['title']),r['occurrences']] for r in detailed[:20]])))
 if len(detailed)>20:pages.append(section('סיכום חתימות ותצפיות | המשך',table(['כלל','תיאור מתוך הקטלוג','מופעים'],[[code(r['id']),escape(r['title']),r['occurrences']] for r in detailed[20:]])))
 def card(row):
  id=row['id'];values=groups[id];entry=entries[id]
  counts=Counter((v['product'],v.get('version'),v.get('tool'),v['evidence_tier']) for v in values)
  body='<article data-rule="'+escape(id)+'" data-count="'+str(len(values))+'"><h2>'+code(id)+' | '+escape(row['title'])+'</h2>'
  body+=paragraph('מספר מופעים: <b>'+str(len(values))+'</b>. סוג כלל: '+code(row['kind'])+'. חומרה בקטלוג: '+code(entry['severity'])+'. סקירה אנושית: '+code(entry['human_review'])+'.')
  body+=table(['מוצר / גרסה / כלי','רמת ראיה','מופעים'],[[escape(str(product))+' / '+code(version)+' / '+code(tool),escape(tier),n] for (product,version,tool,tier),n in sorted(counts.items(),key=lambda x:str(x[0]))])
  # Every proof value below is read from the actual matched-finding facts.
  sample=values[0]
  body+=table(['תנאי הכלל','ערך שנדרש','ערך שחושב'],[[code(c['fact']),code(compact(c.get('value','present'))),code(compact(get(sample['facts'],c['fact'])))] for c in entry['all']])
  for v in values[:2]:
   s=v['source'];location=s.get('file',s.get('archive',''))
   body+=paragraph('עדות: '+code(v['run_id'])+'; מקור '+code(Path(location).name)+'; רשומה '+code(s.get('record'))+'; SHA-256 '+code(s.get('sha256',''))+'.')
  sub=Counter(v['facts'].get('c4_subtype') for v in values if v['facts'].get('c4_subtype'))
  if sub:body+=paragraph('פירוט ערך subtype בפלט: '+code(dict(sub))+'.')
  if 'VIK-F04'==id:body+=paragraph('ערכי cover שחושבו בפלט: '+code(sorted({v['facts']['cover_reference_value'] for v in values}))+'.')
  body+='</article>';return body
 for i in range(0,len(detailed),2):pages.append(section('פירוט ממצאי הכללים | '+str(i+1)+'–'+str(min(i+2,len(detailed))),''.join(card(r) for r in detailed[i:i+2])))
 other=[r for r in rows if r not in detailed]
 if other:pages.append(section('כללים תיאוריים נוספים שהתאימו',table(['כלל','כותרת הקטלוג','מופעים'],[[code(r['id']),escape(r['title']),r['occurrences']] for r in other])))
 # Native run state is displayed as data; no conclusion about a passing product is added.
 for start in range(0,len(d['runs']),18):
  values=d['runs'][start:start+18]
  pages.append(section('תוצאות מקורות הריצה | '+str(start+1),table(['הרצה','מוצר / גרסה','כלי','תוצאה native / קוד יציאה'],[[code(v['id']),escape(str(v.get('product')))+' / '+code(v.get('version')),code(v.get('tool')),code(v.get('native_status',v.get('native_run_status','not recorded')))+' / '+code(v.get('native_exit'))] for v in values])))
 terminal=[r for r in d['runs'] if r.get('native_status')=='STOPPED_AT_FIRST_FAILURE' and r.get('last_http_500_rules')]
 if terminal:pages.append(section('כללים בתגובת 500 האחרונה בריצות שנעצרו',
  paragraph('הטבלה מציגה חיבור לפי מקור הרשומה האחרונה ב־HTTP 500 והכללים שהתאימו לה; תוצאת native מוצגת בנפרד. אין כאן הסקת סיבה מעבר לתנאי הכללים.')+
  table(['הרצה','כללים תואמים לרשומת 500 האחרונה'],[[code(r['id']),', '.join(code(x) for x in r['last_http_500_rules'])] for r in terminal])))
 pages.append(section('כיסוי תיאורי והקשר חסר',
  table(['משפחה ורמת בדיקה','מספר מדידות'],[[code(k),v] for k,v in sorted(d.get('descriptive_family_coverage',{}).items())])+
  paragraph('ספירות אלו מתארות התאמות ומדידות שהמתאם הצליח לבנות. הן אינן מספר באגים, ואינן הוכחת תקינות של מדיניות עסקית שלא הוגדרה.')))
 missing=Counter((x['family'],x['reason']) for x in d['unknown_evidence'])
 pages.append(section('הכרעות שלא ניתן להשלים מן הראיות',
  table(['משפחה','הסיבה שהמנוע רשם','רשומות'],[[code(f),code(reason),n] for (f,reason),n in sorted(missing.items())])+
  paragraph('פרופיל השדות הוציא מהשוואות roundtrip את המדידות הבאות: '+code(d.get('excluded_measurement_counts',{}))+'. הערכים נשמרים בפלט כמדידות שהוחרגו; אין סיווג של שינוי metadata כהפרת ערך לקוח.')+
  paragraph('חתימת פרופיל המדיניות: '+code(d['profile_sha256'])+'.')))
 pages.append(section('עקיבות ושחזור',
  paragraph('כל שורת ממצא ב־PDF נגזרה מ־finding_records בקובץ analysis.json. מסמך זה אינו קורא NOTE, אינדקס ממצאים, ניתוח ידני או דוח PDF קודם.')+
  paragraph('מקורות נתונים שנפתחו: '+str(len(d['input_inventory']))+'. קובצי קוד שנרשמו: '+str(len(d.get('code_inventory',[])))+'. בקשות חדשות לשרת: '+str(d['new_sut_requests'])+'.')+
  paragraph('חתימת תצורת המקורות: '+code(d.get('corpus_sha256'))+'.')+
  table(['קטלוג כללים','SHA-256'],[[code(c['name']),code(c['sha256'])] for c in d['catalogs']])+
  paragraph('לשחזור יש להשתמש בגרסת הקוד, בפרופיל ובמקורות המדויקים הרשומים בקובץ JSON. קובץ חסר או כשל מתאם מסיימים את ההרצה בשגיאה; אין המרה אוטומטית לתוצאה נקייה.')))
 css='''@font-face{font-family:R;src:url(file:///usr/share/fonts/truetype/dejavu/DejaVuSans.ttf)}@font-face{font-family:R;src:url(file:///usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf);font-weight:bold}@page{size:A4;margin:15mm 15mm 18mm;@bottom-right{content:"דוח אוטומטי | v012";font-family:R;font-size:8pt;color:#64748b}@bottom-left{content:"עמוד " counter(page) " מתוך " counter(pages);font-family:R;font-size:8pt;color:#64748b}}body{font-family:R,sans-serif;direction:rtl;font-size:9.6pt;line-height:1.5;color:#1f2937}section{break-before:page}section:first-child{break-before:auto}.eyebrow{color:#64748b;font-size:8pt;border-bottom:1px solid #cbd5e1;padding-bottom:7px;margin-bottom:16px}h1{font-size:19pt;color:#123c51;line-height:1.35;margin:8px 0 14px}h2{font-size:12.5pt;color:#0f6478;line-height:1.45}p{margin:7px 0 11px;orphans:3;widows:3}.code{font-family:R,sans-serif;font-size:.86em;unicode-bidi:isolate;overflow-wrap:anywhere}table{border-collapse:collapse;width:100%;table-layout:fixed;font-size:8pt;line-height:1.5;margin:10px 0 14px}th{background:#123c51;color:white;text-align:right;padding:6px}td{padding:6px;vertical-align:top;border-bottom:1px solid #d8e3e9;overflow-wrap:anywhere}tr:nth-child(even) td{background:#f2f6f8}tr{break-inside:avoid}thead{display:table-header-group}article{border-bottom:1px solid #d0dce4;padding-bottom:8px;margin-bottom:12px}'''
 htmltext='<!doctype html><html lang="he" dir="rtl"><meta charset="utf-8"><title>ממצאים אוטומטיים של הנתחן v012</title><style>'+css+'</style><body>'+''.join(pages)+'</body></html>'
 output.mkdir(parents=True,exist_ok=True);(output/'report.html').write_text(htmltext)
 md=['# Automatically generated Natchan findings','', 'Analysis SHA256: '+reporthash,'','| Rule | Count |','|---|---:|']
 md+=['| '+r['id']+' | '+str(r['occurrences'])+' |' for r in rows];(output/'report.md').write_text('\n'.join(md)+'\n')
 model=dict(schema_version='natchan-report-view/1',analysis_sha256=reporthash,rows=rows,source='analysis.finding_records only',analyst_narrative_used=False)
 (output/'report-view.json').write_text(json.dumps(model,ensure_ascii=False,indent=2)+'\n')
 if create_pdf:
  from weasyprint import HTML
  HTML(string=htmltext,base_url=str(output.resolve())).write_pdf(output/'Natchan_Automated_Findings_v012.pdf')
 return model
