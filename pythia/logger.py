import datetime
import logging
import sys

class Style:
    RED = '\033[31m'
    YELLOW = '\033[33m'
    WHITE = '\033[97m'
    GREEN = '\033[32m'
    BLUE = '\033[94m'
    ESCAPE = '\033[0m'
    UNDERLINE = '\033[4m'
    BOLD = '\033[1m'


LOG_COLORS = {
    'DEBUG': Style.BLUE,
    'INFO': Style.WHITE,
    'WARNING': Style.YELLOW,
    'ERROR': Style.RED,
    'CRITICAL': Style.RED,
}


class ColoredFormatter(logging.Formatter):

    def __init__(self, msg):
        logging.Formatter.__init__(self, fmt=msg)

    def format(self, record):
        record.reset = Style.ESCAPE
        record.color = LOG_COLORS[record.levelname]
        return logging.Formatter.format(self, record)


def init_logging(debug, enable_warnings, name='pythia'):

    class LogFilter(logging.Filter):
        def filter(self, record):
            """ Log up to INFO to stdout """
            return record.levelno <= logging.INFO

    log = logging.getLogger(name)
    level = logging.DEBUG if debug else logging.INFO
    log.setLevel(level)

    colored_formatter = ColoredFormatter(
        '%(color)s[*] %(message)s %(reset)s')

    handler_stdout = logging.StreamHandler(sys.stdout)
    handler_stdout.setFormatter(colored_formatter)
    handler_stdout.setLevel(logging.DEBUG)
    handler_stdout.addFilter(LogFilter())


    level = logging.WARNING if enable_warnings else logging.ERROR
    handler_stderr = logging.StreamHandler(sys.stderr)
    handler_stderr.setFormatter(colored_formatter)
    handler_stderr.setLevel(level)

    log.addHandler(handler_stderr)
    log.addHandler(handler_stdout)

    return log
