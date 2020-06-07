from inventory import Item


class Object(Item):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def on_select(self, game):
        super().on_select(game)
        game.player.mine_speed += 100

    def on_deselect(self, game):
        super().on_deselect(game)
        game.player.mine_speed -= 100
