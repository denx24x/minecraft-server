import pygame
import os
import math
import sys

if getattr(sys, 'frozen', False):
    application_path = os.path.dirname(sys.executable)
else:
    application_path = os.path.dirname(os.path.abspath(__file__))


class TileImage:
    def __init__(self, image, width, height):
        self.image = image
        self.width = width
        self.height = height
        if self.image is not None:
            bf = make_gl_image(pygame.transform.scale(self.image, (self.width, self.height)))
            self.gl_image = createTexDL(bf[0], self.width, self.height)
            self.rect = bf[1]
        else:
            self.gl_image = None
            self.rect = pygame.Rect(0, 0, 0, 0)


def createTexDL(texture, width, height):
    new = glGenLists(1)
    glNewList(new, GL_COMPILE)
    glBindTexture(GL_TEXTURE_2D, texture)
    glBegin(GL_QUADS)

    glTexCoord2f(0, 1)
    glVertex2f(0, 0)

    glTexCoord2f(0, 0)
    glVertex2f(0, height)

    glTexCoord2f(1, 0)
    glVertex2f(width, height)

    glTexCoord2f(1, 1)
    glVertex2f(width , 0)

    glEnd()
    glEndList()
    return new


def gl_draw_single_tex(tex, width, height):
    glBindTexture(GL_TEXTURE_2D, tex)
    glBegin(GL_QUADS)
    glTexCoord2f(0, 1)
    glVertex2f(0, 0)
    glTexCoord2f(0, 0)
    glVertex2f(0, height)
    glTexCoord2f(1, 0)
    glVertex2f(width, height)
    glTexCoord2f(1, 1)
    glVertex2f(width, 0)
    glEnd()


def load_image(name):
    fullname = os.path.join(application_path, 'data', name)
    image = pygame.image.load(fullname)
    image = image.convert_alpha()
    return image


def make_gl_image(img):
    rect = img.get_rect()
    textureData = pygame.image.tostring(img, "RGBA", 1)
    width = img.get_width()
    height = img.get_height()
    texture = glGenTextures(1)
    glBindTexture(GL_TEXTURE_2D, texture)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
    glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, width, height, 0, GL_RGBA,
                     GL_UNSIGNED_BYTE, textureData)
    glBindTexture(GL_TEXTURE_2D, 0)
    return texture, rect


def draw_resized_image(image, width, height):
    tex = make_gl_image(pygame.transform.scale(image, (width, height)))[0]
    gl_draw_single_tex(tex, width, height)
    glDeleteTextures(1, tex)


def gen_text_image(text, font, color=(0, 0, 0)):
    tex = make_gl_image(font.render(text, False, color))
    return tex


def draw_text(text, font, color=(0, 0, 0), translate_x=True):
    tex = gen_text_image(text, font, color)
    glTranslate(0, -tex[1].height // 2, 0)
    if translate_x:
        glTranslate(-tex[1].width // 2, 0, 0)
    gl_draw_single_tex(tex[0], tex[1].width, tex[1].height)
    glDeleteTextures(1, tex[0])
