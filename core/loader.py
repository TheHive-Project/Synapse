import logging
import os
import importlib

def moduleLoader(submodule):
    #import logger
    logger = logging.getLogger(__name__)

    #Define folder structure and empty vars
    app_dir = os.path.dirname(os.path.abspath(__file__))
    modules_dir = app_dir + "/../modules"
    loaded_modules = {}

    #Read all modules from modules folder
    modules = [ name for name in os.listdir(modules_dir) if os.path.isdir(os.path.join(modules_dir, name)) if os.path.isfile(os.path.join(modules_dir, name, submodule + ".py")) ]

    logger.info("Loading modules for automation")
    #Loop through modules to create a module dictionary
    for module in modules:
        loaded_modules[module] = importlib.import_module("modules.{}.{}".format(module, submodule))
        logger.info("Loaded automation module {}".format(module))
        # for item in dir(loaded_modules[module]):
        #     if not "__" in item:
        #         print(item)

    return loaded_modules