import logging

_global_level = logging.INFO
_loggers = {}

def set_global_log_level(level):
    global _global_level
    _global_level = level
    for logger in _loggers.values():
        logger.setLevel(level)

def get_logger(name):
    if name in _loggers:
        return _loggers[name]
        
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(_global_level)
    
    _loggers[name] = logger
    return logger