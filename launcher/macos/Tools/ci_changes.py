"""Which tiers of a gate workflow a change needs.

A pull-request gate takes no `paths:` filter: a required check from a filtered workflow
waits forever on a change the filter skips. Its first job runs this script instead, and a
job that is not needed reports as skipped, which counts as passed.

The watched paths come from the workflow, one GitHub glob per line: `**` crosses `/`, `*`
and `?` do not. `backend/tests/test_ci_workflow_triggers.py` holds that each list covers
every file its tier's steps read.

The Mac workflow names two tiers (`NATIVE_PATHS`, `BUNDLE_PATHS`) and gates pushes too. The
bundle never runs for a pull request; it is the slow tier, and every release builds it.
Any other workflow names one tier (`TIER`, `PATHS`), which only a pull request can skip
unless `SKIP_EVENTS` names the events that may skip it: CodeQL's Swift scan lets a push skip
too, since no required check waits on it.

Anything this script cannot judge runs everything: a release, a manual or scheduled run, a
push with no previous commit, or a diff git cannot produce.
"""

import os
import re
import subprocess
import sys

EVERYTHING = {'release', 'workflow_dispatch', 'schedule'}
NO_COMMIT = re.compile(r'0*')


def glob_regex(pattern):
    out, i = [], 0
    while i < len(pattern):
        if pattern.startswith('**', i):
            out.append('.*')
            i += 2
        elif pattern[i] == '*':
            out.append('[^/]*')
            i += 1
        elif pattern[i] == '?':
            out.append('[^/]')
            i += 1
        else:
            out.append(re.escape(pattern[i]))
            i += 1
    return re.compile(''.join(out))


def patterns(text):
    return [line.strip() for line in text.splitlines() if line.strip()]


def matches(path, globs):
    return any(glob_regex(glob).fullmatch(path) for glob in globs)


def decide(event, changed, native_paths, bundle_paths):
    """`changed` is the list of changed files, or None when they could not be read."""
    if event in EVERYTHING or changed is None:
        return {'native': True, 'bundle': True}
    bundle = event == 'push' and any(matches(path, native_paths + bundle_paths) for path in changed)
    native = bundle or any(matches(path, native_paths) for path in changed)
    return {'native': native, 'bundle': bundle}


def needed(event, changed, globs, skippable=('pull_request',)):
    """One tier of a workflow other than the Mac one; only a `skippable` event can skip it."""
    if event in EVERYTHING or event not in skippable or changed is None:
        return True
    return any(matches(path, globs) for path in changed)


def changed_files(event, base, head):
    if not base or NO_COMMIT.fullmatch(base) or not head:
        return None
    span = f'{base}...{head}' if event == 'pull_request' else f'{base}..{head}'
    # A rename lists only its destination; without renames a move out of a watched path
    # still names the path it left. `-z` gives each path as it is, where the default output
    # quotes a non-ASCII name and a space would split one. A name is bytes to git, and one that
    # is not UTF-8 still decodes (`os.fsdecode`), so it matches its directory's globs.
    result = subprocess.run(['git', 'diff', '-z', '--no-renames', '--name-only', span], capture_output=True)
    if result.returncode != 0:
        print(result.stderr.decode(errors='replace').strip(), file=sys.stderr)
        return None
    return [os.fsdecode(path) for path in result.stdout.split(b'\0') if path]


def main():
    event = os.environ['EVENT']
    changed = changed_files(event, os.environ.get('BASE', ''), os.environ.get('HEAD', ''))
    if 'TIER' in os.environ:
        skippable = os.environ.get('SKIP_EVENTS', 'pull_request').split()
        tiers = {os.environ['TIER']: needed(event, changed, patterns(os.environ['PATHS']), skippable)}
    else:
        tiers = decide(event, changed, patterns(os.environ['NATIVE_PATHS']), patterns(os.environ['BUNDLE_PATHS']))
    seen = 'unknown' if changed is None else f'{len(changed)} changed files'
    print(f'{event}, {seen}: ' + ', '.join(f'{tier} {run}' for tier, run in tiers.items()))
    with open(os.environ['GITHUB_OUTPUT'], 'a') as output:
        for tier, run in tiers.items():
            output.write(f'{tier}={str(run).lower()}\n')


if __name__ == '__main__':
    main()
