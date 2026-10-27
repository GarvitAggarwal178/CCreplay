#!/usr/bin/env python3
"""Browser acceptance against a real normal-user Studio/API/worker.

Run after building and starting Studio. No mocked fetches or canned results.
Saved acceptance artifacts stay in ignored runtime/acceptance; owner files are
never removed by broad prefix. The lab's privileged acceptance is separate.
"""
import json
import os
from pathlib import Path
import sys
import time
import urllib.request
import urllib.error
from playwright.sync_api import sync_playwright,expect

BASE=sys.argv[1] if len(sys.argv)>1 else 'http://127.0.0.1:8000'
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'runtime/acceptance/browser'
OUT.mkdir(parents=True,exist_ok=True)


def http(path,body=None):
    req=urllib.request.Request(BASE+'/api'+path,data=json.dumps(body).encode() if body is not None else None,
                               headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=60) as r:return json.load(r)


def algorithm_demo(page):
    from playwright.sync_api import expect
    page.goto(BASE+'/#/algorithm-workbench')
    expect(page.get_by_role('heading',name='Same input. Two decisions.')).to_be_visible()
    page.wait_for_function("document.querySelectorAll('.cm-content')[0]?.innerText.includes('transition')")
    presets=http('/algorithm-workbench/presets')
    def run():
        with page.expect_response(lambda r:r.url.endswith('/api/algorithm-workbench/compare') and r.request.method=='POST') as response:
            page.get_by_role('button',name='2 · Run both algorithms',exact=True).click()
        jid=response.value.json()['id']
        expect(page.get_by_role('region',name='Computed comparison')).to_be_visible(timeout=130000)
        return jid,http('/experiments/'+jid)
    def index(i):
        page.get_by_role('spinbutton',name='Selected event index').fill(str(i))
    def outputs(a,b):
        expect(page.locator('.awb-decision').nth(0).locator('.awb-values strong').nth(0)).to_have_text(str(a))
        expect(page.locator('.awb-decision').nth(1).locator('.awb-values strong').nth(0)).to_have_text(str(b))
    jid,saved=run()
    print('PASS independent algorithms: actual default 12-event run',flush=True)
    result=saved['result']
    assert (result['compared_events'],result['disagreements'],result['first_difference'])==(12,5,1)
    page.get_by_role('button',name='Jump to first difference',exact=True).click();outputs(13,15)
    expect(page.get_by_text('Index 1 · seq 2 · cong_avoid',exact=True)).to_be_visible()
    page.get_by_role('button',name='Next',exact=True).focus();page.keyboard.press('Enter');outputs(19,22)
    page.get_by_role('button',name='Previous',exact=True).click();outputs(13,15)
    index(6);outputs(24,24)
    for i,value in enumerate([16,20]):
        expect(page.locator('.awb-decision').nth(i).locator('.awb-values strong').nth(1)).to_have_text(str(value))
    page.screenshot(path=str(OUT/'algorithm-threshold-1366.png'),full_page=True)
    assert not page.evaluate('document.documentElement.scrollWidth > window.innerWidth')
    files=page.locator('input[type=file]')
    files.nth(1).set_input_files(str(ROOT/'examples/algorithm_workbench/step_growth.py'))
    files.nth(2).set_input_files(str(ROOT/'examples/algorithm_workbench/batch_growth.py'))
    page.locator('.awb-source .cm-content').nth(1).fill(presets['source_b'].replace('increment = min(4, acked)','increment = 2'))
    expect(page.get_by_role('region',name='Computed comparison')).not_to_be_visible()
    edited,_=run();index(1);outputs(13,14)
    with page.expect_download() as exported:
        page.get_by_role('button',name='Export computed JSON',exact=True).click()
    exported.value.save_as(str(OUT/'algorithm-computed.json'))
    page.locator('.awb-source .cm-content').nth(1).fill(presets['source_a'])
    _,equal=run();assert equal['result']['disagreements']==0
    expect(page.get_by_role('button',name='Jump to first difference',exact=True)).to_be_disabled()
    page.locator('.awb-source .cm-content').nth(1).fill(presets['source_b'])
    page.get_by_label('Input source',exact=True).select_option('recording')
    page.get_by_label('Recording',exact=True).select_option('raw__r0__rep1')
    recorded,real=run();assert real['result']['disagreements']==29
    expect(page.locator('.awb-results')).to_contain_text('Connection window [0, 100) of 37260 events')
    before=len(http('/experiments'))
    page.reload();expect(page.get_by_role('region',name='Computed comparison')).to_be_visible()
    assert len(http('/experiments'))==before
    with page.expect_response(lambda r:'/rerun' in r.url and r.request.method=='POST') as response:
        page.get_by_role('button',name='Rerun saved inputs',exact=True).click()
    rerun=response.value.json()['id'];assert rerun!=recorded
    expect(page.get_by_role('region',name='Computed comparison')).to_be_visible(timeout=30000)
    assert http('/experiments/'+rerun)['result']==real['result']
    page.get_by_role('link',name='Runs',exact=True).first.click()
    link=page.locator(f'a[href="#/algorithm-workbench?job={recorded}"]')
    expect(link).to_be_visible();link.click()
    expect(page.get_by_role('region',name='Computed comparison')).to_be_visible()
    page.get_by_label('Input source',exact=True).select_option('scenario')
    page.get_by_text('Inspect or edit the supplied callback inputs',exact=True).click()
    text=page.get_by_label('Callback input JSON')
    text.fill('{')
    page.get_by_role('button',name='2 · Run both algorithms',exact=True).click()
    expect(page.get_by_role('alert')).to_be_visible()
    invalid=presets['scenario'];invalid['events'][0]['in_acked']=-1;text.fill(json.dumps(invalid))
    page.get_by_role('button',name='2 · Run both algorithms',exact=True).click()
    expect(page.get_by_role('alert')).to_contain_text('unsigned 32-bit')
    invalid['events'][0]['in_acked']=1;text.fill(json.dumps(invalid))
    for source,error in [('def broken(', 'SyntaxError'),('raise RuntimeError("browser intentional exception")','browser intentional exception')]:
        page.locator('.awb-source .cm-content').nth(0).fill(source)
        page.get_by_role('button',name='2 · Run both algorithms',exact=True).click()
        expect(page.get_by_role('alert')).to_contain_text(error,timeout=10000)
    page.locator('.awb-source .cm-content').nth(0).fill('while True: pass')
    with page.expect_response(lambda r:r.url.endswith('/api/algorithm-workbench/compare') and r.request.method=='POST') as response:
        page.get_by_role('button',name='2 · Run both algorithms',exact=True).click()
    hanging=response.value.json()['id']
    page.reload()
    expect(page.get_by_role('status')).to_contain_text('Executing',timeout=10000)
    expect(page.get_by_label('Input source',exact=True)).to_be_disabled()
    page.get_by_role('link',name='Controllers',exact=True).first.click()
    page.goto(BASE+'/#/algorithm-workbench?job='+hanging)
    expect(page.get_by_role('status')).to_be_visible()
    print('PASS independent algorithm browser demo: defaults, navigation, threshold semantics, imports/edit, equal sources, captured window, export/history/rerun, validation; waiting for real timeout',flush=True)
    expect(page.get_by_role('alert')).to_contain_text('timed out',timeout=130000)
    return hanging

def replace_editor(page, value):
    editor=page.locator('.cm-content')
    expect(editor).not_to_be_empty()
    editor.click()
    page.keyboard.press('Control+a')
    page.keyboard.insert_text(value)


def followup_demo(page):
    page.goto(BASE)
    page.get_by_role('link',name='Compare two imported algorithms',exact=False).click()
    expect(page.get_by_role('heading',name='Same input. Two decisions.')).to_be_visible()
    page.wait_for_function("document.querySelectorAll('.cm-content')[0]?.innerText.includes('transition')")
    page.get_by_text('Import interface & blank template',exact=True).click()
    with page.expect_download() as download:
        page.get_by_role('link',name='Download blank Python interface',exact=True).click()
    download.value.save_as(str(OUT/'downloaded-controller-template.py'))
    assert 'def transition' in (OUT/'downloaded-controller-template.py').read_text()
    page.get_by_label('Execution mode',exact=True).select_option('stateful')
    scenario=http('/algorithm-workbench/presets')['scenario']
    event=dict(scenario['events'][0],callback_id=2,in_acked=1,pre_is_cwnd_limited=1,pre_snd_cwnd=12)
    scenario['events']=[dict(event,seq=i+1) for i in range(8)]
    files=page.locator('input[type=file]')
    files.nth(0).set_input_files({'name':'controlled-state-history.json','mimeType':'application/json','buffer':json.dumps(scenario).encode()})
    files.nth(1).set_input_files(str(ROOT/'examples/algorithm_workbench/packet_credit.py'))
    files.nth(2).set_input_files(str(ROOT/'examples/algorithm_workbench/callback_credit.py'))
    expect(page.get_by_label('Algorithm A name',exact=True)).to_have_value('packet_credit.py')
    expect(page.get_by_label('Algorithm B name',exact=True)).to_have_value('callback_credit.py')
    def run():
        with page.expect_response(lambda r:r.url.endswith('/api/algorithm-workbench/compare') and r.request.method=='POST') as response:
            page.get_by_role('button',name='2 · Run both algorithms',exact=True).click()
        jid=response.value.json()['id']
        expect(page.get_by_role('region',name='Computed comparison')).to_be_visible(timeout=30000)
        return jid,http('/experiments/'+jid)
    jid,job=run();assert job['result']['first_difference']==2
    page.get_by_role('button',name='Jump to first difference').click()
    expect(page.locator('.awb-private').nth(0)).to_contain_text('ack_credit')
    expect(page.locator('.awb-private').nth(1)).to_contain_text('eligible_callbacks')
    expect(page.locator('.awb-private').nth(1)).to_contain_text('2')
    page.screenshot(path=str(OUT/'stateful-independent-imports.png'),full_page=True)
    assert not page.evaluate('document.documentElement.scrollWidth > window.innerWidth')
    page.reload();expect(page.get_by_role('region',name='Computed comparison')).to_be_visible()
    page.get_by_role('button',name='Rerun saved inputs',exact=True).click()
    expect(page.get_by_role('region',name='Computed comparison')).to_be_visible(timeout=30000)
    rerun=page.url.split('job=')[1];assert rerun!=jid and http('/experiments/'+rerun)['result']==job['result']
    with page.expect_download() as download:
        page.get_by_role('button',name='Export computed JSON',exact=True).click()
    download.value.save_as(str(OUT/'stateful-export.json'))
    assert json.loads((OUT/'stateful-export.json').read_text())['initialization_sha256']
    page.locator('input[type=file]').nth(2).set_input_files(str(ROOT/'examples/algorithm_workbench/packet_credit.py'))
    _,same=run();assert same['result']['disagreements']==0
    expect(page.get_by_role('button',name='Jump to first difference')).to_be_disabled()
    source=(ROOT/'examples/algorithm_workbench/packet_credit.py').read_text()
    page.locator('.awb-source .cm-content').nth(1).fill(source.replace('credit // 4','credit // 2').replace('credit %= 4','credit %= 2'))
    _,changed=run();assert changed['result']['rows'][1]['b']['post_snd_cwnd']==13
    page.locator('.awb-source .cm-content').nth(1).fill('def transition(e,s): return {}, s')
    page.get_by_role('button',name='2 · Run both algorithms',exact=True).click()
    expect(page.get_by_role('alert')).to_contain_text('ABI-v0',timeout=10000)
    page.locator('.awb-source .cm-content').nth(1).fill(source.replace("{'ack_credit': 0}","{'ack_credit': float('nan')}"))
    page.get_by_role('button',name='2 · Run both algorithms',exact=True).click()
    expect(page.get_by_role('alert')).to_contain_text('finite JSON',timeout=10000)
    page.locator('.awb-source .cm-content').nth(1).fill(source)
    page.get_by_label('Input source',exact=True).select_option('recording')
    page.get_by_label('Recording',exact=True).select_option('raw__r0__rep1')
    page.get_by_role('spinbutton',name='Start index',exact=True).fill('5')
    page.get_by_role('button',name='2 · Run both algorithms',exact=True).click()
    expect(page.get_by_role('alert')).to_contain_text('must start at index 0')
    page.get_by_label('Input source',exact=True).select_option('scenario')
    page.locator('.awb-source .cm-content').nth(0).fill('while True: pass')
    page.get_by_role('button',name='2 · Run both algorithms',exact=True).click()
    expect(page.get_by_role('button',name='Cancel execution',exact=True)).to_be_visible()
    page.get_by_role('button',name='Cancel execution',exact=True).click()
    expect(page.get_by_role('alert')).to_contain_text('cancelled',timeout=10000)
    print('PASS initialized independent imports, private PRE/POST, source names, template, reload/rerun/export, equal-source, edit, invalid states/interfaces, offset rejection, cancellation',flush=True)

    page.goto(BASE+'/#/controllers?from=cubic')
    expect(page.get_by_role('heading',name='Make a change you can inspect')).to_be_visible()
    page.wait_for_function("document.querySelector('.cm-content')?.innerText.includes('CUBIC')")
    def save(name):
        page.get_by_label('Revision name',exact=True).fill(name+str(int(time.time()*1000)))
        with page.expect_response(lambda r:r.url.endswith('/api/controllers/user') and r.request.method=='POST',timeout=90000) as response:
            page.get_by_role('button',name='Save source revision & validate',exact=True).click()
        data=response.value.json();assert data['validation']['ok'],data
        expect(page.get_by_role('heading',name='Interface and sample replay checks passed')).to_be_visible()
        return data['id']
    untouched=save('actual_source_noop_')
    def replay(cid):
        page.get_by_role('link',name='Replay',exact=True).click()
        page.get_by_role('combobox',name='Recording',exact=True).select_option('raw__cubic_replay__primary__rep1')
        page.get_by_role('combobox',name='Candidate',exact=True).select_option(cid)
        page.get_by_role('button',name='Run comparison',exact=True).click()
        expect(page.locator('.verdict')).to_be_visible(timeout=120000)
        sid=page.url.split('session=')[1].split('&')[0]
        return sid,http('/replay/sessions/'+sid)
    sid,clean=replay(untouched);assert clean['summary']['n_disagree']==0 and clean['summary']['n_events']==78688
    page.get_by_role('link',name='Open controller editor',exact=True).click()
    source=(ROOT/'user/cubic_model.py').read_text()+"\nfrom types import SimpleNamespace\nCONTROLLER = SimpleNamespace(**{key: globals()[key] for key in ('transition','INITIAL_PRIVATE_STATE','NONE_PRIVATE_STATE','COMPARISON_FIELDS','comparison_fields') if key in globals()})\n"
    injection="\n_original_transition = transition\ndef transition(event, state):\n    output, next_state = _original_transition(event, state)\n    if event['callback_id'] == 1:\n        output = dict(output)\n        output['result'] += 1\n    return output, next_state\n"
    replace_editor(page,source.replace('\nfrom types import SimpleNamespace',injection+'\nfrom types import SimpleNamespace'))
    edited=save('actual_source_plus_one_');_,bad=replay(edited)
    assert str(bad['summary']['first_difference']['seq'])=='1705'
    page.get_by_role('button',name='First difference',exact=True).click()
    expect(page.locator('.inspector .reference strong')).to_have_text('145')
    expect(page.locator('.inspector .candidate strong')).to_have_text('146')
    page.get_by_role('button',name='Reproduce from checkpoint',exact=True).click()
    expect(page.get_by_text('"values_and_private_state_verified": true',exact=False)).to_be_visible(timeout=90000)
    page.screenshot(path=str(OUT/'actual-source-editor-roundtrip.png'),full_page=True)
    page.get_by_role('link',name='Open controller editor',exact=True).click();replace_editor(page,source)
    fixed=save('actual_source_fixed_');_,clean=replay(fixed);assert clean['summary']['n_disagree']==0
    page.get_by_role('link',name='Network Lab',exact=True).click()
    page.get_by_label('Record callback boundary',exact=True).check()
    page.get_by_label('Live controller',exact=True).select_option('covegas')
    page.get_by_label('Record callback boundary',exact=True).uncheck()
    expect(page.get_by_label('Live controller',exact=True)).to_have_value('reno')
    print('PASS actual builtin source → editor → unchanged save → full Mode B → rule edit 145/146 → verified checkpoint → fix; CoVegas capture toggle reset',flush=True)

def main():
    """Core review workflows; never starts privileged live networking."""
    errors=[]; checks=[]
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True,args=['--no-sandbox'])
        page=browser.new_page(viewport={'width':1366,'height':768},accept_downloads=True)
        page.on('pageerror',lambda exc:errors.append(str(exc)))
        def layout(name):
            for width,height,zoom in [(1366,768,'1.25'),(1920,1080,'1')]:
                page.set_viewport_size({'width':width,'height':height})
                page.evaluate('(z)=>document.documentElement.style.zoom=z',zoom)
                assert not page.evaluate('document.documentElement.scrollWidth > window.innerWidth'),name
                page.screenshot(path=str(OUT/f'{name}-{width}.png'),full_page=True)
        for route,heading in [('/', 'Record TCP behavior. Compare controller code.'),('/lab','Run TCP through a controlled network'),('/recordings','Choose the evidence to inspect'),('/controllers','Make and validate a new controller revision'),('/replay','New controller comparison'),('/runs','Runs & Compare'),('/advanced','Advanced tools & evidence')]:
            page.goto(BASE+'/#'+route)
            expect(page.get_by_role('heading',name=heading,exact=True)).to_be_visible(timeout=30000)
            layout(route.strip('/') or 'start');checks.append('route '+route+' at both review sizes')
        for old,new in [('diff','replay'),('history','runs'),('traces','recordings')]:
            page.goto(BASE+'/#/'+old);page.wait_for_url('**/#/'+new);checks.append('redirect '+old)
        print('PASS all routes, redirects, both review viewports',flush=True)
        # Explicit empty-catalog UI test; not a measured-result fixture.
        page.route('**/api/traces',lambda route:route.fulfill(json=[]))
        page.goto(BASE+'/#/')
        expect(page.get_by_role('heading',name='No replayable recordings')).to_be_visible()
        page.goto(BASE+'/#/replay')
        expect(page.get_by_role('heading',name='No replayable recordings')).to_be_visible()
        checks.append('Start and Replay empty catalogs')
        page.unroute('**/api/traces')
        # Same-route navigation retains the mounted resource; restore the real catalog.
        page.reload()
        trace='raw__cubic_replay__primary__rep1'
        def run(candidate='cubic',mode='B'):
            page.goto(BASE+f'/#/replay?trace={trace}&candidate={candidate}&reference=cubic&mode={mode}')
            expect(page.get_by_role('button',name='Run comparison',exact=True)).to_be_enabled(timeout=30000)
            expect(page.get_by_role('combobox',name='Candidate',exact=True)).to_have_value(candidate)
            expect(page.get_by_role('combobox',name='Reference',exact=True)).to_have_value('cubic')
            with page.expect_response(lambda r:r.url.endswith('/api/replay/sessions') and r.request.method=='POST',timeout=30000) as created:
                page.get_by_role('button',name='Run comparison',exact=True).click()
            sid=created.value.json()['id']
            expect(page.get_by_role('heading',name='Behavior comparison',exact=True)).to_be_visible(timeout=180000)
            return sid,http('/replay/sessions/'+sid)
        sid,baseline=run()
        assert baseline['summary']['n_disagree']==0
        assert baseline['summary']['n_events']==78688
        checks.append('full-recording self comparison')
        failing,result=run('cubic_bug_ssthresh')
        assert result['summary']['comparison_profile_v1']['types']['return_value']==14
        expect(page.get_by_role('heading',name='Recorded seq 1705',exact=False)).to_be_visible(timeout=30000)
        expect(page.locator('.inspector .reference strong')).to_have_text('145')
        expect(page.locator('.inspector .candidate strong')).to_have_text('146')
        expect(page.locator('.source-code')).to_contain_text('+ 1')
        page.get_by_role('button',name='Next event',exact=False).click()
        expect(page.get_by_role('heading',name='Recorded seq 1706',exact=False)).to_be_visible()
        page.get_by_role('button',name='First difference',exact=True).click()
        page.get_by_text('Checkpoint reproduction',exact=True).click()
        page.get_by_role('button',name='Reproduce from checkpoint').click()
        expect(page.get_by_text('"values_and_private_state_verified": true',exact=False)).to_be_visible(timeout=120000)
        layout('replay');checks.append('seeded computed outputs, source, navigation and checkpoint')
        count=len(http('/replay/sessions'));page.reload()
        expect(page.get_by_role('heading',name='Recorded seq 1705',exact=False)).to_be_visible(timeout=30000)
        assert len(http('/replay/sessions'))==count
        with page.expect_download() as dl:page.get_by_role('link',name='Export',exact=True).click()
        dl.value.save_as(str(OUT/'saved-export.json'))
        assert json.loads((OUT/'saved-export.json').read_text())['id']==failing
        page.get_by_role('button',name='Use configuration for new comparison').click()
        expect(page.get_by_role('combobox',name='Candidate',exact=True)).to_have_value('cubic_bug_ssthresh')
        assert len(http('/replay/sessions'))==count
        checks.append('immutable refresh, export and cloned draft')
        print('PASS actual full-stream agreement, behavior summary, source, checkpoint, immutable refresh/export/draft',flush=True)
        page.goto(BASE+'/#/controllers')
        page.get_by_label('Revision name',exact=True).fill('browser_beta_'+str(time.time_ns()))
        page.get_by_label('BETA',exact=True).fill('819')
        with page.expect_response(lambda r:'/api/controllers/param' in r.url and r.request.method=='POST',timeout=90000) as response:
            page.get_by_role('button',name='Save parameter revision & validate').click()
        variant=response.value.json()['id']
        expect(page.get_by_role('link',name='Compare this revision',exact=True)).to_be_visible(timeout=90000)
        page.get_by_role('link',name='Compare this revision',exact=True).click()
        expect(page.get_by_role('combobox',name='Candidate',exact=True)).to_have_value(variant)
        beta,summary=run(variant)
        assert summary['summary']['first_difference']['seq']=='742'
        events=http(f'/replay/sessions/{beta}/events?differences_only=true&limit=100')['events']
        assert len(events)>25
        selected=events[60]['index']
        page.goto(BASE+f'/#/replay?session={beta}&event={selected}')
        expect(page.get_by_role('heading',name=f'Recorded seq {events[60]["seq"]}',exact=False)).to_be_visible(timeout=30000)
        page.get_by_label('Differences only',exact=True).check()
        expect(page.locator('.events .event-row[aria-pressed=true]')).to_be_visible()
        assert page.locator('.events .event-row').count()<=25
        page.get_by_role('button',name='Next difference',exact=True).click()
        expect(page.get_by_role('heading',name=f'Recorded seq {events[61]["seq"]}',exact=False)).to_be_visible()
        checks.append('validated parameter revision and anchored navigation beyond 25 differences')
        print('PASS validated BETA edit, private-state divergence, anchored navigation beyond 25 differences',flush=True)
        pending_templates=[]
        page.route('**/api/controllers/templates/cubic',lambda route:pending_templates.append(route))
        page.goto(BASE+'/#/controllers')
        page.get_by_role('button',name='Edit Python source',exact=True).click()
        expect(page.get_by_text('Loading controller source…',exact=True)).to_be_visible()
        expect(page.get_by_role('button',name='Save source revision & validate',exact=True)).to_be_disabled()
        expect(page.locator('.cm-content')).to_have_attribute('contenteditable','false')
        assert len(pending_templates)==1
        pending_templates[0].continue_()
        page.unroute('**/api/controllers/templates/cubic')
        checks.append('source editing and saving blocked until the real template loads')
        page.get_by_label('Revision name',exact=True).fill('browser_offset_'+str(time.time_ns()))
        template=urllib.request.urlopen(BASE+'/api/controllers/templates/cubic').read().decode()
        editor=page.locator('.cm-content').first
        expect(editor).to_have_attribute('contenteditable','true')
        expect(editor).to_contain_text('OFFSET = 0')
        edited=template.replace('OFFSET = 0','OFFSET = 1')
        editor.click();page.keyboard.press('ControlOrMeta+a');page.keyboard.insert_text(edited)
        with page.expect_response(lambda r:'/api/controllers/user' in r.url and r.request.method=='POST',timeout=90000) as response:
            page.get_by_role('button',name='Save source revision & validate').click()
        assert response.value.request.post_data_json['code']==edited
        custom=response.value.json()['id']
        expect(page.get_by_role('heading',name='Interface and sample replay checks passed')).to_be_visible(timeout=90000)
        custom_sid,_=run(custom)
        event=http(f'/replay/sessions/{custom_sid}/event/1704')
        assert (event['reference']['computed']['result'],event['candidate']['computed']['result'])==(145,144)
        checks.append('trusted source edit and actual 145/144 computation')
        _,mode_a=run('cubic_bug_ssthresh','A')
        page.get_by_text('Checkpoint reproduction',exact=True).click()
        expect(page.get_by_role('button',name='Reproduce from checkpoint')).to_be_disabled()
        page.goto(BASE+f'/#/replay?trace={trace}&reference=reno&candidate=cubic')
        expect(page.get_by_role('button',name='Run comparison',exact=True)).to_be_disabled()
        checks.append('Mode A checkpoint restriction and cross-ABI prevention')
        cap=http('/lab/capabilities')
        page.goto(BASE+'/#/lab')
        if not cap.get('can_run_lab'):
            expect(page.get_by_role('button',name='Start network run',exact=True)).to_be_disabled()
            page.get_by_text('Host setup & diagnostics',exact=True).click()
            if cap.get('api_uid')==0:
                expect(page.get_by_text('The root development override enables Studio, but does not enable lab-agent access.',exact=False)).to_be_visible()
            else:
                expect(page.locator('main code').filter(has_text='sudo bash scripts/start_lab_agent.sh').first).to_be_visible()
            expect(page.get_by_text('No experiment has started. No measured telemetry is available.',exact=True)).to_be_visible()
            checks.append('disconnected lab disabled with setup guidance')
        runs=http('/lab/runs')
        native=[r for r in runs if r['status']=='completed' and r['instrumentation']=='native-uninstrumented']
        if len(native)>=2:
            left,right=native[:2]
            page.goto(BASE+f'/#/runs?left={left["id"]}&right={right["id"]}')
            expect(page.get_by_role('heading',name='Measured outcomes')).to_be_visible(timeout=30000)
            expect(page.get_by_text('Loading all cursor-paged measurements…',exact=True)).not_to_be_visible(timeout=60000)
            for name in ['cwnd','Sampled smoothed RTT','Sampled ACKed-data rate','FIFO queue backlog']:
                page.get_by_role('button',name=name,exact=True).click()
            page.goto(BASE+f'/#/lab?clone={left["id"]}&baseline={left["id"]}')
            expect(page.get_by_label('Live controller',exact=True)).to_have_value('cubic' if left['config']['controller']=='reno' else 'reno')
            assert len(http('/lab/runs'))==len(runs)
            checks.append('saved native measurements and independent-run prefill')
            print('PASS saved actual native comparison, four metrics and independent prefill',flush=True)
        else:print('NOT VERIFIED measured native pair: no saved complete pair; no privileged runs started',flush=True)
        # Retain deeper sandbox regression as an explicitly requested optional rehearsal.
        if '--sandbox' in sys.argv:
            followup_demo(page);algorithm_demo(page)
        page.goto(BASE+'/#/');page.get_by_role('button',name='Toggle color theme').click();layout('dark-start')
        assert not errors,errors
        checks.append('dark theme, layout and no browser runtime errors')
        browser.close()
    print(f'PASS core browser review: {len(checks)} workflow checks; live networking requires separate owner qualification',flush=True)
    (OUT/'review-checks.json').write_text(json.dumps({'passed':checks,'browser_errors':errors},indent=2))
    return 0


if __name__=='__main__':sys.exit(main())
