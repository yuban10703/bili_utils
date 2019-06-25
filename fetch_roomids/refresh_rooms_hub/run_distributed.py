import asyncio
from random import shuffle
from os import path

import rsa
from aiohttp import web

import utils
from tasks.utils import UtilsTask
from static_rooms import var_static_room_checker
from online_rooms import var_online_room_checker
from printer import info as print


loop = asyncio.get_event_loop()
distributed_clients = ['http://127.0.0.1:9001', ]  # eg: ['http://127.0.0.1:9001', ]


async def check_page_size():
    max_rooms_num = 0
    for client in distributed_clients:
        data = await UtilsTask.check_client(client)
        max_rooms_num += data['remain_roomids'] + len(data['roomids_monitored'])
    if max_rooms_num >= 10000:
        return 200
    if max_rooms_num >= 7000:
        return 160
    return 70

page_size = loop.run_until_complete(check_page_size())
print(f'PAGE_SIZE = {page_size}')


class OnlineRoomNotStaticCheckers:  # 在线房间，剔除静态的结果
    def __init__(self):
        var_online_room_checker.page_size = page_size
        self.online_room_checker = var_online_room_checker
        self.static_rooms = var_static_room_checker.get_rooms()

    async def refresh_and_get_rooms(self):
        await self.online_room_checker.refresh()
        rooms = self.online_room_checker.get_rooms()
        return [i for i in rooms if i not in self.static_rooms]  # 过滤掉静态房间里面的

    def status(self) -> dict:
        return self.online_room_checker.status()


class WebServer:
    def __init__(self, admin_privkey: rsa.PrivateKey):
        self.rooms = []

        self.checker = OnlineRoomNotStaticCheckers()

        self.admin_privkey = admin_privkey
        self.max_remain_roomids = 0
        self.max_num_roomids = -1

    async def intro(self, _):
        data = {
            'code': 0,
            'version': '1.0.0b5',
            **self.checker.status(),
            'max_remain_roomids': self.max_remain_roomids,
            'max_num_roomids': self.max_num_roomids,
            'page_size': page_size
        }
        return web.json_response(data)

    async def check_index(self, request):
        roomid = request.match_info['roomid']
        try:
            roomid = int(roomid)
            code = 0
            if roomid in self.rooms:
                is_in = True
                index = self.rooms.index(roomid)
            else:
                is_in = False
                index = -1
        except ValueError:
            code = -1
            is_in = False
            index = -1

        data = {'code': code, 'is_in': is_in, 'index': index}

        return web.json_response(data)

    async def refresh_and_get_rooms(self):
        self.rooms = await self.checker.refresh_and_get_rooms()
        self.max_num_roomids = max(self.max_num_roomids, len(self.rooms))
        
    async def push_roomids(self) -> float:  # 休眠时间
        print('正在准备推送房间')
        shuffle(distributed_clients)
        print(f'有效房间 {len(self.rooms)}')

        roomids_monitored = []  # 所有的正在监控的房间
        remain_roomids = []  # 每个 client 的空余量
        for client in distributed_clients:
            data = await UtilsTask.check_client(client)
            remain_roomids.append(data['remain_roomids'])
            roomids_monitored += data['roomids_monitored']

        new_roomids = list(set(self.rooms) - set(roomids_monitored))

        if new_roomids:
            sleep_time = 0
            cursor = 0
            for i, client in enumerate(distributed_clients):
                if cursor >= len(new_roomids):
                    break
                roomid_sent = new_roomids[cursor: cursor+remain_roomids[i]]
                if roomid_sent:  # 是 0 的话没必要推送了
                    sleep_time = max(
                        sleep_time, await UtilsTask.add_new_roomids(client, self.admin_privkey, roomid_sent))
                cursor += remain_roomids[i]
            self.max_remain_roomids = max(self.max_remain_roomids, len(new_roomids) - cursor)
            return sleep_time
        return 0


async def init():
    key_path = f'{path.dirname(path.realpath(__file__))}/key'
    with open(f'{key_path}/admin_privkey.pem', 'rb') as f:
        admin_privkey = rsa.PrivateKey.load_pkcs1(f.read())

    app = web.Application()
    webserver = WebServer(admin_privkey)
    app.router.add_get('/', webserver.intro)
    app.router.add_get('/is_in/{roomid}', webserver.check_index)
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', 9000)
    await site.start()

    wanted_time = 0
    while True:
        await webserver.refresh_and_get_rooms()
        await asyncio.sleep(wanted_time-utils.curr_time()+3)
        wanted_time = utils.curr_time() + await webserver.push_roomids()


loop.run_until_complete(init())
loop.run_forever()