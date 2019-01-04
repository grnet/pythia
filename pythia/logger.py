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


class Logger:
    cached_loggers = {}

    @classmethod
    def get_logger(cls, logger_name):
        if logger_name in cls.cached_loggers:
            return cls.cached_loggers[logger_name]
        return cls(logger_name)

    def __init__(self, logger_name):
        self.cached_loggers[logger_name] = self
        self.enable_warnings=False
        self.enable_debug=False

    def init_logger(self, enable_debug=False, enable_warnings=False):
        self.enable_warnings = enable_warnings
        self.enable_debug = enable_debug

    def info(self, args):
        print('{0}[*] {1}{2}'.format(Style.WHITE, args, Style.ESCAPE))

    def error(self, args):
        print('{0}[*] {1}{2}'.format(Style.RED, args, Style.ESCAPE))

    def warn(self, args):
        if self.enable_warnings:
            print('{0}[*] {1}{2}'.format(Style.YELLOW, args, Style.ESCAPE))

    def debug(self, args):
        if self.enable_debug:
            print('{0}[*] {1}{2}'.format(Style.BLUE, args, Style.ESCAPE))
