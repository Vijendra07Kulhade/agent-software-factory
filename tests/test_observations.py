import os
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit
from test_integrations import Response, Transport
from factory.integrations import LangfuseClient, IntegrationError


class ObservationTests(unittest.TestCase):
    def test_v2_is_scoped_time_bounded_and_cursor_paginated(self):
        transport = Transport(Response({'data':[{'id':'span-1','traceId':'trace-1'}], 'meta':{'cursor':'next+page'}}),
                              Response({'data':[{'id':'span-2','traceId':'trace-1'}], 'meta':{'cursor':None}}))
        client = LangfuseClient('https://approved.example', approved_hosts={'approved.example'}, transport=transport)
        self.assertTrue(hasattr(client, 'fetch_observations'), 'v2 adapter missing')
        with patch.dict(os.environ, {'LANGFUSE_PUBLIC_KEY':'pub','LANGFUSE_SECRET_KEY':'secret'}):
            rows = client.fetch_observations('trace-1', start='2026-11-01T00:00:00Z', end='2026-11-02T00:00:00Z')
        self.assertEqual([row['id'] for row in rows], ['span-1', 'span-2'])
        first = parse_qs(urlsplit(transport.calls[0][0].full_url).query)
        second = parse_qs(urlsplit(transport.calls[1][0].full_url).query)
        self.assertEqual(first['traceId'], ['trace-1'])
        self.assertIn('fromStartTime', first)
        self.assertIn('toStartTime', first)
        self.assertEqual(second['cursor'], ['next+page'])
        self.assertNotIn('io', first['fields'][0].split(','))

    def test_incomplete_or_wrong_trace_response_is_not_returned(self):
        self.assertTrue(hasattr(LangfuseClient, 'fetch_observations'), 'v2 adapter missing')
        payloads = [{'data':[{'id':'span-1','traceId':'wrong'}], 'meta':{}},
                    {'data':[], 'meta':{'cursor':'more'}}, {'data':{},'meta':{}}]
        with patch.dict(os.environ, {'LANGFUSE_PUBLIC_KEY':'pub','LANGFUSE_SECRET_KEY':'secret'}):
            for data in payloads:
                client = LangfuseClient('https://approved.example', approved_hosts={'approved.example'}, transport=Transport(Response(data)))
                with self.assertRaises(IntegrationError):
                    client.fetch_observations('trace-1', start='2026-11-01T00:00:00Z', end='2026-11-02T00:00:00Z', max_pages=1)


if __name__ == '__main__': unittest.main()
