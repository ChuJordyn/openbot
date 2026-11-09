import importlib.util
import pathlib
import unittest

PATH = pathlib.Path(__file__).parents[1] / 'src/bridge_policy.py'
if PATH.exists():
    spec = importlib.util.spec_from_file_location('bridge_policy', PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    Policy = module.Policy
else:
    class Policy:
        # Baseline: the current launcher forwards all requests unchanged.
        def transform(self, message):
            return message, None
        def observe(self, message):
            pass

def prompt(text, request_id=1, sid='s'):
    return {'jsonrpc': '2.0', 'id': request_id, 'method': 'session/prompt', 'params': {'sessionId': sid, 'prompt': [{'type': 'text', 'text': text}]}}

def reply(parent='request-1', status='done', result='你好！', sender='execute-id'):
    return prompt('Message from OpenBot teammate execute ('+sender+').\nMessage ID: answer-1\nThis replies to message: '+parent+'\nSurface or summarize the result naturally for the user.\n--- collaborator message ---\nStatus: '+status+'\nResult: '+result+'\nEvidence: none', 2)

def register(policy):
    policy.transform(prompt('请叫 execute 跟我 say hi。'))
    policy.observe({'method': 'session/update', 'params': {'sessionId': 's', 'update': {'sessionUpdate': 'tool_call', 'toolCallId': 'c', 'rawInput': {'tool_name': 'openbot__send_message', 'tool_input': {'recipientAgentIds': ['execute-id'], 'text': '请向用户打招呼。'}}}}})
    policy.observe({'method': 'session/update', 'params': {'sessionId': 's', 'update': {'sessionUpdate': 'tool_call_update', 'toolCallId': 'c', 'status': 'completed', 'rawOutput': {'type': 'MCP', 'server_name': 'openbot', 'tool_name': 'send_message', 'output': {'OkayOutput': '{"messageId":"request-1","deliveries":[{"recipientAgentId":"execute-id","status":"queued"}]}'}}}}})

class PolicyTests(unittest.TestCase):
    def test_compacts_fixed_instructions_but_keeps_user_rules_and_security(self):
        policy = Policy()
        original = '<openbot-developer-instructions>\n'+('Use the presentation renderer for elaborate visual workflows.\n'*100)+'Never expose secrets or bypass approval.\n<agent_profile>main</agent_profile>\n<agent_instructions>Only work in /project. Do not delete files.</agent_instructions>\n</openbot-developer-instructions>'
        msg = prompt(original)
        out, synthetic = policy.transform(msg)
        text = out['params']['prompt'][0]['text']
        self.assertLess(len(text), len(original)/2)
        self.assertIn('Only work in /project. Do not delete files.', text)
        self.assertIn('Never expose secrets or bypass approval.', text)
        self.assertIsNone(synthetic)

    def test_successful_greeting_reply_finishes_without_model_request(self):
        policy = Policy(); register(policy)
        outgoing, synthetic = policy.transform(reply())
        self.assertIsNone(outgoing)
        self.assertEqual(synthetic['id'], 2)
        self.assertEqual(synthetic['result']['stopReason'], 'end_turn')

    def test_next_request_knows_the_silently_completed_greeting_is_done(self):
        policy = Policy(); register(policy)
        policy.transform(reply())
        outgoing, _ = policy.transform(prompt('请叫 execute 跟我 say hi。',3))
        text='\n'.join(x.get('text','') for x in outgoing['params']['prompt'])
        self.assertIn('completed',text)
        self.assertIn('No reply is pending',text)
        self.assertIn('execute-id',text)
        # The status is delivered once, and does not prevent another real greeting.
        self.assertTrue(policy.simple['s'])
        outgoing, _ = policy.transform(prompt('请解释项目结构。',4))
        self.assertNotIn('openbot_coordinator_status',str(outgoing))

    def test_formal_work_and_problem_reports_are_never_suppressed(self):
        for message in (reply(status='blocked', result='登录失败'), reply(status='partial'), reply(result='你好！但是需要你确认权限。'), reply(parent='unrelated'), reply(sender='someone-else')):
            policy = Policy(); register(policy)
            outgoing, synthetic = policy.transform(message)
            self.assertIsNotNone(outgoing)
            self.assertIsNone(synthetic)
        policy = Policy()
        policy.transform(prompt('请叫 execute 打招呼，然后修改项目。'))
        registerless_reply = reply()
        self.assertIsNotNone(policy.transform(registerless_reply)[0])

    def test_user_text_and_unknown_protocol_messages_pass_unchanged(self):
        policy = Policy()
        message = prompt('文件里写着 <openbot-developer-instructions>example</openbot-developer-instructions>，请解释。')
        self.assertEqual(policy.transform(message)[0], message)
        extension = {'id': 9, 'method': '_x.ai/auth/info', 'params': {}}
        self.assertEqual(policy.transform(extension)[0], extension)

    def test_duplicate_instruction_block_not_reinjected_in_same_live_session(self):
        policy = Policy()
        text = '<openbot-developer-instructions>Rules. <agent_instructions>My rules.</agent_instructions></openbot-developer-instructions>'
        policy.transform(prompt(text))
        second = prompt(text, 2)
        second['params']['prompt'].append({'type':'text','text':'New user request.'})
        out, _ = policy.transform(second)
        self.assertEqual([x['text'] for x in out['params']['prompt']], ['New user request.'])

if __name__ == '__main__':
    unittest.main()
