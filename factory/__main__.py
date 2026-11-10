"""Offline reference factory. No production credentials or network are used."""
import argparse
import json
from pathlib import Path
from factory.core import REPO_ROOT, LAB_ROOT, SCENARIOS, run_incident, verify_bundle


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    demo = commands.add_parser('demo', help='Run an explicitly synthetic scenario')
    demo.add_argument('--scenario', choices=SCENARIOS, required=True)
    demo.add_argument('--out', type=Path, required=True, help='New output directory; never overwritten')
    triage = commands.add_parser('triage', help='Triage a normalized synthetic incident JSON')
    triage.add_argument('--incident', type=Path, required=True)
    triage.add_argument('--out', type=Path, required=True)
    verify = commands.add_parser('verify', help='Independently reproduce a bundled scenario and compare artifacts')
    verify.add_argument('--bundle', type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == 'verify':
            report = verify_bundle(LAB_ROOT, args.bundle)
            output = {'verified': True, 'status': report['status'], 'fingerprint': report['fingerprint']}
        else:
            incident = (REPO_ROOT / 'examples/incidents' / (args.scenario + '.json')
                        if args.command == 'demo' else args.incident)
            report = run_incident(LAB_ROOT if args.command == 'demo' else REPO_ROOT, incident, args.out)
            output = {k: report[k] for k in ('fixture_mode', 'status', 'fingerprint', 'changed_paths')}
            output['bundle'] = str(args.out.resolve())
        print(json.dumps(output, indent=2))
        return 0
    except (ValueError, OSError, KeyError, TypeError, AttributeError):
        parser.exit(2, 'Factory refused input: check schema, evidence, new output path, and bundle integrity.\n')


if __name__ == '__main__':
    raise SystemExit(main())
