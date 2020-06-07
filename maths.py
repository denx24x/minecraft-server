def lerp(t, a, b):
    return a + t * (b - a)


def area(a_x, a_y, b_x, b_y, c_x, c_y):
    return (b_x - a_x) * (c_y - a_y) - (b_y - a_y) * (c_x - a_x)


def intersect_1(a, b, c, d):
    if a > b:
        a, b = b, a
    if c > d:
        c, d = d, c
    return max(a, c) <= min(b, d)


def intersect(a_x, a_y, b_x, b_y, c_x, c_y, d_x, d_y):
    return intersect_1(a_x, b_x, c_x, d_x) and intersect_1(a_y, b_y, c_y, d_y) and area(a_x, a_y, b_x, b_y, c_x,
                                                                                        c_y) * area(a_x, a_y, b_x, b_y,
                                                                                                    d_x,
                                                                                                    d_y) <= 0 and area(
        c_x, c_y, d_x, d_y, a_x, a_y) * area(c_x, c_y, d_x, d_y, b_x, b_y) <= 0


def check_intersection(x1, y1, x2, y2, group):
    res = []
    for i in group:
        bf = i.rect
        t_x1, t_y1, t_x2, t_y2 = bf.x, bf.y, bf.x + bf.width, bf.y + bf.height
        lines = [(t_x1, t_y1, t_x1, t_y2), (t_x1, t_y2, t_x2, t_y2), (t_x2, t_y2, t_x2, t_y1), (t_x2, t_y1, t_x1, t_y1)]
        for g in lines:
            if intersect(x1, y1, x2, y2, *g):
                res.append((t_x1, t_y1))
                break
    return sorted(res, key=lambda x: x[1])


def check_square_intersect(x1, y1, x2, y2, x3, y3, x4, y4):
    left = max(x1, x3)
    top = min(y2, y4)
    right = min(x2, x4)
    bottom = max(y1, y3)
    width = right - left
    height = top - bottom
    if width < 0 or height < 0:
        return 0
    return width * height


def check_square_collision(x1, y1, x2, y2, group):
    res = []
    for i in group:
        rect = i.rect
        if check_square_intersect(x1, y1, x2, y2, rect.x, rect.y, rect.x + rect.width, rect.y + rect.height):
            res.append(i.rect)
    return res
