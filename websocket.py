import asyncio
import websockets
from urllib.parse import urlparse, parse_qs

IP_ADDRESS = "127.0.0.1"
PORT = 5011

map_unity_users = {}
map_web_users = {}
id_counter = 0


async def handle_connection(websocket, path):
    global id_counter
    print('User connected!')

    queryparams = parse_qs(urlparse(path).query)
    usertype = queryparams.get('type', [''])[0]
    accesstoken = queryparams.get('token', [''])[0]
    uid = queryparams.get('uid', [''])[0]
    is_unity_user = False

    user_id_with_id = f"{uid}{id_counter}"
    id_counter += 1

    if usertype == "u":
        print('UNITY USER! ', user_id_with_id)
        map_unity_users[user_id_with_id] = websocket
        is_unity_user = True
    elif usertype == "w":
        print('WEB USER! ', user_id_with_id)
        map_web_users[user_id_with_id] = websocket

    print('usertype: ', usertype)
    print('accesstoken: ', accesstoken)

    await websocket.send("Connected!")

    try:
        async for message in websocket:
            print(f'received: {message}')
            if is_unity_user:
                # Send to web users
                for ws in map_web_users.values():
                    await ws.send(message)
            else:
                # Send to unity users
                for ws in map_unity_users.values():
                    await ws.send(message)
    except websockets.ConnectionClosed:
        print(f"Connection closed for user {user_id_with_id}")
    finally:
        if is_unity_user:
            del map_unity_users[user_id_with_id]
        else:
            del map_web_users[user_id_with_id]


async def main():
    async with websockets.serve(handle_connection, IP_ADDRESS, PORT):
        print(f"Server started on ws://{IP_ADDRESS}:{PORT}")
        await asyncio.Future()  # run forever

asyncio.run(main())
