from structures import Block


class Object(Block):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def tick(self, game):
        super().tick(game)
