import random
from scripts.utils.parameters import ParameterSpace

class ConfigGenerator:
    """
    Handles parameter configuration and random generation.
    """
    def __init__(self, parameter_space: ParameterSpace):
        """
        Initialize with a ParameterSpace.
        """
        self.parameter_space = parameter_space

    def generate_random_config(self):
        """
        Generates a random configuration and its vector representation.
        Returns: (config_dict, config_vector)
        """
        config = {}
        config_vector = []
        
        for param in self.parameter_space:
            val = None
            if param.is_bool():
                # Random boolean
                val = random.choice([True, False])
            elif param.is_int():
                # Random int in range [min, max]
                val = random.randint(param.min, param.max)
            
            config[param.name] = val
            
            # Vector representation: True=1, False=0, Int=Int
            if param.is_bool():
                config_vector.append(1 if val else 0)
            else:
                config_vector.append(val)
                
        return config, config_vector

    def get_default_config_vector(self):
        """
        Returns the vector representation of the default configuration.
        """
        config_vector = []
        for param in self.parameter_space:
            val = param.default
            if param.is_bool():
                config_vector.append(1 if val else 0)
            else:
                config_vector.append(val)
        return config_vector

    def get_config_vector_from_dict(self, config):
        """
        Converts a configuration dictionary to its vector representation.
        """
        config_vector = []
        for param in self.parameter_space:
            val = config.get(param.name, param.default)
            if param.is_bool():
                config_vector.append(1 if val else 0)
            else:
                config_vector.append(val)
        return config_vector
