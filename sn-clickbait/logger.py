import logging

FMT_SHELL = '%(levelname)s %(asctime)s %(message)s'
FMT_FILE = '%(levelname)s %(asctime)s [%(filename)s:%(funcName)s:%(lineno)d] %(message)s'

logger = logging.getLogger(__name__)

shell_handler = logging.StreamHandler()
file_handler = logging.FileHandler('debug.log')

logger.setLevel(logging.DEBUG)
shell_handler.setLevel(logging.DEBUG)
file_handler.setLevel(logging.DEBUG)

shell_formatter = logging.Formatter(FMT_SHELL)
file_formatter = logging.Formatter(FMT_FILE)

shell_handler.setFormatter(shell_formatter)
file_handler.setFormatter(file_formatter)

logger.addHandler(shell_handler)
logger.addHandler(file_handler)
