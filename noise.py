import math


def cos_interpolate(a, b, x):
    ft = x * 3.1415927
    f = (1 - math.cos(ft)) * 0.5
    return a * (1 - f) + b * f


class Noise:
    def __init__(self, seed):
        self.seed = seed

    def noise(self, x):
        x = x + self.seed
        n = (x << 13) ^ x
        return 1.0 - ((n * (n * n * 15731 + 789221) + 1376312589) & 0x7fffffff) / 1073741824.0

    def noise1d(self, x, octaves=3, amp=0.6, zoom=0.01, fr=1.5):
        res = 0
        n = octaves
        for i in range(n):
            frequency = fr ** i
            amplitude = amp ** i
            res += self.interpolate(x * frequency * zoom) * amplitude
        return res

    def interpolate(self, x):
        round_x = int(x)
        frac_x = x - round_x
        v0 = self.noise(round_x)
        v1 = self.noise(round_x + 1)
        return cos_interpolate(v0, v1, frac_x)


class TwoDisNoise:
    def __init__(self, seed):
        self.seed = seed

    def noise(self, x, y):
        n = x + y * 57 + self.seed
        n = (n << 13) ^ n
        return 1.0 - ((n * (n * n * self.seed + 789221) + 1376312589) & 0x7fffffff) / 1073741824.0

    def noise2d(self, x, y, octaves=3, amp=0.0035, zoom=0.075, fr=1.5):
        res = 0
        n = octaves
        for i in range(n):
            frequency = fr ** i
            amplitude = amp ** i
            res += self.interpolate(x * frequency * zoom, y * frequency * zoom) * amplitude
        return res

    def interpolate(self, x, y):
        round_x = int(x)
        frac_x = x - round_x

        round_y = int(y)
        frac_y = y - round_y

        v11 = self.noise(round_x, round_y)
        v12 = self.noise(round_x + 1, round_y)
        v13 = self.noise(round_x, round_y + 1)
        v14 = self.noise(round_x + 1, round_y + 1)
        i1 = cos_interpolate(v11, v12, frac_x)
        i2 = cos_interpolate(v13, v14, frac_x)

        return cos_interpolate(i1, i2, frac_y)

