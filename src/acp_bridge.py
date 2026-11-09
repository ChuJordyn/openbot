"""JSON-RPC relay; credentials and model I/O continue through the official Grok CLI."""
import json
import os
import pathlib
import select
import subprocess
import sys
import time
from bridge_policy import Policy

def main():
    policy=Policy()
    process=subprocess.Popen(sys.argv[1:],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=None)
    buffers={sys.stdin.fileno():b'',process.stdout.fileno():b''}
    audit=pathlib.Path(__file__).with_name('bridge-metrics.json')
    def write(stream,message):
        stream.write((json.dumps(message,ensure_ascii=False)+'\n').encode());stream.flush()
    try:
        while process.poll() is None:
            ready,_,_=select.select(list(buffers),[],[],1)
            for fd in ready:
                data=os.read(fd,65536)
                if not data:
                    return
                buffers[fd]+=data
                while b'\n' in buffers[fd]:
                    line,buffers[fd]=buffers[fd].split(b'\n',1)
                    if not line.strip():continue
                    try:message=json.loads(line)
                    except ValueError:
                        if fd==process.stdout.fileno():sys.stdout.buffer.write(line+b'\n');sys.stdout.buffer.flush()
                        continue
                    if fd==sys.stdin.fileno():
                        outgoing,synthetic=policy.transform(message)
                        if synthetic is not None:write(sys.stdout.buffer,synthetic)
                        if outgoing is not None:write(process.stdin,outgoing)
                    else:
                        policy.observe(message)
                        write(sys.stdout.buffer,message)
                    # Metrics contain counts only, never prompts, replies, auth data or tokens.
                    temporary=audit.with_suffix('.tmp.'+str(os.getpid()))
                    temporary.write_text(json.dumps({'updatedAt':time.time(),**policy.stats}))
                    temporary.chmod(0o600)
                    os.replace(temporary,audit)
    finally:
        process.terminate()
        try:process.wait(timeout=5)
        except subprocess.TimeoutExpired:process.kill();process.wait()

if __name__=='__main__':
    main()
