"""Self-contained, printable A.C.E. browser reports. No external dependencies."""
from datetime import datetime
from html import escape
import math
from pathlib import Path


def clean(value):
    return str('' if value is None else value).replace('\u2014', ', ')


def text(value):
    return escape(clean(value), quote=True)


def table(columns, rows):
    header=''.join('<th scope="col">'+text(c)+'</th>' for c in columns)
    body=''.join('<tr>'+''.join('<td>'+text(r.get(c,''))+'</td>' for c in columns)+'</tr>' for r in rows)
    if not body:
        body=f'<tr><td colspan="{len(columns)}">No records during this reporting period.</td></tr>'
    return '<div class="scroll"><table><thead><tr>'+header+'</tr></thead><tbody>'+body+'</tbody></table></div>'


def pie(sheet):
    rows=[r for r in sheet['rows'] if float(r.get('Total Units',0))>0]
    total=sum(float(r['Total Units']) for r in rows)
    if not total:return '<p>No recorded units to chart.</p>'
    colors=['#17617D','#E87722','#237334','#11A4CF','#9B2793','#777777']
    paths=[];legend=[];angle=-math.pi/2
    for i,row in enumerate(rows):
        value=float(row['Total Units']);end=angle+2*math.pi*value/total;color=colors[i%len(colors)]
        label=f"{row['Group']}: {value:,.0f} units ({value/total:.1%})"
        if value==total:
            shape=f'<circle cx="160" cy="160" r="145" fill="{color}"><title>{text(label)}</title></circle>'
        else:
            x,y=160+145*math.cos(angle),160+145*math.sin(angle)
            ex,ey=160+145*math.cos(end),160+145*math.sin(end)
            shape=f'<path d="M160 160 L{x:.4f} {y:.4f} A145 145 0 {int(end-angle>math.pi)} 1 {ex:.4f} {ey:.4f} Z" fill="{color}"><title>{text(label)}</title></path>'
        paths.append(shape);legend.append(f'<li><span style="background:{color}"></span>{text(label)}</li>');angle=end
    return '<div class="chart"><svg viewBox="0 0 320 320" role="img" aria-label="'+text(sheet['sheet_name'])+'">'+''.join(paths)+'</svg><ul>'+''.join(legend)+'</ul></div>'


def write_activity_html(path, report, *, title='A.C.E. Inventory Activity Report', org_line='Resource Management Flight, Detachment 005'):
    p=report['presentation'];s=report['summary'];details=report['sheets'][1:]
    period=f"{report['start_date']} through {report['end_date']}"
    generated=datetime.now().astimezone().strftime('%B %d, %Y %I:%M %p %Z')
    nav='<nav><a href="#summary">Summary</a>'+''.join(f'<a href="#sheet{i}">{text(d["sheet_name"])}</a>' for i,d in enumerate(details,1))+'</nav>'
    cards=''.join('<div class="card"><span>'+text(k)+'</span><strong>'+text(v)+'</strong></div>' for k,v in p['metrics'])
    sections=[]
    for i,d in enumerate(details,1):
        sections.append(f'<section id="sheet{i}"><h2>{text(d["sheet_name"])}</h2>'+('<p>'+text(d['note'])+'</p>' if d.get('note') else '')+table(d['columns'],d['rows'])+(pie(d) if d.get('pie') else '')+'</section>')
    summary='<section id="summary"><div class="cards">'+cards+'</div><h2>BLUF</h2><p>'+text(p['bluf'])+'</p><h2>Daily Activity</h2>'+table(p['daily_columns'],p['daily_rows'])+'<h2>Major Activities</h2><p>'+text(p['major_activities'])+'</p><p class="note">Activity covers '+text(period)+'. Current inventory, loans and mapping coverage reflect the saved database at generation time. Stock adjustments include corrections and are not necessarily new receipts. Zero-stock placeholders are not physical inventory additions. Checkout counts are item transactions, not uniform sets or unique cadets. No activity is inferred for days without saved records.</p></section>'
    css='''body{margin:0;background:#f0f3f6;font:15px Arial,sans-serif;color:#16283d}header{background:#0c2340;color:white;padding:24px 30px}h1{margin:0 0 10px;font-size:28px}nav{display:flex;flex-wrap:wrap;gap:8px;padding:16px 30px;background:white;position:sticky;top:0;z-index:2;border-bottom:1px solid #ddd}a{color:#0c2340;padding:7px 10px;background:#eaf1f7;border-radius:4px;text-decoration:none}main{max-width:1300px;margin:auto;padding:20px}section{background:white;padding:24px;margin-bottom:20px;border-radius:7px;scroll-margin-top:150px}h2{margin-top:0;border-bottom:3px solid #e87722;padding-bottom:10px;font-size:21px}.cards{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:20px}.card{background:#eaf1f7;padding:16px;text-align:center}.card span{display:block;font-size:12px;text-transform:uppercase}.card strong{font-size:30px;display:block;margin-top:8px}p{line-height:1.6;white-space:pre-line}.note{font-size:13px;color:#526170}.scroll{overflow-x:auto}table{border-collapse:collapse;width:100%;font-size:13px}th{background:#0c2340;color:white;text-align:left;white-space:nowrap;padding:12px}td{padding:10px;vertical-align:top;min-width:105px;max-width:420px;white-space:pre-line;border-bottom:1px solid #ddd}tr:nth-child(even){background:#eaf1f7}.chart{display:flex;gap:24px;align-items:center;flex-wrap:wrap;margin-top:20px}.chart svg{width:340px;max-width:100%}.chart ul{list-style:none;padding:0}.chart li{margin:12px 0}.chart li span{display:inline-block;width:14px;height:14px;margin-right:8px}@media(max-width:650px){.cards{grid-template-columns:repeat(2,1fr)}main{padding:10px}section{padding:16px}}@media print{nav{display:none}body{background:white}section{break-before:page}.scroll{overflow:visible}table{font-size:9px}th,td{min-width:0;padding:4px;overflow-wrap:anywhere}thead{display:table-header-group}}'''
    doc='<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+text(title)+'</title><style>'+css+'</style><header><h1>'+text(title)+'</h1><div>'+text(org_line)+'</div><p>'+text(period)+'. Generated '+text(generated)+'.</p></header>'+nav+'<main>'+summary+''.join(sections)+'</main></html>'
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);path.write_text(doc,encoding='utf-8');return path
