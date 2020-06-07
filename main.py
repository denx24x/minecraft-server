import pygame
import sys
from collections import deque
from noise import Noise, TwoDisNoise
from constants import *
import math
import random
from maths import check_square_collision, check_square_intersect
from structures import ObjectData, BlockDrop, GlobalRotatingObject, Block, Player, load_image, make_gl_image, createTexDL, gl_draw_single_tex
from inventory import Inventory, Item
from light_calculation import LightController
from level_generation import ChunkController
from game_interface import GameInterface
from graphics import TileImage, draw_text
import threading
import select
import json
import time
import socket
import os

if getattr(sys, 'frozen', False):
    application_path = os.path.dirname(sys.executable)
else:
    application_path = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.join(application_path, "classes"))  # позволяет pyinstallerу находить динамические классы


def custom_import(path):  # позволяет динамически импортировать классы
    components = path.split('.')
    mod = __import__('.'.join(components[:1]))
    for i in components[1:]:
        mod = getattr(mod, i)
    return mod


class Game:
    def __init__(self):
        self.light_coff = 1

        self.status = IN_GAME

        self.objects = {}
        self.crafts = []

        self.phys_blocks_group = pygame.sprite.Group()
        self.all_blocks = pygame.sprite.Group()

        self.import_objects()

        self.player = None
        self.other_players = {}
        self.lerp_query = {}
        self.data_stack = deque()
        self.stack_lock = threading.Lock()
        self.sun = None
        self.moon = None
        self.pos_center = (0, 0)
        self.gravity_force = 0
        self.chunk_controller = None
        self.light_controller = None
        self.last_target = None
        self.interface = None
        self.running = False
        self.socket = None
        self.is_server = False
        self.connected = False
        self.data_handler = None

        self.block_size = 0
        self.block_height = 0
        self.block_width = 0
        self.additional = 0
        self.started_time = time.time()

    def import_objects(self):  # сериализация всех json обьектов и загрузка py классов
        for i in os.listdir(os.path.join(application_path, 'objects')):
            if os.path.splitext(i)[1] != '.json':
                continue
            st = open(os.path.join(application_path, 'objects', i), 'r')
            object = json.load(st)
            self.objects[object['name']] = ObjectData(
                type=object['name'],
                game=self,
                path=object['path'],
                tile_image=TileImage(None, None, None),
                block_class_path=object['class'],
                item_class_path=object['items_class'],
                block_class=custom_import(object['class'] + '.Object'),
                item_class=custom_import(object['items_class'] + '.Object'),
                is_phys=object['is_phys'],
                is_item=object['is_item'],
                transparent=object['transparent'],
                hp=object['hp'],
                lighting=object['lighting'],
                drop=BlockDrop(*object['drop']) if len(object['drop']) else None
            )
        for i in os.listdir(application_path + '/' + 'recipes'):
            if os.path.splitext(i)[1] != '.json':
                continue
            st = open(os.path.join(application_path, 'recipes/', i), 'r')
            recipe = json.load(st)
            self.crafts.append((recipe['recipe'], recipe['result']))

    def initialise(self, width=BASE_BLOCK_WIDTH, height=BASE_BLOCK_HEIGHT, block_size=BASE_BLOCK_SIZE):  # загрузка всего и всякого
        self.screen = pygame.display.set_mode((width * block_size, height * block_size), pygame.OPENGL | pygame.DOUBLEBUF)
        glLoadIdentity()
        glMatrixMode(GL_PROJECTION)
        gluOrtho2D(0, width * block_size, height * block_size, 0)
        glMatrixMode(GL_MODELVIEW)
        glLoadIdentity()
        glEnable(GL_TEXTURE_2D)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)

        self.block_size = block_size
        self.block_width = width
        self.block_height = height

        self.width = self.block_size * self.block_width
        self.height = self.block_size * self.block_height

        self.x_center = self.width // 2
        self.y_center = self.height // 2

        self.block_x_center = self.width // self.block_size
        self.block_y_center = self.height // self.block_size

        self.additional = 20  # дополнительное ко-во блоков для счета физики и освещения
        # считается, что этого достаточно чтобы не делать слишком частую подгрузку и при этом подгрузка не была тяжелой

        for i in self.objects.values():
            if i.tile_image is not None and i.tile_image.gl_image is not None:
                glDeleteTextures(1, i.tile_image.gl_image)
            i.tile_image = TileImage(load_image(i.path), self.block_size, self.block_size)
        self.text_font = pygame.font.Font(os.path.join(application_path, 'lobster.ttf'),
                                              min(self.block_width * self.block_size // 25,
                                                  self.block_height * self.block_size // 25))
        self.destroy_images = [createTexDL(make_gl_image(
                pygame.transform.scale(load_image("destroy_stage_" + str(i) + ".png"),
                                       (self.block_size, self.block_size)))[0], self.block_size, self.block_size) for i
                                   in range(10)]
        self.sun_tile = TileImage(load_image('sun.png'), self.block_size, self.block_size)
        self.moon_tile = TileImage(load_image('moon.png'), self.block_size, self.block_size)
        self.interface = GameInterface(self)

    def get_view_start(self):  # начальные координаты обзора игрока
        y, x = int(-(self.pos_center[1] - self.player.y) * self.block_size), int(-(self.pos_center[0] - self.player.x) * self.block_size)
        startx, starty = x // self.block_size + self.additional // 2, y // self.block_size + self.additional // 2
        return startx, starty

    def gen_load(self, data):
        self.chunk_controller = ChunkController(self.block_width + self.additional, self.block_height + self.additional,
                                                data['chunk_controller']['seed'])
        self.chunk_controller.load(data['chunk_controller'], self.objects)
        self.started_time = time.time() - data['started_time']
        if not self.is_server:
            inv = data['player']['inventory']
            inventory = Inventory(inv['x_size'], inv['y_size'], self.crafts, self)
            inventory.get_sync(inv, self.objects)
            inventory.craft_model.craft_make_handle(None, None, None, None)
            self.player = Player(data['player']['x'], data['player']['y'], inventory, self)
            self.player.make_model()
            self.status = IN_GAME
            self.light_controller = LightController(self.block_width + self.additional,
                                                    self.block_height + self.additional)
            self.sun = GlobalRotatingObject(self.sun_tile)
            self.moon = GlobalRotatingObject(self.moon_tile, coff=1)
            self.pos_center = (int(self.player.x), int(self.player.y))
            self.gravity_force = 0

    def load(self, path='save.txt'):  # загрузка всех тех jsonов от всех всех объектов - в будующем это будет сделано попроще...
        data = json.loads(open(os.path.join(application_path, path), 'r').read())
        self.gen_load(data)

    def server_leave(self):
        if not self.connected:
            return
        self.connected = False
        self.data_handler = None
        try:
            self.send({'request': LEAVE_REQUEST, 'data': {}})
            self.socket.close()
        except Exception:
            pass
        finally:
            self.socket = None
        self.other_players = {}
        self.data_stack = deque()
        self.lerp_query = {}
        self.status = MENU

    def send(self, data):
        prep = bytes(json.dumps(data), encoding='ascii')
        self.socket.send(len(prep).to_bytes(16, 'big'))  # сначала отправляется длина пакета
        self.socket.send(prep)  # сам пакет

    def receive(self):
        ln = int.from_bytes(self.socket.recv(16), 'big')
        data = json.loads(self.socket.recv(ln))
        return data

    def connect(self, ip, port, name):
        try:
            self.new_game()
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.connect((ip, int(port)))
            self.connected = True
            self.send({'request': JOIN_REQUEST, 'data': {'name': name}})
            response = self.receive()
            if not response['success']:  # запрос наверное может быть отклонен
                self.server_leave()
                self.interface.server_message.generate_text(response['reason'], self.text_font, self.width // 20)
                self.interface.status = CONNECT_ERROR
                return
            self.chunk_controller = ChunkController(self.block_width + self.additional,
                                                    self.block_height + self.additional,
                                                    response['level']['chunk_controller']['seed'])
            self.chunk_controller.load(response['level']['chunk_controller'], self.objects)  # загрузка соответствующего мира
            self.player.x = response['player_data']['x']
            self.player.y = response['player_data']['y']
            self.player.inventory.get_sync(response['player_data']['inventory'], self.objects)
            self.started_time = time.time() - response['started_time']
            for i in response['players']:
                self.other_players[i['id']] = {'name': i['name'], 'model': Player(i['x'], i['y'], None, self), 'selected': self.objects[i['selected']].generate_item(1) if i['selected'] != 'None' else None}
                self.other_players[i['id']]['model'].make_model()
                self.other_players[i['id']]['model'].update_model(self.player.x, self.player.y)
            self.data_handler = threading.Thread(target=self.data_receive)
            self.data_handler.start()
            self.start()
        except socket.error as e:
            self.server_leave()
            self.interface.server_message.generate_text(str(e), self.text_font, self.width // 20)
            self.interface.status = CONNECT_ERROR

    def new_game(self):
        inventory = Inventory(9, 3, self.crafts, self)
        try:  # стартовый набор
            inventory.add_item(self.objects["torch"].generate_item(20))
            inventory.add_item(self.objects["dirt"].generate_item(120))
        except Exception:
            pass
        self.gravity_force = 0
        self.chunk_controller = ChunkController(self.block_width + self.additional, self.block_height + self.additional, random.randint(0, 100000))
        self.light_controller = LightController(self.block_width + self.additional, self.block_height + self.additional)
        self.sun = GlobalRotatingObject(self.sun_tile)
        self.moon = GlobalRotatingObject(self.moon_tile, coff=1)
        val = self.chunk_controller.get_player_start_pos(100000)  # на 0 координате "стык" - мир на отрицательных координатах является отражением мира на положительных
        self.player = Player(100000, val - 2, inventory, self)
        self.player.make_model()
        self.pos_center = (int(self.player.x), int(self.player.y))
        self.started_time = time.time()

    def start(self):
        self.status = IN_GAME
        self.redraw_all()

    def gen_save(self):  # там много вызовов save у разных обьектов и все это в один json схлопывается
        data = {}
        data['chunk_controller'] = self.chunk_controller.save()
        if self.player is not None:
            data['player'] = self.player.save()
        data['started_time'] = time.time() - self.started_time
        return data

    def save(self, path='save.txt'):
        out = open(os.path.join(application_path, path), 'w')
        out.write(json.dumps(self.gen_save()))
        out.close()

    def update_changes(self, was, block):  # обновляет группы
        if was.is_phys:
            self.phys_blocks_group.remove(was)
        if block.is_phys:
            self.phys_blocks_group.add(block)
        self.all_blocks.remove(was)
        self.all_blocks.add(block)
        if block.worldpos[0] not in self.chunk_controller.changes:
            self.chunk_controller.changes[block.worldpos[0]] = {}
        self.chunk_controller.changes[block.worldpos[0]][block.worldpos[1]] = block

    def place_block(self, x, y, player):
        block = self.chunk_controller.chunk[y][x]
        if block.type != 'empty' or player.inventory.get_selected() is None:  # если уже занято
            return
        if player.inventory.get_selected().is_item:  # если не блок
            return
        if pygame.sprite.collide_rect(block, player.model.get_current_tile()):  # если в персонаже
            return
        new = self.objects[player.inventory.get_selected().type].generate_block(x, y, block.worldpos)
        self.update_changes(block, new)
        self.chunk_controller.chunk[y][x] = new
        self.chunk_controller.chunk[y][x].on_place(self)
        player.inventory.place_selected()
        if not new.transparent:
            self.light_controller.max_y[x] = min(self.light_controller.max_y[x], new.worldpos[1])
        elif not block.transparent:
            self.light_controller.calc_max_y_for_x(new.x, self.pos_center, self.chunk_controller, self.objects)
        self.light_controller.calculate_light(self.chunk_controller.chunk, self.chunk_controller.ground_height)
        if self.connected:
            self.send({'request': PLACE_BLOCK, 'data': {'x': new.worldpos[0], 'y': new.worldpos[1]}})

    def draw_single_light(self, block):  # рисует свет на блоке
        if not block.transparent:
            color = (0, 0, 0, 1 - self.light_controller.lighting[block.y][block.x] * self.light_coff)
        else:  # фон остается немного видимым (упрощает навигацию в шахте)
            color = (0, 0, 0, min(0.95, 1 - self.light_controller.lighting[block.y][block.x] * self.light_coff))
        glColor4f(*color)
        glRectf(0, 0, block.rect.width, block.rect.height)
        glColor4f(1, 1, 1, 1)

    def draw_all_light(self):
        glBindTexture(GL_TEXTURE_2D, 0)
        startx, starty = GAME.get_view_start()  # определяет область от общей области, которая видна игроку
        for g in range(startx - 1, startx + self.block_width + 1):
            for k in range(starty - 1, starty + self.block_height + 1):
                i = GAME.chunk_controller.chunk[k][g]
                glLoadIdentity()
                glTranslate(i.rect.x, i.rect.y, 0)
                self.draw_single_light(i)

    def destroy_block(self, x, y, player):
        block = self.chunk_controller.chunk[y][x]
        block.on_destroy(self)
        new = self.objects['empty'].generate_block(x, y, block.worldpos)
        self.update_changes(block, new)
        self.last_target = None
        if block.drop is not None:
            drop = block.drop.get_drop()
            player.inventory.add_item(self.objects[drop[0]].generate_item(drop[1]))
        self.chunk_controller.chunk[y][x] = new
        self.light_controller.calc_max_y_for_x(new.x, self.pos_center, self.chunk_controller, self.objects)
        self.light_controller.calculate_light(self.chunk_controller.chunk, self.chunk_controller.ground_height)
        if self.connected:
            self.send({'request': DESTROY_BLOCK, 'data': {'x': new.worldpos[0], 'y': new.worldpos[1]}})

    def damage_block(self, x, y, dmg, player):
        block = self.chunk_controller.chunk[y][x]
        if block.type == 'empty':
            return
        if self.last_target is not None and self.last_target[0] is not None and self.last_target[1] != block.worldpos:
            self.last_target[0].hp = self.objects[self.last_target[0].type].hp
        if block.damage(dmg):  # если сломал
            self.destroy_block(x, y, player)
        else:
            self.last_target = (block, block.worldpos, block.hp)

    def exit(self):
        self.server_leave()
        self.running = False

    def redraw_all(self):  # обновляет ВСЕ
        self.all_blocks.remove(self.all_blocks)
        self.phys_blocks_group.remove(self.phys_blocks_group)
        self.chunk_controller.update_chunk(self.pos_center[0], self.pos_center[1], self.objects)
        for i in self.chunk_controller.chunk:
            for g in i:
                self.all_blocks.add(g)
                if not g.is_phys:
                    continue
                self.phys_blocks_group.add(g)
        self.all_blocks.update(self.block_width, GAME.block_height, GAME.pos_center, GAME.block_size, GAME.player.x,
                         self.player.y)
        self.light_controller.calc_max_y(self.pos_center, self.chunk_controller, self.objects)
        self.light_controller.calculate_light(self.chunk_controller.chunk, self.chunk_controller.ground_height)

    def draw_blocks_in_screen(self, draw_order):
        startx, starty = GAME.get_view_start()  # определяет область от общей области, которая видна игроку
        for g in range(startx - 1, startx + self.block_width + 1):
            for k in range(starty - 1, starty + self.block_height + 1):
                i = GAME.chunk_controller.chunk[k][g]
                if draw_order == 1:
                    if not (i.type == 'empty' or i.transparent):
                        continue
                elif draw_order == 2:
                    if i.type == 'empty':
                        continue
                i.update(self.block_width, self.block_height, self.pos_center, self.block_size, self.player.x,
                         self.player.y)
                glLoadIdentity()
                glTranslate(i.rect.x, i.rect.y, 0)
                if i.transparent and draw_order != 2:
                    glCallList(self.objects['empty'].tile_image.gl_image)
                if not (i.transparent and draw_order == 1):
                    i.draw()
                #self.draw_single_light(i)
                if i.type != 'empty' and i.hp != self.objects[i.type].hp:
                    glCallList(self.destroy_images[int(min(9, max(0, (1 - i.hp / self.objects[i.type].hp)) / 0.1))])

    def update_mouse(self, pos, events, fps):
        y, x = int(pos[1] - (self.pos_center[1] - self.player.y) * self.block_size), int(
            pos[0] - (self.pos_center[0] - self.player.x) * self.block_size)
        x, y = x // self.block_size + self.additional // 2, y // self.block_size + self.additional // 2
        if int(math.sqrt(  # проверка расстояние от персонажа
                abs(x - (self.block_width + self.additional) // 2 + int(self.pos_center[0] - self.player.x)) ** 2 + abs(
                        y - (self.block_height + self.additional) // 2 + int(
                            self.pos_center[1] - self.player.y) - 1) ** 2)) > 4:
            return
        block = GAME.chunk_controller.chunk[y][x]
        glBindTexture(GL_TEXTURE_2D, 0)
        glLoadIdentity()
        glTranslate(block.rect.x, block.rect.y, 0)
        glBegin(GL_LINE_LOOP)
        glVertex2f(0, 0)
        glVertex2f(block.rect.width, 0)
        glVertex2f(block.rect.width, block.rect.height)
        glVertex2f(0, block.rect.height)
        glEnd()
        if events[0]:
            self.damage_block(x, y, self.player.mine_speed / fps, self.player)
        elif events[2]:
            block.on_use(self)
            if self.player.inventory.get_selected() is not None:
                self.place_block(x, y, self.player)

    def update_inputs(self, fps):
        all_keys = pygame.key.get_pressed()  # проверка ввода
        key_inp = all_keys[273:277]  # стрелки
        alt_key_inp = [all_keys[119], all_keys[115], all_keys[100], all_keys[97]]  # wasd
        move_vec = (0, 0)
        if self.status == IN_GAME:
            for i in range(4):
                move_vec = (move_vec[0] + dirs[i][0] * self.player.speed * max(alt_key_inp[i], key_inp[i]),
                            move_vec[1] + dirs[i][1] * max(alt_key_inp[i], key_inp[i]))
        bf = self.player.model.get_current_tile()
        if check_square_collision(bf.rect.x + 3, bf.rect.y + bf.rect.height, bf.rect.x + bf.rect.width - 3,
                                  bf.rect.y + bf.rect.height + 1, self.phys_blocks_group):  # прыжки если персонаж стоит
            if move_vec[1] < 0 <= self.gravity_force:
                self.gravity_force = -(GRAV_CONST * 12.5)
            else:
                self.gravity_force = 0
        else:
            self.gravity_force += GRAV_CONST  # ускорение
        if move_vec[0] == 0 and move_vec[1] > 0:
            self.player.model.direction = 0
        self.player.move(move_vec[0] / fps, self.gravity_force, 300 / fps)
        if move_vec[0] != 0:
            self.player.moving = True
        else:
            self.player.moving = False
        self.light_coff = self.sun.update_pos(self.started_time, self.x_center, self.y_center, self.width, self.height)
        self.moon.update_pos(self.started_time, self.x_center, self.y_center, self.width, self.height)

    def redraw(self):
        xoffset, yoffset = self.player.x - self.pos_center[0], self.player.y - self.pos_center[1]
        if abs(xoffset) >= self.additional // 2 or abs(yoffset) >= self.additional // 2:  # подгрузка
            self.pos_center = (int(self.player.x), int(self.player.y))
            self.redraw_all()
        self.draw_blocks_in_screen(1)  # чтобы солнце под землей не рисовалось
        self.sun.draw()
        self.moon.draw()
        self.draw_blocks_in_screen(2)

        for i in self.other_players.values():
            if i['model'].moving:
                i['model'].simulate_move(i['model'].model.direction, 300 / fps)
            else:
                i['model'].simulate_move(0, 300 / fps)
            i['model'].update_model(self.player.x, self.player.y)
            i['model'].model.draw(i['selected'], self.block_size)
            glLoadIdentity()
            bf = i['model'].model.get_current_tile().rect
            glTranslate(bf.x + bf.width // 2, bf.y - self.block_size // 2, 0)
            draw_text(i['name'], self.text_font, color=(225, 225, 225, 125))
        self.player.draw()
        self.draw_all_light()

    def data_receive(self):  # получает данные с сервера в отдельном потоке (чтобы основной не ложить)
        try:
            while True:
                data = self.receive()
                if not data or not self.connected:
                    return
                self.stack_lock.acquire()
                try:
                    self.data_stack.append(data)
                finally:
                    self.stack_lock.release()
        except socket.error as e:
            self.interface.server_message.generate_text(str(e), self.text_font, self.width // 20)
            self.server_leave()
            self.interface.status = CONNECT_ERROR
            return
        except Exception:
            pass  # жсоны выбивает если сокет умирает

    def data_handle(self, data):  # обрабатывает данные с сервера
        body = data['data']
        if data['request'] == PING:
            model = self.other_players[body['id']]['model']
            self.lerp_query[body['id']] = (model.x, model.y, body['x'], body['y'], time.time())
            model.x = body['x']
            model.y = body['y']
            model.update_model(self.player.x, self.player.y)
            model.model.direction = body['dir']
            model.moving = body['moving']
            self.other_players[body['id']]['selected'] = self.objects[body['selected']].generate_item(1) if body['selected'] != 'None' else None

        elif data['request'] == JOIN:
            self.other_players[body['id']] = {'name': body['name'], 'model': Player(body['x'], body['y'], None, self),
                                              'selected': (self.objects[body['selected']].generate_item(1) if body['selected'] != 'None' else None)}

            self.other_players[body['id']]['model'].make_model()
            self.other_players[body['id']]['model'].update_model(self.player.x, self.player.y)
        elif data['request'] == BLOCK_UPDATE:
            new = self.chunk_controller.load_block(body['block'], self.objects)
            self.chunk_controller.place_block(body['x'], body['y'], new, self)
        elif data['request'] == LEAVE:
            self.other_players.pop(body['id'])
            self.lerp_query.pop(body['id'])
        elif data['request'] == SYNC_BLOCK:
            self.chunk_controller.get(body['x'], body['y'], self.objects, self).get_sync(body['block'])

    def run(self):
        pygame.init()
        pygame.font.init()
        clock = pygame.time.Clock()

        self.running = True
        self.status = MENU
        self.initialise()
        self.started_time = time.time()
        last_send = time.time()
        while self.running:
            try:
                if self.connected:
                    if time.time() - last_send > PING_TIME:  # пинг на сервер
                        self.send({'request': PING, 'data': {'x': self.player.x, 'y': self.player.y, 'dir': self.player.model.direction, 'moving': self.player.moving, 'selected': self.player.inventory.selected[0]}})
                        last_send = time.time()
                self.stack_lock.acquire()
                try:  # обрабатываю полученные данные с сервера
                    while len(self.data_stack):
                        data = self.data_stack.popleft()
                        self.data_handle(data)
                finally:
                    self.stack_lock.release()
                for i in self.lerp_query.items():  # интерполирую координаты других игроков
                    delta = time.time() - i[1][-1]
                    x1, y1 = i[1][0], i[1][1]
                    x2, y2 = i[1][2], i[1][3]
                    #self.other_players[i[0]]['model'].x = x1 + (1 - math.cos(4 * delta * math.pi)) * (x2 - x1)
                    #self.other_players[i[0]]['model'].y = y1 + (1 - math.cos(4 * delta * math.pi)) * (y2 - y1)
                    self.other_players[i[0]]['model'].x = x1 + 10 * delta * (x2 - x1)
                    self.other_players[i[0]]['model'].y = y1 + 10 * delta * (y2 - y1)
                glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        self.exit()
                    if event.type == pygame.KEYDOWN:
                        if event.key == pygame.K_ESCAPE and self.status in [IN_GAME, PAUSE]:
                            self.status = PAUSE if self.status == IN_GAME else IN_GAME
                        elif event.key == pygame.K_e and self.status not in [MENU, PAUSE, SETTINGS, CONNECT]:
                            self.status = INVENTORY if self.status == IN_GAME else IN_GAME
                    if event.type == pygame.MOUSEBUTTONDOWN and GAME.status == IN_GAME:
                        self.player.inventory.wheel_event(-1 if event.button == 4 else (1 if event.button == 5 else 0))
                    self.interface.handle_event(event)
                if self.status not in [MENU, SETTINGS, CONNECT]:
                    self.update_inputs(fps)
                if self.status != MENU:
                    self.redraw()
                    self.player.inventory.draw_bar_only()
                if self.status == IN_GAME:
                    self.update_mouse(pygame.mouse.get_pos(), pygame.mouse.get_pressed(), fps)
                if self.status != IN_GAME:
                    glLoadIdentity()
                    glBindTexture(GL_TEXTURE_2D, 0)
                    glColor4f(0.75, 0.75, 0.75, 0.75)
                    glRectf(0, 0, self.width, self.height)
                    glColor4f(1, 1, 1, 1)
                if self.status == INVENTORY:
                    self.player.inventory.draw()
                elif self.status == PAUSE:
                    self.interface.draw()
                elif self.status == MENU:
                    self.interface.draw()
                for i in self.all_blocks:
                    i.on_tick(self)
                pygame.display.flip()
                clock.tick(fps)
            except socket.error as e:
                self.interface.server_message.generate_text(str(e), self.text_font, self.width // 20)
                self.server_leave()
                self.interface.status = CONNECT_ERROR
            except Exception as e:
                print(e)
                self.server_leave()
                self.running = False
        pygame.quit()


if __name__ == '__main__':
    GAME = Game()
    GAME.run()
