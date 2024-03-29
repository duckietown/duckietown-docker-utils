import os

__all__ = [
    "get_screen_columns",
    "getTerminalSize",
]

from typing import Tuple


def get_screen_columns() -> int:
    ts = getTerminalSize()
    max_x, _ = ts

    fallback = 90
    if max_x <= 10 or max_x > 1024:
        #         msg = 'Very weird max screen size: %d' % max_x
        #         msg += '\n I will use %s.' % fallback
        #         sys.stderr.write(msg+'\n')

        return fallback
    #         raise ValueError(msg)

    return max_x


def getTerminalSize() -> Tuple[int, int]:
    """
    columns, lines = getTerminalSize()
    """
    cr = ioctl_GWINSZ(0) or ioctl_GWINSZ(1) or ioctl_GWINSZ(2)
    if not cr:
        # noinspection PyBroadException
        try:
            fd = os.open(os.ctermid(), os.O_RDONLY)
            cr = ioctl_GWINSZ(fd)
            # noinspection PyTypeChecker
            os.close(fd)
        except:
            cr = (25, 80)

    columns = int(cr[1])
    lines = int(cr[0])

    env = os.environ
    if "COLUMNS" in env:
        columns = int(env["COLUMNS"])
    if "LINES" in env:
        lines = int(env["LINES"])

    return columns, lines


def ioctl_GWINSZ(fd):
    # noinspection PyBroadException
    try:
        import fcntl
        import termios
        import struct

        # noinspection PyTypeChecker
        s = fcntl.ioctl(fd, termios.TIOCGWINSZ, "1234")
        return struct.unpack("hh", s)
    except:
        return None
