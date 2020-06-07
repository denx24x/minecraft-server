import json
import os
import socket
from main import Game
import select
import time
import importlib
import sys
import threading
from constants import *
from structures import Player
from inventory import Inventory
import socketserver
import requests
import flask
from level_generation import ChunkController

if getattr(sys, 'frozen', False):
    application_path = os.path.dirname(sys.executable)
else:
    application_path = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.join(application_path, "classes"))


player_lock = threading.Lock()


import socket
import threading
import os
import random
last_id = 0
app = flask.Flask(__name__)

class ClientInstance:
    def __init__(self, name, socket, address, player, id):
        self.name = name
        self.socket = socket
        self.address = address
        self.player = player
        self.id = id
        self.direction = 0

    def ping(self, data):
        self.player.x = data['x']
        self.player.y = data['y']
        self.player.moving = data['moving']
        self.direction = data['dir']
        self.player.inventory.set_selected(data['selected'])

    def save(self):
        return {
            'player': self.player.save(),
            'id': self.id,
            'name': self.name
        }

    def load(self, data):
        self.id = data['id']
        self.name = data['name']
        self.player.load(data['player'])


class Server:
    def __init__(self, port, isLocal=True, conections_limit=40):
        self.port = int(os.environ.get("PORT", port))
        self.ip = '127.0.0.1' if isLocal else '0.0.0.0'
        print(self.ip, self.port)
        self.player_list = {}
        self.player_address = {}
        self.conections_limit = conections_limit
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.bind((self.ip, self.port))
        self.socket.listen(40)
        self.game = Game()
        self.game.is_server = True
        self.running = True
        self.last_id = 0
        self.game.chunk_controller = ChunkController(1, 1, random.randint(0, 100000))
        self.routing = {BLOCK_UPDATE: self.block_update, JOIN_REQUEST: self.handle_join, LEAVE_REQUEST: self.handle_leave, PLACE_BLOCK: self.block_place, DESTROY_BLOCK: self.block_destroy, PING: self.ping, SYNC_INVENTORY: self.sync_inventory, SYNC_BLOCK: self.sync_block}

    def block_update(self, data, address, socket):
        player_lock.acquire()
        try:
            new = self.game.objects[data['type']].generate_block(**data)
            self.game.chunk_controller.place_block(data['x'], data['y'], new, self.game)
            self.send_all({'request': BLOCK_UPDATE, 'data': {'x': data['x'], 'y': data['y'],
                                                             'block': new.save()}}, address)
        finally:
            player_lock.release()

    def send_all(self, data, except_address=None):  # requires to be called in player_lock.acquire() context
        for i in self.player_address.values():
            if self.player_list[i].address == except_address:
                continue
            try:
                self.send(self.player_list[i].socket, data)
            except Exception as e:
                print(e)

    def handle_join(self, data, address, socket):
        player_lock.acquire()
        try:
            if address in self.player_address:
                return {
                    'success': False,
                    'reason': '[server connection error]: Already connected'
                }
            if len([i for i in self.player_address.values() if i == data['name']]):
                return {
                    'success': False,
                    'reason': '[server connection error]: Name ' + data['name'] + 'already taken'
                }
            self.player_address[address] = data['name']
            if data['name'] not in self.player_list:
                self.player_list[data['name']] = ClientInstance(data['name'], socket, address, Player(100000, self.game.chunk_controller.get_player_start_pos(100000), Inventory(9, 3, self.game.crafts, self.game), self.game), self.last_id)
                player = self.player_list[data['name']].player
                self.last_id += 1
                try:
                    player.inventory.add_item(self.game.objects["torch"].generate_item(20))
                    player.inventory.add_item(self.game.objects["dirt"].generate_item(120))
                except Exception:
                    pass
            else:
                player = self.player_list[data['name']].player
                self.player_list[data['name']].name = data['name']
                self.player_list[data['name']].socket = socket
                self.player_list[data['name']].address = address
            level = self.game.gen_save()
            self.send_all({'request': JOIN,
                           'data': {
                                'name': self.player_list[data['name']].name,
                                'x': player.x,
                                'y': player.y,
                                'id': self.player_list[data['name']].id,
                                'selected': player.inventory.get_selected().type if player.inventory.get_selected() is not None else 'None'}}, address)
            to_return = {
                'success': True,
                'level': level,
                'players': [{
                    'id': self.player_list[i].id,
                    'name': self.player_list[i].name,
                    'x': self.player_list[i].player.x,
                    'y': self.player_list[i].player.y,
                    'selected': self.player_list[i].player.inventory.get_selected().type if self.player_list[i].player.inventory.get_selected() is not None else 'None'} for i in self.player_address.values() if self.player_list[i].id != self.player_list[data['name']].id],
                'player_data': player.save(),
                'started_time': time.time() - self.game.started_time
            }
            return to_return

        finally:
            player_lock.release()

    def ping(self, data, address, socket):
        player_lock.acquire()
        try:
            name = self.player_address[address]
            self.player_list[name].ping(data)
            self.send_all({'request': PING,
                           'data': {
                               'id': self.player_list[name].id,
                               'x': self.player_list[name].player.x,
                               'y': self.player_list[name].player.y,
                               'moving': self.player_list[name].player.moving,
                               'dir': self.player_list[name].direction,
                               'selected': self.player_list[name].player.inventory.get_selected().type if self.player_list[name].player.inventory.get_selected() is not None else 'None'}}, address)
        except Exception as E:
            print(E)
        finally:
            player_lock.release()

    def send(self, socket, data):
        prep = bytes(json.dumps(data), encoding='ascii')
        socket.send(len(prep).to_bytes(16, 'big'))
        socket.send(prep)

    def receive(self, socket):
        ln = int.from_bytes(socket.recv(16), 'big')
        data = json.loads(socket.recv(ln))
        return data

    def save(self):
        data = {
        'game': self.game.gen_save(),
        'players': [i.save() for i in self.player_list.values()],
        'last_id': self.last_id
        }
        out = open('save_server.txt', 'w')
        out.write(json.dumps(data))
        out.close()

    def load(self):
        inp = open('save_server.txt', 'r')
        data = json.loads(inp.read())
        self.game.gen_load(data['game'])
        self.last_id = data['last_id']
        for i in data['players']:
            self.player_list[i['name']] = ClientInstance(None, None, None, Player(0, 0, Inventory(9, 3, self.game.crafts, self.game), self.game), 0)
            self.player_list[i['name']].load(i)
        inp.close()

    def handle_leave(self, data, address, socket):
        player_lock.acquire()
        try:
            id = self.player_list[self.player_address[address]].id
            self.player_address.pop(address)
            self.send_all({'request': LEAVE, 'data': {'id': id}})
        finally:
            player_lock.release()

    def sync_inventory(self, data, address, socket):
        player_lock.acquire()
        try:
            self.player_list[self.player_address[address]].player.inventory.get_sync(data, self.game.objects)
        finally:
            player_lock.release()

    def sync_block(self, data, address, socket):
        player_lock.acquire()
        try:
            block = self.game.chunk_controller.get(data['x'], data['y'], self.game.objects, self.game)
            block.get_sync(data['block'])
            self.send_all({'request': SYNC_BLOCK, 'data': block.get_sync_with_server()}, address)
        finally:
            player_lock.release()

    def block_place(self, data, address, socket):
        player_lock.acquire()
        try:
            player = self.player_list[self.player_address[address]].player
            new = self.game.objects[player.inventory.get_selected().type].generate_block(0, 0, (data['x'], data['y']))
            player.inventory.place_selected()
            self.game.chunk_controller.place_block(data['x'], data['y'], new, self.game)
            self.send_all({'request': BLOCK_UPDATE, 'data': {'x': data['x'], 'y': data['y'], 'block': new.save()}}, address)
        finally:
            player_lock.release()

    def block_destroy(self, data, address, socket):
        player_lock.acquire()
        try:
            block = self.game.chunk_controller.get(data['x'], data['y'], self.game.objects, self.game)
            player = self.player_list[self.player_address[address]].player
            if block.drop is not None:
                drop = block.drop.get_drop()
                player.inventory.add_item(self.game.objects[drop[0]].generate_item(drop[1]))
            new = self.game.objects['empty'].generate_block(0, 0, (data['x'], data['y']))
            self.game.chunk_controller.place_block(data['x'], data['y'], new, self.game)
            self.send_all({'request': BLOCK_UPDATE, 'data': {'x': data['x'], 'y': data['y'],
                                                             'block': new.save()}})
        finally:
            player_lock.release()

    def handle_client_connection(self, client_socket, address):
        while self.running:
            try:
                ready = select.select([client_socket], [], [], 20)
                if ready[0]:
                    request = self.receive(client_socket)
                if not ready[0] or not request:
                    self.handle_leave(None, address, socket)
                    break
                req = request
                if req['request'] == LEAVE_REQUEST:
                    self.handle_leave(None, address, socket)
                    break
                data = self.routing[req['request']](req['data'], address, client_socket)
                if data:
                    self.send(client_socket, data)
            except Exception as e:
                print(e)
                try:
                    self.handle_leave(None, address, socket)
                except Exception:
                    pass
                break
        try:
            client_socket.close()
        except Exception:
            return

    def exit(self):
        self.running = False
        self.socket.close()

    def run(self):
        self.running = True
        while self.running:
            try:
                client_sock, address = self.socket.accept()
                client_handler = threading.Thread(
                    target=self.handle_client_connection,
                    args=(client_sock, address)
                )
                client_handler.start()
            except Exception:
                pass

    def listen_cmd(self):
        print(*['commands:', 'exit', 'save', 'load'])
        while self.running:
            cmd = input()
            if cmd == 'exit':
                self.exit()
                print('exited')
            elif cmd == 'save':
                print('saving...')
                player_lock.acquire()
                try:
                    self.save()
                    print('saved')
                except Exception as e:
                    print(e)
                finally:
                    player_lock.release()
            elif cmd == 'load':
                print('loading...')
                player_lock.acquire()
                try:
                    for i in self.player_list.values():
                        try:
                            i.socket.close()
                        except Exception:
                            pass
                    self.load()
                    print('loaded')
                except Exception as e:
                    print(e)
                finally:
                    player_lock.release()
            else:
                print('unknown command')


@app.route('/')
def index():
    return 'Это чтобы он крутился на сервисе'
        

def ping():
    timing = time.time()
    while True:
        if time.time() - timing > 600.0:
            timing = time.time()
            print(requests.get('https://mine-craft-sever.herokuapp.com/'))


if __name__ == '__main__':
    server = Server(440, isLocal=False)
    main = threading.Thread(target=server.run)
    listener = threading.Thread(target=server.listen_cmd)
    main.start()
    listener.start()
    port = int(os.environ.get("PORT", 5000))
    thread = threading.Thread(target = ping)
    thread.start()
    app.run(port=port, host='0.0.0.0')
