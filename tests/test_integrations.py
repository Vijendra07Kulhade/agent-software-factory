"""Local contract tests; no real-service verification or credentials."""
import base64
import importlib
import io
import json
import os
import tempfile
import unittest
from unittest.mock import patch


class Response(io.BytesIO):
    def __init__(self, payload, status=200):
        super().__init__(payload if isinstance(payload, bytes) else json.dumps(payload).encode())
        self.status = status


class Transport:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, request, *, timeout):
        self.calls.append((request, timeout))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class IntegrationTests(unittest.TestCase):
    def module(self):
        try:
            return importlib.import_module('factory.integrations')
        except ModuleNotFoundError:
            self.fail('integration module is not implemented')

    def test_looker_saved_look_login_form_and_auth_schemes(self):
        m = self.module()
        row = {'agent': 'helper', 'skill': 'lookup', 'environment': 'prod', 'release': 'r1', 'tenant_id': 't1', 'window_start': '2026-11-01T00:00:00Z', 'window_end': '2026-11-02T00:00:00Z', 'score_name': 'quality', 'evaluator_version': 'v1', 'score': 0.75, 'count': 4, 'message': 'private'}
        for scheme in ('token', 'Bearer'):
            transport = Transport(Response({'access_token': 'access-secret', 'token_type': 'Bearer', 'expires_in': 3600}), Response([row]))
            with patch.dict(os.environ, {'LOOKER_CLIENT_ID': 'client+id', 'LOOKER_CLIENT_SECRET': 'secret&value'}):
                client = m.LookerClient('https://approved.example', approved_hosts={'approved.example'}, transport=transport, auth_scheme=scheme)
                result = client.run_look('42')
            self.assertEqual(result, [{**{k: v for k, v in row.items() if k != 'message'}, 'source': 'looker'}])
            login, _ = transport.calls[0]
            fetch, _ = transport.calls[1]
            self.assertEqual(login.full_url, 'https://approved.example/api/4.0/login')
            self.assertEqual(login.get_method(), 'POST')
            self.assertEqual(login.data, b'client_id=client%2Bid&client_secret=secret%26value')
            self.assertEqual(login.get_header('Content-type'), 'application/x-www-form-urlencoded')
            self.assertIsNone(login.get_header('Authorization'))
            self.assertEqual(fetch.full_url, 'https://approved.example/api/4.0/looks/42/run/json')
            self.assertEqual(fetch.get_method(), 'GET')
            self.assertEqual(fetch.get_header('Authorization'), scheme + ' access-secret')
        for look_id in ('../42', '42?sql=DROP', 42, '', '0', '01'):
            with self.assertRaises(m.IntegrationError):
                client.run_look(look_id)

    def test_allowlisted_normalization_never_copies_raw_text(self):
        m = self.module()
        raw = {'id': 'trace-1', 'timestamp': '2026-11-01T00:00:00Z', 'environment': 'prod', 'release': 'r1', 'input': 'secret', 'output': 'secret', 'metadata': {'agent': 'helper', 'skill': 'lookup', 'tenant_id': 't1', 'password': 'secret', 'deployment': 'd1'}, 'scores': [{'name': 'quality', 'value': 0.5, 'comment': 'secret'}]}
        normalized = m.sanitize_record(raw, source='langfuse')
        self.assertEqual(normalized, {'source': 'langfuse', 'trace_id': 'trace-1', 'timestamp': '2026-11-01T00:00:00Z', 'environment': 'prod', 'release': 'r1', 'agent': 'helper', 'skill': 'lookup', 'tenant_id': 't1', 'deployment': 'd1'})
        self.assertNotIn('secret', json.dumps(normalized))
        for field, value in [('agent', {'nested': 'secret'}), ('agent', 'private conversation'), ('score', float('nan')), ('count', True), ('count', -1), ('timestamp', 'not-a-date')]:
            with self.subTest(field=field), self.assertRaises(m.IntegrationError):
                m.sanitize_record({field: value}, source='logs')
        with self.assertRaises(m.IntegrationError):
            m.sanitize_record([], source='logs')

    def test_bounded_transport_errors_schema_and_no_redirects(self):
        m = self.module()
        for response in (Response(b'x' * 65), Response({'id': 'wrong'}), Response([]), Response(b'bad secret'), Response({}, 302), TimeoutError('secret'), Response({'id': 'trace-1'}, 500)):
            transport = Transport(response)
            with patch.dict(os.environ, {'LANGFUSE_PUBLIC_KEY': 'pub', 'LANGFUSE_SECRET_KEY': 'secret'}):
                client = m.LangfuseClient('https://approved.example', approved_hosts={'approved.example'}, transport=transport, max_response_bytes=64, timeout=2)
                with self.assertRaises(m.IntegrationError) as caught:
                    client.fetch_trace('trace-1')
            self.assertNotIn('secret', str(caught.exception))
            self.assertEqual(transport.calls[0][1], 2)
        request = m.Request('https://approved.example', headers={'Authorization': 'secret'})
        for status in (301, 302, 303, 307, 308):
            with self.assertRaises(m.IntegrationError):
                m._RejectRedirects().redirect_request(request, None, status, '', {}, 'https://evil.example')
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(m.IntegrationError):
                m.LangfuseClient('https://approved.example', approved_hosts={'approved.example'}, transport=Transport()).fetch_trace('x')
        for kwargs in ({'timeout': 0}, {'timeout': float('nan')}, {'max_response_bytes': 0}):
            with self.assertRaises(m.IntegrationError):
                m.LangfuseClient('https://approved.example', approved_hosts={'approved.example'}, **kwargs)

    def test_reject_unapproved_urls_and_unsafe_ids(self):
        m = self.module()
        for url in ('http://approved.example', 'https://evil.example', 'https://user:pw@approved.example', 'https://approved.example?x=1', 'https://approved.example#x', 'https://approved.example/a/../b', 'https://approved.example/%2fprivate', 'https://approved.example:444'):
            with self.subTest(url=url), self.assertRaises(m.IntegrationError):
                m.LangfuseClient(url, approved_hosts={'approved.example'})
        transport = Transport()
        client = m.LangfuseClient('https://approved.example', approved_hosts={'approved.example'}, transport=transport)
        for token in ('../escape', 'a/b', 'a?x', 'a%2fb', '', 'a\\nb', 12):
            with self.subTest(token=token), self.assertRaises(m.IntegrationError):
                client.fetch_trace(token)
        self.assertEqual(transport.calls, [])

    def test_explicit_trace_basic_auth_and_raw_memory(self):
        m = self.module()
        raw = {'id': 'trace-1', 'input': 'private conversation', 'metadata': {'tenant_id': 't1'}}
        transport = Transport(Response(raw))
        with patch.dict(os.environ, {'LANGFUSE_PUBLIC_KEY': 'public', 'LANGFUSE_SECRET_KEY': 'secret'}):
            client = m.LangfuseClient('https://approved.example/prefix', approved_hosts={'approved.example'}, transport=transport)
            self.assertEqual(client.fetch_trace('trace-1'), raw)
        request, timeout = transport.calls[0]
        self.assertEqual(request.full_url, 'https://approved.example/prefix/api/public/traces/trace-1')
        self.assertEqual(request.get_method(), 'GET')
        self.assertEqual(request.get_header('Authorization'), 'Basic ' + base64.b64encode(b'public:secret').decode())
        self.assertEqual(timeout, 10)


if __name__ == '__main__':
    unittest.main()
