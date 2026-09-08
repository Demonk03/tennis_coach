"""Disposable local UI preview. In-memory data and deterministic AI; never contacts production services."""
import os
import sys
from pathlib import Path
from datetime import datetime, timezone
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ['API_KEY'] = 'preview-key'
os.environ['DASHBOARD_ORIGIN'] = 'http://127.0.0.1:8770'
import app
import db
import gpt

now = lambda: datetime.now(timezone.utc).isoformat()
rows = {'matches': [], 'match_prep': [], 'match_events': [], 'match_reviews': [], 'match_context_updates': [], 'opponent_dossiers': []}
operations = {}
db.get_client = lambda: (_ for _ in ()).throw(RuntimeError("External DB disabled in preview"))
profile = {'level': 'Клубный 3.5', 'experience': 'Несколько лет', 'playing_style': 'С задней линии', 'strengths': 'Форхенд'}
plan = {'opponent_cue': 'Проверь, как соперник отвечает на глубокий мяч.', 'tactics': ['Первая подача без риска.', 'Высокий мяч под бэкхэнд.', 'Короткий на середину — закрывай.'], 'body': 'Начни спокойно, оцени ноги после двух геймов.', 'reset': 'Отвернись → выдох → выбери цель.', 'focus': 'Играю с запасом', 'technical': 'Играю с запасом', 'mental': 'Следующий мяч'}
for i in range(7):
    mid = str(uuid4())
    rows['matches'].append({'id': mid, 'match_date': f'2026-09-{i+1:02}', 'created_at': now(), 'status': 'completed', 'opponent_name': 'andrey_k', 'opponent_level': 'равный', 'opponent_style': 'Много слайсов', 'surface': 'hard', 'match_type': 'singles', 'session_type': 'friendly', 'session_duration': '1h', 'session_format': '1h_session', 'final_score': '6-4 6-3' if i%2 else '4-6 3-6'})
    rows['match_reviews'].append({'id':str(uuid4()),'match_id':mid,'created_at':now(),'physical_rating':3,'mental_rating':4,'opponent_style':'Много слайсов','opponent_what_worked':'Высоко под бэкхэнд','opponent_errors':'Низкие резаные','generated_technical_summary':'Глубокий мяч помогал вернуть инициативу.','generated_mental_summary':'После ошибки помогал короткий выдох.','app_helpful':i%2==0})

def read_all(table, filters=None):
    return [dict(r) for r in rows[table] if all(r.get(k)==v for k,v in (filters or {}).items())]
def one(table, **filters):
    return next(iter(read_all(table, filters)), None)
def claim(key, kind, mid, body_hash):
    old=operations.get(key)
    if old and old['body_hash']!=body_hash:return {'status':'conflict'}
    if old and old['status']=='succeeded':return old
    token=str(uuid4());operations[key]={'status':'pending','token':token,'body_hash':body_hash,'kind':kind,'match_id':mid,'lease_until':'2099-01-01T00:00:00+00:00'}
    return {'status':'claimed','token':token}
def commit(key, token, data):
    op=operations[key];mid=op['match_id'];kind=op['kind']
    if kind.startswith('prep_'):
        if kind=='prep_create':
            mid=str(uuid4());m={**data['match'],'id':mid,'status':'preparing','created_at':now(),'match_date':'2026-09-08'};rows['matches'].append(m)
            p={**data['prep'],'id':str(uuid4()),'match_id':mid,'revision':1,'match_context_snapshot':data['match']};rows['match_prep'].append(p)
        else:
            m=next(r for r in rows['matches'] if r['id']==mid);p=next(r for r in rows['match_prep'] if r['match_id']==mid)
            m.update(data['match']);p.update(data['prep']);p['revision']+=1;p['match_context_snapshot']=data['match']
        result={'match':m.copy(),'prep':p.copy(),'events':[],'review':None}
    elif kind=='event':
        ev={**data,'id':str(uuid4()),'match_id':mid,'idempotency_key':key,'created_at':now()};rows['match_events'].append(ev);result={'event':ev,'advice':ev['generated_advice']}
    elif kind=='finish':
        m=next(r for r in rows['matches'] if r['id']==mid);m.update(status='completed',final_score=data['final_score']);result={'match':m.copy()}
    elif kind=='review':
        review=one('match_reviews',match_id=mid)
        if not review:review={**data,'id':str(uuid4()),'match_id':mid,'created_at':now()};rows['match_reviews'].append(review)
        result={'review':review}
    elif kind=='dossier_refresh':
        rows['opponent_dossiers'][:]=[r for r in rows['opponent_dossiers'] if r['opponent_name']!=data['opponent_name']]
        rows['opponent_dossiers'].append({**data,'updated_at':now()});result={'summary':data['summary']}
    op.update(status='succeeded',result=result);return result

def start(mid, revision):
    m=next(r for r in rows['matches'] if r['id']==mid);m['status']='in_progress';return {'match':m.copy()}
def cancel(mid):
    m=next(r for r in rows['matches'] if r['id']==mid);m['status']='cancelled';return m.copy()

db.read_all=read_all;db.get_match=lambda mid:one('matches',id=mid);db.get_prep_for_match=lambda mid:one('match_prep',match_id=mid);db.get_events_for_match=lambda mid:read_all('match_events',{'match_id':mid});db.get_review_for_match=lambda mid:one('match_reviews',match_id=mid)
db.get_active_match=lambda:next((r.copy() for r in rows['matches'] if r['status'] in ('preparing','in_progress')),None)
db.get_player_profile=lambda:profile;db.save_player_profile=lambda data:profile.update(data) or profile;db.get_recent_reviews=lambda limit=3:rows['match_reviews'][-limit:]
db.renew_operation=lambda *args:True;db.claim_operation=claim;db.commit_operation=commit;db.get_operation=lambda key:operations.get(key);db.fail_operation=lambda key,token,error:operations[key].update(status='failed',error=error);db.start_match_v2=start;db.cancel_match=cancel;db.dossier_cache=lambda name:one('opponent_dossiers',opponent_name=name)
gpt.generate_prep_brief=lambda *args:plan.copy();gpt.generate_changeover_advice=lambda *args:'С его слайса не атакуй. Поднимай мяч выше и глубже — дай себе время вернуться в позицию.';gpt.generate_new_set_advice=lambda *args:'Начни сет с глубины и запаса над сеткой. На первой подаче снизь риск. Между розыгрышами выдохни и выбери одну цель. Сохрани силы для длинных геймов.'
gpt.generate_post_match_review=lambda *args:{'technical':'Глубокий мяч помогал вернуть инициативу. В следующем матче начни с этого.','mental':'Короткий выдох помогал возвращаться к следующему мячу.'}
gpt.generate_opponent_dossier=lambda sources, **kwargs:{'style':{'text':'Часто играет слайсом. По последним записям стиль стабилен.','match_ids':[sources[0]['match_id']]},'what_worked':{'text':'Высокий глубокий мяч под бэкхэнд.','match_ids':[sources[0]['match_id']]},'errors':{'text':'Ошибается на низких резаных.','match_ids':[sources[-1]['match_id']]}}
if __name__=='__main__': app.app.run(host='127.0.0.1',port=8771)
