import pygame
import sys
from noise import Noise, TwoDisNoise
import math
import random
from maths import check_square_collision, check_square_intersect
from structures import ObjectData, BlockDrop, GlobalRotatingObject, Block, Player, load_image, make_gl_image, createTexDL, gl_draw_single_tex
from inventory import Inventory, Item
from light_calculation import LightController
from level_generation import ChunkController
from graphics import TileImage, draw_resized_image, draw_text
from OpenGL.GL import *
from constants import *
from OpenGL.GLU import *
import json
import os
import time

if getattr(sys, 'frozen', False):
    application_path = os.path.dirname(sys.executable)
else:
    application_path = os.path.dirname(os.path.abspath(__file__))

TEXT = 1
NUM = 2
ADDRESS = 3


class Text:
    def __init__(self, text, font):
        self.text = text
        self.font = font

    def handle_event(self, event):
        return

    def draw(self, rect):
        glLoadIdentity()
        glTranslate(rect.x, rect.y, 0)
        draw_text(self.text, self.font, translate_x=False)


class Button:
    def __init__(self, interactor, image, selected_image, text, font, event):
        self.interactor = interactor
        self.image = image
        self.text = text
        self.selected_image = selected_image
        self.font = font
        self.event = event

    def handle_event(self, event):
        return

    def draw(self, rect):
        glLoadIdentity()
        pos = pygame.mouse.get_pos()
        glTranslate(rect.x, rect.y, 0)
        if rect.x <= pos[0] <= rect.x + rect.width and rect.y <= pos[1] <= rect.y + rect.height:
            draw_resized_image(self.selected_image, rect.width, rect.height)
            if pygame.mouse.get_pressed()[0] == 1 and self.interactor.check():
                self.interactor.update()
                self.event()
        else:
            draw_resized_image(self.image, rect.width, rect.height)
        glTranslate(rect.width // 2, rect.height // 2, 0)
        draw_text(self.text, self.font)


class InputBox:  # текстовое поле
    def __init__(self, interactor, font, text='', subtext='', input_type=TEXT, default=0):
        self.interactor = interactor
        self.color = (0.3, 0.3, 0.3, 0.5)
        self.text = text
        self.subtext = subtext
        self.font = font
        self.txt_surface = make_gl_image(font.render(subtext + text, True, self.color))
        self.active = False
        self.input_type = input_type

    def handle_event(self, event):
        if not self.active or event.type != pygame.KEYDOWN:
            return
        if event.key == pygame.K_BACKSPACE:
            if not len(self.text):
                return
            self.text = self.text[:-1]
            glDeleteTextures(1, self.txt_surface[0])
            self.txt_surface = make_gl_image(self.font.render(self.subtext + self.text, False, (0, 0, 0)))
            return
        if len(self.text) > 20:
            return
        sign = event.unicode
        if self.input_type == NUM:
            if not sign.isdigit():
                return
        elif self.input_type == ADDRESS:
            if not sign.isdigit() and sign not in [':', '.']:
                return
        self.text += sign
        glDeleteTextures(1, self.txt_surface[0])
        self.txt_surface = make_gl_image(self.font.render(self.subtext + self.text, False, (0, 0, 0)))

    def handle(self, rect):
        if pygame.mouse.get_pressed()[0] == 1:
            if rect.collidepoint(pygame.mouse.get_pos()):
                if self.interactor.check():
                    self.active = not self.active
                    self.interactor.update()
            else:
                self.active = False
            self.color = (0.7, 0.7, 0.7, 0.5) if self.active else (0.5, 0.5, 0.5, 0.5)

    def draw(self, rect):
        self.handle(rect)
        glLoadIdentity()
        glTranslate(rect.x, rect.y, 0)
        glBindTexture(GL_TEXTURE_2D, 0)
        glColor4f(*self.color)
        glRectf(0, 0, rect.width, rect.height)
        glColor4f(1, 1, 1, 1)
        glTranslate((rect.width - self.txt_surface[1].width) / 2, (rect.height - self.txt_surface[1].height) / 2, 0)
        gl_draw_single_tex(self.txt_surface[0], self.txt_surface[1].width, self.txt_surface[1].height)


class Window:
    def __init__(self, width, height, font, objects):  # просчитываю константы относительно размера и колчества блоков
        self.width = width
        self.height = height
        self.font = font
        self.objects = objects

    def draw(self, xborder=0.2, yborder=0.2, coff=2):
        dist = ((1 - yborder * 2) * self.height) // (len(self.objects) * 2 - 1)
        for ind, i in enumerate(self.objects):
            i.draw(pygame.rect.Rect(self.width * xborder, self.height * yborder + dist * ind * coff, self.width * (1 - xborder * 2), dist))

    def handle_event(self, event):
        for i in self.objects:
            i.handle_event(event)


class ServerErrorWindow(Window):
    def generate_text(self, text, font, count):
        self.objects = [self.objects[-1]]
        res = []
        bf = text
        while len(bf) > count:
            res.append(Text(bf[:count], font))
            bf = bf[count:]
        if len(bf):
            res.append(Text(bf, font))
        self.objects = res + self.objects


class InterfaceInteraction:
    def __init__(self):
        self.last_time = 0

    def update(self):
        self.last_time = time.time()

    def check(self):
        return time.time() - self.last_time > 0.15


class GameInterface:
    def __init__(self, game):
        self.game = game
        self.button = load_image('button.png')
        self.selected_button = load_image('button_pressed.png')
        self.status = MENU
        self.interactor = InterfaceInteraction()

        def gen_button(text, method):
            return Button(self.interactor, self.button, self.selected_button, text, game.text_font, method)

        self.start_screen = Window(game.width, game.height, game.text_font, [
            gen_button('Начать', self.new_game),
            gen_button('Подключиться', self.to_connect),
            gen_button('Загрузить', self.load_save),
            gen_button('Настройки', self.go_settings),
            gen_button('Выйти', self.exit),
        ])

        self.connecting = Window(game.width, game.height, game.text_font, [
            InputBox(self.interactor, game.text_font, text='127.0.0.1', subtext='Адрес: ', input_type=ADDRESS),
            InputBox(self.interactor, game.text_font, text='440', subtext='Порт: ', input_type=NUM),
            InputBox(self.interactor, game.text_font, text='Player', subtext='Ник: ', input_type=TEXT),
            gen_button('Подключиться', self.connect),
            gen_button('Назад', self.return_to_menu),
        ])

        self.settings = Window(game.width, game.height, game.text_font, [
            InputBox(self.interactor, game.text_font, text=str(game.block_size), subtext='Размер блока: ', input_type=NUM),
            InputBox(self.interactor, game.text_font, text=str(game.block_width), subtext='Количество блоков в ширину: ', input_type=NUM),
            InputBox(self.interactor, game.text_font, text=str(game.block_height), subtext='Количество блоков в высоту: ', input_type=NUM),
            gen_button('Назад', self.return_to_menu),
        ])

        self.ingame_menu = Window(game.width, game.height, game.text_font, [
            gen_button('Продолжить', self.continue_game),
            gen_button('Сохранить', self.save),
            gen_button('В меню', self.return_to_menu),
            gen_button('Выйти', self.exit),
        ])

        self.server_message = ServerErrorWindow(game.width, game.height, game.text_font, [
            gen_button('В меню', self.return_to_menu)
        ])

    def handle_event(self, event):
        if self.game.status == PAUSE:
            self.ingame_menu.handle_event(event)
        else:
            if self.status == MENU:
                self.start_screen.handle_event(event)
            elif self.status == SETTINGS:
                self.settings.handle_event(event)
            elif self.status == CONNECT:
                self.connecting.handle_event(event)
            elif self.status == CONNECT_ERROR:
                self.server_message.handle_event(event)

    def draw(self):
        if self.game.status == PAUSE:
            self.ingame_menu.draw()
        else:
            glColor4f(*(0.5, 0.8, 1, 1))
            glRectf(0, 0, self.game.width, self.game.height)  # фон
            glColor4f(1, 1, 1, 1)
            if self.status == MENU:
                self.start_screen.draw()
            elif self.status == SETTINGS:
                self.settings.draw()
            elif self.status == CONNECT:
                self.connecting.draw()
            elif self.status == CONNECT_ERROR:
                self.server_message.draw(coff=1)

    def connect(self):
        vals = [self.connecting.objects[0].text, self.connecting.objects[1].text, self.connecting.objects[2].text]
        if min([len(i) for i in vals]) <= 0:
            return
        self.status = MENU
        self.game.connect(*vals)

    def to_connect(self):
        self.status = CONNECT

    def new_game(self):
        self.game.new_game()
        self.game.start()


    def continue_game(self):
        self.game.status = IN_GAME

    def return_to_menu(self):
        self.game.status = MENU
        try:
            self.game.server_leave()
            vals = [int(self.settings.objects[1].text), int(self.settings.objects[2].text), int(self.settings.objects[0].text)]
            if min(vals) <= 0:
                raise Exception
            self.game.initialise(*vals)
        except Exception:
            return

    def exit(self):
        self.game.exit()

    def load_save(self):
        try:
            self.game.load()
            self.game.start()
        except Exception:
            pass

    def save(self):
        self.game.save()

    def go_settings(self):
        self.status = SETTINGS
