"""Bounded evidence adapters; Python 3.11 stdlib, no SDK dependencies.

Official contracts consulted:
https://langfuse.com/docs/api-and-data-platform/features/public-api
https://langfuse.com/faq/all/deprecated-api-migration
https://docs.cloud.google.com/looker/docs/reference/looker-api/latest/methods/ApiAuth/login
https://docs.cloud.google.com/looker/docs/reference/looker-api/latest/methods/Look/run_look

Explicit trace retrieval uses the requested legacy trace endpoint, NOT a v2
replacement. Verify deployment support: official migration docs deprecate
this read endpoint. No automatic broad-query fallback.
"""
import base64
import json
import os
import re
from urllib.parse import urlsplit, urlencode
from datetime import datetime
import math
from urllib.request import Request, HTTPRedirectHandler, ProxyHandler, build_opener


class IntegrationError(ValueError):
    """Safe, static messages only; never attach response bodies or secrets."""


def _token(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', value):
        raise IntegrationError('invalid identifier')
    return value


def _base_url(value, approved_hosts):
    try:
        parts = urlsplit(value)
        valid = (parts.scheme == 'https' and parts.hostname in approved_hosts
                 and parts.port in (None, 443) and not parts.username and not parts.password
                 and not parts.query and not parts.fragment and '?' not in value and '#' not in value
                 and not any(c.isspace() for c in value)
                 and re.fullmatch(r'(/[A-Za-z0-9_-]+)*/?', parts.path) is not None)
    except (ValueError, TypeError):
        valid = False
    if not valid:
        raise IntegrationError('unapproved base URL')
    return value.rstrip('/')


class _RejectRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise IntegrationError('redirect rejected')


def _credential(name):
    value = os.environ.get(name)
    if not value or any(ord(c) < 32 for c in value):
        raise IntegrationError('missing or invalid credentials')
    return value


def _positive(value, maximum):
    return type(value) in (int, float) and math.isfinite(value) and 0 < value <= maximum


class _Client:
    def __init__(self, base_url, *, approved_hosts, transport=None, timeout=10,
                 max_response_bytes=2_000_000):
        self.base_url = _base_url(base_url, approved_hosts)
        if not _positive(timeout, 120) or type(max_response_bytes) is not int or not _positive(max_response_bytes, 20_000_000):
            raise IntegrationError('invalid resource limits')
        self.timeout = timeout
        self.max_response_bytes = max_response_bytes
        # No ambient proxies and no redirects: credentials stay on approved origin.
        self.transport = transport or build_opener(ProxyHandler({}), _RejectRedirects()).open

    def _request(self, path, *, headers, data=None):
        try:
            request = Request(self.base_url + path, headers=headers, data=data)
            with self.transport(request, timeout=self.timeout) as response:
                if response.status != 200:
                    raise IntegrationError('request rejected')
                body = response.read(self.max_response_bytes + 1)
                if len(body) > self.max_response_bytes:
                    raise IntegrationError('response too large')
            return json.loads(body)
        except IntegrationError:
            raise
        except Exception:
            # Do not echo HTTP bodies, request URLs, headers or transport messages.
            raise IntegrationError('request failed') from None


_DIMENSIONS = ('trace_id', 'tenant_id', 'agent', 'skill', 'environment', 'release',
               'deployment', 'score_name', 'evaluator_version', 'event_code', 'level')
_TIMES = ('timestamp', 'window_start', 'window_end')


def _timestamp(value):
    try:
        if not isinstance(value, str) or len(value) > 40:
            raise ValueError
        result = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if result.tzinfo is None:
            raise ValueError
        return result
    except ValueError:
        raise IntegrationError('invalid timestamp') from None


def sanitize_record(record, *, source):
    """Return a flat allowlist, NOT a core incident schema or RCA conclusion.

    Allowed identifiers are bounded machine labels, not free text. Unknown fields,
    scores arrays, input/output, messages and unknown metadata are discarded.
    Langfuse metadata may supply dimensions; top-level values take precedence.
    Operators must never store secrets in allowed dimension fields. This is a
    schema boundary, not a general-purpose secret detector.
    """
    if not isinstance(record, dict) or source not in ('langfuse', 'looker', 'logs'):
        raise IntegrationError('invalid evidence record')
    values = dict(record)
    if source == 'langfuse':
        metadata = record.get('metadata', {})
        if not isinstance(metadata, dict):
            raise IntegrationError('invalid metadata')
        values = {**{k: metadata[k] for k in _DIMENSIONS if k in metadata}, **values}
        if 'id' in record:
            values['trace_id'] = record['id']
    result = {'source': source}
    for key in _DIMENSIONS:
        if key in values:
            value = values[key]
            if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_.:@/-]{1,128}', value):
                raise IntegrationError('invalid dimension')
            result[key] = value
    for key in _TIMES:
        if key in values:
            _timestamp(values[key])
            result[key] = values[key]
    if 'score' in values:
        score = values['score']
        if type(score) not in (int, float) or not math.isfinite(score):
            raise IntegrationError('invalid score')
        result['score'] = score
    if 'count' in values:
        count = values['count']
        if type(count) is not int or count < 0:
            raise IntegrationError('invalid count')
        result['count'] = count
    return result


class LangfuseClient(_Client):
    """Operator-configured origin; fetch_trace returns sensitive raw data in memory."""

    def fetch_observations(self, trace_id, *, start, end, max_pages=5, max_records=1000):
        """v2 observations for one trace/time window; raw rows stay in memory.

        Does not request input/output fields. Rejects incomplete pagination and
        duplicate/cross-trace rows instead of silently returning partial evidence.
        """
        _token(trace_id)
        if _timestamp(start) >= _timestamp(end) or type(max_pages) is not int or not 1 <= max_pages <= 20 or type(max_records) is not int or not 1 <= max_records <= 10_000:
            raise IntegrationError('invalid observation bounds')
        auth = base64.b64encode((_credential('LANGFUSE_PUBLIC_KEY') + ':' + _credential('LANGFUSE_SECRET_KEY')).encode()).decode()
        params = {'traceId':trace_id, 'fromStartTime':start, 'toStartTime':end,
                  'fields':'core,basic,trace_context', 'limit':min(100, max_records)}
        result, seen_ids, seen_cursors = [], set(), set()
        for _ in range(max_pages):
            page = self._request('/api/public/v2/observations?' + urlencode(params),
                                 headers={'Authorization':'Basic ' + auth})
            if not isinstance(page, dict) or not isinstance(page.get('data'), list) or not isinstance(page.get('meta'), dict):
                raise IntegrationError('invalid observation page')
            for row in page['data']:
                if not isinstance(row, dict) or row.get('traceId') != trace_id:
                    raise IntegrationError('observation trace mismatch')
                identifier = _token(row.get('id'))
                if identifier in seen_ids:
                    raise IntegrationError('duplicate observation')
                seen_ids.add(identifier)
                result.append(row)
                if len(result) > max_records:
                    raise IntegrationError('observation limit exceeded')
            cursor = page['meta'].get('cursor')
            if cursor is None or cursor == '':
                return result
            if not isinstance(cursor, str) or len(cursor) > 4096 or cursor in seen_cursors:
                raise IntegrationError('invalid observation cursor')
            seen_cursors.add(cursor)
            params['cursor'] = cursor
        raise IntegrationError('incomplete observation pagination')

    def fetch_trace(self, trace_id):
        _token(trace_id)
        credentials = _credential('LANGFUSE_PUBLIC_KEY') + ':' + _credential('LANGFUSE_SECRET_KEY')
        auth = base64.b64encode(credentials.encode()).decode()
        result = self._request('/api/public/traces/' + trace_id,
                               headers={'Authorization': 'Basic ' + auth})
        if not isinstance(result, dict) or result.get('id') != trace_id:
            raise IntegrationError('invalid trace response')
        return result


class LookerClient(_Client):
    """Run a pre-created Look; no SQL, query edits, scheduling or dashboard writes.

    login creates an auth token (the sole POST). Official Looker login docs require
    literal ``token`` authorization, not ``Bearer``. Explicit auth_scheme='Bearer'
    is available ONLY for operator-verified compatible deployments/proxies.
    Each run logs in afresh; credentials and tokens are never persisted or logged.
    """

    def __init__(self, base_url, *, approved_hosts, auth_scheme='token', **kwargs):
        super().__init__(base_url, approved_hosts=approved_hosts, **kwargs)
        if auth_scheme not in ('token', 'Bearer'):
            raise IntegrationError('unsupported authorization scheme')
        self.auth_scheme = auth_scheme

    def run_look(self, look_id):
        if not isinstance(look_id, str) or not re.fullmatch(r'[1-9][0-9]{0,17}', look_id):
            raise IntegrationError('invalid Look identifier')
        body = urlencode({'client_id': _credential('LOOKER_CLIENT_ID'),
                          'client_secret': _credential('LOOKER_CLIENT_SECRET')}).encode()
        login = self._request('/api/4.0/login',
                              headers={'Content-Type': 'application/x-www-form-urlencoded'}, data=body)
        token = login.get('access_token') if isinstance(login, dict) else None
        if not isinstance(token, str) or not re.fullmatch(r'[A-Za-z0-9._~+/=-]{1,4096}', token):
            raise IntegrationError('invalid authentication response')
        rows = self._request('/api/4.0/looks/' + look_id + '/run/json',
                             headers={'Authorization': self.auth_scheme + ' ' + token})
        if not isinstance(rows, list) or len(rows) > 10_000:
            raise IntegrationError('invalid Look result')
        return [sanitize_record(row, source='looker') for row in rows]


def read_log_export(path, *, tenant_id, trace_ids, deployment, start, end,
                    max_bytes=2_000_000, max_lines=10_000):
    """Read an operator-selected JSONL export, never SSH or execute log text.

    Reject truncation rather than returning an apparently complete partial result.
    The interval is start-inclusive, end-exclusive. Unknown fields are discarded.
    """
    from pathlib import Path
    import stat
    _token(tenant_id)
    _token(deployment)
    if not isinstance(trace_ids, (set, list, tuple)) or not 1 <= len(trace_ids) <= 100:
        raise IntegrationError('invalid trace scope')
    trace_ids = {_token(value) for value in trace_ids}
    lower, upper = _timestamp(start), _timestamp(end)
    if lower >= upper or type(max_bytes) is not int or not 0 < max_bytes <= 20_000_000 or type(max_lines) is not int or not 0 < max_lines <= 100_000:
        raise IntegrationError('invalid log bounds')
    try:
        path = Path(path)
        if path.is_symlink() or not stat.S_ISREG(path.stat().st_mode):
            raise IntegrationError('invalid log export')
        with path.open('rb') as handle:
            payload = handle.read(max_bytes + 1)
        if len(payload) > max_bytes:
            raise IntegrationError('log export too large')
        lines = payload.decode('utf-8').splitlines()
        if len(lines) > max_lines:
            raise IntegrationError('log line limit exceeded')
        result = []
        for line in lines:
            row = json.loads(line)
            if not isinstance(row, dict):
                raise IntegrationError('invalid log record')
            if (row.get('tenant_id') != tenant_id or row.get('trace_id') not in trace_ids
                    or row.get('deployment') != deployment):
                continue
            when = _timestamp(row.get('timestamp'))
            if lower <= when < upper:
                result.append(sanitize_record(row, source='logs'))
        return result
    except IntegrationError:
        raise
    except (OSError, ValueError, TypeError):
        raise IntegrationError('invalid log export') from None

