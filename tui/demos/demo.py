from urwid import MainLoop, ExitMainLoop, Text, Filler, AttrMap


PALETTE = [
    ('banner', 'black', 'light gray'),
    ('streak', 'black', 'dark red'),
    ('bg', 'black', 'dark blue'),
]


def exit_on_q(key):
    if key == 'Q':
        raise ExitMainLoop()

txt = Text(('banner', u"Hello World"), align='center')
map1 = AttrMap(txt, 'streak')
fill = Filler(map1)

map2 = AttrMap(fill, 'bg')
loop = MainLoop(map2, PALETTE, unhandled_input=exit_on_q)

if __name__ == '__main__':
    loop.run()
