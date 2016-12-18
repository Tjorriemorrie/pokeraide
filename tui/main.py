import urwid


def add_player():
    input =
    overlay = urwid.Overlay()

STATE_SETUP = 'setup'

state = STATE_SETUP
players = []
overlay = None


footer_txt_add = urwid.Text(('footer_txt', 'Add Player'))
footer_txt_quit = urwid.Text(('footer_txt', 'Quit'), align='right')
footer_cols = urwid.Columns([footer_txt_add, footer_txt_quit])
footer = urwid.AttrMap(footer_cols, 'footer')

header_txt = urwid.Text(('streak', 'PokerAide'), align='center')
header_atm = urwid.AttrMap(header_txt, 'streak')

no_players = urwid.Text('no players')
body = urwid.Pile([no_players, urwid.Divider(), no_players])
body = urwid.Filler(urwid.Divider(), 'top')

main_frame = urwid.Frame(body, header=header_atm, footer=footer)


def handler_unhandled_input(key):
    if key == 'Q':
        raise urwid.ExitMainLoop()
    elif state == STATE_SETUP:
        if key == 'A':
            add_player()


PALETTE = [
    ('banner', 'black', 'light gray'),
    ('streak', 'black', 'dark red'),
    ('bg', 'black', 'dark blue'),

    ('footer', urwid.BLACK, urwid.LIGHT_RED),
    ('footer_txt', urwid.BLACK, urwid.DARK_RED),
]

loop = urwid.MainLoop(main_frame, palette=PALETTE, unhandled_input=handler_unhandled_input)

if __name__ == '__main__':
    loop.run()


'''
Standard background and foreground colors
urwid.BLACK = 'black'
urwid.DARK_RED = 'dark red'
urwid.DARK_GREEN = 'dark green'
urwid.BROWN = 'brown'
urwid.DARK_BLUE = 'dark blue'
urwid.DARK_MAGENTA = 'dark magenta'
urwid.DARK_CYAN = 'dark cyan'
urwid.LIGHT_GRAY = 'light gray'

Standard foreground colors (not safe to use as background)
urwid.DARK_GRAY = 'dark gray'
urwid.LIGHT_RED = 'light red'
urwid.LIGHT_GREEN = 'light green'
urwid.YELLOW = 'yellow'
urwid.LIGHT_BLUE = 'light blue'
urwid.LIGHT_MAGENTA = 'light magenta'
urwid.LIGHT_CYAN = 'light cyan'
urwid.WHITE = 'white'
'''
