import pygame
import os
import math
import sys


def set_pos(sprite, x, y):
    sprite.rect.x = x
    sprite.rect.y = y


def check_in_square(pos, coords, size):
    return coords[0] <= pos[0] <= coords[0] + size and coords[1] <= pos[1] <= coords[1] + size


def rotate_and_draw(sprite, ang):  # чтобы руки крутить
    glLoadIdentity()
    glTranslate(sprite.rect.x + sprite.rect.width // 2, sprite.rect.y, 0)
    glRotatef(ang, 0, 0, 1)
    glTranslate(-sprite.rect.width // 2, 0, 0)
    glCallList(sprite.tex)
    return (sprite.rect.bottomright[0] + sprite.rect.bottomleft[0]) / 2, (sprite.rect.bottomright[1] + sprite.rect.bottomleft[1]) / 2  # координата центра справйта?
