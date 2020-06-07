from structures import Block
from inventory import CraftModel, check_craft
from OpenGL.GL import *
from constants import *
import copy


class Object(Block):
    def __init__(self, *args, **kwargs):
        self.craft = None
        self.craft_model = None
        if 'craft' in kwargs:
            self.craft = kwargs['craft']
            kwargs.pop('craft')
            self.craft_model = CraftModel(self, (3, 3), (1, 1), kwargs['game'].crafts, kwargs['game'].objects, check_craft)
            self.craft_model.load(self.craft, kwargs['game'].objects)
        super().__init__(*args, **kwargs)

    def save(self):
        bf = super().save()
        bf['additional'] = {'craft': self.craft_model.craft_field.save()}
        return bf

    def copy_data(self, x, y):
        bf = super().copy_data(x, y)
        bf.craft_model = self.craft_model
        bf.craft = self.craft
        return bf

    def get_sync_with_server(self):
        return {'block': self.craft_model.craft_field.save(), 'x': self.worldpos[0], 'y': self.worldpos[1]}

    def sync_with_server(self):
        if self.craft_model is None:
            return
        self.game.send({'request': SYNC_BLOCK, 'data': self.get_sync_with_server()})

    def get_sync(self, data):
        if self.craft_model is None:
            self.craft_model = CraftModel(self, (3, 3), (1, 1), self.game.crafts, self.game.objects, check_craft)
        self.craft_model.load(data, self.game.objects)

    def copy(self):
        bf = super().copy()
        bf.craft_model = self.craft_model
        bf.craft = self.craft
        return bf

    def on_tick(self, game):
        super().on_tick(game)
        if game.status != self:
            return
        block_size = game.player.inventory.get_inv_size(game.width, game.height)
        lenx1, leny1 = game.player.inventory.x_scale * block_size, game.player.inventory.y_scale * block_size
        startx = int(game.width / 2 - lenx1 / 2)
        starty = int(game.height / 2 - leny1 / 2)
        game.player.inventory.draw_without_craft()
        glLoadIdentity()
        glColor4f(*(0.8, 0.8, 0.8, 0.9))
        glRectf(startx - block_size // 4, starty, startx + lenx1 + block_size // 4,
                    starty - block_size * 3 - block_size // 4)  # фон
        glColor4f(1, 1, 1, 1)
        starty -= block_size * 3 + block_size // 8
        startx += lenx1 // 2 - block_size * 2

        lenx, leny = 3 * block_size, 3 * block_size

        self.craft_model.craft_field.draw(startx, starty, lenx, leny, game.player.inventory.icon, item_buffer=game.player.inventory.item_buffer,
                                          background=(0, 0, 0, 0))
        starty += block_size
        startx += block_size * 4
        self.craft_model.craft_result.draw(startx, starty, block_size, block_size, game.player.inventory.icon,
                                           item_buffer=game.player.inventory.item_buffer, background=(0, 0, 0, 0))
        game.player.inventory.item_buffer.draw(block_size)

    def on_use(self, game):
        super().on_use(game)
        game.status = self

    def on_place(self, game):
        super().on_place(game)
        self.craft_model = CraftModel(self, (3, 3), (1, 1), game.crafts, game.objects, check_craft)
