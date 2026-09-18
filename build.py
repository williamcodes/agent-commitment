import json, re, html, glob
def inline(s):
    s=html.escape(s,quote=False)
    s=re.sub(r'`([^`]+)`',r'<code>\1</code>',s); s=re.sub(r'\*\*(.+?)\*\*',r'<strong>\1</strong>',s)
    s=re.sub(r'\[([^\]]+)\]\(([^)]+)\)',r'<a href="\2">\1</a>',s); return s
def md(src):
    out=[]; lines=src.split('\n'); i=0
    while i<len(lines):
        l=lines[i]
        if not l.strip(): i+=1; continue
        m=re.match(r'^(#{1,3}) (.*)',l)
        if m: out.append(f'<h{len(m[1])}>{inline(m[2])}</h{len(m[1])}>'); i+=1; continue
        if l.startswith('|'):
            rows=[]
            while i<len(lines) and lines[i].startswith('|'): rows.append([c.strip() for c in lines[i].strip().strip('|').split('|')]); i+=1
            rows=[r for r in rows if not all(re.fullmatch(r':?-+:?',c) for c in r)]
            t='<table><thead><tr>'+''.join(f'<th>{inline(c)}</th>' for c in rows[0])+'</tr></thead><tbody>'
            for r in rows[1:]: t+='<tr>'+''.join(f'<td>{inline(c)}</td>' for c in r)+'</tr>'
            out.append('<div class="tbl">'+t+'</tbody></table></div>'); continue
        if re.match(r'^(- |\d+\. )',l):
            tag='ol' if l[0].isdigit() else 'ul'; items=[]
            while i<len(lines) and re.match(r'^(- |\d+\. )',lines[i]): items.append(re.sub(r'^(- |\d+\. )','',lines[i])); i+=1
            out.append(f'<{tag}>'+''.join(f'<li>{inline(x)}</li>' for x in items)+f'</{tag}>'); continue
        para=[]
        while i<len(lines) and lines[i].strip() and not re.match(r'^(#{1,3} |\||- |\d+\. )',lines[i]): para.append(lines[i]); i+=1
        out.append('<p>'+inline(' '.join(para))+'</p>')
    return '\n'.join(out)
def norm(s):
    m=re.match(r'^([a-z]{5})(?![a-z])',(s or '').strip().lower()); return m.group(1) if m else '(other)'
D=json.load(open('data.json'))
rows=['| Arm | Game | Final word | Forks | Forks matching | Different words | Ended |','|---|---|---|---|---|---|---|']
for d in D:
    ws=[norm(t['branch']) for t in d['turns']]; rec=json.load(open(f"results/{'default' if d['arm']=='carried' else 'stripped'}-{d['label'].split()[1]}.json"))
    ended='board full' if rec['stop_reason']=='solved' else 'letters ran out'
    rows.append(f"| {d['arm']} | {d['label'].split()[1]} | {d['final']} | {len(ws)} | {sum(w==d['final'] for w in ws)} | {len(set(ws))} | {ended} |")
appendix=open('appendix.md').read().replace('{{GAMES}}','\n'.join(rows))
tpl=open('template.html').read()
page=tpl.replace('{{SUMMARY}}',md(open('summary.md').read())).replace('{{APPENDIX}}',md(appendix)).replace('{{DATA}}',json.dumps(D))
open('index.html','w').write(page); print('built index.html', len(page))
