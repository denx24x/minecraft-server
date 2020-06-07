import pygame
import os
import math
import sys
from sprite_handle import set_pos, rotate_and_draw
from graphics import gl_draw_single_tex, make_gl_image, createTexDL, load_image, draw_resized_image, TileImage
from maths import check_square_collision
import random
import time
import json
type_func = type


class ObjectData:
    def __init__(self, game, type, path, tile_image, block_class_path, item_class_path, block_class, item_class, is_phys, is_item, transparent, hp, lighting, drop):
        self.type = type
        self.game = game
        self.path = path
        self.tile_image = tile_image
        self.block_class_path = block_class_path
        self.item_class_path = item_class_path
        self.block_class = block_class
        self.item_class = item_class
        self.is_phys = is_phys
        self.is_item = is_item
        self.transparent = transparent
        self.hp = hp
        self.lighting = lighting
        self.drop = drop

    def generate_item(self, count=0, tile_image=None, is_item=None, type=None, additional=None):
        data = {
            'type': self.type,
            'count': count,
            'tile_image': tile_image if tile_image is not None else self.tile_image,
            'is_item': is_item if is_item is not None else self.is_item
        }
        if additional is None:
            additional = {}
        return self.item_class(**dict(data, **additional))

    def generate_block(self, x=0, y=0, worldpos=(0, 0), tile_image=None, is_phys=None, transparent=None, lighting=None, drop=None, hp=None, type=None, additional=None):
        bfdrop = drop if drop is not None else self.drop
        if type_func(bfdrop) == list:
            bfdrop = BlockDrop(*bfdrop)
        data = {
            'type': self.type,
            'game': self.game,
            'x': x,
            'y': y,
            'worldpos': worldpos,
            'tile_image': tile_image if tile_image is not None else self.tile_image,
            'hp': hp if hp is not None else self.hp,
            'is_phys': is_phys if is_phys is not None else self.is_phys,
            'transparent': transparent if transparent is not None else self.transparent,
            'lighting': lighting if lighting is not None else self.lighting,
            'drop': bfdrop
        }
        if additional is None:
            additional = {}
        return self.block_class(**dict(data, **additional))


class BlockDrop:
    def __init__(self, drop_type, min_count, max_count):
        self.drop_type = drop_type
        self.min_count = min_count
        self.max_count = max_count

    def get_drop(self):
        return self.drop_type, random.randint(self.min_count, self.max_count)

    def save(self):
        return [self.drop_type, self.min_count, self.max_count]


class Player:
    def __init__(self, x, y, inventory, game):
        self.game = game
        self.inventory = inventory
        self.mine_speed = 200
        self.speed = 6
        self.model = None
        self.x = x
        self.y = y
        self.moving = False

    def update_model(self, x, y, is_local=False):
        if self.model is not None:
            self.model.update_pos(self.x, self.y, self.game.width, self.game.height, self.game.block_size, x, y, is_local)

    def make_model(self):
        self.model = PlayerModel(self.game.width // 2, self.game.height // 2, self.game.block_size)

    def check_collisions(self, dx, dy, phys_blocks_group):
        bf = self.model.get_current_tile()
        bff = (bf.rect.x, bf.rect.y)
        bf.rect.x += dx
        bf.rect.y += dy
        if pygame.sprite.spritecollideany(bf, phys_blocks_group):
            bf.rect.x = bff[0]
            bf.rect.y = bff[1]
            return True
        bf.rect.x = bff[0]
        bf.rect.y = bff[1]
        return False

    def save(self):
        return {
            'x': self.x,
            'y': self.y,
            'inventory': self.inventory.save()
        }

    def load(self, data):
        self.x = data['x']
        self.y = data['y']
        self.inventory.load(data['inventory'])

    def draw(self):
        self.model.draw(self.inventory.get_selected(), self.game.block_size)

    def simulate_move(self, dx, ang):
        if dx != 0:
            self.model.anim_pos += ang * self.model.anim_pos_coff  # обновление анимации
            if self.model.anim_pos >= 60 or self.model.anim_pos <= -60:  # предед угла анимации
                self.model.anim_pos_coff *= -1
        else:
            self.model.anim_pos_coff = 1
            self.model.anim_pos = 0

    def move(self, dx, dy, ang):
        self.model.direction = dx // abs(dx) if dx != 0 else self.model.direction  # направление для анимации
        was = False  # произошло ли движение
        bf = self.model.get_current_tile().rect
        if dy > 0:  # движение вниз
            col = check_square_collision(bf.x + 3, bf.y + bf.height, bf.x + bf.width - 3,
                                         bf.y + bf.height + dy * self.game.block_size, self.game.phys_blocks_group)
            if not len(col):
                self.y += dy
            else:
                col.sort(key=lambda x: x.y - bf.y)
                self.y -= (bf.y + bf.height - col[0].y) / self.game.block_size
                self.gravity_force = 0
            was = True
        elif dy < 0:  # движение вверх
            col = check_square_collision(bf.x + 3, bf.y + dy * self.game.block_size, bf.x + bf.width - 3, bf.y,
                                         self.game.phys_blocks_group)
            if not len(col):
                self.y += dy
            else:
                col.sort(key=lambda x: x.y - bf.y)
                self.y -= (bf.y - col[0].y - col[0].height) / self.game.block_size
                self.game.gravity_force = 0
            was = True
        self.game.all_blocks.update(self.game.block_width, self.game.block_height, self.game.pos_center, self.game.block_size, self.game.player.x, self.game.player.y)
        if dx != 0:
            bfx = self.x
            if dx > 0:  # движение вправо
                col = check_square_collision(bf.x + 3, bf.y + 3, bf.x + dx * self.game.block_size + bf.width,
                                             bf.y + bf.height - 3, self.game.phys_blocks_group)
                if not len(col):
                    self.x += dx
                else:
                    col.sort(key=lambda x: x.x - (bf.x + bf.width))
                    self.x -= (bf.x + bf.width - col[0].x) / self.game.block_size
            else:  # влево
                col = check_square_collision(bf.x - 3, bf.y + 3, bf.x - dx * self.game.block_size, bf.y + bf.height - 3,
                                             self.game.phys_blocks_group)
                if not len(col):
                    self.x += dx
                else:
                    col.sort(key=lambda x: x.x - bf.x)
                    self.x -= (bf.x - col[0].x - col[0].width) / self.game.block_size
            if bfx != self.x:
                was = True
            self.model.anim_pos += ang * self.model.anim_pos_coff  # обновление анимации
            if self.model.anim_pos >= 60 or self.model.anim_pos <= -60:  # предед угла анимации
                self.model.anim_pos_coff *= -1
        else:
            self.model.anim_pos_coff = 1
            self.model.anim_pos = 0  # останока анимации
        self.model.anim = self.model.direction
        self.update_model(self.x, self.y, True)
        return was


class PlayerModel:
    def __init__(self, X_CENTER, Y_CENTER, BLOCK_SIZE):
        self.imgs = ['player_front.png', 'player_left.png', 'player_right.png']
        self.hand_left = PlayerSprite('player_hand.png', BLOCK_SIZE)
        self.hand_right = PlayerSprite('player_hand.png', BLOCK_SIZE)
        self.leg_left = PlayerSprite('player_leg.png', BLOCK_SIZE)
        self.leg_right = PlayerSprite('player_leg.png', BLOCK_SIZE)
        self.tiles = []
        self.direction = 0
        for i in self.imgs:
            self.tiles.append(PlayerSprite(i, BLOCK_SIZE))
            set_pos(self.tiles[-1], X_CENTER, Y_CENTER)
        self.anims = {0: 0, -1: 1, 1: 2}
        self.anim = 0
        self.anim_pos = 0
        self.anim_pos_coff = 1

    def update(self, X_CENTER, Y_CENTER):
        bf = self.get_current_tile().rect
        bf.x = X_CENTER
        bf.y = Y_CENTER
        set_pos(self.leg_left, X_CENTER + bf.width // 2 - self.leg_left.rect.width // 2,
                Y_CENTER + (bf.height - self.leg_left.rect.height))
        set_pos(self.leg_right, X_CENTER + bf.width // 2 - self.leg_right.rect.width // 2,
                Y_CENTER + (bf.height - self.leg_right.rect.height))
        set_pos(self.hand_left, X_CENTER + bf.width // 2 - self.hand_left.rect.width // 2,
                Y_CENTER + (bf.height - self.leg_left.rect.height) - self.hand_left.rect.height)
        set_pos(self.hand_right, X_CENTER + bf.width // 2 - self.hand_right.rect.width // 2,
                Y_CENTER + (bf.height - self.leg_right.rect.height) - self.hand_right.rect.height)

    def update_pos(self, x, y, width, height, block_size, player_x, player_y, is_local=False):
        if is_local:
            self.update(width // 2, height // 2)
        else:
            self.update_pos_global(x, y, width, height, block_size, player_x, player_y)

    def update_pos_global(self, x, y, width, height, block_size, player_x, player_y):
        X_CENTER = width / 2 + math.ceil(
            (x - player_x) * block_size)
        Y_CENTER = height / 2 + math.ceil(
            (y - player_y) * block_size)
        self.update(X_CENTER, Y_CENTER)

    def draw(self, selected, BLOCK_SIZE):
        if self.direction != 0:
            if self.direction == -1:
                rotate_and_draw(self.leg_right, -self.anim_pos)
                rotate_and_draw(self.hand_left, self.anim_pos)
                self.get_current_tile().draw()
                rotate_and_draw(self.leg_left, self.anim_pos)
                rotate_and_draw(self.hand_right, -self.anim_pos)
                if selected is not None:
                    glLoadIdentity()
                    glTranslate(self.get_current_tile().rect.x + BLOCK_SIZE * 0.25 + BLOCK_SIZE * 0.375 * math.sin(math.radians(self.anim_pos)), self.get_current_tile().rect.y + BLOCK_SIZE * 0.5 + BLOCK_SIZE * 0.375 * math.cos(math.radians(self.anim_pos)), 0)
                    draw_resized_image(selected.tile_image.image, int(BLOCK_SIZE * 0.5), int(BLOCK_SIZE * 0.5))
            else:
                rotate_and_draw(self.hand_left, self.anim_pos)
                if selected is not None:
                    glLoadIdentity()
                    glTranslate(self.get_current_tile().rect.x + BLOCK_SIZE * 0.25 + BLOCK_SIZE * 0.375 * math.sin(
                        math.radians(-self.anim_pos)),
                                self.get_current_tile().rect.y + BLOCK_SIZE * 0.5 + BLOCK_SIZE * 0.375 * math.cos(
                                    math.radians(-self.anim_pos)), 0)
                    draw_resized_image(selected.tile_image.image, int(BLOCK_SIZE * 0.5), int(BLOCK_SIZE * 0.5))
                self.get_current_tile().draw()
                rotate_and_draw(self.leg_right, -self.anim_pos)
                rotate_and_draw(self.leg_left, self.anim_pos)
                rotate_and_draw(self.hand_right, -self.anim_pos)
        else:
            self.get_current_tile().draw()
            if selected is not None:
                glLoadIdentity()
                glTranslate(self.get_current_tile().rect.x + BLOCK_SIZE * 0.625,
                            self.get_current_tile().rect.y + BLOCK_SIZE * 1, 0)
                draw_resized_image(selected.tile_image.image, int(BLOCK_SIZE * 0.5), int(BLOCK_SIZE * 0.5))

    def get_current_tile(self):
        return self.tiles[self.anims[self.direction]]


class CustomSprite(pygame.sprite.Sprite):
    def __init__(self, tile_image):
        super().__init__()
        self.tex = tile_image.gl_image
        self.rect = tile_image.rect.copy()

    def draw(self):
        glLoadIdentity()
        glTranslate(self.rect.x, self.rect.y, 0)
        glCallList(self.tex)


class Block(CustomSprite):
    def __init__(self, type, game, x, y, worldpos, tile_image, is_phys, transparent, lighting, hp, drop):
        super().__init__(tile_image)
        self.type = type
        self.game = game
        self.worldpos = worldpos
        self.hp = hp
        self.x = x
        self.y = y
        self.is_phys = is_phys
        self.lighting = lighting
        self.tile_image = tile_image
        self.transparent = transparent
        self.drop = drop

    def copy(self):
        return type(self)(**{
            'type': self.type,
            'game': self.game,
            'x': self.x,
            'y': self.y,
            'worldpos': self.worldpos,
            'tile_image': self.tile_image,
            'is_phys': self.is_phys,
            'transparent': self.transparent,
            'lighting': self.lighting,
            'hp': self.hp,
            'drop': self.drop
        })

    def copy_data(self, x, y):
        return type(self)(**{
            'type': self.type,
            'game': self.game,
            'x': x,
            'y': y,
            'worldpos': self.worldpos,
            'tile_image': self.tile_image,
            'is_phys': self.is_phys,
            'transparent': self.transparent,
            'lighting': self.lighting,
            'hp': self.hp,
            'drop': self.drop
        })

    def damage(self, dmg):
        self.hp -= dmg
        if self.hp <= 0:
            return True
        return False

    def update(self, width, height, pos_center, BLOCK_SIZE, player_x, player_y):
        self.rect.x = math.ceil((width / 2 + (self.worldpos[0] - pos_center[0]) + (pos_center[0] - player_x)) * BLOCK_SIZE)
        self.rect.y = math.ceil((height / 2 + (self.worldpos[1] - pos_center[1]) + (pos_center[1] - player_y)) * BLOCK_SIZE)

    def on_tick(self, game):
        return

    def on_select(self, game):
        return

    def on_deselect(self, game):
        return

    def on_use(self, game):
        return

    def on_destroy(self, game):
        return

    def on_place(self, game):
        return

    def save(self):
        data = {
            'type': self.type,
            'hp': self.hp,
            'transparent': self.transparent,
            'lighting': self.lighting,
            'is_phys': self.is_phys,
            'worldpos': self.worldpos
        }
        if self.drop is not None:
            data['drop'] = self.drop.save()
        return data


class GlobalRotatingObject(CustomSprite):  # луна с солнцем
    def __init__(self, tile_image, coff=0):
        super().__init__(tile_image)
        self.coff = coff

    def update_pos(self, started_time, X_CENTER, Y_CENTER, WIDTH, HEIGHT):
        ang = (time.time() - started_time) / 240 * 360 + 180 * self.coff
        self.rect.x = X_CENTER + (WIDTH - self.rect.height) / 2 * math.sin(math.radians(ang))
        self.rect.y = Y_CENTER - (HEIGHT - self.rect.height) / 2 * math.cos(math.radians(ang))
        return 1 - (min(ang, 360 - ang)) / 360


class PlayerSprite(CustomSprite):
    def __init__(self, path, BLOCK_SIZE):
        image = load_image(path)
        rect = image.get_rect()
        image = pygame.transform.scale(image, (int(rect.width * (BLOCK_SIZE / 32)), int(rect.height * (BLOCK_SIZE / 32))))
        rect = image.get_rect()
        tile = TileImage(image, rect.width, rect.height)
        super().__init__(tile)
