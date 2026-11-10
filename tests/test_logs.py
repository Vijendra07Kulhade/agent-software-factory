import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from test_integrations import Response, Transport
from factory import integrations as m


class LogTests(unittest.TestCase):
    def test_bounded_scoped_log_export(self):
        self.assertTrue(hasattr(m, 'read_log_export'), 'log export adapter missing')
        base = {'trace_id': 'trace-1', 'tenant_id': 'tenant-a', 'deployment': 'v1',
                'timestamp': '2026-11-01T00:30:00Z', 'event_code': 'timeout',
                'message': 'DO NOT EXPORT THIS PRIVATE TEXT'}
        rows = [base, dict(base, tenant_id='tenant-b'), dict(base, trace_id='trace-2'),
                dict(base, deployment='v2'), dict(base, timestamp='2026-11-01T01:00:00Z')]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'logs.jsonl'
            path.write_text(''.join(json.dumps(r) + '\n' for r in rows))
            kwargs = dict(tenant_id='tenant-a', trace_ids={'trace-1'}, deployment='v1',
                          start='2026-11-01T00:00:00Z', end='2026-11-01T01:00:00Z')
            result = m.read_log_export(path, **kwargs)
            self.assertEqual(len(result), 1)
            self.assertNotIn('message', result[0])
            self.assertNotIn('PRIVATE', json.dumps(result))
            for limits in ({'max_bytes': 1}, {'max_lines': 1}):
                with self.assertRaises(m.IntegrationError):
                    m.read_log_export(path, **kwargs, **limits)
            path.write_text('{bad json}\n')
            with self.assertRaises(m.IntegrationError):
                m.read_log_export(path, **kwargs)

    def test_looker_malformed_auth_and_result_fail_closed(self):
        for login, rows in [([], []), ({}, []), ({'access_token': 'x\nsecret'}, []),
                            ({'access_token': 'okay'}, {}), ({'access_token': 'okay'}, [5])]:
            with self.subTest(login=login, rows=rows):
                transport = Transport(Response(login), Response(rows))
                with patch.dict(os.environ, {'LOOKER_CLIENT_ID': 'id', 'LOOKER_CLIENT_SECRET': 'secret'}):
                    client = m.LookerClient('https://approved.example', approved_hosts={'approved.example'}, transport=transport)
                    with self.assertRaises(m.IntegrationError):
                        client.run_look('42')
        with self.assertRaises(m.IntegrationError):
            m.LookerClient('https://approved.example', approved_hosts={'approved.example'}, auth_scheme='bad\nheader')


if __name__ == '__main__':
    unittest.main()
