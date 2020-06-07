import pygame
import os
import math
import sys
import time
from constants import *
from sprite_handle import  check_in_square
from graphics import createTexDL, make_gl_image, load_image, gl_draw_single_tex, draw_resized_image


if getattr(sys, 'frozen', False):
    application_path = os.path.dirname(sys.executable)
else:
    application_path = os.path.dirname(os.path.abspath(__file__))


class ContainerEvent:
    def __init__(self, type, x, y, absolute_pos):
        self.type = type
        self.x = x
        self.y = y
        self.absolute_pos = absolute_pos


class Item:
    def __init__(self, type, count, tile_image, is_item):
        self.type = type
        self.count = count
        self.tile_image = tile_image
        self.is_item = is_item

    def draw(self, size, font, border):
        glTranslate(int(size * border), int(size * border), 0)
        draw_resized_image(self.tile_image.image, int(size * (1 - border * 2)), int(size * (1 - border * 2)))
        glTranslate(-int(size * border), -int(size * border), 0)
        glTranslate(size * 0.5, size * 0.5, 0)
        bf = make_gl_image(font.render(str(self.count), False, (255, 255, 255)))
        gl_draw_single_tex(bf[0], bf[1].width, bf[1].height)
        glDeleteTextures(1, bf[0])
        glTranslate(-size * 0.5, -size * 0.5, 0)

    def copy(self):
        return type(self)(**{
            'type': self.type,
            'count': self.count,
            'tile_image': self.tile_image,
            'is_item': self.is_item
        })

    def on_select(self, game):
        return

    def save(self):
        return {
            'type': self.type,
            'count': self.count
        }

    def on_deselect(self, game):
        return


class ItemBuffer:
    def __init__(self, owner):
        self.item = None
        self.last_interacted = 0
        self.owner = owner

    def save(self):
        return 'None' if self.item is None else self.item.save()

    def lclick(self, container, x, y):
        if time.time() - self.last_interacted < 0.15:
            return
        if self.item is None:  # взять предмет
            if container.get(x, y) is not None:
                self.item = container.take_event(x, y, container.get(x, y).count)
        else:

            if container.get(x, y) is None:  # положить предмет
                if container.take_only:
                    return
                container.add_event(x, y, self.item)
                self.item = None
            elif container.get(x, y) is not None and container.get(x, y).type == self.item.type:
                if container.take_only:
                    bf = container.take_event(x, y, container.get(x, y).count)
                    self.item.count += bf.count
                else:
                    container.add_event(x, y, self.item)
                    self.item = None
            else:
                bf = container.take_event(x, y, container.get(x, y).count)  # обменять предметы
                container.add_event(x, y, self.item)
                self.item = bf
        if self.owner.game.connected:
            container.sync_with_server()
            self.owner.sync_with_server()
        self.last_interacted = time.time()

    def rclick(self, container, x, y):
        if time.time() - self.last_interacted < 0.15:
            return
        if container.take_only:
            return
        if self.item is None:
            if container.get(x, y) is not None:  # взять половину предмета
                bf = math.ceil(container.get(x, y).count / 2)
                self.item = container.take_event(x, y, bf)
            else:
                return
        else:
            bf = self.item.copy()
            bf.count = 1
            if container.get(x, y) is None:  # полоижть предмет
                container.add_event(x, y, bf)
            elif container.get(x, y) is not None and container.get(x, y).type == self.item.type:
                container.add_event(x, y, bf)  # добавить одним предмет
            else:
                return
            self.item.count -= 1
            if self.item.count <= 0:
                self.item = None
        self.last_interacted = time.time()
        if self.owner.game.connected:
            container.sync_with_server()
            self.owner.sync_with_server()

    def draw(self, block_size):
        if self.item is not None:
            glLoadIdentity()
            glTranslate(pygame.mouse.get_pos()[0] - block_size // 2, pygame.mouse.get_pos()[1] - block_size // 2, 0)
            self.item.draw(block_size, pygame.font.Font(os.path.join((application_path), 'lobster.ttf'),
                                                                    block_size // 3), 0.05)


class ItemContainer:
    def __init__(self, owner, x_size, y_size, take_only=False, take_handler=None):
        self.owner = owner
        self.take_handler = take_handler
        self.take_only = take_only
        self.x_size = x_size
        self.y_size = y_size
        self.container = [[None for g in range(x_size)] for i in range(y_size)]

    def take_event(self, x, y, count):
        res = self.get(x, y).copy()
        count = min(count, res.count)
        res.count = count
        self.get(x, y).count -= count
        if self.get(x, y).count <= 0:
            self.set(x, y, None)
        if self.take_handler is not None:
            self.take_handler(-1, x, y, res)
        return res

    def sync_with_server(self):
        self.owner.sync_with_server()

    def save(self):
        res = [[None for g in range(self.x_size)] for i in range(self.y_size)]
        for g in range(self.x_size):
            for i in range(self.y_size):
                if self.container[i][g] is None:
                    res[i][g] = 'None'
                    continue
                res[i][g] = self.container[i][g].save()
        return res

    def add_event(self, x, y, item):
        if self.get(x, y) is not None:
            if self.get(x, y).type != item.type:
                return
            self.get(x, y).count += item.count
        else:
            self.set(x, y, item.copy())
        if self.take_handler is not None:
            self.take_handler(1, x, y, item)

    def get(self, x, y):
        return self.container[y][x]

    def delete(self, x, y):
        self.container[y][x] = None

    def set(self, x, y, val):
        self.container[y][x] = val

    def add(self, item):
        bf = self.find(item.type)
        if bf is not None:
            self.get(bf[0], bf[1]).count += item.count
            return True
        for i in range(self.y_size):
            for g in range(self.x_size):
                if self.get(g, i) is None:
                    self.set(g, i, item)
                    return True
        return False

    def find(self, type):
        for i in range(self.y_size):
            for g in range(self.x_size):
                if self.container[i][g] is None:
                    continue
                if self.container[i][g].type == type:
                    return g, i
        return None

    def load(self, data, objects):
        for g in range(self.x_size):
            for i in range(self.y_size):
                if data[i][g] == 'None':
                    self.container[i][g] = None
                    continue
                self.container[i][g] = objects[data[i][g]['type']].generate_item(**data[i][g])

    def draw(self, start_x, start_y, width, height, icon, item_buffer=None, x_background_offset=0, y_background_offset=0, background=(0.8, 0.8, 0.8, 0.9), floating=(1, 1, 1, 0.5), border=0.05):
        block_size = min(int(height // self.y_size), int(width // self.x_size))
        clicked = 1 if pygame.mouse.get_pressed()[0] else (-1 if pygame.mouse.get_pressed()[2] else 0)
        text_font = pygame.font.Font(os.path.join(application_path, 'lobster.ttf'), block_size // 3)  # lobстер
        glLoadIdentity()
        glColor4f(*background)
        glRectf(start_x - x_background_offset, start_y - y_background_offset, start_x + width + x_background_offset, start_y + height + y_background_offset)  # фон
        glColor4f(1, 1, 1, 1)
        for i in range(self.y_size):
            for g in range(self.x_size):
                last = (start_x + g * block_size, start_y + i * block_size)
                glLoadIdentity()
                glTranslate(last[0], last[1], 0)
                if item_buffer is not None and check_in_square(pygame.mouse.get_pos(), last, block_size) and clicked != 0:  # взаимодействие
                    if clicked == 1:
                        item_buffer.lclick(self, g, i)
                    elif clicked == -1:
                        item_buffer.rclick(self, g, i)
                draw_resized_image(icon, block_size, block_size)
                if self.get(g, i) is not None:
                    self.get(g, i).draw(block_size, text_font, border)
                if check_in_square(pygame.mouse.get_pos(), last, block_size):  # выделение
                    glBindTexture(GL_TEXTURE_2D, 0)
                    glColor4f(*floating)
                    glRectf(0, 0, block_size, block_size)
                    glColor4f(1, 1, 1, 1)


class BarContainer(ItemContainer):
    def draw_in_game(self, start_x, start_y, width, height, icon, sel_icon, selected, item_buffer=None, x_background_offset=0, y_background_offset=0, background=(0.8, 0.8, 0.8, 0.9), floating=(1, 1, 1, 0.5), border=0.1):
        block_size = min(int(height // self.y_size), int(width // self.x_size))
        text_font = pygame.font.Font(os.path.join(application_path, 'lobster.ttf'), block_size // 3)
        self.draw(start_x, start_y, width, height, icon, item_buffer, x_background_offset, y_background_offset, background, floating, border)
        pos = (start_x + selected[0] * block_size, start_y)
        glLoadIdentity()
        glTranslate(pos[0], pos[1], 0)
        draw_resized_image(sel_icon, block_size, block_size)
        if self.get(selected[0], 0) is not None:
            self.get(selected[0], 0).draw(block_size, text_font, border)


class CraftModel:
    def __init__(self, owner, field_size, target_size, crafts, objects, craft_func=None):
        self.owner = owner
        self.craft_field = ItemContainer(self, field_size[0], field_size[1], take_handler=self.craft_make_handle)
        self.craft_result = ItemContainer(self, target_size[0], target_size[1], take_only=True, take_handler=self.craft_handle)
        self.crafts = crafts
        self.objects = objects
        self.field_size = field_size
        self.target_size = target_size
        self.craft_func = craft_func if craft_func is not None else check_craft

    def craft_handle(self, event, x, y, item):
        craft = self.craft_func(self.crafts, self.craft_field, self.field_size[0], self.field_size[1])
        if craft is None:
            return
        pos = craft[0]
        craft = self.crafts[craft[1]]
        for i in range(pos[0], pos[0] + len(craft[0])):
            for g in range(pos[1], pos[1] + len(craft[0][i - pos[0]])):
                if craft[0][i - pos[0]][g - pos[1]][0] == 'None':
                    continue
                self.craft_field.take_event(g, i, craft[0][i - pos[0]][g - pos[1]][1])

    def craft_make_handle(self, event, x, y, item):
        craft = self.craft_func(self.crafts, self.craft_field, self.field_size[0], self.field_size[1])
        if craft is None:
            self.craft_result.set(0, 0, None)
            return
        self.craft_result.set(0, 0, self.objects[self.crafts[craft[1]][1][0]].generate_item(self.crafts[craft[1]][1][1]))

    def save(self):
        return self.craft_field.save()

    def sync_with_server(self):
        self.owner.sync_with_server()

    def load(self, data, objects):
        self.craft_field.load(data, objects)
        self.craft_make_handle(None, None, None, None)


class Inventory:
    def __init__(self, x_scale, y_scale, crafts, game):
        self.x_scale = x_scale
        self.y_scale = y_scale
        self.selected = (0, y_scale)
        self.game = game
        if not game.is_server:
            self.icon = load_image('icon.png')
            self.arrow = load_image('arrow.png')
            self.bar_icon = load_image('bar_icon.png')
            self.selected_icon = load_image('selected_icon.png')
        self.main_container = ItemContainer(self, x_scale, y_scale)
        self.bar_container = BarContainer(self, x_scale, 1)
        self.item_buffer = ItemBuffer(self)
        self.crafts = crafts
        self.grabbed = None
        self.craft_model = CraftModel(self, (2, 2), (1, 1), self.crafts, self.game.objects, check_craft)

    def sync_with_server(self):
        if not self.game.connected:
            return
        self.game.send({'request': SYNC_INVENTORY, 'data': self.save()})

    def get_selected(self):
        return self.get(self.selected[0], self.selected[1])

    def place_selected(self):
        self.bar_container.take_event(self.selected[0], 0, 1)

    def get_sync(self, data, objects):
        self.bar_container.load(data['bar'], objects)
        self.main_container.load(data['main'], objects)
        self.craft_model.load(data['craft'], objects)
        if data['buffer'] == 'None':
            self.item_buffer.item = None
        else:
            self.item_buffer.item = objects[data['buffer']['type']].generate_item(**data['buffer'])
        self.craft_model.craft_make_handle(None, None, None, None)

    def save(self):
        data = {
            'x_size': self.x_scale,
            'y_size': self.y_scale,
            'main': self.main_container.save(),
            'bar': self.bar_container.save(),
            'buffer': self.item_buffer.save(),
            'craft': self.craft_model.save()
        }
        return data

    def load(self, data):
        self.main_container.load(data['main'], self.game.objects)
        self.bar_container.load(data['bar'], self.game.objects)
        self.craft_model.load(data['craft'], self.game.objects)
        if data['buffer'] == 'None':
            self.item_buffer.item = None
        else:
            self.item_buffer.item = self.game.objects[data['buffer']['type']].generate_item(**data['buffer'])

    def get_inv_size(self, WIDTH, HEIGHT):
        lenx, leny = WIDTH * 0.8, HEIGHT * (self.y_scale / self.x_scale) * 0.8
        block_size = min(int(leny // self.y_scale), int(lenx // self.x_scale))
        return block_size

    def get(self, x, y):
        if y == self.y_scale:
            return self.bar_container.get(x, 0)
        return self.main_container.get(x, y)

    def set(self, x, y, val):
        if y == self.y_scale:
            self.bar_container.set(x, 0, val)
            return
        return self.main_container.container[y][x]

    def find_item(self, type):
        res = self.bar_container.find(type)
        if res is not None:
            return res[0], self.y_scale
        res = self.main_container.find(type)
        return res

    def add_item(self, item):
        if not self.bar_container.add(item):
            return self.main_container.add(item)
        return True

    def check_selection(self, was):
        if was is not None:
            was.on_deselect(self.game)
        if self.get_selected() is not None:
            self.get(self.selected[0], self.selected[1]).on_select(self.game)

    def set_selected(self, val):
        was = self.get_selected()
        self.selected = (val, self.selected[1])
        self.check_selection(was)

    def wheel_event(self, change):
        was = self.get_selected()
        self.selected = ((self.selected[0] + change) % self.x_scale, self.selected[1])
        self.check_selection(was)

    def draw_body(self, startx, starty):
        block_size = self.get_inv_size(self.game.width, self.game.height)
        lenx1, leny1 = self.x_scale * block_size, self.y_scale * block_size
        self.main_container.draw(startx, starty, lenx1, leny1, self.icon, item_buffer=self.item_buffer,
                                 x_background_offset=block_size // 4, y_background_offset=block_size // 4)
        lenx, leny = self.x_scale * block_size, block_size
        self.bar_container.draw(startx, starty + leny1 + 25, lenx, leny, self.icon, item_buffer=self.item_buffer,
                                x_background_offset=block_size // 4, y_background_offset=block_size // 4)

    def draw_craft(self, startx, starty):
        block_size = self.get_inv_size(self.game.width, self.game.height)
        lenx, leny = 2 * block_size, 2 * block_size
        self.craft_model.craft_field.draw(startx, starty, lenx, leny, self.icon, item_buffer=self.item_buffer, background=(0, 0, 0, 0))
        starty += block_size // 2
        startx += block_size * 3
        self.craft_model.craft_result.draw(startx, starty, block_size, block_size, self.icon, item_buffer=self.item_buffer, background=(0, 0, 0, 0))

    def draw_without_craft(self):
        block_size = self.get_inv_size(self.game.width, self.game.height)
        lenx1, leny1 = self.x_scale * block_size, self.y_scale * block_size
        startx = int(self.game.width / 2 - lenx1 / 2)
        starty = int(self.game.height / 2 - leny1 / 2)
        self.draw_body(startx, starty)

    def draw(self):
        block_size = self.get_inv_size(self.game.width, self.game.height)
        lenx1, leny1 = self.x_scale * block_size, self.y_scale * block_size
        startx = int(self.game.width / 2 - lenx1 / 2)
        starty = int(self.game.height / 2 - leny1 / 2)
        self.draw_body(startx, starty)
        glLoadIdentity()
        glColor4f(*(0.8, 0.8, 0.8, 0.9))
        glRectf(startx - block_size // 4, starty, startx + lenx1 + block_size // 4, starty - block_size * 3 - block_size // 4)  # фон
        glColor4f(1, 1, 1, 1)
        starty -= block_size * 3
        startx += lenx1 // 2 - block_size
        self.draw_craft(startx, starty)
        self.item_buffer.draw(block_size)

    def draw_bar_only(self):
        block_size = self.get_inv_size(self.game.width, self.game.height)
        lenx, leny = self.x_scale * block_size, block_size
        startx, starty = (self.game.width - lenx) // 2, self.game.height - block_size
        self.bar_container.draw_in_game(startx, starty, lenx, leny, self.bar_icon, self.selected_icon, self.selected, floating=(0, 0, 0, 0), background=(0, 0, 0, 0))


def check_craft(crafts, container, x_size, y_size):
    cnt = sum([sum(1 for g in i if g is not None) for i in container.container])
    for i in range(y_size):
        for g in range(x_size):
            for ind, recipe in enumerate(crafts):
                was = True
                item_cnt = 0
                if i + len(recipe[0]) > y_size:
                    continue
                for f in range(len(recipe[0])):
                    for s in range(len(recipe[0][f])):
                        if g + s >= x_size:
                            was = False
                            break
                        if recipe[0][f][s][0] == 'None':
                            if container.get(g + s, i + f) is not None:
                                was = False
                        else:
                            if container.get(g + s, i + f) is None or container.get(g + s, i + f).type != recipe[0][f][s][0] or container.get(g + s, i + f).count < recipe[0][f][s][1]:
                                was = False
                            item_cnt += 1
                if was and cnt == item_cnt:
                    return (i, g), ind
    return None
