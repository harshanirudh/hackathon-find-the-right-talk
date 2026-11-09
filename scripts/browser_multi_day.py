"""Focused three-day UI acceptance. Default mocked; CHECK_LIVE_CONFERENCE=1 opts into one real extraction."""
import json
import os
from pathlib import Path
from urllib.parse import urlparse
from playwright.sync_api import expect, sync_playwright

BASE = os.getenv('APP_URL', 'http://127.0.0.1:8000').rstrip('/')
OUT = Path(__file__).resolve().parents[1] / 'artifacts'
PROMPT = ('Day 1: Kubernetes and security, all experience levels, maximum 2 sessions. '
          'Day 2: observability and tracing, all experience levels, maximum 2 sessions. '
          'Day 3: platform engineering, all experience levels, maximum 2 sessions.')
DATES = ['2026-11-10', '2026-11-11', '2026-11-12']


def mock_talk(identifier, day, hour):
    return {'id':identifier, 'title':f'Example {identifier}', 'speaker':'Test Speaker', 'track':'Security',
            'level':'beginner', 'description':'Indexed conference session', 'tags':['kubernetes'],
            'start':f'{day}T{hour}:00:00-07:00', 'end':f'{day}T{hour}:30:00-07:00',
            'room':'Test room', 'accessibility':{'captioned':True}, 'reason':'Matches this day’s interests; no clash.'}


def run_mock():
    records = {t['id']:t for t in [mock_talk('a',DATES[0],'10'),mock_talk('b',DATES[0],'11'),
                                    mock_talk('c',DATES[1],'10'),mock_talk('d',DATES[1],'11'),mock_talk('e',DATES[2],'10')]}
    day_ids = [['a','b'],['c','d'],['e']]
    results = [{'day':day,'day_number':index+1,'status':'ok','error':None,'talks':[records[i] for i in day_ids[index]],
                'total':len(day_ids[index]),'interests':['kubernetes security','observability','platform engineering'][index],
                'effective_level':['beginner','intermediate'] if index == 0 else None,'max_talks':2,'source':'elasticsearch',
                'mode':'keyword' if index != 1 else 'hybrid','degraded_reason':None,'selection_note':'','clashes':[]}
               for index,day in enumerate(DATES)]
    response = {'days':results,'interpretation_source':'openai','model':'mock-test','extraction_calls':1}
    plans, held, calls, writes = {}, {}, [], []

    def send(route, body):
        route.fulfill(content_type='application/json', body=json.dumps(body))

    def api(route):
        request = route.request; path = urlparse(request.url).path
        body = request.post_data_json if request.method in ('POST','PUT') else {}
        if path == '/api/build-conference':
            calls.append(body)
            assert body['mode'] == 'auto'
            if body['interests'] == 'slow': held['build'] = route
            elif body['interests'] == 'mixedfailures':
                send(route,{**response,'days':[results[0],{**results[1],'talks':[],'total':0,'status':'error','source':'unavailable','mode':'none','error':'Retrieval unavailable'},
                                                {**results[2],'talks':[],'total':0,'status':'empty','source':'not_queried','mode':'none','selection_note':'No preferences were specified for this day.'}]})
            else: send(route,response)
        elif path == '/api/plans' and request.method == 'POST':
            identifier=f'plan-{len(plans)+1}'
            assert all(records[i]['start'].startswith(body['day']) for i in body['talk_ids'])
            record={**body,'id':identifier,'talks':[records[i] for i in body['talk_ids']],'talk_count':len(body['talk_ids']),'source':'elasticsearch'}
            plans[identifier]=record; writes.append(('POST',identifier,body))
            if body['name'].startswith('Delayed'): held['save']=(route,record)
            else: send(route,record)
        elif path == '/api/plans': send(route,{'plans':list(plans.values()),'source':'elasticsearch'})
        elif path.startswith('/api/plans/'):
            identifier=path.rsplit('/',1)[1]
            if request.method == 'PUT':
                writes.append(('PUT',identifier,body))
                plans[identifier].update({**body,'talks':[records[i] for i in body['talk_ids']]})
            send(route,plans[identifier])
        elif path == '/api/agenda':
            send(route,{'talks':[records[i] for i in body['talk_ids']],'clashes':[],'alternatives':{},'day':body['day'],'source':'elasticsearch'})
        else: raise AssertionError(f'Unexpected API request: {path}')

    with sync_playwright() as p:
        browser=p.chromium.launch(channel='chromium');page=browser.new_page(viewport={'width':1440,'height':1000})
        page.set_default_timeout(10000);page.route('**/api/**',api)
        errors=[];page.on('pageerror',lambda e:errors.append(str(e)));page.goto(BASE)
        page.locator('#interests').fill(PROMPT)
        expect(page.locator('#plan-scope')).to_have_value('conference')
        expect(page.locator('#interests')).to_have_attribute('maxlength','2000')
        page.locator('#build-button').click()
        expect(page.locator('[data-conference-day]')).to_have_count(3)
        assert len(calls)==1
        for day in DATES: expect(page.locator(f'#conference-{day} .agenda-item').first).to_be_visible()
        expect(page.locator(f'#conference-{DATES[0]} .daily-preferences')).to_contain_text('beginner + intermediate')
        expect(page.locator(f'#conference-{DATES[1]} .daily-source')).to_contain_text('Hybrid')
        before = page.locator(f'#conference-{DATES[1]} .agenda-item').count()
        page.locator('[data-conference-remove="a"]').click()
        expect(page.locator(f'#conference-{DATES[0]} .agenda-item')).to_have_count(1)
        expect(page.locator(f'#conference-{DATES[1]} .agenda-item')).to_have_count(before)
        for day in DATES:
            page.locator(f'[data-day-save="{day}"] button').click()
            expect(page.locator(f'#conference-{day} .daily-save-status')).to_contain_text('Saved in Elasticsearch')
        assert len([w for w in writes if w[0]=='POST'])==3
        assert {w[2]['day'] for w in writes}==set(DATES)
        page.locator('#saved-library').evaluate('el => el.open = true')
        page.locator('[data-load-plan="plan-2"]').click()
        expect(page.locator('[data-conference-day]')).to_have_count(3)
        expect(page.locator(f'#conference-{DATES[1]} .daily-preferences')).to_contain_text('Saved daily plan')
        expect(page.locator(f'#conference-{DATES[0]} .agenda-item')).to_have_count(1)
        page.screenshot(path=str(OUT/'conference-mocked-desktop.png'),full_page=True)
        page.set_viewport_size({'width':390,'height':844})
        page.evaluate('new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))')
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        page.screenshot(path=str(OUT/'conference-mocked-mobile.png'),full_page=False)
        page.set_viewport_size({'width':1440,'height':1000})

        def build(text):
            page.locator('#request-editor').evaluate('el => el.open = true')
            page.locator('#interests').fill(text);page.locator('#build-button').click()
        build('mixedfailures')
        expect(page.locator(f'#conference-{DATES[1]} .daily-source')).to_have_text('Retrieval unavailable')
        expect(page.locator(f'#conference-{DATES[2]} .daily-source')).to_have_text('Not queried')
        expect(page.locator(f'#conference-{DATES[0]} .agenda-item')).to_have_count(2)
        build('slow')
        page.locator('[data-conference-remove="a"]').click()
        send(held.pop('build'),response)
        expect(page.locator('#notice')).to_contain_text('Your current choices were kept')
        expect(page.locator(f'#conference-{DATES[0]} .agenda-item')).to_have_count(1)
        expect(page.locator(f'#conference-{DATES[1]} .daily-source')).to_have_text('Retrieval unavailable')
        build(PROMPT)
        expect(page.locator(f'#conference-{DATES[0]} .agenda-item')).to_have_count(2)
        name=page.locator(f'[data-day-name="{DATES[0]}"]')
        name.fill('Delayed current daily draft')
        page.locator(f'[data-day-save="{DATES[0]}"] button').click()
        page.locator('[data-conference-remove="a"]').click()
        page.locator(f'[data-day-name="{DATES[0]}"]').fill('Newer daily edits')
        old_route,record=held.pop('save');send(old_route,record)
        expect(page.locator(f'[data-day-save="{DATES[0]}"] button')).to_have_text('Save changes')
        expect(page.locator(f'#conference-{DATES[0]} .daily-save-status')).to_contain_text('Unsaved changes')
        post_count=len([w for w in writes if w[0]=='POST'])
        page.locator(f'[data-day-save="{DATES[0]}"] button').click()
        expect(page.locator(f'#conference-{DATES[0]} .daily-save-status')).to_contain_text('Saved in Elasticsearch')
        assert writes[-1][0:2]==('PUT',record['id'])
        assert len([w for w in writes if w[0]=='POST'])==post_count
        assert not errors,errors
        browser.close()
    print('PASS: mocked one conference request,3dated sections,independent removes/daily saves/reopen,isolated empty/error,stale request guard,daily-save identity,mobile')


def run_live():
    from multi_day_smoke import EXAMPLE
    with sync_playwright() as p:
        browser=p.chromium.launch(channel='chromium');page=browser.new_page(viewport={'width':1440,'height':1000})
        page.set_default_timeout(120000);page.goto(BASE)
        errors=[];page.on('pageerror',lambda e:errors.append(str(e)));created=[]
        try:
            page.locator('#interests').fill(EXAMPLE)
            with page.expect_response('**/api/build-conference') as pending: page.locator('#build-button').click()
            data=pending.value.json()
            assert pending.value.status==200 and data['extraction_calls']==1 and data['interpretation_source']=='openai',data
            expect(page.locator('[data-conference-day]')).to_have_count(3)
            for day in data['days']:
                assert day['source']=='elasticsearch' and day['talks'], {k:day.get(k) for k in ('day','status','source','error','selection_note')}
                assert all(t['start'].startswith(day['day']) for t in day['talks'])
                node=page.locator(f'#conference-{day["day"]}')
                expect(node.locator('.agenda-item')).to_have_count(len(day['talks']))
                node.locator('[data-day-name]').fill(f'Browser conference {day["day"]}')
                with page.expect_response(lambda response: response.url.endswith('/api/plans') and response.request.method=='POST') as saved:
                    node.locator('[data-day-save] button').click()
                assert saved.value.status==200
                record=saved.value.json();created.append(record['id'])
                assert record['day']==day['day']
                expect(node.locator('.daily-save-status')).to_contain_text('Saved in Elasticsearch')
            page.locator('#saved-library').evaluate('el => el.open = true')
            page.locator(f'[data-load-plan="{created[1]}"]').click()
            expect(page.locator(f'#conference-{DATES[1]} .daily-preferences')).to_contain_text('Saved daily plan')
            expect(page.locator('[data-conference-day]')).to_have_count(3)
            page.locator('#dismiss-notice').click()
            page.screenshot(path=str(OUT/'conference-live-desktop.png'),full_page=True)
            page.set_viewport_size({'width':390,'height':844})
            page.evaluate('new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))')
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            page.screenshot(path=str(OUT/'conference-live-mobile.png'),full_page=False)
            assert not errors,errors
            print('PASS: live one OpenAI extraction,3Elasticsearch dated results,3separate daily saves,reopen day2 without losing others,mobile')
        finally:
            key=page.evaluate("localStorage.getItem('righttalk-planner-key')")
            for identifier in created:
                response=page.request.delete(f'{BASE}/api/plans/{identifier}',headers={'X-Planner-Key':key})
                assert response.status==200,'Test daily-plan cleanup failed'
            browser.close()


if __name__=='__main__':
    OUT.mkdir(exist_ok=True)
    run_live() if os.getenv('CHECK_LIVE_CONFERENCE')=='1' else run_mock()
