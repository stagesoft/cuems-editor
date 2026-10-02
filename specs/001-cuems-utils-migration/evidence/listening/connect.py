"""Connect to ws://localhost:9092/ and print the first frames' types (T016)."""
import asyncio, json
from websockets.asyncio.client import connect

async def main():
    async with connect('ws://localhost:9092/') as ws:
        for _ in range(4):
            frame = json.loads(await asyncio.wait_for(ws.recv(), 5))
            value = frame.get('value')
            shape = list(value)[:6] if isinstance(value, dict) else value
            print(frame['type'], shape)
        await ws.send(json.dumps({'action': 'project_list'}))
        print(json.loads(await asyncio.wait_for(ws.recv(), 5)))

asyncio.run(main())
