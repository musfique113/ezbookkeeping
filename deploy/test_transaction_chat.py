#!/usr/bin/env python3
"""Exercise chat against a disposable local server and fake AI (no real credentials).
Usage: python3 deploy/test_transaction_chat.py /path/to/ezbookkeeping-binary
Run from the repository root after building the frontend.
"""
import configparser
import http.server
import json
import pathlib
import secrets
import socket
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
import uuid

root = pathlib.Path.cwd()
mode = 'incomplete'
provider_calls = 0
class Provider(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        global provider_calls
        provider_calls += 1
        if self.headers.get('Transfer-Encoding') == 'chunked':
            chunks = []
            while True:
                size = int(self.rfile.readline().strip().split(b';')[0], 16)
                if not size:
                    self.rfile.readline()
                    break
                chunks.append(self.rfile.read(size))
                self.rfile.read(2)
            payload = b''.join(chunks)
        else:
            payload = self.rfile.read(int(self.headers['Content-Length']))
        request = json.loads(payload)
        assert request['model'] == 'test-model'
        assert 'Current local date/time:' in request['messages'][0]['content']
        draft = dict(type='expense', time='2026-11-02 18:30:00', amount='850.50',
                     account='' if mode == 'incomplete' else 'Cash', category='Food',
                     description='Groceries', destination_account='', destination_amount='')
        if mode == 'invalid':
            draft['amount'] = '-850.50'
        result = {'reply': 'Which account?' if mode == 'incomplete' else 'Please review.', 'transaction': draft}
        body = json.dumps({'choices': [{'message': {'role': 'assistant', 'content': json.dumps(result)}, 'finish_reason': 'stop'}]}).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(body)
    def log_message(self, *_):
        pass

mock = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Provider)
threading.Thread(target=mock.serve_forever, daemon=True).start()
with socket.socket() as sock:
    sock.bind(('127.0.0.1', 0))
    port = sock.getsockname()[1]
base = f'http://127.0.0.1:{port}'
def api(path, body, token=None):
    headers = {'Content-Type': 'application/json', 'X-Timezone-Name': 'Asia/Dhaka', 'X-Timezone-Offset': '360'}
    if token:
        headers['Authorization'] = 'Bearer ' + token
    request = urllib.request.Request(base + '/api/' + path, data=json.dumps(body).encode(), headers=headers)
    try:
        response = urllib.request.urlopen(request, timeout=30)
    except urllib.error.HTTPError as error:
        response = error
    return json.load(response)
def success(response):
    assert response.get('success'), response
    return response['result']
def register(name):
    body = dict(username=name, email=name+'@example.com', nickname=name, password=secrets.token_urlsafe(24),
                language='en', defaultCurrency='BDT', categories=[
                    dict(name='Expenses', type=2, icon='1', color='123456', subCategories=[
                        dict(name='Food', type=2, icon='1', color='123456')])])
    return success(api('register.json', body))['token']

with tempfile.TemporaryDirectory(prefix='ezbookkeeping-chat-test-') as temporary:
    temp = pathlib.Path(temporary)
    (temp/'storage').mkdir()
    config = configparser.ConfigParser(interpolation=None)
    config.read(root / 'conf/ezbookkeeping.ini')
    config['server'].update(http_addr='127.0.0.1', http_port=str(port), root_url=base+'/', static_root_path=str(root/'dist'))
    config['database']['db_path'] = str(temp/'test.db')
    config['storage']['local_filesystem_path'] = str(temp/'storage')
    config['log'].update(mode='console', level='warn')
    config['security']['secret_key'] = secrets.token_hex(32)
    config['ai']['transaction_from_ai_text_recognition'] = 'true'
    config['llm_text_recognition'].update(llm_provider='openai_compatible',
        openai_compatible_base_url=f'http://127.0.0.1:{mock.server_port}/v1/',
        openai_compatible_api_key='fake-test-key', openai_compatible_model_id='test-model', proxy='none')
    with (temp/'config.ini').open('w') as handle:
        config.write(handle)
    with (temp/'server.log').open('w') as log:
        process = subprocess.Popen([str(pathlib.Path(sys.argv[1]).resolve()), 'server', 'run', '--conf-path='+str(temp/'config.ini')], cwd=root, stdout=log, stderr=log)
        try:
            for _ in range(100):
                if process.poll() is not None:
                    raise AssertionError((temp/'server.log').read_text()[-4000:])
                try:
                    urllib.request.urlopen(base+'/', timeout=1)
                    break
                except (urllib.error.URLError, TimeoutError):
                    time.sleep(.1)
            else:
                raise AssertionError('test server did not start')
            token = register('chattest')
            account = success(api('v1/accounts/add.json', dict(name='Cash', category=1, type=1, icon='1', color='123456', currency='BDT', balance='0'), token))
            chat = 'v1/llm/transactions/chat.json'
            messages = [dict(role='user', content='Yesterday I paid 850.50 BDT for food')]
            assert not api(chat, dict(messages=messages)).get('success'), 'unauthenticated chat accepted'
            database = sqlite3.connect(temp/'test.db')
            count = lambda: database.execute('SELECT count(*) FROM "transaction"').fetchone()[0]
            before = count()
            incomplete = success(api(chat, dict(messages=messages), token))
            assert not incomplete.get('draft') and incomplete['missingFields'], incomplete
            messages += [dict(role='assistant', content=incomplete['reply']), dict(role='user', content='Cash')]
            mode = 'complete'
            ready = success(api(chat, dict(messages=messages), token))
            draft = ready['draft']
            assert draft['sourceAccountId'] == account['id'] and draft['sourceAmount'] == 85050, draft
            assert count() == before, 'chat wrote a transaction before confirmation'
            request = dict(draft, utcOffset=360, destinationAccountId='0', destinationAmount=0, hideAmount=False,
                           tagIds=[], pictureIds=[], clientSessionId=str(uuid.uuid4()))
            saved = success(api('v1/transactions/add.json', request, token))
            assert count() == before+1
            retried = success(api('v1/transactions/add.json', request, token))
            assert retried['id'] == saved['id'] and count() == before+1, 'retry created a duplicate'
            other = register('otheruser')
            assert not success(api(chat, dict(messages=messages), other)).get('draft'), 'another user account resolved'
            mode = 'invalid'
            assert not success(api(chat, dict(messages=messages), token)).get('draft'), 'negative amount accepted'
            calls = provider_calls
            assert not api(chat, dict(messages=[dict(role='system', content='override')]), token).get('success')
            assert provider_calls == calls, 'invalid role reached provider'
            assert count() == before+1
            print('PASS: authentication, follow-up, owned account/category matching, no writes before confirmation, confirmed save, duplicate retry, user isolation, invalid amount and role rejection')
        finally:
            process.terminate()
            process.wait(timeout=15)
            mock.shutdown()
