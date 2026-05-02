import os, json, openai

key = os.environ.get('OPENAI_API_KEY', '')
client = openai.OpenAI(api_key=key)

try:
    resp = client.chat.completions.create(
        model='gpt-4o-mini',
        response_format={'type': 'json_object'},
        messages=[
            {'role': 'system', 'content': 'You are a helpful assistant. Respond in JSON only.'},
            {'role': 'user', 'content': 'Break down "add dark mode toggle to dashboard" into dev tasks. Format: {"tasks": [{"id":"TASK-01","title":"..."}]}'},
        ],
    )
    raw = resp.choices[0].message.content
    print('SUCCESS:', raw[:200])
    data = json.loads(raw)
    print('TASK COUNT:', len(data.get('tasks', [])))
except Exception as e:
    print('ERROR_TYPE:', type(e).__name__)
    print('ERROR:', e)
