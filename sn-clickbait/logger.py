import logging

logger = logging.getLogger(__name__)

file_handler = logging.FileHandler('debug.log')

logger.setLevel(logging.DEBUG)
file_handler.setLevel(logging.DEBUG)

fmt_file = '%(levelname)s %(asctime)s [%(filename)s:%(funcName)s:%(lineno)d] %(message)s'
file_formatter = logging.Formatter(fmt_file)
file_handler.setFormatter(file_formatter)

logger.addHandler(file_handler)
