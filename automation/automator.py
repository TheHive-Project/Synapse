import importlib
import os

#Define folder structure and empty vars
app_dir = os.path.dirname(os.path.abspath(__file__))
modules_dir = app_dir + "/../modules"
loaded_modules = {}

#Read all modules from modules folder
modules = [ name for name in os.listdir(modules_dir) if os.path.isdir(os.path.join(modules_dir, name)) ]

#Loop through modules to create a module dictionary
for module in modules:
    loaded_modules[module] = importlib.import_module("modules.{}.automators".format(module))
    self.logger.info("Loaded module {} for automation".format(module))
    # for item in dir(loaded_modules[module]):
    #     if not "__" in item:
    #         print(item)

class Automator():
    def __init__(cfg):
        self.cfg = cfg
    
    def Automate(task, task_config):

        #Split the task name on the dot to have a module and a function variable in a list
        try:
            self.task = task.split(".")
            #Should probably also do some matching for words to mitigate some security concerns?

        except:
            self.logger.error("{} does not seem to be a valid automator task name".format(task))
        
        #Load the Automators class from the module to initialise it
        automators = getattr(loaded_modules[self.task[0]], Automators)(self.cfg)
        #Run the function for the task and return the results
        results = getattr(automators, '{}'.format(self.task[1]))(task_config)
        return results
        