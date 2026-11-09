import json,os,pathlib,select,subprocess,sys,time
from test_policy import prompt,reply
root=pathlib.Path(__file__).resolve().parents[1]
p=subprocess.Popen([sys.executable,str(root/'src/acp_bridge.py'),sys.executable,str(pathlib.Path(__file__).with_name('fake_cli.py'))],stdin=subprocess.PIPE,stdout=subprocess.PIPE,env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'})
buf=b''
def request(message):
    global buf
    p.stdin.write((json.dumps(message)+'\n').encode());p.stdin.flush()
    deadline=time.monotonic()+8;events=[]
    while time.monotonic()<deadline:
        if b'\n' not in buf:
            if select.select([p.stdout],[],[],1)[0]:buf+=os.read(p.stdout.fileno(),65536)
            continue
        line,buf=buf.split(b'\n',1);d=json.loads(line)
        if d.get('id')==message['id']:return d,events
        events.append(d)
    raise TimeoutError(message['method'])
try:
    r,_=request({'id':90,'method':'initialize','params':{'protocolVersion':1}});assert r['result']['protocolVersion']==1
    r,_=request({'id':91,'method':'session/new','params':{'cwd':'/test','mcpServers':[{'name':'openbot'},{'name':'computer_use'}]}});assert r['result']['seenServers']==['openbot']
    r,events=request(prompt('请叫 execute 跟我 say hi。'));assert r['result']['promptsSeen']==1 and events
    r,events=request(reply());assert r['result']['stopReason']=='end_turn' and not events and r['result']['_meta']['usage']['modelCalls']==0
    r,_=request({'id':92,'method':'_x.ai/auth/info','params':{}});assert r['result']=={'authenticated':True,'promptsSeen':1}
    r,events=request(reply(parent='other-request',status='blocked',result='需要登录'));assert r['result']['promptsSeen']==2 and events and r['result']['completionStatusSeen']
    r,events=request(prompt('请解释项目结构。',3));assert r['result']['promptsSeen']==3 and not r['result']['completionStatusSeen']
    print('PASS: protocol forwarding, messaging, zero-call greeting reply, auth passthrough, blocked-result delivery, one-time completion status.')
finally:
    p.stdin.close()
    try:p.wait(timeout=5)
    except subprocess.TimeoutExpired:p.terminate();p.wait(timeout=5)
