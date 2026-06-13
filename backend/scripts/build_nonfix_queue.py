"""Очередь нефикс-облигаций для разбора по v1.3 (флоатеры + валютные).
Группирует по эмитенту (issuer_slug), помечает статус risk.md (есть/серый),
тянет КС-спред/рейтинг/цену/дюрацию/валюту. Пишет _worklog/nonfix_queue.json."""
import json, os, sys
from collections import defaultdict
from statistics import median
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.services.moex_bonds import issuer_slug
from app.db.session import SessionLocal
from app.models.bond import Bond

BASE=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ISS=os.path.join(BASE,'bond_issuers')

def has_md(slug): return bool(slug) and os.path.isfile(f'{ISS}/{slug}/risk.md')
def greyed(slug):
    p=f'{ISS}/{slug}/risk.md'
    if not (slug and os.path.isfile(p)): return None
    t=open(p,encoding='utf-8').read()
    return ('light:gray' in t or 'light: gray' in t or 'неприменим' in t or 'не строится' in t)

db=SessionLocal()
bonds=db.query(Bond).all(); db.close()
groups=defaultdict(list)
for b in bonds:
    if b.bond_type=='ofz': continue  # ОФЗ-флоатеры/линкеры не разбираем как кредит
    slug=issuer_slug(b.short_name) or issuer_slug(b.issuer_name)
    cur=(b.currency or 'SUR')
    is_val = cur not in ('SUR','RUB')
    is_fl = b.coupon_type=='floater'
    if not (is_fl or is_val): continue
    groups[slug].append(b)

def num(x):
    try: return float(x)
    except: return None

q=[]
for slug, bs in groups.items():
    if not slug: continue
    fl=[b for b in bs if b.coupon_type=='floater']
    val=[b for b in bs if (b.currency or 'SUR') not in ('SUR','RUB')]
    kind = 'both' if (fl and val) else ('floater' if fl else 'valuta')
    rep=sorted(bs, key=lambda b:-(1 if b.last_price else 0))[0]
    fl_sp=[b.floater_spread_bp for b in fl if b.floater_spread_bp is not None]
    durs=[b.duration_days for b in bs if b.duration_days]
    q.append({
        'slug':slug, 'issuer': rep.issuer_name or rep.short_name, 'kind':kind,
        'nbonds':len(bs), 'rating': rep.agency_rating, 'tier': rep.risk_tier,
        'defaulted': bool(rep.is_defaulted),
        'floater_spread_bp': int(median(fl_sp)) if fl_sp else None,
        'currencies': sorted({(b.currency or 'SUR') for b in val}),
        'rep_secid': rep.secid, 'last_price': num(rep.last_price), 'ytm': num(rep.ytm),
        'duration_years': round(median(durs)/365,1) if durs else None,
        'has_md': has_md(slug), 'greyed': greyed(slug),
    })
q.sort(key=lambda e:(e['has_md'] and not e['greyed'], -e['nbonds']))  # сначала без md и серые, крупные
json.dump(q, open(f'{ISS}/_worklog/nonfix_queue.json','w'), ensure_ascii=False, indent=2)
done=[e for e in q if e['has_md'] and not e['greyed']]
nfl=sum(1 for e in q if e['kind'] in ('floater','both'))
nval=sum(1 for e in q if e['kind'] in ('valuta','both'))
print('нефикс-эмитентов:', len(q), '| флоатеры:', nfl, '| валютные:', nval)
print('нужно разобрать (нет md или серый):', len(q)-len(done), '| готовых не-серых:', len(done))
print('первые 8 на разбор:')
for e in q[:8]: print(' ', e['slug'], e['kind'], 'r='+str(e['rating']), 'КС+'+str(e['floater_spread_bp']), e['currencies'] or '', 'md='+str(e['has_md']), 'grey='+str(e['greyed']), 'n='+str(e['nbonds']))
