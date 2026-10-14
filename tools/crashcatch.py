"""Attach the exception tracer (ktrace.py, kill breakpoints only) to every test-bed trek.exe as soon as it
starts, so crashes before the observer runs (lobby, loading a save) are caught too.
usage: crashcatch.py <logdir>   (stops when <logdir>/catch.stop exists; detaches the tracers then)
One log per process: <logdir>/catch_<inst>_<pid>.log"""
import os, subprocess, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
TEST = os.environ.get('BOTF_TEST', os.path.join(HERE, '..', 'test'))

def procs():
    out = subprocess.run(['powershell', '-NoProfile', '-Command',
                          "Get-CimInstance Win32_Process -Filter \"Name='trek.exe'\" | ForEach-Object { \"$($_.ProcessId) $($_.ExecutablePath)\" }"],
                         capture_output=True, text=True).stdout
    res = {}
    for line in out.splitlines():
        pid, _, path = line.strip().partition(' ')
        inst = os.path.basename(os.path.dirname(path))
        if pid.isdigit() and os.path.normcase(os.path.dirname(os.path.dirname(path))) == os.path.normcase(os.path.abspath(TEST)):
            res[int(pid)] = inst
    return res

def main():
    out = sys.argv[1]; os.makedirs(out, exist_ok=True)
    stopf = os.path.join(out, 'catch.stop')
    if os.path.exists(stopf): os.remove(stopf)
    env = dict(os.environ, TRACER_STOP=stopf, ONLY2='1', LOADTRACE='1', LOADQUIET='1')
    env.pop('HEAPTRACE', None)
    seen = {}
    while not os.path.exists(stopf):
        for pid, inst in procs().items():
            if pid not in seen:
                seen[pid] = subprocess.Popen([sys.executable, '-I', '-u', os.path.join(HERE, 'ktrace.py'), str(pid), '86400'],
                                             stdout=open(os.path.join(out, 'catch_%s_%d.log' % (inst, pid)), 'a'),
                                             stderr=subprocess.STDOUT, env=env)
                print(time.strftime('%H:%M:%S'), 'attached', inst, pid); sys.stdout.flush()
        time.sleep(1)
    for p in seen.values():
        try: p.wait(15)
        except Exception: pass

if __name__ == '__main__':
    main()
