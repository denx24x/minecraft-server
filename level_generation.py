import pygame
import sys
from noise import Noise, TwoDisNoise
import math
import random
from maths import check_square_collision, check_square_intersect
from structures import GlobalRotatingObject, Block, Player, load_image, make_gl_image, createTexDL, \
    gl_draw_single_tex
from inventory import Inventory, Item
from graphics import TileImage
from OpenGL.GL import *
from OpenGL.GLU import *
import json
import os
from structures import BlockDrop
import json


if getattr(sys, 'frozen', False):
    application_path = os.path.dirname(sys.executable)
else:
    application_path = os.path.dirname(os.path.abspath(__file__))

GRASS = 'grass'
DIRT = 'dirt'
STONE = 'stone'
EMPTY = 'empty'


class ChunkController:
    def __init__(self, width, height, seed, changes=None, min_height=128, max_height=-128):
        self.width = width
        self.height = height
        self.ground_height = [0 for g in range(self.width)]  # небольшая оптимизация
        self.tree_map = [[0 for g in range(self.width)] for i in
                         range(self.height)]
        self.sub_tree_map = [0 for g in range(self.width)]
        self.max_ground = 25
        self.chunk = [[0 for g in range(self.width)] for i in
                      range(self.height)]
        self.seed = seed
        self.cave_generator = TwoDisNoise(self.seed)
        self.generator = Noise(self.seed)
        self.min_height = min_height
        self.max_height = max_height
        self.changes = changes if changes is not None else {}

    def get_player_start_pos(self, x):
        return self.max_ground - int(self.generator.noise1d(x) * self.max_ground) - 2

    def place_block(self, x, y, block, game):
        if x not in self.changes:
            self.changes[x] = {}
        self.changes[x][y] = block
        if not game.is_server:
            lx, ly = x - game.pos_center[0] + (game.block_width + game.additional) // 2, y - game.pos_center[1] + (game.block_height + game.additional) // 2
            if 0 <= lx < (game.block_width + game.additional) and 0 <= ly < (game.block_height + game.additional):
                was = self.chunk[ly][lx]
                self.chunk[ly][lx] = block
                block.x = lx
                block.y = ly
                game.update_changes(was, block)
                if not block.transparent:
                    game.light_controller.max_y[lx] = min(game.light_controller.max_y[lx], y)
                elif not was.transparent:
                    game.light_controller.calc_max_y_for_x(lx, game.pos_center, self, game.objects)
                game.light_controller.calculate_light(self.chunk, self.ground_height)
        block.on_place(game)

    def generate_trees(self, x, y):
        self.tree_map = [[0 for g in range(self.height)] for i in
                         range(self.width)]
        self.sub_map = [0 for g in range(self.width)]
        for i in range(-self.width // 2,
                       math.ceil(self.width / 2)):
            val = self.max_ground - int(self.generator.noise1d((int(x) + i)) * self.max_ground)
            self.ground_height[i + self.width // 2] = val
            subval = abs(self.cave_generator.noise2d(int(x) + i, val, octaves=3, amp=0.02, zoom=0.05, fr=3))
            if subval > 0.5:
                continue
            if self.generator.noise1d((int(x) + i), amp=15, fr=0.001, zoom=10, octaves=1) > 0.85:
                self.sub_map[i + self.width // 2] = 1
        if int(y) - self.height // 2 > max(self.ground_height):
            return
        offsets_tree = [(0, -1), (0, -2), (0, -3)]
        offsets = [(0, -4), (0, -5), (1, -4), (1, -5), (2, -4), (2, -5), (-1, -4), (-1, -5), (-2, -4), (-2, -5),
                   (-1, -6), (1, -6), (0, -6)]
        for i in range(-self.width // 2, math.ceil(self.width / 2)):
            for g in range(- self.height // 2, math.ceil(self.height / 2)):
                was = False
                if self.tree_map[i + self.width // 2][g + self.height // 2] != 0:
                    continue
                for k in offsets_tree:
                    if not (0 <= i + self.width // 2 + k[0] < self.width):
                        continue
                    if self.sub_map[i + self.width // 2 + k[0]] and int(y) + g - \
                            self.ground_height[i + self.width // 2 + k[0]] == k[1]:
                        self.tree_map[i + self.width // 2][g + self.height // 2] = 2
                        was = True
                        break
                if was:
                    continue
                for k in offsets:
                    if not (0 <= i + self.width // 2 + k[0] < self.width):
                        continue
                    if self.sub_map[i + self.width // 2 + k[0]] and int(y) + g - \
                            self.ground_height[i + self.width // 2 + k[0]] == k[1]:
                        self.tree_map[i + self.width // 2][
                            g + self.height // 2] = 1
                        break

    def get(self, x, y, blocks, game):  # получить блок в любой точке мира
        if not game.is_server:
            lx, ly = x - game.pos_center[0] + (game.block_width + game.additional) // 2, y - game.pos_center[1] + (
                        game.block_height + game.additional) // 2
            if 0 <= lx < (game.block_width + game.additional) and 0 <= ly < (game.block_height + game.additional):
                return self.chunk[ly][lx]
        buff = type(self)(1, 1, self.seed, changes=self.changes)
        buff.update_chunk(x, y, blocks)
        return buff.chunk[0][0]

    def update_chunk(self, x, y, blocks):
        self.generate_trees(x, y)
        for i in range(-self.width // 2,
                       math.ceil(self.width / 2)):
            val = self.ground_height[i + self.width // 2]
            for g in range(-self.height // 2,
                           math.ceil(self.height / 2)):
                lx, ly = i + self.width // 2, g + self.height // 2  # локальные
                wx, wy = int(x) + i, int(y) + g  # глобальные
                block_type = EMPTY
                if self.min_height > wy > self.max_height and wy >= val:
                    if wy == val:
                        block_type = GRASS
                    elif wy > val + 10 + val % 2:
                        block_type = STONE
                    else:
                        block_type = DIRT
                original = block_type
                if wy >= val and not (wx in self.changes and wy in self.changes[wx]):
                    subval = abs(self.cave_generator.noise2d(wx, wy, octaves=3, amp=0.02, zoom=0.05, fr=3))
                    if subval > 0.5:
                        block_type = EMPTY
                    else:
                        subval = self.cave_generator.noise2d(wx, wy)  # у руд другие настройки генератора
                        if self.min_height > wy > val + 10 + val % 2 and subval < -0.15:
                            if -0.9 < subval < -0.85:
                                block_type = 'gold_ore'
                            elif -0.77 < subval < -0.7:
                                block_type = "iron_ore"
                            elif -0.42 < subval < -0.3:
                                block_type = 'coal_ore'
                            elif -0.7 < subval < -0.67:
                                block_type = 'diamond_ore'
                            elif -0.23 < subval < -0.15:
                                block_type = 'redstone_ore'
                if self.tree_map[i + self.width // 2][
                    g + self.height // 2] != 0:
                    block_type = 'orig_wood' if self.tree_map[i + self.width // 2][
                                                    g + self.height // 2] == 2 else 'leaves'
                if self.min_height == wy:
                    block_type = 'bedrock'
                if wx in self.changes and wy in self.changes[wx]:  # обновление измененного блока
                    self.chunk[ly][lx] = self.changes[wx][wy]
                    self.chunk[ly][lx].x = lx
                    self.chunk[ly][lx].y = ly
                    continue
                self.chunk[ly][lx] = blocks[block_type].generate_block(lx, ly, (wx, wy))
                self.chunk[ly][lx].x = lx
                self.chunk[ly][lx].y = ly

    def save(self):
        changes = {}
        for i in self.changes.keys():
            changes[i] = {}
            for g in self.changes[i].keys():
                changes[i][g] = self.changes[i][g].save()
        return {'seed': self.seed, 'changes': changes}

    def load_block(self, data, blocks):
        return blocks[data['type']].generate_block(**data)

    def load(self, data, blocks):
        self.seed = data['seed']
        changes = data['changes']
        for i in changes.keys():
            self.changes[int(i)] = {}
            for g in changes[i].keys():
                changes[i][g]['x'] = 0
                changes[i][g]['y'] = 0
                if 'drop' in changes[i][g]:
                    changes[i][g]['drop'] = BlockDrop(*changes[i][g]['drop'])
                self.changes[int(i)][int(g)] = self.load_block(changes[i][g], blocks)
