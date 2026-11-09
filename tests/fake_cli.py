import json,sys
prompts=0
def send(d):print(json.dumps(d),flush=True)
for line in sys.stdin:
    q=json.loads(line);method=q.get('method');rid=q.get('id')
    if method=='initialize':r={'protocolVersion':1,'agentCapabilities':{}}
    elif method=='session/new':r={'sessionId':'s','seenServers':[x['name'] for x in q['params'].get('mcpServers',[])]}
    elif method=='session/prompt':
        prompts+=1
        if prompts==1:
            for update in [
                {'sessionUpdate':'tool_call','toolCallId':'c','rawInput':{'tool_name':'openbot__send_message','tool_input':{'recipientAgentIds':['execute-id'],'text':'请向用户打招呼。'}}},
                {'sessionUpdate':'tool_call_update','toolCallId':'c','status':'completed','rawOutput':{'type':'MCP','server_name':'openbot','tool_name':'send_message','output':{'OkayOutput':'{"messageId":"request-1","deliveries":[{"recipientAgentId":"execute-id","status":"queued"}]}'}}},
            ]:send({'method':'session/update','params':{'sessionId':'s','update':update}})
        send({'method':'session/update','params':{'sessionId':'s','update':{'sessionUpdate':'agent_message_chunk','content':{'type':'text','text':'已通知。' if prompts==1 else '需要用户处理。'}}}})
        status_seen=any('No reply is pending' in b.get('text','') for b in q['params']['prompt'])
        r={'stopReason':'end_turn','promptsSeen':prompts,'completionStatusSeen':status_seen}
    elif method=='_x.ai/auth/info':r={'authenticated':True,'promptsSeen':prompts}
    else:r={'ok':True}
    if rid is not None:send({'jsonrpc':'2.0','id':rid,'result':r})
