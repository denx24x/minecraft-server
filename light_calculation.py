import pygame
import sys
from noise import Noise, TwoDisNoise
import math
import random
from maths import check_square_collision, check_square_intersect
from structures import ObjectData, BlockDrop, GlobalRotatingObject, Block, Player, load_image, make_gl_image, createTexDL, gl_draw_single_tex
from inventory import Inventory, Item
from graphics import TileImage
from OpenGL.GL import *
from OpenGL.GLU import *
import json
import os


if getattr(sys, 'frozen', False):
    application_path = os.path.dirname(sys.executable)
else:
    application_path = os.path.dirname(os.path.abspath(__file__))


class LightController:
    def __init__(self, width, height, min_height=128, max_height=-128):
        self.width = width
        self.height = height
        self.max_y = [0] * self.width
        self.min_height = min_height
        self.max_height = max_height
        self.lighting = [[0 for g in range(self.width)] for i in range(self.height)]

    def sub_light_calc(self, lights, chunk):
        visited = [[0 for g in range(self.width)] for i in range(self.height)]
        new = set()
        for i in lights:  # источники не взаимодействуют между собой
            visited[i[1]][i[0]] = 1
        while len(lights):
            for x in sorted(lights, key=lambda z: (z[0], -z[1])):
                for i in range(-1, 2):
                    for g in range(-1, 2):
                        newx, newy = x[0] + i, x[1] + g
                        if newy < 0 or newy >= self.height or newx < 0 or newx >= self.width or visited[newy][newx]:
                            continue
                        coff = 0.2 if not chunk[x[1]][x[0]].transparent else 0.85
                        if i != 0 and g != 0:
                            coff *= 0.9
                        self.lighting[newy][newx] = max(self.lighting[x[1]][x[0]] * coff, self.lighting[newy][newx])
                        new.add((newx, newy))
            lights = list(new)
            for i in lights:  # новый слой не действует на предыдущий
                visited[i[1]][i[0]] = 1
            new.clear()

    def calculate_light(self, chunk, heights):  # основная функция просчета света
        self.lighting = [[0 for g in range(self.width)] for i in range(self.height)]
        lights = []
        for g in range(self.width):  # определение источников света (вертикальный луч света)
            for i in range(self.height):
                if chunk[i][g].worldpos[1] > self.max_y[g]:
                    continue
                val = heights[g]
                if self.max_y[g] >= chunk[i][g].worldpos[1] >= val:
                    if chunk[i][g].transparent:
                        val = max(0, chunk[i][g].lighting, 1 - abs(chunk[i][g].worldpos[1] - val) / self.min_height * 1.5)
                    else:
                        val = max(0, 1 - abs(chunk[i][g].worldpos[1] - val) / self.min_height * 1.5)
                else:
                    val = 1
                self.lighting[i][g] = max(val, self.lighting[i][g])
                lights.append((g, i))
        self.sub_light_calc(lights, chunk)
        lights = []
        for g in range(self.width):  # определение искусственных источников света
            for i in range(self.height):
                if chunk[i][g].lighting != 0:
                    self.lighting[i][g] = chunk[i][g].lighting
                    lights.append((g, i))
                    self.sub_light_calc(lights, chunk)
                    lights.pop()

    def calc_max_y_for_x(self, x, pos_center, chunk_controller, blocks):
        last = self.max_height
        for g in range(self.max_height, self.min_height):
            last = g
            if (x - self.width // 2 + int(
                    pos_center[0])) in chunk_controller.changes and \
                    g in chunk_controller.changes[
                x - self.width // 2 + int(pos_center[0])]:
                if not chunk_controller.changes[
                    x - self.width // 2 + int(pos_center[0])][g].transparent:
                    break  # был поставлен непрозрачный блок
                else:
                    continue  # был поставлен прозрачный блок
            if g >= chunk_controller.ground_height[x] and abs(
                    chunk_controller.cave_generator.noise2d(
                        x - self.width // 2 + int(pos_center[0]), g,
                        octaves=3,
                        amp=0.02, zoom=0.05, fr=3)) <= 0.5:
                break  # не была сгенерирована пещера
            if (g - chunk_controller.ground_height[x]) >= -3 and chunk_controller.sub_tree_map[x] and (
                    (x - self.width // 2 + int(
                        pos_center[0])) not in chunk_controller.changes or g not in
                    chunk_controller.changes[
                        x - self.width // 2 + int(pos_center[0])] or
                    not chunk_controller.changes[
                        x - self.width // 2 + int(pos_center[0])][g].transparent):
                break
        self.max_y[x] = last

    def calc_max_y(self, pos_center, chunk_controller, blocks):  # просчет наивысшего непрозрачного блока
            for i in range(self.width):
                 self.calc_max_y_for_x(i, pos_center, chunk_controller, blocks)
